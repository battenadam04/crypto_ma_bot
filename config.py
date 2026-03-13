from dotenv import load_dotenv
import os

load_dotenv()

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

# Backtest parameters
BACKTEST_INTERVAL_HOURS = int(os.getenv('BACKTEST_INTERVAL_HOURS', '168'))  # 168h = weekly
BACKTEST_SLIPPAGE_BPS = float(os.getenv('BACKTEST_SLIPPAGE_BPS', '5'))
BACKTEST_COMMISSION_BPS = float(os.getenv('BACKTEST_COMMISSION_BPS', '4'))
BACKTEST_COOLDOWN_BARS = int(os.getenv('BACKTEST_COOLDOWN_BARS', '10'))
BACKTEST_LOOKAHEAD = int(os.getenv('BACKTEST_LOOKAHEAD', '50'))
BACKTEST_DAYS = int(os.getenv('BACKTEST_DAYS', '90'))

# Daily loss protection
DAILY_LOSS_LIMIT = float(os.getenv('DAILY_LOSS_LIMIT', '0.30'))