"""Phemex live trading execution module.

Handles authenticated order placement, position sizing, and TP/SL management.
Only active when LIVE_TRADING_ENABLED is True and API keys are configured.

Capital protection:
- Daily trade count limit
- Daily loss auto-disable
- Minimum balance floor
- Maximum capital deployed cap
- Cooldown after losses
- Exchange consistency validation (signals must come from same exchange as execution)
"""

import time
import config
from utils.utils import log_event


_authenticated_exchange = None

# Rolling trade log: list of {'timestamp': float, 'symbol': str, 'pnl': float|None}
_daily_trades: list[dict] = []
_daily_start_balance: float | None = None
_last_loss_timestamp: float = 0.0

# Active positions tracker for outcome monitoring
# key=symbol, value={'side','entry','tp','sl','strategy','timeframe','opened_at'}
_tracked_positions: dict[str, dict] = {}


def get_authenticated_exchange():
    """Return a Phemex exchange instance with trading credentials."""
    import ccxt

    global _authenticated_exchange
    if _authenticated_exchange is not None:
        return _authenticated_exchange

    if not config.PHEMEX_API_KEY or not config.PHEMEX_API_SECRET:
        raise ValueError("Phemex API credentials not configured. Set PHEMEX_API_KEY and PHEMEX_API_SECRET in .env")

    _authenticated_exchange = ccxt.phemex({
        'apiKey': config.PHEMEX_API_KEY,
        'secret': config.PHEMEX_API_SECRET,
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'},
    })
    _authenticated_exchange.load_markets()
    log_event("Authenticated Phemex exchange client initialized.")
    return _authenticated_exchange


def reset_authenticated_exchange():
    """Force re-creation of the authenticated client (e.g. after key rotation)."""
    global _authenticated_exchange
    _authenticated_exchange = None


def validate_exchange_consistency():
    """Ensure signal source and execution venue are the same exchange (Phemex)."""
    if config.EXCHANGE.strip().lower() != config.LIVE_TRADING_PLATFORM.strip().lower():
        return False, (
            f"Exchange mismatch: signals from '{config.EXCHANGE}' but "
            f"live trading on '{config.LIVE_TRADING_PLATFORM}'. "
            f"Prices may differ — refusing to trade."
        )
    return True, None


def _prune_daily_trades():
    """Remove trades older than 24h from the rolling window."""
    cutoff = time.time() - 86400
    _daily_trades[:] = [t for t in _daily_trades if t['timestamp'] > cutoff]


def _daily_trade_count() -> int:
    """Number of trades placed in the last 24 hours."""
    _prune_daily_trades()
    return len(_daily_trades)


def _daily_realised_pnl() -> float:
    """Sum of realised PnL (USDT) in the last 24h from recorded trades."""
    _prune_daily_trades()
    return sum(t.get('pnl', 0) or 0 for t in _daily_trades)


def record_trade(symbol: str, pnl: float | None = None):
    """Record a trade for daily tracking."""
    _daily_trades.append({
        'timestamp': time.time(),
        'symbol': symbol,
        'pnl': pnl,
    })


def record_loss():
    """Mark a loss event to trigger cooldown."""
    global _last_loss_timestamp
    _last_loss_timestamp = time.time()


def track_position(symbol: str, side: str, entry: float, tp: float, sl: float,
                   strategy: str = "trend", timeframe: str = "15m"):
    """Register an opened position for outcome monitoring."""
    _tracked_positions[symbol] = {
        'side': side,
        'entry': entry,
        'tp': tp,
        'sl': sl,
        'strategy': strategy,
        'timeframe': timeframe,
        'opened_at': time.time(),
    }
    log_event(f"📌 Tracking position: {symbol} {side} entry={entry} TP={tp} SL={sl}")


def untrack_position(symbol: str):
    """Remove a position from outcome monitoring (manual close, emergency, etc.)."""
    _tracked_positions.pop(symbol, None)


