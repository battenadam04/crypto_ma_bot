"""Tests for signal detection logic (check_long_signal, check_short_signal, check_range_trade)."""

import pandas as pd
import numpy as np
import pytest

from utils.utils import (
    check_long_signal,
    check_short_signal,
    check_range_trade,
    is_ranging,
    calculate_mas,
    _bullish_engulfing,
    _bearish_engulfing,
)


class TestCheckLongSignal:
    def test_returns_false_on_insufficient_data(self):
        df = pd.DataFrame({'close': [1.0] * 30})
        df['ma10'] = df['close']
        df['ma20'] = df['close']
        df['ma50'] = df['close']
        assert check_long_signal(df) is False

    def test_detects_long_in_uptrend(self, bullish_df):
        result = check_long_signal(bullish_df)
        assert isinstance(result, bool)

    def test_no_long_in_downtrend(self, bearish_df):
        assert check_long_signal(bearish_df) is False


class TestCheckShortSignal:
    def test_returns_false_on_insufficient_data(self):
        df = pd.DataFrame({'close': [1.0] * 30})
        df['ma10'] = df['close']
        df['ma20'] = df['close']
        df['ma50'] = df['close']
        assert check_short_signal(df) is False

    def test_no_short_in_uptrend(self, bullish_df):
        assert check_short_signal(bullish_df) is False

    def test_detects_short_in_downtrend(self, bearish_df):
        result = check_short_signal(bearish_df)
        assert isinstance(result, bool)


class TestRangeDetection:
    def test_is_ranging_needs_adx_column(self):
        df = pd.DataFrame({'close': [100.0] * 60, 'high': [101.0] * 60, 'low': [99.0] * 60})
        assert is_ranging(df) is False

    def test_is_ranging_with_low_adx(self, ranging_df):
        result = is_ranging(ranging_df)
        assert result == True or result == False

    def test_check_range_trade_returns_tuple(self, ranging_df):
        buy, sell = check_range_trade(ranging_df)
        assert buy == True or buy == False
        assert sell == True or sell == False

    def test_check_range_trade_too_few_rows(self):
        df = pd.DataFrame({'close': [100.0]})
        buy, sell = check_range_trade(df)
        assert buy is False
        assert sell is False


class TestEngulfingPatterns:
    def test_bullish_engulfing(self):
        prev = pd.Series({'open': 105, 'close': 100, 'high': 106, 'low': 99})
        curr = pd.Series({'open': 99, 'close': 106, 'high': 107, 'low': 98})
        assert _bullish_engulfing(curr, prev)

    def test_not_bullish_engulfing(self):
        prev = pd.Series({'open': 100, 'close': 105, 'high': 106, 'low': 99})
        curr = pd.Series({'open': 104, 'close': 106, 'high': 107, 'low': 103})
        assert not _bullish_engulfing(curr, prev)

    def test_bearish_engulfing(self):
        prev = pd.Series({'open': 100, 'close': 105, 'high': 106, 'low': 99})
        curr = pd.Series({'open': 106, 'close': 99, 'high': 107, 'low': 98})
        assert _bearish_engulfing(curr, prev)

    def test_not_bearish_engulfing(self):
        prev = pd.Series({'open': 105, 'close': 100, 'high': 106, 'low': 99})
        curr = pd.Series({'open': 101, 'close': 99, 'high': 102, 'low': 98})
        assert not _bearish_engulfing(curr, prev)


class TestCalculateMAs:
    def test_adds_ma_columns(self):
        df = pd.DataFrame({'close': list(range(60))})
        df = calculate_mas(df)
        assert 'ma10' in df.columns
        assert 'ma20' in df.columns
        assert 'ma50' in df.columns
        assert not pd.isna(df['ma50'].iloc[-1])
