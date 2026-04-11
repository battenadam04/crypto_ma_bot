from dotenv import load_dotenv
import os
import json
import threading

# Always load the project-root .env (same folder as this file). Plain load_dotenv() only
# reads cwd, so e.g. `cd strategies && python simulate_trades.py` would miss ../.env and
# BACKTEST_DAYS / API keys would fall back to defaults.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Split the crypto pairs string into a list
CRYPTO_PAIRS = os.getenv('CRYPTO_PAIRS', '').split(',')

TP_PERCENT = float(os.getenv('TP_PERCENT', 2.0))
SL_PERCENT = float(os.getenv('SL_PERCENT', 1.0))

# Trade sizing (live)
TRADE_CAPITAL = float(os.getenv('TRADE_CAPITAL', 50))
TRADE_CAPITAL_PCT = float(os.getenv('TRADE_CAPITAL_PCT', 0.25))

# Optional: minimum ADX for trend signals (0 = disabled). Applied in live and backtest.
MIN_ADX_TREND = float(os.getenv('MIN_ADX_TREND', '0'))

# KuCoin API credentials
KUCOIN_API_KEY = os.getenv('KUCOIN_API_KEY')
KUCOIN_SECRET_KEY = os.getenv('KUCOIN_SECRET_KEY')
KUCOIN_PASSPHRASE = os.getenv('KUCOIN_PASSPHRASE')

TRADING_SIGNALS_ONLY = os.getenv('TRADING_SIGNALS_ONLY', 'false').lower() == 'true'

# Runtime-controlled (Telegram)
TRADING_ENABLED = False   # default OFF

# Runtime-controlled (Telegram): active chart timeframe for signal generation
# Defaults to env var, but can be overridden at runtime and persisted to disk.
_RUNTIME_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "runtime_config.json")
_runtime_lock = threading.Lock()

TIMEFRAME = os.getenv("TIMEFRAME", "5m")


def _load_runtime_config():
    global TIMEFRAME
    try:
        if not os.path.isfile(_RUNTIME_CONFIG_FILE):
            return
        with open(_RUNTIME_CONFIG_FILE, "r") as f:
            data = json.load(f) or {}
        tf = data.get("TIMEFRAME")
        if isinstance(tf, str) and tf.strip():
            TIMEFRAME = tf.strip()
    except Exception:
        # Never crash import on config load failures
        return


def _persist_runtime_config():
    tmp = _RUNTIME_CONFIG_FILE + ".tmp"
    data = {"TIMEFRAME": TIMEFRAME}
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, _RUNTIME_CONFIG_FILE)


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


_load_runtime_config()

# Live trading parameters
DEFAULT_LEVERAGE = int(os.getenv('DEFAULT_LEVERAGE', '10'))
MAX_OPEN_TRADES = int(os.getenv('MAX_OPEN_TRADES', '3'))
MAX_LOSSES_PER_SYMBOL = int(os.getenv('MAX_LOSSES_PER_SYMBOL', '5'))
ENTRY_BUFFER_PCT = float(os.getenv('ENTRY_BUFFER_PCT', '0.05'))
MAIN_LOOP_INTERVAL_SEC = int(os.getenv('MAIN_LOOP_INTERVAL_SEC', '300'))

# Signal thresholds
RSI_OVERSOLD = float(os.getenv('RSI_OVERSOLD', '35'))
RSI_OVERBOUGHT = float(os.getenv('RSI_OVERBOUGHT', '65'))
RANGE_ADX_THRESHOLD = float(os.getenv('RANGE_ADX_THRESHOLD', '25'))

# Suggested limit-entry placement for signal messages
# Example: 0.0015 = 0.15% away from level to improve fills.
LIMIT_ENTRY_OFFSET_PCT = float(os.getenv('LIMIT_ENTRY_OFFSET_PCT', '0.0015'))
LIMIT_IDEA_FALLBACK_PCT = float(os.getenv('LIMIT_IDEA_FALLBACK_PCT', '0.003'))

# Backtest parameters
# Not used by live bot.py (backtest is manual via strategies/simulate_trades.py). Kept for scripts / env docs.
BACKTEST_INTERVAL_HOURS = int(os.getenv('BACKTEST_INTERVAL_HOURS', '168'))  # 168h = weekly
BACKTEST_SLIPPAGE_BPS = float(os.getenv('BACKTEST_SLIPPAGE_BPS', '5'))
BACKTEST_COMMISSION_BPS = float(os.getenv('BACKTEST_COMMISSION_BPS', '4'))
BACKTEST_COOLDOWN_BARS = int(os.getenv('BACKTEST_COOLDOWN_BARS', '10'))
BACKTEST_LOOKAHEAD = int(os.getenv('BACKTEST_LOOKAHEAD', '50'))
BACKTEST_DAYS = int(os.getenv('BACKTEST_DAYS', '28'))
BACKTEST_USE_LIMIT_IDEAS = os.getenv('BACKTEST_USE_LIMIT_IDEAS', 'false').lower() == 'true'
BACKTEST_LIMIT_FILL_BARS = int(os.getenv('BACKTEST_LIMIT_FILL_BARS', '3'))
BACKTEST_MIN_RR_RATIO = float(os.getenv('BACKTEST_MIN_RR_RATIO', '2.0'))

# Daily loss protection
DAILY_LOSS_LIMIT = float(os.getenv('DAILY_LOSS_LIMIT', '0.30'))