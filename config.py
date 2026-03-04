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