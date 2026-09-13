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


def send_telegram(text, image_path=None, parse_mode=None, bypass_rate_limit: bool = False, chat_id=None):
    """Send a message (and optional image) to Telegram.

    chat_id defaults to TELEGRAM_CHAT_ID (Pro channel / signal destination).
    Pass chat_id for command replies so DMs don't leak into the public channel.
    """
    if (not bypass_rate_limit) and _rate_limited():
        log_event("⚠️ Telegram rate limit hit, message suppressed")
        return

    target = chat_id if chat_id is not None else config.TELEGRAM_CHAT_ID
    if not target:
        log_event("❌ TELEGRAM_CHAT_ID is not set — cannot send")
        return

    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': target, 'text': text}
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
                    data={'chat_id': target},
                    timeout=45,
                )
                r2.raise_for_status()
    except Exception as e:
        log_event(f"⚠️ Telegram error: {e}")


TELEGRAM_POLL_IDLE_SECONDS = 90

# Commands that change shared bot state — admin only when TELEGRAM_ADMIN_IDS is set.
ADMIN_COMMANDS = {
    "/on", "on", "/off", "off",
    "/timeframe", "timeframe", "/tf", "tf",
    "/night", "night",
    "/macro", "macro",
    "/config", "config",
    "/live", "live",
    "/close", "close",
    "/alerts", "alerts",
    "/positions", "positions",
    "/guards", "guards",
}


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
                from_user = message.get("from") or {}
                chat = message.get("chat") or {}

                callback = update.get("callback_query") or {}
                if not text and callback:
                    text = callback.get("data") or (callback.get("message") or {}).get("text")
                    from_user = callback.get("from") or from_user
                    chat = (callback.get("message") or {}).get("chat") or chat

                if text:
                    user_id = from_user.get("id")
                    reply_chat_id = chat.get("id")
                    log_event(f"Telegram message from {user_id}: {text}")
                    response, parse_mode = handle_telegram_command(text, user_id=user_id)
                    # Always reply in the chat where the command was sent (usually admin DM).
                    send_telegram(
                        response,
                        parse_mode=parse_mode,
                        bypass_rate_limit=True,
                        chat_id=reply_chat_id if reply_chat_id is not None else None,
                    )
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
            "",
            "<b>🛡️ Protection</b>",
            f"Max trades/day: {config.LIVE_TRADING_DAILY_MAX_TRADES}",
            f"Daily loss limit: {config.LIVE_TRADING_DAILY_LOSS_LIMIT_PCT}%",
            f"Min balance floor: {config.LIVE_TRADING_MIN_BALANCE_USDT} USDT",
            f"Max capital deployed: {config.LIVE_TRADING_MAX_CAPITAL_DEPLOYED_PCT}%",
            f"Post-loss cooldown: {config.LIVE_TRADING_COOLDOWN_AFTER_LOSS_SEC}s",
        ]
        if config.LIVE_TRADING_LAST_SET_AT_UTC:
            lines.append(
                f"\nLast toggle: <code>{config.LIVE_TRADING_LAST_SET_AT_UTC}</code> "
                f"by <code>{config.LIVE_TRADING_LAST_SET_BY or 'unknown'}</code>"
            )
        lines.append("")
        lines.append("<code>/live on</code> — enable live order execution")
        lines.append("<code>/live off</code> — disable live orders (signals only)")
        lines.append("<code>/guards</code> — real-time protection status")
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


