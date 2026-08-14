import config
import json
import os
import time
import requests
from datetime import datetime, timezone
from typing import List

from utils.utils import log_event

BACKTEST_STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_backtest.json')

last_update_id = 0

_send_timestamps: List[float] = []
TELEGRAM_RATE_LIMIT = 20
TELEGRAM_RATE_WINDOW_SEC = 60


def _rate_limited():
    """Return True if we've exceeded TELEGRAM_RATE_LIMIT sends in the last window."""
    now = time.time()
    cutoff = now - TELEGRAM_RATE_WINDOW_SEC
    _send_timestamps[:] = [t for t in _send_timestamps if t > cutoff]
    if len(_send_timestamps) >= TELEGRAM_RATE_LIMIT:
        return True
    _send_timestamps.append(now)
    return False


def get_updates():
    global last_update_id

    if not config.TELEGRAM_TOKEN:
        log_event("❌ TELEGRAM_TOKEN is not set")
        return []

    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates?timeout=30&offset={last_update_id + 1}"
    try:
        response = requests.get(url, timeout=35)
        response.raise_for_status()

        data = response.json()

        if "ok" not in data or not data["ok"]:
            log_event(f"❌ Telegram API returned not OK: {data}")
            return []

        return data.get("result", [])

    except requests.exceptions.RequestException as e:
        log_event(f"❌ Requests exception: {e}")
        return []
    except ValueError as e:
        log_event(f"❌ Failed to parse JSON response: {e}")
        return []


def send_telegram(text, image_path=None, parse_mode=None, bypass_rate_limit: bool = False):
    """Send a message (and optional image) to Telegram."""
    if (not bypass_rate_limit) and _rate_limited():
        log_event("⚠️ Telegram rate limit hit, message suppressed")
        return

    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': config.TELEGRAM_CHAT_ID, 'text': text}
        if parse_mode:
            payload['parse_mode'] = parse_mode
        r = requests.post(url, data=payload, timeout=20)
        r.raise_for_status()

        if image_path:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendPhoto"
            with open(image_path, 'rb') as img:
                r2 = requests.post(
                    url,
                    files={'photo': img},
                    data={'chat_id': config.TELEGRAM_CHAT_ID},
                    timeout=45,
                )
                r2.raise_for_status()
    except Exception as e:
        log_event(f"⚠️ Telegram error: {e}")


TELEGRAM_POLL_IDLE_SECONDS = 90


def poll_telegram():
    global last_update_id
    while True:
        updates = get_updates()
        if not updates:
            time.sleep(TELEGRAM_POLL_IDLE_SECONDS)
            continue

        for update in updates:
            try:
                last_update_id = update.get("update_id", last_update_id)

                message = update.get("message") or update.get("edited_message") or {}
                text = message.get("text")

                callback = update.get("callback_query") or {}
                if not text and callback:
                    text = callback.get("data") or (callback.get("message") or {}).get("text")

                if text:
                    log_event(f"Telegram message: {text}")
                    response, parse_mode = handle_telegram_command(text)
                    send_telegram(response, parse_mode=parse_mode, bypass_rate_limit=True)
                else:
                    log_event(f"Telegram update had no text. Keys={list(update.keys())}")
            except Exception as e:
                log_event(f"⚠️ Telegram poll loop error: {e}")

            time.sleep(0.2)


LEGAL_DISCLAIMER = (
    "<i>Not financial advice. Signals are educational / informational only. "
    "Crypto trading involves substantial risk of loss. You use these signals "
    "entirely at your own risk — we place no orders and accept no liability "
    "for decisions or losses.</i>"
)


def _cmd_on():
    if config.TRADING_ENABLED:
        return (
            f"ℹ️ Signal scanning already ON\n"
            f"Instance: <code>{config.BOT_INSTANCE_ID}</code>\n\n"
            f"{LEGAL_DISCLAIMER}"
        )
    config.set_trading_enabled(True, by="telegram:/on")
    return (
        f"✅ Signal scanning ON — alerts will be sent (no live orders)\n"
        f"Instance: <code>{config.BOT_INSTANCE_ID}</code>\n\n"
        f"{LEGAL_DISCLAIMER}"
    )


def _cmd_off():
    if not config.TRADING_ENABLED:
        return f"ℹ️ Signal scanning already OFF\nInstance: <code>{config.BOT_INSTANCE_ID}</code>"
    config.set_trading_enabled(False, by="telegram:/off")
    return f"⛔ Signal scanning OFF — no new alerts\nInstance: <code>{config.BOT_INSTANCE_ID}</code>"