def check_capital_guards(exchange) -> tuple[bool, str | None]:
    """
    Run all capital protection checks before allowing a new trade.
    Returns (allowed, rejection_reason).
    """
    global _daily_start_balance

    # 1. Exchange consistency
    ok, err = validate_exchange_consistency()
    if not ok:
        return False, err

    # 2. Daily trade count limit
    if _daily_trade_count() >= config.LIVE_TRADING_DAILY_MAX_TRADES:
        return False, f"Daily trade limit reached ({config.LIVE_TRADING_DAILY_MAX_TRADES} trades in 24h)"

    # 3. Post-loss cooldown
    since_loss = time.time() - _last_loss_timestamp
    if _last_loss_timestamp > 0 and since_loss < config.LIVE_TRADING_COOLDOWN_AFTER_LOSS_SEC:
        remaining = int(config.LIVE_TRADING_COOLDOWN_AFTER_LOSS_SEC - since_loss)
        return False, f"Cooling off after loss ({remaining}s remaining)"

    # 4. Balance checks
    try:
        balance = exchange.fetch_balance()
        usdt_total = float(balance.get('USDT', {}).get('total', 0) or 0)
        usdt_free = float(balance.get('USDT', {}).get('free', 0) or 0)
        usdt_used = float(balance.get('USDT', {}).get('used', 0) or 0)
    except Exception as e:
        return False, f"Cannot fetch balance: {e}"

    # Record starting balance on first check of the day
    if _daily_start_balance is None:
        _daily_start_balance = usdt_total
        log_event(f"Daily starting balance recorded: {usdt_total:.2f} USDT")

    # 5. Minimum balance floor
    if usdt_free < config.LIVE_TRADING_MIN_BALANCE_USDT:
        return False, (
            f"Balance too low: {usdt_free:.2f} USDT free "
            f"(minimum: {config.LIVE_TRADING_MIN_BALANCE_USDT} USDT)"
        )

    # 6. Daily loss limit
    if _daily_start_balance > 0:
        loss_pct = (((_daily_start_balance - usdt_total) / _daily_start_balance) * 100)
        if loss_pct >= config.LIVE_TRADING_DAILY_LOSS_LIMIT_PCT:
            config.LIVE_TRADING_ENABLED = False
            msg = (
                f"DAILY LOSS LIMIT HIT: {loss_pct:.1f}% drawdown "
                f"(limit: {config.LIVE_TRADING_DAILY_LOSS_LIMIT_PCT}%). "
                f"Live trading auto-disabled. Use /live on to re-enable."
            )
            log_event(f"🚨 {msg}")
            return False, msg

    # 7. Maximum capital deployed
    if usdt_total > 0:
        deployed_pct = (usdt_used / usdt_total) * 100
        if deployed_pct >= config.LIVE_TRADING_MAX_CAPITAL_DEPLOYED_PCT:
            return False, (
                f"Max capital deployed: {deployed_pct:.1f}% in use "
                f"(limit: {config.LIVE_TRADING_MAX_CAPITAL_DEPLOYED_PCT}%)"
            )

    return True, None


def get_position_size(exchange, symbol, entry_price, sl_price):
    """Calculate position size based on risk percentage of available balance."""
    try:
        balance = exchange.fetch_balance()
        usdt_free = float(balance.get('USDT', {}).get('free', 0) or 0)

        if usdt_free <= 0:
            return None, "No available USDT balance"

        # Never risk more than the configured % of free balance
        risk_amount = usdt_free * (config.LIVE_TRADING_RISK_PCT / 100.0)
        sl_distance = abs(entry_price - sl_price)

        if sl_distance <= 0:
            return None, "Invalid SL distance"

        # Position size = risk / (SL distance as fraction of entry)
        position_size_usd = risk_amount / (sl_distance / entry_price)

        # Hard cap: never use more than 30% of free balance for one trade's margin
        max_single_trade = usdt_free * 0.30
        position_size_usd = min(position_size_usd, max_single_trade)

        market = exchange.market(symbol)
        min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
        contract_size = float(market.get('contractSize', 1) or 1)

        contracts = position_size_usd / (entry_price * contract_size)

        if contracts < (min_amount or 0):
            return None, f"Position too small ({contracts:.4f} < min {min_amount})"

        return contracts, None
    except Exception as e:
        return None, f"Position sizing error: {e}"


