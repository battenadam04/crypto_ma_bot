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


def normalize_telegram_chat_id(raw):
    """
    Normalize Telegram chat ids from env / dashboard paste mistakes.

    Channel/supergroup ids must look like -100xxxxxxxxxx.
    People often paste 100xxxxxxxxxx (missing leading '-') from t.me/c/… links.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(" ", "")
    if not s:
        return None
    # Allow chat_id=@channelusername style
    if s.startswith("@") or s.startswith("-"):
        return s
    if s.isdigit() and s.startswith("100") and len(s) >= 12:
        return f"-{s}"
    return s


TELEGRAM_CHAT_ID = normalize_telegram_chat_id(os.getenv("TELEGRAM_CHAT_ID"))
# Comma-separated Telegram user IDs allowed to change bot settings (/on, /timeframe, etc.).
# Empty = solo mode (anyone who can message the bot may run admin commands).
# For Whop/channel launch: set your user id(s) so paying members cannot change shared settings.
TELEGRAM_ADMIN_IDS = os.getenv("TELEGRAM_ADMIN_IDS", "")


def telegram_admin_id_set():
    """Parsed admin user ids from TELEGRAM_ADMIN_IDS."""
    ids = set()
    for part in str(TELEGRAM_ADMIN_IDS or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def is_telegram_admin(user_id) -> bool:
    """
    True if user may run admin commands.
    When TELEGRAM_ADMIN_IDS is unset/empty, all users are treated as admin (solo / legacy).
    """
    admins = telegram_admin_id_set()
    if not admins:
        return True
    try:
        return int(user_id) in admins
    except (TypeError, ValueError):
        return False


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
MIN_ADX_TREND = 0.0  # disabled — plain MA + HTF path; 0 = no ADX gate

# Signals-only product (live trading lives on tag v1.0.0-live-trading).
TRADING_SIGNALS_ONLY = True

# Master scan/alert gate — toggled at runtime via Telegram /on /off.
# Default ON for the Pro channel feed; set TRADING_ENABLED=false in env to boot off.
# /on and /off persist to runtime_config.json (survives restarts; lost on ephemeral redeploy unless disk attached).
def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


TRADING_ENABLED = _env_bool("TRADING_ENABLED", True)

# ---------------------------------------------------------------------------
# Live trading via Phemex (admin-controlled, independent of signal scanning)
# ---------------------------------------------------------------------------
LIVE_TRADING_ENABLED = False
LIVE_TRADING_PLATFORM = "phemex"
LIVE_TRADING_LEVERAGE = 5
LIVE_TRADING_RISK_PCT = 1.0  # % of balance to risk per trade
LIVE_TRADING_MAX_POSITIONS = 3
# If a new signal is the opposite side of an open position, flatten then reverse
# (better than only moving SL — the original thesis is invalidated).
LIVE_TRADING_REVERSE_ON_FLIP = True
LIVE_TRADING_LAST_SET_AT_UTC = None
LIVE_TRADING_LAST_SET_BY = None

# Capital protection — hard limits to prevent blowing the account
LIVE_TRADING_DAILY_MAX_TRADES = 5        # max new trades per 24h rolling window
LIVE_TRADING_DAILY_LOSS_LIMIT_PCT = 10.0 # auto-disable if daily losses exceed this % of starting balance
LIVE_TRADING_MIN_BALANCE_USDT = 20.0     # stop opening trades if free balance drops below this
LIVE_TRADING_COOLDOWN_AFTER_LOSS_SEC = 1800  # 30min pause after a losing trade closes
LIVE_TRADING_MAX_CAPITAL_DEPLOYED_PCT = 50.0  # never use more than 50% of total balance across all positions

# Trade outcome alerts — Telegram notifications when TP/SL hit (live trading)
TRADE_OUTCOME_ALERTS_ENABLED = True

# Channel follow-ups when a posted signal hits TP/SL or expires (signals product)
SIGNAL_OUTCOME_ALERTS_ENABLED = True

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
# Single signal TF only (no dual 5m+15m alerts). Classic stack: 15m entries + 1h HTF filter.
MULTI_TF_ENABLED = False
MULTI_TF_EXTRA = []

# Overnight scan pause (Telegram /night on|off arms/disarms; state persists).
# Default OFF for a signals product — 22–06 UTC was wiping ~1/3 of scanning time.
NIGHT_QUIET_ENABLED = True
NIGHT_QUIET_START_HOUR = 22
NIGHT_QUIET_END_HOUR = 6
NIGHT_QUIET_TZ = "UTC"
NIGHT_QUIET_SLEEP_SEC = 60
NIGHT_QUIET_ARMED_DEFAULT = False
NIGHT_QUIET_ARMED = False

# US high-impact macro pause (CPI / NFP / FOMC / GDP). Telegram /macro on|off.
# Pauses scanning before + after official release so temporary crypto dumps don't poison signals.
MACRO_PAUSE_ENABLED = True
MACRO_PAUSE_ARMED_DEFAULT = True
MACRO_PAUSE_ARMED = False
MACRO_PAUSE_BEFORE_MIN = 30       # pause starts this many minutes before release
MACRO_PAUSE_AFTER_MIN = 120       # resume this many minutes after release
MACRO_PAUSE_SLEEP_SEC = 60
MACRO_PAUSE_NOTIFY = True         # Telegram when pause starts / ends
# US-morning heads-up on release days (America/New_York), sent once per event.
MACRO_MORNING_WARN_ENABLED = True
MACRO_MORNING_WARN_HOUR = 8       # send at/after this local US hour
MACRO_MORNING_WARN_TZ = "America/New_York"
MACRO_CALENDAR_URL = "https://xoomar.com/api/markets/calendar?importance=high"
MACRO_CALENDAR_CACHE_SEC = 6 * 3600
MACRO_CALENDAR_TIMEOUT_SEC = 15

MAIN_LOOP_INTERVAL_SEC = 300

# Channel quiet-period heartbeat (Pro channel reassurance when filters hold)
CHANNEL_HEARTBEAT_ENABLED = True
CHANNEL_HEARTBEAT_AFTER_QUIET_HOURS = 8   # only after this long with no setups
CHANNEL_HEARTBEAT_EVERY_HOURS = 8         # at most once per this interval while quiet

# Signal volume controls
# Keep LIM off (proximity spam). Restore pre-drought cooldown/caps for confirmed SIGs.
SIGNAL_COOLDOWN_SEC = 1800
MAX_SIGNALS_PER_CYCLE = 5
# Off: proximity LIM alerts flooded the Pro channel and dominated SL outcomes.
ENABLE_LIMIT_IDEA_FALLBACK = False

# Slightly wider RSI bands so range mean-reversion can fire in mid-alt chop.
RSI_OVERSOLD = 36.0
RSI_OVERBOUGHT = 64.0
RANGE_ADX_THRESHOLD = 25.0
RANGE_MAX_PCT = 0.055
SR_LOOKBACK_BARS = 80  # ~20h on 15m
RANGE_TOUCH_BUFFER = 0.015
# Range SL: placed beyond support/resistance (industry-style invalidation), not entry±ATR.
RANGE_SL_BUFFER_PCT = 0.003       # min % beyond S/R level
RANGE_SL_ATR_MULT = 0.5         # also allow at least this × ATR beyond S/R
RANGE_TP_TARGET = "mid"    # "opposite" = other range edge | "mid" = range midpoint
# Continuations: 0.3% tag (pre-combo_v1 volume). 0.5% was too sparse for the live feed.
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
# Backtest cooldown bars are derived from SIGNAL_COOLDOWN_SEC / TIMEFRAME at runtime
# (see utils.signalLogic.signal_cooldown_bars) so live and screens share one silence window.
# Kept for docs / older ablation scripts only — simulate_trades no longer reads this.
BACKTEST_COOLDOWN_BARS = 2  # ≈ SIGNAL_COOLDOWN_SEC=1800 at 15m
# ~12h at 15m
BACKTEST_LOOKAHEAD = 72
BACKTEST_DAYS = 42
BACKTEST_USE_LIMIT_IDEAS = False
BACKTEST_LIMIT_FILL_BARS = 3
BACKTEST_MIN_RR_RATIO = 1.5
BACKTEST_WIN_RATE_THRESHOLD = 40.0
MIN_SETUP_RR = 0.0  # disabled — do not reject MA entries on indicative RR
BACKTEST_ENFORCE_RR = False
BACKTEST_APPLY_FEES = True
BACKTEST_MIN_TRADES = 3
BACKTEST_AUTO_TOP_PAIRS = True
# After excluding mega-caps / non-crypto junk, screen a wide liquid universe by volume.
# Liquidity is only the discovery floor — live pairs still require WR ≥ threshold.
BACKTEST_TOP_N = 80
# Mega-caps chop too hard for this MA pullback edge — skip them in auto discovery.
# Also skip Phemex equity/commodity/stock-token perps that pollute volume rankings.
BACKTEST_EXCLUDE_BASES = [
    "BTC", "ETH", "BNB",
    "XAU", "XAG", "QQQ", "SPY", "AVGO", "AAPL", "TSLA", "NVDA", "AMZN", "META",
    "GOOG", "MSFT", "SAMSUNG", "SOXL", "SOXS", "MRNA", "QCOM", "SKHY", "SKHYNIX",
    "OPENAI", "RKLB", "NBIS", "SNDK", "BMNR", "MUX", "COIN", "HOOD", "MSTR",
    "PONS", "MARSCOIN", "SYN", "LSK", "USELESS", "VVV", "DRAM", "SNXX",
]
BACKTEST_MIN_QUOTE_VOLUME = 500_000.0
# 0 = rank by exchange 24h quote volume only (no large-cap CoinGecko filter)
BACKTEST_COINGECKO_MIN_CAP = 0.0
# Leave empty so auto top-N volume discovery is used.
# Deprecated alias: per-pair LIM now always follows ENABLE_LIMIT_IDEA_FALLBACK (no live/backtest drift).
BACKTEST_PAIRS = []
BACKTEST_PER_PAIR_LIMIT_FALLBACK = False  # ignored; use ENABLE_LIMIT_IDEA_FALLBACK
BACKTEST_OHLCV_LIMIT = 1000
BACKTEST_FETCH_SLEEP_SEC = 0.05
BACKTEST_VERBOSE = False

# Set True by simulate_trades.py for quieter shared helpers during backtests.
IS_BACKTESTING = False


def set_trading_enabled(enabled: bool, by: str = "unknown") -> bool:
    """Set scanning enabled flag, persist it, and record provenance for observability."""
    global TRADING_ENABLED, TRADING_ENABLED_LAST_SET_AT_UTC, TRADING_ENABLED_LAST_SET_BY
    with _runtime_lock:
        TRADING_ENABLED = bool(enabled)
        TRADING_ENABLED_LAST_SET_AT_UTC = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        TRADING_ENABLED_LAST_SET_BY = (by or "unknown").strip()[:120]
        _persist_runtime_config()
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
    global TIMEFRAME, NIGHT_QUIET_ARMED, MACRO_PAUSE_ARMED, TRADING_ENABLED
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
        macro_armed = data.get("MACRO_PAUSE_ARMED")
        if MACRO_PAUSE_ENABLED and isinstance(macro_armed, bool):
            MACRO_PAUSE_ARMED = macro_armed
        trading = data.get("TRADING_ENABLED")
        if isinstance(trading, bool):
            TRADING_ENABLED = trading
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
    data["TRADING_ENABLED"] = bool(TRADING_ENABLED)
    if NIGHT_QUIET_ENABLED:
        data["NIGHT_QUIET_ARMED"] = NIGHT_QUIET_ARMED
    if MACRO_PAUSE_ENABLED:
        data["MACRO_PAUSE_ARMED"] = MACRO_PAUSE_ARMED
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, _RUNTIME_CONFIG_FILE)


NIGHT_QUIET_ARMED = NIGHT_QUIET_ENABLED and NIGHT_QUIET_ARMED_DEFAULT
MACRO_PAUSE_ARMED = MACRO_PAUSE_ENABLED and MACRO_PAUSE_ARMED_DEFAULT
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


def set_macro_pause_armed(armed: bool) -> bool:
    """Persist whether US macro-release pause is armed (Telegram /macro on|off)."""
    global MACRO_PAUSE_ARMED
    if not MACRO_PAUSE_ENABLED:
        raise ValueError("Macro pause is disabled in config.py (MACRO_PAUSE_ENABLED=False).")
    with _runtime_lock:
        MACRO_PAUSE_ARMED = bool(armed)
        _persist_runtime_config()
    return MACRO_PAUSE_ARMED


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
