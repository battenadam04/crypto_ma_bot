from dotenv import load_dotenv
import os
import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
import socket
import uuid

# Secrets only — everything else is hardcoded below for production.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Phemex API credentials for live trading (optional; signals work without these).
PHEMEX_API_KEY = os.getenv("PHEMEX_API_KEY", "")
PHEMEX_API_SECRET = os.getenv("PHEMEX_API_SECRET", "")

# ---------------------------------------------------------------------------
# Production settings (edit here if you ever need to change behaviour)
# ---------------------------------------------------------------------------

# Market-data venue: "phemex" | "binance_margin" | "kucoin" | "kucoin_futures"
EXCHANGE = "phemex"

# Optional fixed watchlist; empty = use last_backtest.json, else built-in defaults.
CRYPTO_PAIRS = []

TP_PERCENT = 2.0
SL_PERCENT = 1.0
# Require clearer momentum on the signal timeframe for trend entries (0 = disabled).
MIN_ADX_TREND = 18.0

# Signals-only product (live trading lives on tag v1.0.0-live-trading).
TRADING_SIGNALS_ONLY = True

# Master scan/alert gate — toggled at runtime via Telegram /on /off (default OFF).
TRADING_ENABLED = False

# ---------------------------------------------------------------------------
# Live trading via Phemex (admin-controlled, independent of signal scanning)
# ---------------------------------------------------------------------------
LIVE_TRADING_ENABLED = False
LIVE_TRADING_PLATFORM = "phemex"
LIVE_TRADING_LEVERAGE = 5
LIVE_TRADING_RISK_PCT = 1.0  # % of balance to risk per trade
LIVE_TRADING_MAX_POSITIONS = 3
LIVE_TRADING_LAST_SET_AT_UTC = None
LIVE_TRADING_LAST_SET_BY = None

# Capital protection — hard limits to prevent blowing the account
LIVE_TRADING_DAILY_MAX_TRADES = 5        # max new trades per 24h rolling window
LIVE_TRADING_DAILY_LOSS_LIMIT_PCT = 10.0 # auto-disable if daily losses exceed this % of starting balance
LIVE_TRADING_MIN_BALANCE_USDT = 20.0     # stop opening trades if free balance drops below this
LIVE_TRADING_COOLDOWN_AFTER_LOSS_SEC = 1800  # 30min pause after a losing trade closes
LIVE_TRADING_MAX_CAPITAL_DEPLOYED_PCT = 50.0  # never use more than 50% of total balance across all positions

BOT_STARTED_AT_UTC = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
BOT_HOSTNAME = socket.gethostname()
BOT_PID = os.getpid()
BOT_INSTANCE_ID = f"{BOT_HOSTNAME}:{BOT_PID}:{uuid.uuid4().hex[:8]}"

TRADING_ENABLED_LAST_SET_AT_UTC = None
TRADING_ENABLED_LAST_SET_BY = None

_RUNTIME_CONFIG_FILE = os.path.join(_PROJECT_ROOT, "runtime_config.json")
_runtime_lock = threading.Lock()

# Default scan timeframe; /timeframe in Telegram can override and persist.
TIMEFRAME = "15m"
# Higher-timeframe trend filter used by live + backtest.
HTF_TIMEFRAME = "1h"
# Multi-timeframe scanning: also check these timeframes each cycle for more entries.
MULTI_TF_ENABLED = True
MULTI_TF_EXTRA = ["5m"]

# Overnight scan pause (Telegram /night on|off arms/disarms; state persists).
NIGHT_QUIET_ENABLED = True
NIGHT_QUIET_START_HOUR = 22
NIGHT_QUIET_END_HOUR = 6
NIGHT_QUIET_TZ = "UTC"
NIGHT_QUIET_SLEEP_SEC = 60
NIGHT_QUIET_ARMED_DEFAULT = True
NIGHT_QUIET_ARMED = False