def get_open_positions(exchange):
    """Return list of open positions on Phemex."""
    try:
        positions = exchange.fetch_positions()
        return [p for p in positions if float(p.get('contracts', 0) or 0) > 0]
    except Exception as e:
        log_event(f"Error fetching positions: {e}")
        return []


def execute_trade(symbol, side, entry_price, tp_price, sl_price, strategy_type="trend"):
    """
    Execute a live trade on Phemex with TP/SL.

    Runs all capital protection checks before placing any order.
    Returns dict with 'success', 'order_id', 'error' keys.
    """
    if not config.LIVE_TRADING_ENABLED:
        return {'success': False, 'error': 'Live trading is disabled'}

    try:
        exchange = get_authenticated_exchange()

        # Run all capital guards
        allowed, reason = check_capital_guards(exchange)
        if not allowed:
            log_event(f"Trade blocked for {symbol}: {reason}")
            return {'success': False, 'error': reason}

        # Position limits
        open_positions = get_open_positions(exchange)
        if len(open_positions) >= config.LIVE_TRADING_MAX_POSITIONS:
            return {'success': False, 'error': f'Max positions reached ({config.LIVE_TRADING_MAX_POSITIONS})'}

        symbol_positions = [p for p in open_positions if p.get('symbol') == symbol]
        if symbol_positions:
            return {'success': False, 'error': f'Already in position for {symbol}'}

        # Set leverage
        try:
            exchange.set_leverage(config.LIVE_TRADING_LEVERAGE, symbol)
        except Exception as e:
            log_event(f"Leverage set warning for {symbol}: {e}")

        # Size the position
        contracts, err = get_position_size(exchange, symbol, entry_price, sl_price)
        if err:
            return {'success': False, 'error': err}

        market = exchange.market(symbol)
        amount_precision = market.get('precision', {}).get('amount', 8)
        contracts = round(contracts, amount_precision)

        log_event(f"Placing {side} order: {symbol} x{contracts} @ market (leverage: {config.LIVE_TRADING_LEVERAGE}x)")

        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=contracts,
        )

        order_id = order.get('id', 'unknown')
        log_event(f"Order placed: {order_id} for {symbol}")

        # Record trade for daily tracking
        record_trade(symbol)

        # Place TP/SL — SL is CRITICAL. If SL fails, emergency close.
        sl_ok = _place_sl_with_retries(exchange, symbol, side, contracts, sl_price)
        if not sl_ok:
            log_event(f"🚨 CRITICAL: SL failed for {symbol} — emergency closing position")
            _emergency_close(exchange, symbol, side, contracts)
            from utils.telegramUtils import send_telegram
            send_telegram(
                f"🚨 EMERGENCY CLOSE: {symbol}\n"
                f"Stop-loss order could not be placed after retries.\n"
                f"Position was closed at market to prevent unprotected exposure.",
                bypass_rate_limit=True,
            )
            return {'success': False, 'error': 'SL placement failed — position emergency closed'}

        # TP is nice-to-have but not critical
        _place_tp_order(exchange, symbol, side, contracts, tp_price)

        # Track position for outcome monitoring
        track_position(symbol, side, entry_price, tp_price, sl_price, strategy_type)

        return {'success': True, 'order_id': order_id, 'contracts': contracts}

    except Exception as e:
        log_event(f"Live trade execution failed for {symbol}: {e}")
        return {'success': False, 'error': str(e)}


