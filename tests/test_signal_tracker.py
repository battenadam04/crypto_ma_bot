"""Tests for the EOD signal tracker."""

import pytest
from unittest.mock import MagicMock

from utils.signalTracker import (
    record_signal, get_daily_signals, reset_daily_signals,
    build_eod_summary, _resolve_signal,
)


class TestRecordSignal:
    def setup_method(self):
        reset_daily_signals()

    def test_records_signal(self):
        record_signal('BTC/USDT', 'long', 'trend', 100.0, 105.0, 95.0)
        signals = get_daily_signals()
        assert len(signals) == 1
        assert signals[0]['symbol'] == 'BTC/USDT'
        assert signals[0]['direction'] == 'long'
        assert signals[0]['entry'] == 100.0

    def test_records_multiple(self):
        record_signal('BTC/USDT', 'long', 'trend', 100.0, 105.0, 95.0)
        record_signal('ETH/USDT', 'short', 'range', 3000.0, 2900.0, 3100.0)
        assert len(get_daily_signals()) == 2

    def test_reset_clears(self):
        record_signal('BTC/USDT', 'long', 'trend', 100.0, 105.0, 95.0)
        reset_daily_signals()
        assert len(get_daily_signals()) == 0


class TestResolveSignal:
    def test_long_win(self):
        exchange = MagicMock()
        exchange.fetch_ticker.return_value = {'last': 110.0}
        signal = {'symbol': 'BTC/USDT', 'direction': 'long', 'entry': 100.0, 'tp': 105.0, 'sl': 95.0}
        result, pnl = _resolve_signal(signal, exchange)
        assert result == 'win'
        assert pnl > 0

    def test_long_loss(self):
        exchange = MagicMock()
        exchange.fetch_ticker.return_value = {'last': 90.0}
        signal = {'symbol': 'BTC/USDT', 'direction': 'long', 'entry': 100.0, 'tp': 105.0, 'sl': 95.0}
        result, pnl = _resolve_signal(signal, exchange)
        assert result == 'loss'
        assert pnl < 0

    def test_long_open(self):
        exchange = MagicMock()
        exchange.fetch_ticker.return_value = {'last': 102.0}
        signal = {'symbol': 'BTC/USDT', 'direction': 'long', 'entry': 100.0, 'tp': 105.0, 'sl': 95.0}
        result, pnl = _resolve_signal(signal, exchange)
        assert result == 'open'
        assert pnl > 0

    def test_short_win(self):
        exchange = MagicMock()
        exchange.fetch_ticker.return_value = {'last': 90.0}
        signal = {'symbol': 'BTC/USDT', 'direction': 'short', 'entry': 100.0, 'tp': 95.0, 'sl': 105.0}
        result, pnl = _resolve_signal(signal, exchange)
        assert result == 'win'
        assert pnl > 0

    def test_short_loss(self):
        exchange = MagicMock()
        exchange.fetch_ticker.return_value = {'last': 110.0}
        signal = {'symbol': 'BTC/USDT', 'direction': 'short', 'entry': 100.0, 'tp': 95.0, 'sl': 105.0}
        result, pnl = _resolve_signal(signal, exchange)
        assert result == 'loss'
        assert pnl < 0

    def test_missing_tp_sl(self):
        exchange = MagicMock()
        signal = {'symbol': 'BTC/USDT', 'direction': 'long', 'entry': 100.0, 'tp': None, 'sl': None}
        result, pnl = _resolve_signal(signal, exchange)
        assert result == 'unresolved'

    def test_exchange_error(self):
        exchange = MagicMock()
        exchange.fetch_ticker.side_effect = Exception("API error")
        signal = {'symbol': 'BTC/USDT', 'direction': 'long', 'entry': 100.0, 'tp': 105.0, 'sl': 95.0}
        result, pnl = _resolve_signal(signal, exchange)
        assert result == 'unresolved'


class TestBuildEodSummary:
    def setup_method(self):
        reset_daily_signals()

    def test_no_signals_returns_none(self):
        exchange = MagicMock()
        assert build_eod_summary(exchange) is None

    def test_with_signals(self):
        record_signal('BTC/USDT', 'long', 'trend', 100.0, 105.0, 95.0)
        exchange = MagicMock()
        exchange.fetch_ticker.return_value = {'last': 110.0}
        summary = build_eod_summary(exchange)
        assert summary is not None
        assert 'BTC/USDT' in summary
        assert 'WIN' in summary
        assert 'Win rate' in summary