MAIN_LOOP_INTERVAL_SEC = 300

# Signal volume controls
SIGNAL_COOLDOWN_SEC = 1800
MAX_SIGNALS_PER_CYCLE = 5
ENABLE_LIMIT_IDEA_FALLBACK = True

# Slightly wider RSI bands so range mean-reversion can fire in mid-alt chop.
RSI_OVERSOLD = 36.0
RSI_OVERBOUGHT = 64.0
RANGE_ADX_THRESHOLD = 25.0
RANGE_MAX_PCT = 0.055
SR_LOOKBACK_BARS = 80  # ~20h on 15m
RANGE_TOUCH_BUFFER = 0.015
# Continuations must tag closer to MA10 (reduces chop entries on loose pullbacks).
CONTINUATION_PULLBACK_PCT = 0.003

LIMIT_ENTRY_OFFSET_PCT = 0.0015
LIMIT_IDEA_FALLBACK_PCT = 0.003

# Backtest (strategies/simulate_trades.py)
# Weekly in-bot refresh of last_backtest.json (Sunday 06:00 UTC by default).
AUTO_BACKTEST_ENABLED = True
AUTO_BACKTEST_DAY = "sunday"  # schedule.every().<day>
AUTO_BACKTEST_AT = "06:00"  # HH:MM
AUTO_BACKTEST_TZ = "UTC"
AUTO_BACKTEST_NOTIFY = True  # Telegram start + finish summary
BACKTEST_INTERVAL_HOURS = 168  # documentation alias for weekly cadence
BACKTEST_SLIPPAGE_BPS = 5.0
BACKTEST_COMMISSION_BPS = 4.0
# ~1h at 15m
BACKTEST_COOLDOWN_BARS = 4
# ~12h at 15m
BACKTEST_LOOKAHEAD = 48
BACKTEST_DAYS = 42
BACKTEST_USE_LIMIT_IDEAS = False
BACKTEST_LIMIT_FILL_BARS = 3
BACKTEST_MIN_RR_RATIO = 1.5
BACKTEST_WIN_RATE_THRESHOLD = 40.0
MIN_SETUP_RR = 1.5
BACKTEST_ENFORCE_RR = False
BACKTEST_APPLY_FEES = True
BACKTEST_MIN_TRADES = 3
BACKTEST_AUTO_TOP_PAIRS = True
# After excluding mega-caps, keep this many liquid mid-alts by volume.
BACKTEST_TOP_N = 30
# Mega-caps chop too hard for this MA pullback edge — skip them in auto discovery.
BACKTEST_EXCLUDE_BASES = ["BTC", "ETH", "BNB"]
BACKTEST_MIN_QUOTE_VOLUME = 1_000_000.0
# 0 = rank by exchange 24h quote volume only (no large-cap CoinGecko filter)
BACKTEST_COINGECKO_MIN_CAP = 0.0
BACKTEST_PAIRS = []  # leave empty so auto top-N volume discovery is used
BACKTEST_PER_PAIR_LIMIT_FALLBACK = False
BACKTEST_OHLCV_LIMIT = 1000
BACKTEST_FETCH_SLEEP_SEC = 0.05
BACKTEST_VERBOSE = False

# Set True by simulate_trades.py for quieter shared helpers during backtests.
IS_BACKTESTING = False


def set_trading_enabled(enabled: bool, by: str = "unknown") -> bool:
    """Set scanning enabled flag and record provenance for observability."""
    global TRADING_ENABLED, TRADING_ENABLED_LAST_SET_AT_UTC, TRADING_ENABLED_LAST_SET_BY
    TRADING_ENABLED = bool(enabled)
    TRADING_ENABLED_LAST_SET_AT_UTC = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    TRADING_ENABLED_LAST_SET_BY = (by or "unknown").strip()[:120]
    return TRADING_ENABLED