def _place_sl_with_retries(exchange, symbol, side, contracts, sl_price, max_retries=3):
    """
    Place stop-loss order with retries. Returns True if successful, False if all attempts fail.
    SL is the critical safety net — this MUST succeed or the position gets closed.
    """
    if not sl_price:
        log_event(f"🚨 No SL price provided for {symbol} — cannot protect position")
        return False

    close_side = 'sell' if side == 'buy' else 'buy'

    for attempt in range(1, max_retries + 1):
        try:
            exchange.create_order(
                symbol=symbol,
                type='stop',
                side=close_side,
                amount=contracts,
                price=sl_price,
                params={
                    'reduceOnly': True,
                    'stopPrice': sl_price,
                    'triggerType': 'ByLastPrice',
                },
            )
            log_event(f"SL order placed for {symbol} @ {sl_price} (attempt {attempt})")
            return True
        except Exception as e:
            log_event(f"SL attempt {attempt}/{max_retries} failed for {symbol}: {e}")
            if attempt < max_retries:
                time.sleep(2 * attempt)

    return False


def _place_tp_order(exchange, symbol, side, contracts, tp_price):
    """Place take-profit order. Non-critical — failure is logged but doesn't trigger emergency."""
    if not tp_price:
        return

    close_side = 'sell' if side == 'buy' else 'buy'
    try:
        exchange.create_order(
            symbol=symbol,
            type='limit',
            side=close_side,
            amount=contracts,
            price=tp_price,
            params={'reduceOnly': True},
        )
        log_event(f"TP order placed for {symbol} @ {tp_price}")
    except Exception as e:
        log_event(f"⚠️ TP placement failed for {symbol} (non-critical): {e}")


def _emergency_close(exchange, symbol, side, contracts):
    """Immediately close a position at market when SL cannot be placed."""
    close_side = 'sell' if side == 'buy' else 'buy'
    try:
        exchange.create_order(
            symbol=symbol,
            type='market',
            side=close_side,
            amount=contracts,
            params={'reduceOnly': True},
        )
        log_event(f"🚨 Emergency close executed for {symbol}")
    except Exception as e:
        log_event(f"🚨🚨 CRITICAL: Emergency close ALSO failed for {symbol}: {e}")


def verify_position_has_sl(exchange, symbol) -> bool:
    """
    Check if a position has an active stop-loss order on the exchange.
    Returns True if protected, False if naked.
    """
    try:
        open_orders = exchange.fetch_open_orders(symbol)
        for order in open_orders:
            order_type = (order.get('type') or '').lower()
            is_reduce = order.get('reduceOnly', False) or order.get('info', {}).get('reduceOnly', False)
            if order_type in ('stop', 'stop_market', 'stopmarket') and is_reduce:
                return True
        return False
    except Exception as e:
        log_event(f"Error checking SL orders for {symbol}: {e}")
        return False


def watchdog_check_positions():
    """
    Periodic safety check: verify all open positions have SL orders.
    If any position is unprotected, attempt to place SL or emergency close.
    Call this from the main loop every cycle.
    """
    if not config.LIVE_TRADING_ENABLED:
        return

    try:
        exchange = get_authenticated_exchange()
        positions = get_open_positions(exchange)

        for pos in positions:
            symbol = pos.get('symbol')
            if not symbol:
                continue

            has_sl = verify_position_has_sl(exchange, symbol)
            if has_sl:
                continue

            # Position has no SL — this is dangerous
            contracts = float(pos.get('contracts', 0))
            pos_side = pos.get('side', 'long')
            entry_price = float(pos.get('entryPrice', 0) or pos.get('markPrice', 0) or 0)

            if contracts <= 0 or entry_price <= 0:
                continue

            log_event(f"🚨 WATCHDOG: {symbol} has no SL order — attempting to place emergency SL")

            # Calculate emergency SL at 2% from entry (wider than normal to avoid immediate trigger)
            if pos_side == 'long':
                emergency_sl = entry_price * 0.98
                side = 'buy'
            else:
                emergency_sl = entry_price * 1.02
                side = 'sell'

            sl_ok = _place_sl_with_retries(exchange, symbol, side, contracts, emergency_sl, max_retries=2)
            if not sl_ok:
                log_event(f"🚨 WATCHDOG: Cannot place SL for {symbol} — emergency closing")
                close_side = 'sell' if pos_side == 'long' else 'buy'
                _emergency_close(exchange, symbol, close_side, contracts)

                try:
                    from utils.telegramUtils import send_telegram
                    send_telegram(
                        f"🚨 WATCHDOG EMERGENCY CLOSE: {symbol}\n"
                        f"Position had no stop-loss and SL placement failed.\n"
                        f"Emergency closed at market to prevent liquidation.",
                        bypass_rate_limit=True,
                    )
                except Exception:
                    pass
            else:
                try:
                    from utils.telegramUtils import send_telegram
                    send_telegram(
                        f"⚠️ WATCHDOG: Placed emergency SL for {symbol} @ {emergency_sl:.6f}\n"
                        f"Position was found without stop-loss protection.",
                        bypass_rate_limit=True,
                    )
                except Exception:
                    pass

    except Exception as e:
        log_event(f"Watchdog check error: {e}")


