"""Tests for trade level calculation and TP/SL validation."""

import pytest
import pandas as pd
import numpy as np

from utils.utils import calculate_trade_levels, add_atr_column, safe_place_tp_sl, get_decimal_places


class TestCalculateTradeLevels:
    def test_buy_tp_above_entry(self, atr_df):
        levels = calculate_trade_levels(105.0, 'buy', atr_df, len(atr_df) - 1, 'trend')
        assert levels['take_profit'] > levels['entry']
        assert levels['stop_loss'] < levels['entry']

    def test_sell_tp_below_entry(self, atr_df):
        levels = calculate_trade_levels(105.0, 'sell', atr_df, len(atr_df) - 1, 'trend')
        assert levels['take_profit'] < levels['entry']
        assert levels['stop_loss'] > levels['entry']

    def test_invalid_direction_raises(self, atr_df):
        with pytest.raises(ValueError, match="Invalid direction"):
            calculate_trade_levels(100.0, 'hold', atr_df, 0, 'trend')

    def test_invalid_price_raises(self, atr_df):
        with pytest.raises(ValueError, match="Invalid price"):
            calculate_trade_levels(None, 'buy', atr_df, 0, 'trend')

    def test_out_of_range_index_raises(self, atr_df):
        with pytest.raises(IndexError):
            calculate_trade_levels(100.0, 'buy', atr_df, 999, 'trend')

    def test_missing_atr_raises(self):
        df = pd.DataFrame({'close': [100.0], 'high': [101.0], 'low': [99.0]})
        with pytest.raises(ValueError, match="ATR not computed"):
            calculate_trade_levels(100.0, 'buy', df, 0, 'trend')

    def test_range_strategy_levels(self, atr_df):
        levels = calculate_trade_levels(105.0, 'buy', atr_df, len(atr_df) - 1, 'range')
        assert levels['take_profit'] > levels['entry']
        assert levels['stop_loss'] < levels['entry']

    def test_scalp_strategy_levels(self, atr_df):
        levels = calculate_trade_levels(105.0, 'sell', atr_df, len(atr_df) - 1, 'scalp')
        assert levels['take_profit'] < levels['entry']
        assert levels['stop_loss'] > levels['entry']

    def test_fallback_atr_when_nan(self):
        df = pd.DataFrame({
            'close': [100.0], 'high': [101.0], 'low': [99.0],
            'ATR': [float('nan')],
        })
        levels = calculate_trade_levels(100.0, 'buy', df, 0, 'trend')
        assert levels['take_profit'] > 100.0


class TestAddATRColumn:
    def test_adds_atr(self):
        n = 20
        df = pd.DataFrame({
            'high': [101.0] * n,
            'low': [99.0] * n,
            'close': [100.0] * n,
        })
        result = add_atr_column(df, period=7)
        assert 'ATR' in result.columns
        assert not pd.isna(result['ATR'].iloc[-1])

    def test_does_not_mutate_original(self):
        df = pd.DataFrame({
            'high': [101.0] * 20,
            'low': [99.0] * 20,
            'close': [100.0] * 20,
        })
        original_cols = list(df.columns)
        add_atr_column(df, period=7)
        assert list(df.columns) == original_cols


class TestSafePlaceTPSL:
    def test_valid_buy(self):
        result = safe_place_tp_sl(
            tp_price=105.0, sl_price=95.0,
            entry_price=100.0, direction='buy', symbol='BTC/USDT'
        )
        assert result is not None
        assert result['valid'] is True
        assert result['take_profit'] > 100.0
        assert result['stop_loss'] < 100.0

    def test_valid_sell(self):
        result = safe_place_tp_sl(
            tp_price=95.0, sl_price=105.0,
            entry_price=100.0, direction='sell', symbol='BTC/USDT'
        )
        assert result is not None
        assert result['valid'] is True
        assert result['take_profit'] < 100.0
        assert result['stop_loss'] > 100.0

    def test_missing_tp_returns_none(self):
        result = safe_place_tp_sl(
            tp_price=None, sl_price=95.0,
            entry_price=100.0, direction='buy', symbol='TEST'
        )
        assert result is None

    def test_missing_sl_returns_none(self):
        result = safe_place_tp_sl(
            tp_price=105.0, sl_price=0,
            entry_price=100.0, direction='buy', symbol='TEST'
        )
        assert result is None


class TestGetDecimalPlaces:
    def test_integer(self):
        assert get_decimal_places(1) == 0

    def test_float_with_decimals(self):
        result = get_decimal_places(0.001)
        assert result >= 6

    def test_zero_float(self):
        assert get_decimal_places(0.0) == 10

    def test_non_numeric_fallback(self):
        assert get_decimal_places("abc") == 6
