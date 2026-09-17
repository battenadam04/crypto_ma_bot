"""Pro channel signal message formatting (member-facing, no operator noise)."""

from __future__ import annotations

import config


def fmt_price(value) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if value < 0.01:
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if value < 1:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if value < 100:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{value:.2f}"


def display_symbol(symbol: str) -> str:
    """XRP/USDT:USDT → XRP/USDT for cleaner channel copy."""
    s = str(symbol or "").strip()
    if ":" in s:
        s = s.split(":", 1)[0]
    return s


def strategy_label(strategy_type: str, signal_source: str = "SIG") -> str:
    labels = {
        "trend": "Trend",
        "range": "Range",
        "breakout": "Breakout",
    }
    base = labels.get(str(strategy_type or "").lower(), str(strategy_type or "Setup").title())
    if str(signal_source or "").upper() == "LIM":
        return f"{base} · limit idea"
    return base


def pct_move(entry, target) -> str | None:
    try:
        entry_f = float(entry)
        target_f = float(target)
    except (TypeError, ValueError):
        return None
    if entry_f == 0:
        return None
    pct = ((target_f - entry_f) / entry_f) * 100.0
    return f"{pct:+.2f}%"


def reward_risk(entry, tp, sl) -> str | None:
    try:
        entry_f = float(entry)
        tp_f = float(tp)
        sl_f = float(sl)
    except (TypeError, ValueError):
        return None
    risk = abs(entry_f - sl_f)
    reward = abs(tp_f - entry_f)
    if risk <= 0:
        return None
    return f"{reward / risk:.2f}"


def format_signal_message(
    symbol,
    direction,
    timeframe,
    strategy_type,
    entry,
    tp,
    sl,
    signal_source="SIG",
    limit_hint: str = "",
    status: str = "success",
    error: str = "",
) -> str:
    """Member-facing Pro channel signal — compact, scannable, no operator noise."""
    is_long = direction == "long"
    side = "LONG" if is_long else "SHORT"
    emoji = "📈" if is_long else "📉"
    pair = display_symbol(symbol)
    setup = strategy_label(strategy_type, signal_source)
    htf = config.HTF_TIMEFRAME
    bias = "up" if is_long else "down"

    tp_pct = pct_move(entry, tp)
    sl_pct = pct_move(entry, sl)
    rr = reward_risk(entry, tp, sl)

    lines = [
        f"{emoji} <b>{side}</b> · <b>{pair}</b> · {timeframe}",
        f"{setup} · {htf} {bias}",
        "",
        f"<b>Entry</b>  {fmt_price(entry)}",
        f"<b>TP</b>     {fmt_price(tp)}" + (f"  <i>({tp_pct})</i>" if tp_pct else ""),
        f"<b>SL</b>     {fmt_price(sl)}" + (f"  <i>({sl_pct})</i>" if sl_pct else ""),
    ]
    if rr:
        lines.append(f"<b>R:R</b>    {rr}")
    if limit_hint:
        lines.append("")
        lines.append(limit_hint)
    if status != "success" and error:
        lines.append("")
        lines.append(f"<i>Levels note: {error}</i>")
    return "\n".join(lines)


def format_limit_hint(limit_price, dist_pct: float, direction: str) -> str:
    side = "below" if direction == "long" else "above"
    return f"<b>Limit</b>  {fmt_price(limit_price)}  <i>(~{abs(dist_pct):.2f}% {side})</i>"