def close_position(symbol, reason="manual"):
    """Close an open position for a symbol."""
    if not config.LIVE_TRADING_ENABLED:
        return {'success': False, 'error': 'Live trading is disabled'}

    try:
        exchange = get_authenticated_exchange()
        positions = get_open_positions(exchange)
        pos = next((p for p in positions if p.get('symbol') == symbol), None)

        if not pos:
            return {'success': False, 'error': f'No open position for {symbol}'}

        contracts = float(pos.get('contracts', 0))
        pos_side = pos.get('side', 'long')
        side = 'sell' if pos_side == 'long' else 'buy'

        # Record PnL for daily tracking
        pnl = float(pos.get('unrealizedPnl', 0) or 0)

        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=contracts,
            params={'reduceOnly': True},
        )

        # Track the result
        record_trade(symbol, pnl=pnl)
        if pnl < 0:
            record_loss()
            log_event(f"Loss recorded for {symbol}: {pnl:.2f} USDT — cooldown active")

        untrack_position(symbol)
        log_event(f"Position closed for {symbol} (reason: {reason}): {order.get('id')} PnL: {pnl:+.2f}")
        return {'success': True, 'order_id': order.get('id'), 'pnl': pnl}

    except Exception as e:
        log_event(f"Failed to close position for {symbol}: {e}")
        return {'success': False, 'error': str(e)}


def get_account_summary():
    """Return a summary of the Phemex trading account."""
    try:
        exchange = get_authenticated_exchange()
        balance = exchange.fetch_balance()
        positions = get_open_positions(exchange)

        usdt_total = float(balance.get('USDT', {}).get('total', 0) or 0)
        usdt_free = float(balance.get('USDT', {}).get('free', 0) or 0)
        usdt_used = float(balance.get('USDT', {}).get('used', 0) or 0)

        return {
            'balance_total': usdt_total,
            'balance_free': usdt_free,
            'balance_used': usdt_used,
            'open_positions': len(positions),
            'daily_trades': _daily_trade_count(),
            'daily_trade_limit': config.LIVE_TRADING_DAILY_MAX_TRADES,
            'daily_pnl': _daily_realised_pnl(),
            'positions': [
                {
                    'symbol': p.get('symbol'),
                    'side': p.get('side'),
                    'contracts': p.get('contracts'),
                    'pnl': p.get('unrealizedPnl'),
                    'leverage': p.get('leverage'),
                }
                for p in positions
            ],
        }
    except Exception as e:
        return {'error': str(e)}


def get_protection_status():
    """Return current state of all capital protection mechanisms."""
    _prune_daily_trades()
    since_loss = time.time() - _last_loss_timestamp if _last_loss_timestamp > 0 else None
    cooldown_active = (
        since_loss is not None and since_loss < config.LIVE_TRADING_COOLDOWN_AFTER_LOSS_SEC
    )

    return {
        'exchange_match': config.EXCHANGE.strip().lower() == config.LIVE_TRADING_PLATFORM.strip().lower(),
        'daily_trades': _daily_trade_count(),
        'daily_limit': config.LIVE_TRADING_DAILY_MAX_TRADES,
        'daily_pnl': _daily_realised_pnl(),
        'daily_loss_limit_pct': config.LIVE_TRADING_DAILY_LOSS_LIMIT_PCT,
        'min_balance_usdt': config.LIVE_TRADING_MIN_BALANCE_USDT,
        'max_capital_deployed_pct': config.LIVE_TRADING_MAX_CAPITAL_DEPLOYED_PCT,
        'cooldown_active': cooldown_active,
        'cooldown_remaining_sec': max(0, int(config.LIVE_TRADING_COOLDOWN_AFTER_LOSS_SEC - since_loss)) if cooldown_active else 0,
        'starting_balance': _daily_start_balance,
    }