def _cmd_live(args=None):
    """Admin command: toggle live trading on Phemex."""
    args = args or []
    if not args:
        state = "ON" if config.LIVE_TRADING_ENABLED else "OFF"
        lines = [
            f"<b>⚡ Live Trading</b>",
            f"Status: <b>{state}</b>",
            f"Platform: {config.LIVE_TRADING_PLATFORM}",
            f"Leverage: {config.LIVE_TRADING_LEVERAGE}x",
            f"Risk/trade: {config.LIVE_TRADING_RISK_PCT}%",
            f"Max positions: {config.LIVE_TRADING_MAX_POSITIONS}",
            f"API key: {'configured' if config.PHEMEX_API_KEY else '<b>NOT SET</b>'}",
        ]
        if config.LIVE_TRADING_LAST_SET_AT_UTC:
            lines.append(
                f"Last toggle: <code>{config.LIVE_TRADING_LAST_SET_AT_UTC}</code> "
                f"by <code>{config.LIVE_TRADING_LAST_SET_BY or 'unknown'}</code>"
            )
        lines.append("")
        lines.append("<code>/live on</code> — enable live order execution")
        lines.append("<code>/live off</code> — disable live orders (signals only)")
        return "\n".join(lines)

    sub = (args[0] or "").strip().lower()
    if sub in ("on", "enable", "true", "1", "yes"):
        try:
            config.set_live_trading_enabled(True, by="telegram:/live on")
        except ValueError as e:
            return f"❌ {e}"
        return (
            f"⚡ <b>Live trading ENABLED</b> on {config.LIVE_TRADING_PLATFORM}\n"
            f"Leverage: {config.LIVE_TRADING_LEVERAGE}x | Risk: {config.LIVE_TRADING_RISK_PCT}%\n"
            f"Max positions: {config.LIVE_TRADING_MAX_POSITIONS}\n\n"
            f"⚠️ Real orders will be placed. Use /live off to disable."
        )
    if sub in ("off", "disable", "false", "0", "no"):
        config.set_live_trading_enabled(False, by="telegram:/live off")
        return "⛔ Live trading <b>DISABLED</b>. Signals-only mode."
    return "Use <code>/live</code>, <code>/live on</code>, or <code>/live off</code>"


