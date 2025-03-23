import pandas as pd
from ta.trend import SMAIndicator
import matplotlib.pyplot as plt
import mplfinance as mpf
import os
import ccxt
from config import KUCOIN_API_KEY, KUCOIN_SECRET_KEY, KUCOIN_PASSPHRASE

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

def place_futures_order(exchange, symbol, side, usdt_amount, leverage=10):
    try:
        # Set leverage
        set_leverage(exchange, symbol, leverage)

        # Get market price
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']

        # Calculate base size (amount in contracts)
        base_amount = usdt_amount / price

        # Create order
        order = exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=round(base_amount, 4),
            params={'leverage': leverage}
        )

        return {'status': 'success', 'order': order}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def calculate_mas(df):
    df['ma10'] = SMAIndicator(df['close'], window=10).sma_indicator()
    df['ma20'] = SMAIndicator(df['close'], window=20).sma_indicator()
    df['ma50'] = SMAIndicator(df['close'], window=50).sma_indicator()
    return df

def check_long_signal(df):
    last, prev = df.iloc[-1], df.iloc[-2]
    crossover = prev['ma10'] < prev['ma20'] and last['ma10'] > last['ma20']
    alignment = last['ma20'] > last['ma50']
    return crossover and alignment

def check_short_signal(df):
    last, prev = df.iloc[-1], df.iloc[-2]
    crossover = prev['ma10'] > prev['ma20'] and last['ma10'] < last['ma20']
    alignment = last['ma20'] < last['ma50']
    return crossover and alignment

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
    markets = exchange.load_markets()
    volume_data = []

    for symbol in markets:
        market = markets[symbol]
        if market['quote'] == quote and market['active']:
            volume = market.get('info', {}).get('quoteVolume') or market.get('info', {}).get('volume')
            if volume:
                try:
                    volume = float(volume)
                    volume_data.append((symbol, volume))
                except ValueError:
                    continue

    top_pairs = sorted(volume_data, key=lambda x: x[1], reverse=True)[:top_n]
    return [pair[0] for pair in top_pairs]