def monitor_trade_outcomes():
    """
    Check tracked positions and send Telegram alerts when trades complete.
    Called each cycle from the main loop. Detects TP hit, SL hit, or unknown close.
    """
    if not _tracked_positions:
        return

    try:
        exchange = get_authenticated_exchange()
        open_positions = get_open_positions(exchange)
        open_symbols = {p.get('symbol') for p in open_positions}
    except Exception as e:
        log_event(f"Outcome monitor: cannot fetch positions: {e}")
        return

    closed_symbols = [sym for sym in list(_tracked_positions) if sym not in open_symbols]

    for symbol in closed_symbols:
        pos_info = _tracked_positions.pop(symbol)
        _send_outcome_alert(exchange, symbol, pos_info)


def _send_outcome_alert(exchange, symbol: str, pos_info: dict):
    """Determine trade outcome and send Telegram notification."""
    from utils.telegramUtils import send_telegram

    side = pos_info['side']
    entry = pos_info['entry']
    tp = pos_info['tp']
    sl = pos_info['sl']
    strategy = pos_info.get('strategy', 'unknown')
    timeframe = pos_info.get('timeframe', '?')
    opened_at = pos_info.get('opened_at', 0)

    # Try to get the last price to determine outcome
    outcome = "CLOSED"
    pnl_estimate = None
    try:
        ticker = exchange.fetch_ticker(symbol)
        last_price = float(ticker.get('last', 0) or 0)

        if side == 'buy':
            tp_distance = abs(last_price - tp) if tp else float('inf')
            sl_distance = abs(last_price - sl) if sl else float('inf')
            pnl_estimate = ((last_price - entry) / entry) * 100
        else:
            tp_distance = abs(last_price - tp) if tp else float('inf')
            sl_distance = abs(last_price - sl) if sl else float('inf')
            pnl_estimate = ((entry - last_price) / entry) * 100

        if tp and sl:
            if tp_distance < sl_distance:
                outcome = "TP HIT ✅"
            else:
                outcome = "SL HIT ❌"
        elif pnl_estimate is not None:
            outcome = "TP HIT ✅" if pnl_estimate > 0 else "SL HIT ❌"
    except Exception:
        pass

    # Calculate duration
    duration_sec = int(time.time() - opened_at) if opened_at else 0
    if duration_sec >= 3600:
        duration_str = f"{duration_sec // 3600}h {(duration_sec % 3600) // 60}m"
    elif duration_sec >= 60:
        duration_str = f"{duration_sec // 60}m"
    else:
        duration_str = f"{duration_sec}s"

    # Record PnL in daily tracking
    if pnl_estimate is not None and pnl_estimate < 0:
        record_loss()

    emoji = "🎯" if "TP" in outcome else "🛑" if "SL" in outcome else "📊"

    msg = (
        f"{emoji} <b>Trade {outcome}</b>\n"
        f"\n"
        f"<b>Pair:</b> {symbol}\n"
        f"<b>Side:</b> {side.upper()}\n"
        f"<b>Strategy:</b> {strategy} ({timeframe})\n"
        f"\n"
        f"<b>Entry:</b> {entry}\n"
        f"<b>TP:</b> {tp}\n"
        f"<b>SL:</b> {sl}\n"
    )

    if pnl_estimate is not None:
        msg += f"<b>Est. P&L:</b> {pnl_estimate:+.2f}%\n"

    msg += f"<b>Duration:</b> {duration_str}\n"

    try:
        send_telegram(msg, parse_mode="HTML", bypass_rate_limit=True)
    except Exception as e:
        log_event(f"Failed to send outcome alert for {symbol}: {e}")
