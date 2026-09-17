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


def display_timeframe(tf: str) -> str:
    """15m → 15-min chart (beginner-friendly)."""
    raw = str(tf or "").strip().lower()
    mapping = {
        "1m": "1-min chart",
        "3m": "3-min chart",
        "5m": "5-min chart",
        "15m": "15-min chart",
        "30m": "30-min chart",
        "1h": "1-hour chart",
        "4h": "4-hour chart",
        "1d": "daily chart",
    }
    return mapping.get(raw, f"{tf} chart" if tf else "chart")


def strategy_label(strategy_type: str, signal_source: str = "SIG") -> str:
    labels = {
        "trend": "Trend setup",
        "range": "Range setup",
        "breakout": "Breakout setup",
    }
    base = labels.get(str(strategy_type or "").lower(), "Setup")
    if str(signal_source or "").upper() == "LIM":
        return f"{base} (limit-style)"
    return base


def htf_bias_line(direction: str) -> str:
    """Explain higher-timeframe confirmation in plain English."""
    htf = str(getattr(config, "HTF_TIMEFRAME", "1h") or "1h").strip().lower()
    htf_name = {
        "15m": "15-minute",
        "30m": "30-minute",
        "1h": "1-hour",
        "4h": "4-hour",
        "1d": "daily",
    }.get(htf, htf)
    if direction == "long":
        return f"Confirmed by the {htf_name} uptrend"
    return f"Confirmed by the {htf_name} downtrend"


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
    """Member-facing Pro channel signal — clear for beginners, still scannable."""
    is_long = direction == "long"
    side = "LONG" if is_long else "SHORT"
    emoji = "📈" if is_long else "📉"
    pair = display_symbol(symbol)
    setup = strategy_label(strategy_type, signal_source)

    tp_pct = pct_move(entry, tp)
    sl_pct = pct_move(entry, sl)
    rr = reward_risk(entry, tp, sl)

    lines = [
        f"{emoji} <b>{side}</b> · <b>{pair}</b> · {display_timeframe(timeframe)}",
        f"{setup} · {htf_bias_line(direction)}",
        "",
        f"<b>Entry</b>        {fmt_price(entry)}",
        f"<b>Take-profit</b>  {fmt_price(tp)}" + (f"  <i>({tp_pct})</i>" if tp_pct else ""),
        f"<b>Stop-loss</b>    {fmt_price(sl)}" + (f"  <i>({sl_pct})</i>" if sl_pct else ""),
    ]
    if rr:
        lines.append(f"<b>Reward/risk</b>  {rr}×")
    if limit_hint:
        lines.append("")
        lines.append(limit_hint)
    if status != "success" and error:
        lines.append("")
        lines.append(f"<i>Levels note: {error}</i>")
    return "\n".join(lines)


def format_limit_hint(limit_price, dist_pct: float, direction: str) -> str:
    """Optional passive entry — explained for beginners."""
    if direction == "long":
        return (
            f"<b>Optional limit entry</b>  {fmt_price(limit_price)}  "
            f"<i>(~{abs(dist_pct):.2f}% below)</i>\n"
            f"<i>Wait for this price if you prefer not to buy at market right now.</i>"
        )
    return (
        f"<b>Optional limit entry</b>  {fmt_price(limit_price)}  "
        f"<i>(~{abs(dist_pct):.2f}% above)</i>\n"
        f"<i>Wait for this price if you prefer not to sell at market right now.</i>"
    )
