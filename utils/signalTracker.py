"""Track signals sent during the day and produce an EOD summary."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone

import config
from utils.utils import log_event

_daily_signals: list[dict] = []
_open_signals: list[dict] = []
_open_lock = threading.Lock()
_OPEN_SIGNALS_FILE = os.path.join(os.path.dirname(__file__), "..", "open_signals.json")
_open_loaded = False

# Path-dependent EOD resolution uses this TF so TP/SL touches aren't missed.
_RESOLVE_TIMEFRAME = "5m"
_RESOLVE_OHLCV_LIMIT = 500


def record_signal(symbol, direction, strategy_type, entry_price, tp_price, sl_price, timeframe=None):
    """Call this every time a signal is generated."""
    sig = {
        "id": uuid.uuid4().hex[:12],
        "symbol": symbol,
        "direction": direction,
        "strategy_type": strategy_type,
        "entry": entry_price,
        "tp": tp_price,
        "sl": sl_price,
        "timeframe": timeframe or getattr(config, "TIMEFRAME", "15m"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _daily_signals.append(sig)
    log_event(f"Signal recorded: {direction} {symbol} @ {entry_price}")
    try:
        from utils.channelHeartbeat import note_signal_sent
        note_signal_sent()
    except Exception as e:
        log_event(f"Heartbeat signal stamp failed: {e}")
    _add_open_signal(sig)


def _load_open_signals() -> None:
    global _open_loaded, _open_signals
    if _open_loaded:
        return
    with _open_lock:
        if _open_loaded:
            return
        try:
            if os.path.isfile(_OPEN_SIGNALS_FILE):
                with open(_OPEN_SIGNALS_FILE, "r") as f:
                    data = json.load(f) or []
                if isinstance(data, list):
                    _open_signals = [s for s in data if isinstance(s, dict)]
        except Exception as e:
            log_event(f"Open signals load failed: {e}")
            _open_signals = []
        _open_loaded = True


def _persist_open_signals() -> None:
    tmp = _OPEN_SIGNALS_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(_open_signals, f)
        os.replace(tmp, _OPEN_SIGNALS_FILE)
    except Exception as e:
        log_event(f"Open signals save failed: {e}")


def _add_open_signal(sig: dict) -> None:
    _load_open_signals()
    with _open_lock:
        _open_signals.append(dict(sig))
        # Bound memory / file size
        if len(_open_signals) > 100:
            _open_signals[:] = _open_signals[-100:]
        _persist_open_signals()


def get_open_signals() -> list[dict]:
    _load_open_signals()
    with _open_lock:
        return [dict(s) for s in _open_signals]


def reset_open_signals_for_tests() -> None:
    global _open_loaded
    with _open_lock:
        _open_signals.clear()
        _open_loaded = True
        try:
            if os.path.isfile(_OPEN_SIGNALS_FILE):
                os.remove(_OPEN_SIGNALS_FILE)
        except Exception:
            pass


def _parse_signal_ts(signal) -> datetime | None:
    raw = signal.get('timestamp')
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _lookahead_seconds() -> int:
    """Match backtest unresolved window: BACKTEST_LOOKAHEAD bars of the signal TF."""
    tf = (config.TIMEFRAME or "15m").strip().lower()
    minutes = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240,
    }.get(tf, 15)
    bars = max(1, int(getattr(config, "BACKTEST_LOOKAHEAD", 48)))
    return bars * minutes * 60


def _pnl_pct(entry: float, exit_price: float, is_long: bool) -> float:
    if is_long:
        return ((exit_price - entry) / entry) * 100
    return ((entry - exit_price) / entry) * 100


def _first_touch(is_long: bool, tp: float, sl: float, candles) -> tuple[str, float] | None:
    """Walk candles in time order. Same-bar TP+SL → conservative SL (loss)."""
    for row in candles:
        high = float(row[2])
        low = float(row[3])
        if is_long:
            hit_tp = high >= tp
            hit_sl = low <= sl
        else:
            hit_tp = low <= tp
            hit_sl = high >= sl
        if hit_tp and hit_sl:
            return "loss", sl
        if hit_sl:
            return "loss", sl
        if hit_tp:
            return "win", tp
    return None


def _resolve_from_ohlcv(signal, exchange, entry, tp, sl, is_long):
    """Return (result, pnl) from candle path, or None if OHLCV unavailable."""
    ts = _parse_signal_ts(signal)
    if ts is None:
        return None
    since_ms = int(ts.timestamp() * 1000)
    try:
        ohlcv = exchange.fetch_ohlcv(
            signal["symbol"],
            timeframe=_RESOLVE_TIMEFRAME,
            since=since_ms,
            limit=_RESOLVE_OHLCV_LIMIT,
        )
    except Exception as e:
        log_event(f"EOD OHLCV resolve failed for {signal.get('symbol')}: {e}")
        return None
    if not ohlcv or not isinstance(ohlcv, (list, tuple)):
        return None

    touch = _first_touch(is_long, tp, sl, ohlcv)
    last_close = float(ohlcv[-1][4])
    if touch:
        result, exit_px = touch
        return result, _pnl_pct(entry, exit_px, is_long)

    age_sec = (datetime.now(timezone.utc) - ts).total_seconds()
    mtm = _pnl_pct(entry, last_close, is_long)
    if age_sec >= _lookahead_seconds():
        return "expired", mtm
    return "open", mtm


def _resolve_from_last_price(signal, exchange, entry, tp, sl, is_long):
    """Fallback: last ticker only (can mis-label touches that already retraced)."""
    try:
        ticker = exchange.fetch_ticker(signal["symbol"])
        current = ticker["last"]
        if current is None:
            return "unresolved", 0.0
        current = float(current)
    except Exception:
        return "unresolved", 0.0

    if is_long:
        if current >= tp:
            return "win", _pnl_pct(entry, tp, True)
        if current <= sl:
            return "loss", _pnl_pct(entry, sl, True)
        return "open", _pnl_pct(entry, current, True)
    if current <= tp:
        return "win", _pnl_pct(entry, tp, False)
    if current >= sl:
        return "loss", _pnl_pct(entry, sl, False)
    return "open", _pnl_pct(entry, current, False)


def _resolve_signal(signal, exchange):
    """Check if TP or SL was touched since the signal using candle highs/lows."""
    try:
        entry = float(signal["entry"])
    except Exception:
        return "unresolved", 0.0
    tp = signal.get("tp")
    sl = signal.get("sl")
    is_long = signal["direction"] in ("long", "buy")

    if tp is None or sl is None:
        return "unresolved", 0.0
    try:
        tp = float(tp)
        sl = float(sl)
    except Exception:
        return "unresolved", 0.0

    path = _resolve_from_ohlcv(signal, exchange, entry, tp, sl, is_long)
    if path is not None:
        return path
    return _resolve_from_last_price(signal, exchange, entry, tp, sl, is_long)


def build_eod_summary(exchange):
    """Build an HTML summary of today's signals and their outcomes."""
    if not _daily_signals:
        return None

    wins = losses = opens = expired = unresolved = 0
    lines = [f"<b>📋 Daily Signal Report</b> ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"]
    lines.append(f"Signals today: {len(_daily_signals)}\n")

    for sig in _daily_signals:
        result, pnl_pct = _resolve_signal(sig, exchange)
        arrow = {
            "win": "🟢",
            "loss": "🔴",
            "open": "🟡",
            "expired": "⚪",
            "unresolved": "⚪",
        }.get(result, "⚪")
        direction_icon = "📈" if sig["direction"] in ("long", "buy") else "📉"

        lines.append(
            f"{arrow} {direction_icon} <b>{sig['symbol']}</b> ({sig['strategy_type']})\n"
            f"    Entry: {sig['entry']} | Result: {result.upper()} ({pnl_pct:+.2f}%)"
        )

        if result == "win":
            wins += 1
        elif result == "loss":
            losses += 1
        elif result == "open":
            opens += 1
        elif result == "expired":
            expired += 1
        else:
            unresolved += 1

    total_resolved = wins + losses
    win_rate = (wins / total_resolved * 100) if total_resolved > 0 else 0

    lines.append("\n<b>Summary:</b>")
    lines.append(
        f"  Wins: {wins} | Losses: {losses} | Still open: {opens} | Expired: {expired}"
    )
    if total_resolved > 0:
        lines.append(f"  Win rate: <b>{win_rate:.0f}%</b> ({total_resolved} resolved, TP/SL first-touch)")
    lines.append(
        "<i>Open = TP/SL not touched yet. Expired = no touch within the 12h setup window. "
        "Resolved from candle highs/lows, not last price.</i>"
    )

    return "\n".join(lines)


