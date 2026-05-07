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
    """Send a message (and optional image) to Telegram.

    Args:
        parse_mode: 'HTML', 'Markdown', or None for plain text.
    """
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

        # Process every update we received. Taking only the last one can silently drop commands.
        for update in updates:
            try:
                last_update_id = update.get("update_id", last_update_id)

                # Telegram can deliver different shapes: message, edited_message, callback_query, etc.
                message = update.get("message") or update.get("edited_message") or {}
                text = message.get("text")

                callback = update.get("callback_query") or {}
                if not text and callback:
                    text = callback.get("data") or (callback.get("message") or {}).get("text")

                if text:
                    log_event(f"Telegram message: {text}")
                    response, parse_mode = handle_telegram_command(text)
                    # Never suppress command responses; otherwise /signals looks "stuck".
                    send_telegram(response, parse_mode=parse_mode, bypass_rate_limit=True)
                else:
                    # Log the keys so we can see what Telegram is sending (no sensitive payload).
                    log_event(f"Telegram update had no text. Keys={list(update.keys())}")
            except Exception as e:
                log_event(f"⚠️ Telegram poll loop error: {e}")

            time.sleep(0.2)


def _cmd_on():
    if config.TRADING_ENABLED:
        mode = "signals only" if config.TRADING_SIGNALS_ONLY else "live trading"
        return f"ℹ️ Bot already ON ({mode})\nInstance: <code>{config.BOT_INSTANCE_ID}</code>"
    config.set_trading_enabled(True, by="telegram:/on")
    if config.TRADING_SIGNALS_ONLY:
        return f"✅ Bot ON — signals only mode (no live orders)\nInstance: <code>{config.BOT_INSTANCE_ID}</code>"
    return f"✅ Bot ON — live trading mode\nInstance: <code>{config.BOT_INSTANCE_ID}</code>"


def _cmd_off():
    if not config.TRADING_ENABLED:
        return f"ℹ️ Bot already OFF\nInstance: <code>{config.BOT_INSTANCE_ID}</code>"
    config.set_trading_enabled(False, by="telegram:/off")
    return f"⛔ Bot OFF — no signals or trades will be processed\nInstance: <code>{config.BOT_INSTANCE_ID}</code>"


def _cmd_status():
    if config.TRADING_SIGNALS_ONLY:
        mode = "SIGNALS ONLY (no live orders)"
    else:
        mode = "LIVE TRADING (real orders)"
    state = "ON" if config.TRADING_ENABLED else "OFF"
    exchange_name = os.getenv("EXCHANGE", "phemex")
    lines = [
        f"<b>Bot Status</b>",
        f"Instance: <code>{config.BOT_INSTANCE_ID}</code>",
        f"Started: <code>{config.BOT_STARTED_AT_UTC}</code>",
        f"State: <b>{state}</b>",
        f"Mode: {mode}",
        f"Exchange: {exchange_name}",
    ]
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
    lines.append(
        "\n<i>Toggle with /on /off. Overnight: /night. Live orders need TRADING_SIGNALS_ONLY=false.</i>"
    )
    return "\n".join(lines)


def _cmd_balance():
    from utils.exchangeUtils import get_exchange, EXCHANGE_NAME
    try:
        ex = get_exchange()
        ts = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
        if EXCHANGE_NAME == "binance_margin":
            spot = ex.fetch_balance({'type': 'spot'})
            margin = ex.fetch_balance({'type': 'margin'})
            spot_total = spot['total'].get('USDT', 0)
            spot_free = spot['free'].get('USDT', 0)
            margin_total = margin['total'].get('USDT', 0)
            margin_free = margin['free'].get('USDT', 0)
            combined = spot_total + margin_total
            return (
                f"<b>💰 Balance</b> ({ts})\n"
                f"Spot:     <code>{spot_total:.2f}</code> (avail: <code>{spot_free:.2f}</code>)\n"
                f"Margin: <code>{margin_total:.2f}</code> (avail: <code>{margin_free:.2f}</code>)\n"
                f"Combined: <code>{combined:.2f}</code> USDT"
            )
        else:
            balance = ex.fetch_balance()
            return (
                f"<b>💰 Balance</b> ({ts})\n"
                f"Total: <code>{balance['total'].get('USDT', 0):.2f}</code> USDT\n"
                f"Available: <code>{balance['free'].get('USDT', 0):.2f}</code> USDT"
            )
    except Exception as e:
        return f"❌ Failed to fetch balance: {e}"


