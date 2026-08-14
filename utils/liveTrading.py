"""Phemex live trading execution module.

Handles authenticated order placement, position sizing, and TP/SL management.
Only active when LIVE_TRADING_ENABLED is True and API keys are configured.
"""

import ccxt
import config
from utils.utils import log_event


_authenticated_exchange = None


def get_authenticated_exchange():
    """Return a Phemex exchange instance with trading credentials."""
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


def get_position_size(exchange, symbol, entry_price, sl_price):
    """Calculate position size based on risk percentage of available balance."""
    try:
        balance = exchange.fetch_balance()
        usdt_free = float(balance.get('USDT', {}).get('free', 0) or 0)

        if usdt_free <= 0:
            return None, "No available USDT balance"

        risk_amount = usdt_free * (config.LIVE_TRADING_RISK_PCT / 100.0)
        sl_distance = abs(entry_price - sl_price)

        if sl_distance <= 0:
            return None, "Invalid SL distance"

        position_size_usd = risk_amount / (sl_distance / entry_price)
        position_size_usd = min(position_size_usd, usdt_free * 0.9)

        market = exchange.market(symbol)
        min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
        contract_size = float(market.get('contractSize', 1) or 1)

        contracts = position_size_usd / (entry_price * contract_size)

        if contracts < min_amount:
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

    Returns dict with 'success', 'order_id', 'error' keys.
    """
    if not config.LIVE_TRADING_ENABLED:
        return {'success': False, 'error': 'Live trading is disabled'}

    try:
        exchange = get_authenticated_exchange()

        open_positions = get_open_positions(exchange)
        if len(open_positions) >= config.LIVE_TRADING_MAX_POSITIONS:
            return {'success': False, 'error': f'Max positions reached ({config.LIVE_TRADING_MAX_POSITIONS})'}

        symbol_positions = [p for p in open_positions if p.get('symbol') == symbol]
        if symbol_positions:
            return {'success': False, 'error': f'Already in position for {symbol}'}

        try:
            exchange.set_leverage(config.LIVE_TRADING_LEVERAGE, symbol)
        except Exception as e:
            log_event(f"Leverage set warning for {symbol}: {e}")

        contracts, err = get_position_size(exchange, symbol, entry_price, sl_price)
        if err:
            return {'success': False, 'error': err}

        market = exchange.market(symbol)
        amount_precision = market.get('precision', {}).get('amount', 8)
        contracts = round(contracts, amount_precision)

        log_event(f"Placing {side} order: {symbol} x{contracts} @ market")

        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=contracts,
        )

        order_id = order.get('id', 'unknown')
        log_event(f"Order placed: {order_id} for {symbol}")

        _place_tp_sl_orders(exchange, symbol, side, contracts, tp_price, sl_price)

        return {'success': True, 'order_id': order_id, 'contracts': contracts}

    except Exception as e:
        log_event(f"Live trade execution failed for {symbol}: {e}")
        return {'success': False, 'error': str(e)}


def _place_tp_sl_orders(exchange, symbol, side, contracts, tp_price, sl_price):
    """Place take-profit and stop-loss orders after entry fill."""
    close_side = 'sell' if side == 'buy' else 'buy'

    try:
        if tp_price:
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
        log_event(f"Failed to place TP for {symbol}: {e}")

    try:
        if sl_price:
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
            log_event(f"SL order placed for {symbol} @ {sl_price}")
    except Exception as e:
        log_event(f"Failed to place SL for {symbol}: {e}")


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
        side = 'sell' if pos.get('side') == 'long' else 'buy'

        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=contracts,
            params={'reduceOnly': True},
        )

        log_event(f"Position closed for {symbol} (reason: {reason}): {order.get('id')}")
        return {'success': True, 'order_id': order.get('id')}

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
            'positions': [
                {
                    'symbol': p.get('symbol'),
                    'side': p.get('side'),
                    'contracts': p.get('contracts'),
                    'pnl': p.get('unrealizedPnl'),
                }
                for p in positions
            ],
        }
    except Exception as e:
        return {'error': str(e)}
