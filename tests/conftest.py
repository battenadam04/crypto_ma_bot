"""Shared fixtures for the test suite."""

import os
import sys
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault('TELEGRAM_TOKEN', 'test-token')
os.environ.setdefault('TELEGRAM_CHAT_ID', '12345')
os.environ.setdefault('EXCHANGE', 'binance_margin')
os.environ.setdefault('TRADING_SIGNALS_ONLY', 'true')
os.environ.setdefault('BINANCE_API_KEY', 'test')
os.environ.setdefault('BINANCE_SECRET_KEY', 'test')


@pytest.fixture
def bullish_df():
    """DataFrame simulating a clear uptrend with MA crossover."""
    np.random.seed(42)
    n = 100
    base = 100.0
    closes = [base]
    for i in range(1, n):
        closes.append(closes[-1] + np.random.uniform(0.1, 0.5))
    closes = np.array(closes)
    highs = closes + np.random.uniform(0.2, 1.0, n)
    lows = closes - np.random.uniform(0.2, 1.0, n)
    opens = closes - np.random.uniform(-0.3, 0.3, n)

    df = pd.DataFrame({
        'timestamp': pd.date_range('2025-01-01', periods=n, freq='5min'),
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': np.random.uniform(1000, 5000, n),
    })
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['rsi'] = 55.0
    df['adx'] = 30.0
    df['support'] = df['low'].rolling(window=50).min()
    df['resistance'] = df['high'].rolling(window=50).max()
    return df


@pytest.fixture
def bearish_df():
    """DataFrame simulating a clear downtrend."""
    np.random.seed(42)
    n = 100
    base = 200.0
    closes = [base]
    for i in range(1, n):
        closes.append(closes[-1] - np.random.uniform(0.1, 0.5))
    closes = np.array(closes)
    highs = closes + np.random.uniform(0.2, 1.0, n)
    lows = closes - np.random.uniform(0.2, 1.0, n)
    opens = closes + np.random.uniform(-0.3, 0.3, n)

    df = pd.DataFrame({
        'timestamp': pd.date_range('2025-01-01', periods=n, freq='5min'),
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': np.random.uniform(1000, 5000, n),
    })
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['rsi'] = 45.0
    df['adx'] = 30.0
    df['support'] = df['low'].rolling(window=50).min()
    df['resistance'] = df['high'].rolling(window=50).max()
    return df


@pytest.fixture
def ranging_df():
    """DataFrame simulating a range-bound market."""
    np.random.seed(42)
    n = 100
    midpoint = 150.0
    closes = midpoint + np.sin(np.linspace(0, 6 * np.pi, n)) * 2.0
    highs = closes + np.random.uniform(0.1, 0.5, n)
    lows = closes - np.random.uniform(0.1, 0.5, n)
    opens = closes + np.random.uniform(-0.2, 0.2, n)

    df = pd.DataFrame({
        'timestamp': pd.date_range('2025-01-01', periods=n, freq='5min'),
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': np.random.uniform(1000, 5000, n),
    })
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['rsi'] = 50.0
    df['adx'] = 15.0
    df['support'] = df['low'].rolling(window=50).min()
    df['resistance'] = df['high'].rolling(window=50).max()
    return df


@pytest.fixture
def atr_df():
    """Small DF with ATR precomputed for trade level tests."""
    n = 20
    closes = [100.0 + i * 0.5 for i in range(n)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]

    df = pd.DataFrame({
        'timestamp': pd.date_range('2025-01-01', periods=n, freq='5min'),
        'open': closes,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': [1000] * n,
    })
    from utils.utils import add_atr_column
    df = add_atr_column(df, period=7)
    return df
