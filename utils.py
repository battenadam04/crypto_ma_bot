import pandas as pd
from ta.trend import SMAIndicator
import matplotlib.pyplot as plt
import mplfinance as mpf
import os

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