def _cmd_positions():
    from utils.exchangeUtils import get_exchange
    try:
        positions = get_exchange().fetch_positions()
        open_pos = [p for p in positions if float(p.get('contracts', 0)) > 0]
        if not open_pos:
            return "📭 No open positions."
        lines = ["<b>📋 Open Positions</b>"]
        for p in open_pos:
            sym = p.get('symbol', '?')
            side = p.get('side', '?')
            size = p.get('contracts', 0)
            pnl = p.get('unrealizedPnl', 0)
            entry = p.get('entryPrice', 0)
            lines.append(
                f"\n<b>{sym}</b> ({side})\n"
                f"  Size: {size} | Entry: {entry}\n"
                f"  uPnL: <code>{float(pnl):.2f}</code> USDT"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to fetch positions: {e}"


def _cmd_pairs():
    try:
        if not os.path.isfile(BACKTEST_STATE_FILE):
            return "📭 No backtest data available yet."
        with open(BACKTEST_STATE_FILE, 'r') as f:
            data = json.load(f)
        pairs = data.get('pairs', [])
        results = data.get('results', {})
        if not pairs:
            return "📭 No pairs selected by last backtest."
        lines = ["<b>📋 Active Pairs</b> (from backtest)"]
        for sym in pairs:
            wr = results.get(sym, {}).get('win_rate', '?')
            trades = results.get(sym, {}).get('total_trades', '?')
            lines.append(f"  • {sym}: <b>{wr}%</b> win rate ({trades} trades)")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to load pairs: {e}"


def _cmd_pnl():
    from utils.dailyChecksUtils import start_of_day_balance
    from utils.exchangeUtils import get_exchange
    try:
        balance = get_exchange().fetch_balance()
        current = balance['total'].get('USDT', 0)
        if start_of_day_balance is None or start_of_day_balance == 0:
            return (
                f"<b>📈 Current Balance</b>\n"
                f"<code>{current:.2f}</code> USDT\n"
                f"(Start-of-day balance not set yet)"
            )
        change = current - start_of_day_balance
        pct = (change / start_of_day_balance) * 100
        arrow = "🟢" if change >= 0 else "🔴"
        return (
            f"<b>📈 Daily P&amp;L</b>\n"
            f"Start: <code>{start_of_day_balance:.2f}</code> USDT\n"
            f"Now:   <code>{current:.2f}</code> USDT\n"
            f"{arrow} Change: <code>{change:+.2f}</code> ({pct:+.2f}%)"
        )
    except Exception as e:
        return f"❌ Failed to compute P&L: {e}"


def _cmd_backtest():
    try:
        if not os.path.isfile(BACKTEST_STATE_FILE):
            return "📭 No backtest results available."
        with open(BACKTEST_STATE_FILE, 'r') as f:
            data = json.load(f)
        run_at = data.get('run_at', '?')
        threshold = data.get('win_rate_threshold', '?')
        pairs = data.get('pairs', [])
        results = data.get('results', {})
        portfolio_wr = data.get('portfolio_win_rate', None)

        lines = [
            f"<b>📊 Last Backtest</b>",
            f"Run: {run_at}",
            f"Threshold: {threshold}%",
            f"Pairs passed: {len(pairs)}/{len(results)}",
        ]
        if portfolio_wr is not None:
            lines.append(f"Portfolio win rate: <b>{portfolio_wr}%</b>")
        for sym, r in results.items():
            if isinstance(r, dict):
                mark = "✅" if sym in pairs else "❌"
                lines.append(f"  {mark} {sym}: {r.get('win_rate', '?')}% ({r.get('total_trades', '?')} trades)")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to load backtest: {e}"


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
        f"Exchange: {os.getenv('EXCHANGE', 'phemex')}",
        f"Timeframe: <code>{config.TIMEFRAME}</code>",
        f"Signals only: {config.TRADING_SIGNALS_ONLY}",
        f"Trade capital %: {config.TRADE_CAPITAL_PCT * 100:.0f}%",
        f"Leverage: {config.DEFAULT_LEVERAGE}x",
        f"Max open trades: {config.MAX_OPEN_TRADES}",
        f"Daily loss limit: {config.DAILY_LOSS_LIMIT * 100:.0f}%",
        f"Min ADX: {config.MIN_ADX_TREND}",
        f"RSI bounds: {config.RSI_OVERSOLD}/{config.RSI_OVERBOUGHT}",
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
            "Overnight pause is off in .env (<code>NIGHT_QUIET_ENABLED=false</code>). "
            "Set it <code>true</code>, configure hours/TZ, restart the bot, then use <code>/night</code>."
        )
    window = f"{config.NIGHT_QUIET_START_HOUR}:00–{config.NIGHT_QUIET_END_HOUR}:00 {config.NIGHT_QUIET_TZ}"
    if not args:
        armed = "ON" if config.NIGHT_QUIET_ARMED else "OFF"
        now_in = "inside" if config.in_night_quiet_window() else "outside"
        return (
            f"<b>Overnight pause</b>\n"
            f"Window: <code>{window}</code>\n"
            f"Armed: <b>{armed}</b> (when bot ON + armed + in window, pair scan is skipped)\n"
            f"Now: <b>{now_in}</b> quiet window\n\n"
            f"<code>/night on</code> — arm (fewer API calls overnight)\n"
            f"<code>/night off</code> — disarm (scan 24/7 while bot is ON)"
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
        return "Overnight pause <b>disarmed</b>. No night skip while the bot is ON."
    return "Use <code>/night</code>, <code>/night on</code>, or <code>/night off</code>"

HELP_TEXT = (
    "<b>📖 Available Commands</b>\n\n"
    "/on — Enable trading\n"
    "/off — Disable trading\n"
    "/status — Bot state and mode\n"
    "/balance — Current USDT balance\n"
    "/positions — Open positions\n"
    "/pairs — Active pairs with win rates\n"
    "/signals — Today's signals with outcomes\n"
    "/pnl — Today's profit/loss\n"
    "/backtest — Last backtest results\n"
    "/timeframe — Get/set timeframe (ex: /timeframe 15m)\n"
    "/night — Overnight pause (needs NIGHT_QUIET_ENABLED in .env)\n"
    "/config — Current configuration\n"
    "/help — This message"
)

COMMAND_MAP = {
    "/on": _cmd_on,
    "on": _cmd_on,
    "/off": _cmd_off,
    "off": _cmd_off,
    "/status": _cmd_status,
    "status": _cmd_status,
    "/balance": _cmd_balance,
    "balance": _cmd_balance,
    "/positions": _cmd_positions,
    "positions": _cmd_positions,
    "/pairs": _cmd_pairs,
    "pairs": _cmd_pairs,
    "/signals": _cmd_signals,
    "signals": _cmd_signals,
    "/pnl": _cmd_pnl,
    "pnl": _cmd_pnl,
    "/backtest": _cmd_backtest,
    "backtest": _cmd_backtest,
    "/config": _cmd_config,
    "config": _cmd_config,
    "/help": lambda: HELP_TEXT,
    "help": lambda: HELP_TEXT,
}

HTML_COMMANDS = {
    "/on", "on", "/off", "off",
    "/status", "status", "/balance", "balance", "/positions", "positions",
    "/pairs", "pairs", "/signals", "signals", "/pnl", "pnl", "/backtest", "backtest",
    "/timeframe", "timeframe", "/tf", "tf",
    "/config", "config", "/help", "help",
    "/night", "night",
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

    handler = COMMAND_MAP.get(cmd)
    if handler:
        response = handler()
        parse_mode = 'HTML' if cmd in HTML_COMMANDS else None
        return response, parse_mode

    return HELP_TEXT, 'HTML'
