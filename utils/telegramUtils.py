import config
import json
import os
import time
import requests
from datetime import datetime, timezone

from utils.utils import log_event

BACKTEST_STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_backtest.json')

last_update_id = 0

_send_timestamps: list[float] = []
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


def send_telegram(text, image_path=None, parse_mode=None):
    """Send a message (and optional image) to Telegram.

    Args:
        parse_mode: 'HTML', 'Markdown', or None for plain text.
    """
    if _rate_limited():
        log_event("⚠️ Telegram rate limit hit, message suppressed")
        return

    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': config.TELEGRAM_CHAT_ID, 'text': text}
        if parse_mode:
            payload['parse_mode'] = parse_mode
        requests.post(url, data=payload)

        if image_path:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendPhoto"
            with open(image_path, 'rb') as img:
                requests.post(url, files={'photo': img}, data={'chat_id': config.TELEGRAM_CHAT_ID})
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

        update = updates[-1]
        last_update_id = update["update_id"]

        message = update.get("message", {})
        text = message.get("text")
        log_event(f"Latest Telegram message: {text}")

        if not text:
            time.sleep(1)
            continue

        response, parse_mode = handle_telegram_command(text)
        send_telegram(response, parse_mode=parse_mode)

        time.sleep(1)


def _cmd_on():
    if config.TRADING_ENABLED:
        mode = "signals only" if config.TRADING_SIGNALS_ONLY else "live trading"
        return f"ℹ️ Bot already ON ({mode})"
    config.TRADING_ENABLED = True
    if config.TRADING_SIGNALS_ONLY:
        return "✅ Bot ON — signals only mode (no live orders)"
    return "✅ Bot ON — live trading mode"


def _cmd_off():
    if not config.TRADING_ENABLED:
        return "ℹ️ Bot already OFF"
    config.TRADING_ENABLED = False
    return "⛔ Bot OFF — no signals or trades will be processed"


def _cmd_status():
    if config.TRADING_SIGNALS_ONLY:
        mode = "📡 SIGNALS ONLY (no live orders)"
    else:
        mode = "💹 LIVE TRADING (real orders)"
    state = "ON" if config.TRADING_ENABLED else "OFF"
    exchange_name = os.getenv("EXCHANGE", "kucoin")
    return (
        f"<b>📊 Bot Status</b>\n"
        f"State: <b>{state}</b>\n"
        f"Mode: {mode}\n"
        f"Exchange: {exchange_name}\n\n"
        f"<i>Toggle with /on /off. To switch to live trading, set TRADING_SIGNALS_ONLY=false in your env.</i>"
    )


def _cmd_balance():
    from utils.exchangeUtils import get_exchange
    try:
        balance = get_exchange().fetch_balance()
        usdt_total = balance['total'].get('USDT', 0)
        usdt_free = balance['free'].get('USDT', 0)
        ts = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
        return (
            f"<b>💰 Balance</b> ({ts})\n"
            f"Total: <code>{usdt_total:.2f}</code> USDT\n"
            f"Available: <code>{usdt_free:.2f}</code> USDT"
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


def _cmd_config():
    return (
        f"<b>⚙️ Configuration</b>\n"
        f"Exchange: {os.getenv('EXCHANGE', 'kucoin')}\n"
        f"Signals only: {config.TRADING_SIGNALS_ONLY}\n"
        f"Trade capital %: {config.TRADE_CAPITAL_PCT * 100:.0f}%\n"
        f"Leverage: {config.DEFAULT_LEVERAGE}x\n"
        f"Max open trades: {config.MAX_OPEN_TRADES}\n"
        f"Daily loss limit: {config.DAILY_LOSS_LIMIT * 100:.0f}%\n"
        f"Min ADX: {config.MIN_ADX_TREND}\n"
        f"RSI bounds: {config.RSI_OVERSOLD}/{config.RSI_OVERBOUGHT}"
    )


HELP_TEXT = (
    "<b>📖 Available Commands</b>\n\n"
    "/on — Enable trading\n"
    "/off — Disable trading\n"
    "/status — Bot state and mode\n"
    "/balance — Current USDT balance\n"
    "/positions — Open positions\n"
    "/pairs — Active pairs with win rates\n"
    "/pnl — Today's profit/loss\n"
    "/backtest — Last backtest results\n"
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
    "/status", "status", "/balance", "balance", "/positions", "positions",
    "/pairs", "pairs", "/pnl", "pnl", "/backtest", "backtest",
    "/config", "config", "/help", "help",
}


def handle_telegram_command(text):
    """Return (response_text, parse_mode) tuple."""
    text = text.strip().lower()
    log_event(f"Telegram command received: {text}")

    handler = COMMAND_MAP.get(text)
    if handler:
        response = handler()
        parse_mode = 'HTML' if text in HTML_COMMANDS else None
        return response, parse_mode

    return HELP_TEXT, 'HTML'