def build_quiet_day_eod_message() -> str:
    """Short EOD note when filters produced zero setups."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return "\n".join(
        [
            f"<b>📋 Daily Signal Report</b> ({day})",
            "",
            "Signals today: <b>0</b>",
            "",
            "A quiet day usually means the filters held — weak or high-risk setups "
            "were skipped on purpose. That is the strategy working, not downtime.",
            "",
            "<i>No signal ≠ offline.</i>",
        ]
    )


def send_eod_report():
    """Scheduled job: build the EOD summary and send to Telegram, then reset."""
    from utils.exchangeUtils import get_exchange
    from utils.telegramUtils import send_telegram

    try:
        if not _daily_signals:
            send_telegram(
                build_quiet_day_eod_message(),
                parse_mode="HTML",
                bypass_rate_limit=True,
            )
            log_event("EOD quiet-day report sent to Telegram.")
            return

        summary = build_eod_summary(get_exchange())
        if summary:
            # Don't let rate limiting suppress the daily report.
            send_telegram(summary, parse_mode="HTML", bypass_rate_limit=True)
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


def format_and_maybe_send_outcome(signal: dict, result: str, pnl_pct: float, send_fn) -> bool:
    """Send a channel outcome alert. Returns True if sent."""
    if result not in ("win", "loss", "expired"):
        return False
    from utils.signalFormat import format_signal_outcome_message

    msg = format_signal_outcome_message(signal, result, pnl_pct)
    try:
        send_fn(msg, parse_mode="HTML", bypass_rate_limit=True)
    except TypeError:
        send_fn(msg)
    except Exception as e:
        log_event(f"Signal outcome notify failed: {e}")
        return False
    return True


def monitor_signal_outcomes(exchange=None, send_fn=None) -> list[dict]:
    """
    Resolve open posted signals and announce TP/SL/expiry on the Pro channel.
    Returns list of {signal, result, pnl} that were closed this pass.
    """
    if not getattr(config, "SIGNAL_OUTCOME_ALERTS_ENABLED", True):
        return []

    _load_open_signals()
    if exchange is None:
        from utils.exchangeUtils import get_exchange
        exchange = get_exchange()
    if send_fn is None:
        from utils.telegramUtils import send_telegram
        send_fn = send_telegram

    closed: list[dict] = []
    remaining: list[dict] = []

    with _open_lock:
        snapshot = list(_open_signals)

    for sig in snapshot:
        try:
            result, pnl = _resolve_signal(sig, exchange)
        except Exception as e:
            log_event(f"Signal outcome resolve failed for {sig.get('symbol')}: {e}")
            remaining.append(sig)
            continue

        if result in ("win", "loss", "expired"):
            if format_and_maybe_send_outcome(sig, result, pnl, send_fn):
                log_event(
                    f"Signal outcome posted: {result} {sig.get('symbol')} ({pnl:+.2f}%)"
                )
            closed.append({"signal": sig, "result": result, "pnl": pnl})
        elif result == "unresolved":
            # Keep trying next cycle
            remaining.append(sig)
        else:
            # still open
            remaining.append(sig)

    with _open_lock:
        _open_signals[:] = remaining
        _persist_open_signals()

    return closed