def _cmd_positions():
    """Show open Phemex positions."""
    if not config.LIVE_TRADING_ENABLED:
        return "ℹ️ Live trading is disabled. Use <code>/live on</code> first."
    if not config.PHEMEX_API_KEY:
        return "❌ Phemex API keys not configured."
    try:
        from utils.liveTrading import get_account_summary
        summary = get_account_summary()
        if 'error' in summary:
            return f"❌ {summary['error']}"
        lines = [
            "<b>📊 Phemex Account</b>",
            f"Balance: <b>{summary['balance_total']:.2f}</b> USDT",
            f"Available: {summary['balance_free']:.2f} USDT",
            f"In use: {summary['balance_used']:.2f} USDT",
            f"Open positions: <b>{summary['open_positions']}</b>/{config.LIVE_TRADING_MAX_POSITIONS}",
        ]
        for p in summary.get('positions', []):
            pnl = p.get('pnl') or 0
            icon = "🟢" if float(pnl) >= 0 else "🔴"
            lines.append(
                f"  {icon} {p['symbol']} {p['side']} x{p['contracts']} (PnL: {float(pnl):+.2f})"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error: {e}"


def _cmd_close(args=None):
    """Close a specific position or all positions."""
    args = args or []
    if not config.LIVE_TRADING_ENABLED:
        return "ℹ️ Live trading is disabled."
    if not args:
        return "Usage: <code>/close SYMBOL</code> (e.g. /close ADA/USDT:USDT)"
    symbol = args[0].strip().upper()
    if '/' not in symbol:
        symbol = f"{symbol}/USDT:USDT"
    try:
        from utils.liveTrading import close_position
        result = close_position(symbol, reason="telegram:/close")
        if result.get('success'):
            return f"✅ Position closed: {symbol} (order: {result.get('order_id')})"
        return f"❌ {result.get('error', 'Unknown error')}"
    except Exception as e:
        return f"❌ Error closing position: {e}"


def _load_backtest_state():
    """Return last_backtest.json dict, or None if missing/unreadable."""
    if not os.path.isfile(BACKTEST_STATE_FILE):
        return None
    try:
        with open(BACKTEST_STATE_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _fmt_backtest_run_at(run_at) -> str:
    """Make ISO timestamps readable for Telegram (keep original if parse fails)."""
    if not run_at or run_at == "?":
        return "unknown"
    raw = str(run_at).strip()
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return raw


def _backtest_confidence_lines(data) -> list:
    """Short trust summary: portfolio win rate + when last run."""
    if not data:
        return ["Backtest: <i>no results yet — waiting for weekly auto-backtest or run simulate_trades.py</i>"]
    run_at = _fmt_backtest_run_at(data.get("run_at"))
    portfolio_wr = data.get("portfolio_win_rate")
    pairs = data.get("pairs") or []
    results = data.get("results") or {}
    threshold = data.get("win_rate_threshold", "?")
    lines = []
    if portfolio_wr is not None:
        lines.append(f"Portfolio win rate: <b>{portfolio_wr}%</b>")
    else:
        lines.append("Portfolio win rate: <i>n/a</i>")
    lines.append(f"Last backtest: <code>{run_at}</code>")
    lines.append(f"Pairs qualifying (≥{threshold}%): <b>{len(pairs)}</b>/{len(results)}")
    return lines


def _cmd_status():
    state = "ON" if config.TRADING_ENABLED else "OFF"
    live_state = "ON" if config.LIVE_TRADING_ENABLED else "OFF"
    lines = [
        f"<b>Bot Status</b>",
        f"Instance: <code>{config.BOT_INSTANCE_ID}</code>",
        f"Started: <code>{config.BOT_STARTED_AT_UTC}</code>",
        f"Scanning: <b>{state}</b>",
        f"Live trading: <b>{live_state}</b> ({config.LIVE_TRADING_PLATFORM})",
        f"Mode: {'LIVE TRADING' if config.LIVE_TRADING_ENABLED else 'SIGNALS ONLY'}",
        f"Exchange (market data): {config.EXCHANGE}",
        f"Timeframe: <code>{config.TIMEFRAME}</code>",
        f"Multi-TF: {'ON (' + ','.join(config.MULTI_TF_EXTRA) + ')' if config.MULTI_TF_ENABLED else 'OFF'}",
        f"Alerts/cycle: {config.MAX_SIGNALS_PER_CYCLE} | Cooldown: {config.SIGNAL_COOLDOWN_SEC}s",
        "",
        "<b>📊 Edge (last backtest)</b>",
    ]
    lines.extend(_backtest_confidence_lines(_load_backtest_state()))
    if config.TRADING_ENABLED_LAST_SET_AT_UTC:
        lines.append(
            f"Last toggle: <code>{config.TRADING_ENABLED_LAST_SET_AT_UTC}</code> by "
            f"<code>{config.TRADING_ENABLED_LAST_SET_BY or 'unknown'}</code>"
        )
    if config.NIGHT_QUIET_ENABLED:
        nq = "armed" if config.NIGHT_QUIET_ARMED else "disarmed"
        inside = "yes" if config.in_night_quiet_window() else "no"
        lines.append(
            f"Night pause: <b>{nq}</b> ({config.NIGHT_QUIET_START_HOUR}:00–{config.NIGHT_QUIET_END_HOUR}:00 "
            f"{config.NIGHT_QUIET_TZ}, in window now: {inside})"
        )
    lines.append("\n<i>/backtest for full pair breakdown. Toggle: /on /off. Live: /live</i>")
    return "\n".join(lines)


def _cmd_pairs():
    data = _load_backtest_state()
    if not data:
        return "📭 No backtest data available yet."
    pairs = data.get("pairs", [])
    results = data.get("results", {})
    if not pairs:
        return "📭 No pairs selected by last backtest."
    lines = [
        "<b>📋 Active Pairs</b> (from last backtest)",
        f"Last run: <code>{_fmt_backtest_run_at(data.get('run_at'))}</code>",
    ]
    portfolio_wr = data.get("portfolio_win_rate")
    if portfolio_wr is not None:
        lines.append(f"Portfolio win rate: <b>{portfolio_wr}%</b>")
    lines.append("")
    for sym in pairs:
        wr = results.get(sym, {}).get("win_rate", "?")
        trades = results.get(sym, {}).get("total_trades", "?")
        lines.append(f"  • {sym}: <b>{wr}%</b> win rate ({trades} trades)")
    return "\n".join(lines)


def _cmd_backtest():
    data = _load_backtest_state()
    if not data:
        return (
            "📭 No backtest results available.\n"
            "Run <code>python strategies/simulate_trades.py</code> to generate them."
        )
    pairs = data.get("pairs", [])
    results = data.get("results", {})
    threshold = data.get("win_rate_threshold", "?")

    lines = ["<b>📊 Last Backtest</b>"]
    lines.extend(_backtest_confidence_lines(data))
    lines.append(f"Qualify threshold: {threshold}%")
    lines.append("")
    lines.append("<b>Per-pair results</b>")

    def _wr(sym):
        r = results.get(sym) or {}
        try:
            return float(r.get("win_rate") or 0)
        except (TypeError, ValueError):
            return 0.0

    for sym in sorted(results.keys(), key=_wr, reverse=True):
        r = results.get(sym)
        if not isinstance(r, dict):
            continue
        mark = "✅" if sym in pairs else "❌"
        lines.append(
            f"  {mark} {sym}: <b>{r.get('win_rate', '?')}%</b> "
            f"({r.get('total_trades', '?')} trades)"
        )
    return "\n".join(lines)


def _cmd_signals():
    from utils.signalTracker import get_daily_signals, build_eod_summary
    signals = get_daily_signals()
    if not signals:
        return "📭 No signals sent today."
    try:
        from utils.exchangeUtils import get_exchange
        summary = build_eod_summary(get_exchange())
        return summary if summary else "📭 No signals sent today."
    except Exception as e:
        return f"❌ Failed to build signal summary: {e}"


def _cmd_config():
    lines = [
        f"<b>Configuration</b>",
        f"Exchange (market data): {config.EXCHANGE}",
        f"Timeframe: <code>{config.TIMEFRAME}</code>",
        f"Multi-TF: {'ON (' + ','.join(config.MULTI_TF_EXTRA) + ')' if config.MULTI_TF_ENABLED else 'OFF'}",
        f"Mode: {'LIVE TRADING' if config.LIVE_TRADING_ENABLED else 'signals only'}",
        f"Max alerts/cycle: {config.MAX_SIGNALS_PER_CYCLE}",
        f"Signal cooldown: {config.SIGNAL_COOLDOWN_SEC}s",
        f"Limit-idea fallback: {config.ENABLE_LIMIT_IDEA_FALLBACK}",
        f"Min ADX: {config.MIN_ADX_TREND}",
        f"RSI bounds: {config.RSI_OVERSOLD}/{config.RSI_OVERBOUGHT}",
        "",
        f"<b>Live Trading</b>",
        f"Platform: {config.LIVE_TRADING_PLATFORM}",
        f"Enabled: {config.LIVE_TRADING_ENABLED}",
        f"Leverage: {config.LIVE_TRADING_LEVERAGE}x",
        f"Risk/trade: {config.LIVE_TRADING_RISK_PCT}%",
        f"Max positions: {config.LIVE_TRADING_MAX_POSITIONS}",
        f"API key: {'configured' if config.PHEMEX_API_KEY else 'NOT SET'}",
    ]
    if config.NIGHT_QUIET_ENABLED:
        lines.append(
            f"Night quiet: {config.NIGHT_QUIET_START_HOUR}:00–{config.NIGHT_QUIET_END_HOUR}:00 {config.NIGHT_QUIET_TZ}, "
            f"armed={config.NIGHT_QUIET_ARMED}, sleep={config.NIGHT_QUIET_SLEEP_SEC}s"
        )
    return "\n".join(lines)


_ALLOWED_TIMEFRAMES = (
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h",
    "1d",
)


def _cmd_timeframe(args=None):
    args = args or []
    if not args:
        allowed = ", ".join(f"<code>{t}</code>" for t in _ALLOWED_TIMEFRAMES)
        return (
            f"<b>🕒 Timeframe</b>\n"
            f"Current: <code>{config.TIMEFRAME}</code>\n"
            f"Set with: <code>/timeframe 15m</code> (or <code>/tf 15m</code>)\n"
            f"Allowed: {allowed}"
        )

    tf = (args[0] or "").strip().lower()
    if tf not in _ALLOWED_TIMEFRAMES:
        allowed = ", ".join(_ALLOWED_TIMEFRAMES)
        return f"❌ Invalid timeframe <code>{tf}</code>. Allowed: {allowed}"

    try:
        config.set_timeframe(tf)
    except Exception as e:
        return f"❌ Failed to set timeframe: {e}"

    return f"✅ Timeframe set to <code>{config.TIMEFRAME}</code>"


def _cmd_night(args=None):
    args = args or []
    if not config.NIGHT_QUIET_ENABLED:
        return (
            "Overnight pause is disabled in <code>config.py</code> "
            "(<code>NIGHT_QUIET_ENABLED=False</code>)."
        )
    window = f"{config.NIGHT_QUIET_START_HOUR}:00–{config.NIGHT_QUIET_END_HOUR}:00 {config.NIGHT_QUIET_TZ}"
    if not args:
        armed = "ON" if config.NIGHT_QUIET_ARMED else "OFF"
        now_in = "inside" if config.in_night_quiet_window() else "outside"
        return (
            f"<b>Overnight pause</b>\n"
            f"Window: <code>{window}</code>\n"
            f"Armed: <b>{armed}</b> (when scanning ON + armed + in window, pair scan is skipped)\n"
            f"Now: <b>{now_in}</b> quiet window\n\n"
            f"<code>/night on</code> — arm (fewer API calls overnight)\n"
            f"<code>/night off</code> — disarm (scan 24/7 while scanning is ON)"
        )
    sub = (args[0] or "").strip().lower()
    if sub in ("on", "arm", "true", "1", "yes"):
        try:
            config.set_night_quiet_armed(True)
        except Exception as e:
            return f"Error: {e}"
        return "Overnight pause <b>armed</b>. Scanning pauses during the configured night window."
    if sub in ("off", "disarm", "false", "0", "no"):
        try:
            config.set_night_quiet_armed(False)
        except Exception as e:
            return f"Error: {e}"
        return "Overnight pause <b>disarmed</b>. No night skip while scanning is ON."
    return "Use <code>/night</code>, <code>/night on</code>, or <code>/night off</code>"


HELP_TEXT = (
    "<b>📖 Available Commands</b>\n\n"
    "<b>Signals</b>\n"
    "/on — Start signal scanning\n"
    "/off — Pause signal scanning\n"
    "/status — Bot state + portfolio win rate & last backtest time\n"
    "/backtest — Full backtest: win rate, run time, per-pair results\n"
    "/pairs — Active pairs with win rates\n"
    "/signals — Today's signals with outcomes\n"
    "/timeframe — Get/set timeframe (ex: /timeframe 15m)\n"
    "/night — Overnight scan pause\n"
    "/config — Current configuration\n\n"
    "<b>Live Trading (Admin)</b>\n"
    "/live — View/toggle live trading on Phemex\n"
    "/positions — Open positions & account balance\n"
    "/close — Close a position (ex: /close ADA)\n\n"
    "/help — This message\n\n"
    f"{LEGAL_DISCLAIMER}"
)

COMMAND_MAP = {
    "/on": _cmd_on,
    "on": _cmd_on,
    "/off": _cmd_off,
    "off": _cmd_off,
    "/status": _cmd_status,
    "status": _cmd_status,
    "/pairs": _cmd_pairs,
    "pairs": _cmd_pairs,
    "/signals": _cmd_signals,
    "signals": _cmd_signals,
    "/backtest": _cmd_backtest,
    "backtest": _cmd_backtest,
    "/config": _cmd_config,
    "config": _cmd_config,
    "/positions": _cmd_positions,
    "positions": _cmd_positions,
    "/help": lambda: HELP_TEXT,
    "help": lambda: HELP_TEXT,
}

HTML_COMMANDS = {
    "/on", "on", "/off", "off",
    "/status", "status",
    "/pairs", "pairs", "/signals", "signals", "/backtest", "backtest",
    "/timeframe", "timeframe", "/tf", "tf",
    "/config", "config", "/help", "help",
    "/night", "night",
    "/live", "live", "/positions", "positions", "/close", "close",
}


def handle_telegram_command(text):
    """Return (response_text, parse_mode) tuple."""
    raw = (text or "").strip()
    parts = raw.split()
    cmd = parts[0].lower() if parts else ""
    args = parts[1:] if len(parts) > 1 else []
    log_event(f"Telegram command received: {raw}")

    if cmd in {"/timeframe", "timeframe", "/tf", "tf"}:
        return _cmd_timeframe(args), "HTML"

    if cmd in {"/night", "night"}:
        return _cmd_night(args), "HTML"

    if cmd in {"/live", "live"}:
        return _cmd_live(args), "HTML"

    if cmd in {"/close", "close"}:
        return _cmd_close(args), "HTML"

    handler = COMMAND_MAP.get(cmd)
    if handler:
        response = handler()
        parse_mode = 'HTML' if cmd in HTML_COMMANDS else None
        return response, parse_mode

    return HELP_TEXT, 'HTML'