def _cmd_alerts(args=None):
    """Toggle trade outcome alerts (Telegram notifications when TP/SL hit)."""
    args = args or []
    if not args:
        state = "ON ✅" if config.TRADE_OUTCOME_ALERTS_ENABLED else "OFF ❌"
        return (
            f"<b>🔔 Trade Outcome Alerts</b>\n"
            f"Status: <b>{state}</b>\n\n"
            f"When enabled, you'll receive a Telegram message\n"
            f"every time a trade hits its TP or SL.\n\n"
            f"<code>/alerts on</code> — enable notifications\n"
            f"<code>/alerts off</code> — disable notifications"
        )

    sub = (args[0] or "").strip().lower()
    if sub in ("on", "enable", "true", "1", "yes"):
        config.TRADE_OUTCOME_ALERTS_ENABLED = True
        return "🔔 Trade outcome alerts <b>ENABLED</b>. You'll be notified when trades hit TP or SL."
    if sub in ("off", "disable", "false", "0", "no"):
        config.TRADE_OUTCOME_ALERTS_ENABLED = False
        return "🔕 Trade outcome alerts <b>DISABLED</b>. Trades will close silently."
    return "Use <code>/alerts</code>, <code>/alerts on</code>, or <code>/alerts off</code>"


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
            f"Trades today: {summary.get('daily_trades', 0)}/{summary.get('daily_trade_limit', '?')}",
            f"Daily PnL: {summary.get('daily_pnl', 0):+.2f} USDT",
        ]
        for p in summary.get('positions', []):
            pnl = p.get('pnl') or 0
            icon = "🟢" if float(pnl) >= 0 else "🔴"
            lev = p.get('leverage') or '?'
            lines.append(
                f"  {icon} {p['symbol']} {p['side']} x{p['contracts']} ({lev}x) PnL: {float(pnl):+.2f}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error: {e}"


def _cmd_guards():
    """Show capital protection status."""
    try:
        from utils.liveTrading import get_protection_status
        status = get_protection_status()
        exchange_ok = "✅" if status['exchange_match'] else "❌ MISMATCH"
        cooldown_str = (
            f"🔴 Active ({status['cooldown_remaining_sec']}s left)"
            if status['cooldown_active'] else "✅ Clear"
        )
        lines = [
            "<b>🛡️ Capital Protection Status</b>",
            "",
            f"Exchange match: {exchange_ok} (signals: {config.EXCHANGE}, execution: {config.LIVE_TRADING_PLATFORM})",
            f"Daily trades: <b>{status['daily_trades']}</b>/{status['daily_limit']}",
            f"Daily PnL: {status['daily_pnl']:+.2f} USDT",
            f"Daily loss limit: {status['daily_loss_limit_pct']}% of starting balance",
            f"Starting balance: {status['starting_balance']:.2f}" if status['starting_balance'] else "Starting balance: <i>not yet recorded</i>",
            f"Min balance floor: {status['min_balance_usdt']} USDT",
            f"Max capital deployed: {status['max_capital_deployed_pct']}%",
            f"Post-loss cooldown: {cooldown_str}",
            "",
            "<b>Settings</b>",
            f"Risk/trade: {config.LIVE_TRADING_RISK_PCT}% of free balance",
            f"Leverage: {config.LIVE_TRADING_LEVERAGE}x",
            f"Max positions: {config.LIVE_TRADING_MAX_POSITIONS}",
            f"Max trades/day: {config.LIVE_TRADING_DAILY_MAX_TRADES}",
        ]
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
    if config.MACRO_PAUSE_ENABLED:
        from utils.macroCalendar import active_macro_pause, next_upcoming_event
        mq = "armed" if config.MACRO_PAUSE_ARMED else "disarmed"
        pause = active_macro_pause() if config.MACRO_PAUSE_ARMED else None
        if pause:
            left = max(1, int(pause["remaining_sec"] // 60))
            lines.append(
                f"Macro pause: <b>{mq}</b> — active on <b>{pause['name']}</b>, resume in ~{left}m"
            )
        else:
            nxt = next_upcoming_event()
            if nxt:
                when = nxt["scheduled_at"].strftime("%Y-%m-%d %H:%M UTC")
                lines.append(
                    f"Macro pause: <b>{mq}</b> — next: {nxt['name']} at <code>{when}</code>"
                )
            else:
                lines.append(f"Macro pause: <b>{mq}</b> — no upcoming high-impact US releases cached")
    admins = config.telegram_admin_id_set()
    if admins:
        lines.append(f"Admin lock: <b>ON</b> ({len(admins)} id(s)) — Pro channel mode")
    else:
        lines.append("Admin lock: <b>OFF</b> (solo — set TELEGRAM_ADMIN_IDS for Whop launch)")
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
    if config.MACRO_PAUSE_ENABLED:
        lines.append(
            f"Macro pause: armed={config.MACRO_PAUSE_ARMED}, "
            f"−{config.MACRO_PAUSE_BEFORE_MIN}m/+{config.MACRO_PAUSE_AFTER_MIN}m around US high-impact releases"
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


def _cmd_macro(args=None):
    args = args or []
    if not config.MACRO_PAUSE_ENABLED:
        return (
            "Macro pause is disabled in <code>config.py</code> "
            "(<code>MACRO_PAUSE_ENABLED=False</code>)."
        )

    from utils.macroCalendar import active_macro_pause, next_upcoming_event, get_macro_events

    if not args:
        armed = "ON" if config.MACRO_PAUSE_ARMED else "OFF"
        lines = [
            "<b>US macro pause</b>",
            f"Armed: <b>{armed}</b>",
            f"Window: <code>−{config.MACRO_PAUSE_BEFORE_MIN}m</code> before release → "
            f"<code>+{config.MACRO_PAUSE_AFTER_MIN}m</code> after",
            "Covers high-impact US releases (CPI, NFP, FOMC, GDP).",
        ]
        pause = active_macro_pause() if config.MACRO_PAUSE_ARMED else None
        if pause:
            left = max(1, int(pause["remaining_sec"] // 60))
            resume = pause["resume_at"].strftime("%Y-%m-%d %H:%M UTC")
            lines.append("")
            lines.append(f"<b>Paused now</b> for <b>{pause['name']}</b>")
            lines.append(f"Resume at <code>{resume}</code> (~{left}m left)")
        else:
            nxt = next_upcoming_event()
            if nxt:
                when = nxt["scheduled_at"].strftime("%Y-%m-%d %H:%M UTC")
                lines.append("")
                lines.append(f"Next: <b>{nxt['name']}</b> at <code>{when}</code>")
            else:
                # Force a refresh so status isn't empty after a cold start.
                get_macro_events(force_refresh=True)
                nxt = next_upcoming_event()
                if nxt:
                    when = nxt["scheduled_at"].strftime("%Y-%m-%d %H:%M UTC")
                    lines.append("")
                    lines.append(f"Next: <b>{nxt['name']}</b> at <code>{when}</code>")
                else:
                    lines.append("")
                    lines.append("No upcoming high-impact US releases found.")
        lines.append("")
        lines.append("<code>/macro on</code> — arm pause around US data releases")
        lines.append("<code>/macro off</code> — disarm (scan through data prints)")
        return "\n".join(lines)

    sub = (args[0] or "").strip().lower()
    if sub in ("on", "arm", "true", "1", "yes"):
        try:
            config.set_macro_pause_armed(True)
        except Exception as e:
            return f"Error: {e}"
        return (
            "Macro pause <b>armed</b>. Scanning will pause around high-impact US data releases "
            f"(−{config.MACRO_PAUSE_BEFORE_MIN}m / +{config.MACRO_PAUSE_AFTER_MIN}m)."
        )
    if sub in ("off", "disarm", "false", "0", "no"):
        try:
            config.set_macro_pause_armed(False)
        except Exception as e:
            return f"Error: {e}"
        return "Macro pause <b>disarmed</b>. Bot will scan through US data releases."
    return "Use <code>/macro</code>, <code>/macro on</code>, or <code>/macro off</code>"


HELP_TEXT = (
    "<b>📖 Admin commands</b>\n\n"
    "<b>Signals</b>\n"
    "/on — Start signal scanning\n"
    "/off — Pause signal scanning\n"
    "/status — Bot state + portfolio win rate & last backtest time\n"
    "/backtest — Full backtest: win rate, run time, per-pair results\n"
    "/pairs — Active pairs with win rates\n"
    "/signals — Today's signals with outcomes\n"
    "/timeframe — Get/set timeframe (ex: /timeframe 15m)\n"
    "/night — Overnight scan pause\n"
    "/macro — US data-release pause (CPI/NFP/FOMC)\n"
    "/config — Current configuration\n\n"
    "<b>Live Trading</b>\n"
    "/live — View/toggle live trading on Phemex\n"
    "/positions — Open positions & account balance\n"
    "/guards — Capital protection status & limits\n"
    "/close — Close a position (ex: /close ADA)\n"
    "/alerts — Toggle trade outcome notifications (TP/SL hit)\n\n"
    "/help — This message\n\n"
    "<i>Signals are broadcast to the Pro channel (TELEGRAM_CHAT_ID). "
    "Subscribers join via invite — they do not control settings.</i>\n\n"
    f"{LEGAL_DISCLAIMER}"
)

MEMBER_HELP_TEXT = (
    "<b>Fathom Pro</b>\n\n"
    "Trade setups are posted in the <b>private Pro channel</b> you joined via invite.\n"
    "Bot settings (timeframe, scanning, pauses) are controlled by the operator only — "
    "this keeps the feed consistent for everyone.\n\n"
    "Read-only commands you can use in DM:\n"
    "/status — scanning state & last backtest summary\n"
    "/pairs — active pairs\n"
    "/backtest — last backtest digest\n"
    "/signals — today's signal outcomes\n"
    "/help — this message\n\n"
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
    "/guards": _cmd_guards,
    "guards": _cmd_guards,
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
    "/macro", "macro",
    "/live", "live", "/positions", "positions", "/close", "close",
    "/guards", "guards", "/alerts", "alerts",
}

_PUBLIC_READ_COMMANDS = {
    "/help", "help",
    "/status", "status",
    "/pairs", "pairs",
    "/backtest", "backtest",
    "/signals", "signals",
}


def _admin_denied_message():
    return (
        "🔒 That command is <b>admin-only</b>.\n"
        "Fathom uses one shared feed for all Pro members — "
        "settings like timeframe are not per-user.\n\n"
        f"{MEMBER_HELP_TEXT}"
    )


def handle_telegram_command(text, user_id=None):
    """Return (response_text, parse_mode) tuple.

    When TELEGRAM_ADMIN_IDS is set, only those users may run admin commands.
    """
    raw = (text or "").strip()
    parts = raw.split()
    cmd = parts[0].lower() if parts else ""
    args = parts[1:] if len(parts) > 1 else []
    log_event(f"Telegram command received: {raw} (user={user_id})")

    is_admin = config.is_telegram_admin(user_id)

    if cmd in {"/help", "help"}:
        return (HELP_TEXT if is_admin else MEMBER_HELP_TEXT), "HTML"

    if cmd in ADMIN_COMMANDS and not is_admin:
        return _admin_denied_message(), "HTML"

    if cmd in {"/timeframe", "timeframe", "/tf", "tf"}:
        return _cmd_timeframe(args), "HTML"

    if cmd in {"/night", "night"}:
        return _cmd_night(args), "HTML"

    if cmd in {"/macro", "macro"}:
        return _cmd_macro(args), "HTML"

    if cmd in {"/live", "live"}:
        return _cmd_live(args), "HTML"

    if cmd in {"/close", "close"}:
        return _cmd_close(args), "HTML"

    if cmd in {"/alerts", "alerts"}:
        return _cmd_alerts(args), "HTML"

    handler = COMMAND_MAP.get(cmd)
    if handler:
        response = handler()
        parse_mode = 'HTML' if cmd in HTML_COMMANDS else None
        return response, parse_mode

    # Unknown command: members get member help; admins get full help
    return (HELP_TEXT if is_admin else MEMBER_HELP_TEXT), "HTML"

