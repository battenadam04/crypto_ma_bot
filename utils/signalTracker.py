"""Track signals sent during the day and produce an EOD summary."""

from datetime import datetime, timezone
from utils.utils import log_event

_daily_signals: list[dict] = []


def record_signal(symbol, direction, strategy_type, entry_price, tp_price, sl_price):
    """Call this every time a signal is generated."""
    _daily_signals.append({
        'symbol': symbol,
        'direction': direction,
        'strategy_type': strategy_type,
        'entry': entry_price,
        'tp': tp_price,
        'sl': sl_price,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })
    log_event(f"Signal recorded: {direction} {symbol} @ {entry_price}")


def _resolve_signal(signal, exchange):
    """Check if TP or SL was hit since the signal was sent by looking at the current price."""
    symbol = signal['symbol']
    entry = float(signal['entry'])
    tp = signal.get('tp')
    sl = signal.get('sl')
    is_long = signal['direction'] in ('long', 'buy')

    if tp is None or sl is None:
        return 'unresolved', 0.0

    tp = float(tp)
    sl = float(sl)

    try:
        ticker = exchange.fetch_ticker(symbol)
        current = ticker['last']
        if current is None:
            return 'unresolved', 0.0
    except Exception:
        return 'unresolved', 0.0

    if is_long:
        if current >= tp:
            return 'win', ((tp - entry) / entry) * 100
        if current <= sl:
            return 'loss', ((sl - entry) / entry) * 100
        return 'open', ((current - entry) / entry) * 100
    else:
        if current <= tp:
            return 'win', ((entry - tp) / entry) * 100
        if current >= sl:
            return 'loss', ((entry - sl) / entry) * 100
        return 'open', ((entry - current) / entry) * 100


def build_eod_summary(exchange):
    """Build an HTML summary of today's signals and their outcomes."""
    if not _daily_signals:
        return None

    wins = losses = opens = unresolved = 0
    lines = [f"<b>📋 Daily Signal Report</b> ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"]
    lines.append(f"Signals today: {len(_daily_signals)}\n")

    for sig in _daily_signals:
        result, pnl_pct = _resolve_signal(sig, exchange)
        arrow = {'win': '🟢', 'loss': '🔴', 'open': '🟡', 'unresolved': '⚪'}.get(result, '⚪')
        direction_icon = '📈' if sig['direction'] in ('long', 'buy') else '📉'

        lines.append(
            f"{arrow} {direction_icon} <b>{sig['symbol']}</b> ({sig['strategy_type']})\n"
            f"    Entry: {sig['entry']} | Result: {result.upper()} ({pnl_pct:+.2f}%)"
        )

        if result == 'win':
            wins += 1
        elif result == 'loss':
            losses += 1
        elif result == 'open':
            opens += 1
        else:
            unresolved += 1

    total_resolved = wins + losses
    win_rate = (wins / total_resolved * 100) if total_resolved > 0 else 0

    lines.append(f"\n<b>Summary:</b>")
    lines.append(f"  Wins: {wins} | Losses: {losses} | Still open: {opens}")
    if total_resolved > 0:
        lines.append(f"  Win rate: <b>{win_rate:.0f}%</b> ({total_resolved} resolved)")

    return "\n".join(lines)


def send_eod_report():
    """Scheduled job: build the EOD summary and send to Telegram, then reset."""
    from utils.exchangeUtils import get_exchange
    from utils.telegramUtils import send_telegram

    if not _daily_signals:
        log_event("EOD report: no signals today, skipping.")
        return

    try:
        summary = build_eod_summary(get_exchange())
        if summary:
            send_telegram(summary, parse_mode='HTML')
            log_event("EOD signal report sent to Telegram.")
    except Exception as e:
        log_event(f"Failed to send EOD report: {e}")
    finally:
        reset_daily_signals()


def reset_daily_signals():
    """Clear the day's signals (called after EOD report)."""
    _daily_signals.clear()


def get_daily_signals():
    """Return a copy of today's signals (for testing or Telegram commands)."""
    return list(_daily_signals)