def set_live_trading_enabled(enabled: bool, by: str = "unknown") -> bool:
    """Toggle live order execution on Phemex. Requires API keys to be configured."""
    global LIVE_TRADING_ENABLED, LIVE_TRADING_LAST_SET_AT_UTC, LIVE_TRADING_LAST_SET_BY
    if enabled and (not PHEMEX_API_KEY or not PHEMEX_API_SECRET):
        raise ValueError(
            "Cannot enable live trading: PHEMEX_API_KEY and PHEMEX_API_SECRET must be set in .env"
        )
    LIVE_TRADING_ENABLED = bool(enabled)
    LIVE_TRADING_LAST_SET_AT_UTC = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    LIVE_TRADING_LAST_SET_BY = (by or "unknown").strip()[:120]
    return LIVE_TRADING_ENABLED


def _load_runtime_config():
    global TIMEFRAME, NIGHT_QUIET_ARMED
    try:
        if not os.path.isfile(_RUNTIME_CONFIG_FILE):
            return
        with open(_RUNTIME_CONFIG_FILE, "r") as f:
            data = json.load(f) or {}
        tf = data.get("TIMEFRAME")
        if isinstance(tf, str) and tf.strip():
            TIMEFRAME = tf.strip()
        armed = data.get("NIGHT_QUIET_ARMED")
        if NIGHT_QUIET_ENABLED and isinstance(armed, bool):
            NIGHT_QUIET_ARMED = armed
    except Exception:
        return


def _persist_runtime_config():
    tmp = _RUNTIME_CONFIG_FILE + ".tmp"
    data = {}
    if os.path.isfile(_RUNTIME_CONFIG_FILE):
        try:
            with open(_RUNTIME_CONFIG_FILE, "r") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
    data["TIMEFRAME"] = TIMEFRAME
    if NIGHT_QUIET_ENABLED:
        data["NIGHT_QUIET_ARMED"] = NIGHT_QUIET_ARMED
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, _RUNTIME_CONFIG_FILE)


NIGHT_QUIET_ARMED = NIGHT_QUIET_ENABLED and NIGHT_QUIET_ARMED_DEFAULT
_load_runtime_config()


def hour_in_night_quiet_window(hour: int, start_h: int, end_h: int) -> bool:
    """True if hour is in [start_h, end_h) when end wraps past midnight."""
    if start_h < end_h:
        return start_h <= hour < end_h
    return hour >= start_h or hour < end_h


def _night_quiet_now_local_hour() -> int:
    try:
        tz = ZoneInfo(NIGHT_QUIET_TZ)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).hour


def in_night_quiet_window() -> bool:
    if not NIGHT_QUIET_ENABLED:
        return False
    return hour_in_night_quiet_window(
        _night_quiet_now_local_hour(), NIGHT_QUIET_START_HOUR, NIGHT_QUIET_END_HOUR
    )


def should_skip_cycle_for_night_quiet() -> bool:
    return NIGHT_QUIET_ENABLED and NIGHT_QUIET_ARMED and in_night_quiet_window()


def set_night_quiet_armed(armed: bool) -> bool:
    """Persist whether overnight pause is armed (Telegram /night on|off)."""
    global NIGHT_QUIET_ARMED
    if not NIGHT_QUIET_ENABLED:
        raise ValueError("Overnight pause is disabled in config.py (NIGHT_QUIET_ENABLED=False).")
    with _runtime_lock:
        NIGHT_QUIET_ARMED = bool(armed)
        _persist_runtime_config()
    return NIGHT_QUIET_ARMED


def set_timeframe(new_timeframe: str) -> str:
    """Set the active timeframe and persist it. Returns the normalized timeframe."""
    global TIMEFRAME
    tf = (new_timeframe or "").strip()
    if not tf:
        raise ValueError("Timeframe cannot be empty")
    with _runtime_lock:
        TIMEFRAME = tf
        _persist_runtime_config()
    return TIMEFRAME
