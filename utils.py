import pandas as pd
from ta.trend import SMAIndicator
import matplotlib.pyplot as plt
import mplfinance as mpf
import os
import ccxt
from config import KUCOIN_API_KEY, KUCOIN_SECRET_KEY, KUCOIN_PASSPHRASE
from ta.trend import ADXIndicator

def init_kucoin_futures():
    return ccxt.kucoinfutures({
        'apiKey': KUCOIN_API_KEY,
        'secret': KUCOIN_SECRET_KEY,
        'password': KUCOIN_PASSPHRASE,
        'enableRateLimit': True
    })

def set_leverage(exchange, symbol, leverage=10):
    market = exchange.market(symbol)
    try:
        response = exchange.set_leverage(leverage, symbol)
        return response
    except Exception as e:
        return {'error': str(e)}

def place_futures_order(exchange, symbol, side, usdt_amount, tp_price, sl_price, leverage=10):
    try:
        # Set leverage
        set_leverage(exchange, symbol, leverage)

        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        base_amount = usdt_amount / price

        # Market entry
        entry_order = exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=round(base_amount, 4),
            params={'leverage': leverage}
        )

        # Determine opposite side for TP/SL
        close_side = 'sell' if side == 'buy' else 'buy'

        # Create TAKE PROFIT conditional order
        tp_order = exchange.create_order(
            symbol=symbol,
            type='takeProfitMarket',
            side=close_side,
            amount=round(base_amount, 4),
            params={
                'stopPrice': round(tp_price, 4),
                'reduceOnly': True,
                'leverage': leverage
            }
        )

        # Create STOP LOSS conditional order
        sl_order = exchange.create_order(
            symbol=symbol,
            type='stopMarket',
            side=close_side,
            amount=round(base_amount, 4),
            params={
                'stopPrice': round(sl_price, 4),
                'reduceOnly': True,
                'leverage': leverage
            }
        )

        return {
            'status': 'success',
            'entry_order': entry_order,
            'tp_order': tp_order,
            'sl_order': sl_order
        }

    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def calculate_mas(df):
    df['ma10'] = SMAIndicator(df['close'], window=10).sma_indicator()
    df['ma20'] = SMAIndicator(df['close'], window=20).sma_indicator()
    df['ma50'] = SMAIndicator(df['close'], window=50).sma_indicator()
    return df

def check_long_signal(df):
    if len(df) < 51:  # Ensure at least 50 candles for MA50
        return False

    last, prev = df.iloc[-1], df.iloc[-2]
    
    # ✅ Crossover check (10 crosses above 20)
    crossover = prev['ma10'] < prev['ma20'] and last['ma10'] > last['ma20']
    
    # ✅ MA alignment (trend confirmation)
    alignment = last['ma20'] > last['ma50']

    # ✅ Extra condition: Price should be above MA10 (bullish momentum)
    price_momentum = last['close'] > last['ma10']

    # ✅ Final confirmation: Add volume filter (optional)
    volume_confirmation = last['volume'] > prev['volume']  # Ensure increasing volume

    return crossover and alignment and price_momentum and volume_confirmation


def check_short_signal(df):
    if len(df) < 51:  # Ensure we have enough data
        return False

    last, prev = df.iloc[-1], df.iloc[-2]

    # ✅ Crossover check (10 crosses below 20)
    crossover = prev['ma10'] > prev['ma20'] and last['ma10'] < last['ma20']

    # ✅ MA alignment (bearish trend confirmation)
    alignment = last['ma20'] < last['ma50']

    # ✅ Extra condition: Price should be below MA10 (selling momentum)
    price_momentum = last['close'] < last['ma10']

    # ✅ Volume confirmation (optional)
    volume_confirmation = last['volume'] > prev['volume']  # Ensure increasing selling volume

    return crossover and alignment and price_momentum and volume_confirmation

def save_chart(df, symbol):
    df = df.copy()
    df.index = pd.to_datetime(df['timestamp'])
    add_plot = [
        mpf.make_addplot(df['ma10'], color='blue'),
        mpf.make_addplot(df['ma20'], color='orange'),
        mpf.make_addplot(df['ma50'], color='green')
    ]
    path = f'charts/{symbol.replace("/", "_")}.png'
    mpf.plot(df, type='candle', style='charles', addplot=add_plot, volume=True,
             title=f"{symbol} MA Crossover", savefig=path)
    return path

def calculate_trade_levels(price, direction, tp_pct=2.0, sl_pct=1.0):
    if direction == 'long':
        tp = price * (1 + tp_pct / 100)
        sl = price * (1 - sl_pct / 100)
    else:
        tp = price * (1 - tp_pct / 100)
        sl = price * (1 + sl_pct / 100)
    return {
        'entry': round(price, 4),
        'take_profit': round(tp, 4),
        'stop_loss': round(sl, 4)
    }

def get_top_volume_pairs(exchange, quote='USDT', top_n=5):
    print("⏳ Fetching tickers...")
    try:
        tickers = exchange.fetch_tickers()
        print(f"✅ Fetched {len(tickers)} tickers.")
    except Exception as e:
        print("❌ Error fetching tickers:", e)
        return []

    volume_data = []

    # List of stablecoins to filter out
    stablecoins = {'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI', 'FDUSD', 'UST'}

    for symbol, ticker in tickers.items():
            if not symbol.endswith(f"/{quote}"):
                continue

            base = symbol.split('/')[0]

            if base in stablecoins:
                continue  # skip stablecoin-to-stablecoin pairs

            volume = ticker.get('quoteVolume')
            if volume:
                try:
                    volume = float(volume)
                    volume_data.append((symbol, volume))
                except ValueError:
                    continue

    top_pairs = sorted(volume_data, key=lambda x: x[1], reverse=True)[:top_n]
    print("🔥 Top pairs:", top_pairs)
    return [pair[0] for pair in top_pairs]



def is_weak_trend(df, period=14, threshold=20):
    adx = ADXIndicator(df['high'], df['low'], df['close'], window=period)
    df['adx'] = adx.adx()
    return df['adx'].iloc[-1] < threshold

def are_mas_compressed(df, threshold_pct=0.3):
    last = df.iloc[-1]
    ma_values = [last['ma10'], last['ma20'], last['ma50']]
    max_ma = max(ma_values)
    min_ma = min(ma_values)
    spread = ((max_ma - min_ma) / min_ma) * 100
    return spread < threshold_pct

def is_consolidating(df, lookback=20, threshold_pct=1.5):
    recent = df.tail(lookback)
    high = recent['high'].max()
    low = recent['low'].min()
    range_pct = ((high - low) / low) * 100

    return range_pct < threshold_pct  # Returns True if it's consolidating

def should_trade(df):
    if is_consolidating(df):
        return False
    if are_mas_compressed(df):
        return False
    if is_weak_trend(df):
        return False
    return True


def is_early_breakout(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # MA10 crossing MA20
    crossover = prev['ma10'] < prev['ma20'] and last['ma10'] > last['ma20']

    # Both are still under or near MA50
    under_ma50 = last['ma10'] < last['ma50'] and last['ma20'] < last['ma50']

    # Price is approaching MA50
    near_ma50 = abs(last['close'] - last['ma50']) / last['ma50'] < 0.005  # within 0.5%

    return crossover and (under_ma50 or near_ma50)