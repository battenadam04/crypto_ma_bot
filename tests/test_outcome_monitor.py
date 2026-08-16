"""Tests for trade outcome monitoring in utils/liveTrading.py."""

import time
from unittest.mock import patch, MagicMock

import config
from utils.liveTrading import (
    track_position,
    untrack_position,
    monitor_trade_outcomes,
    _tracked_positions,
)


class TestTrackPosition:
    def setup_method(self):
        _tracked_positions.clear()

    def teardown_method(self):
        _tracked_positions.clear()

    def test_track_adds_to_dict(self):
        track_position("BTC/USDT:USDT", "buy", 50000, 52000, 49000, "trend", "15m")
        assert "BTC/USDT:USDT" in _tracked_positions
        info = _tracked_positions["BTC/USDT:USDT"]
        assert info['side'] == "buy"
        assert info['entry'] == 50000
        assert info['tp'] == 52000
        assert info['sl'] == 49000
        assert info['strategy'] == "trend"
        assert info['timeframe'] == "15m"
        assert info['opened_at'] > 0

    def test_untrack_removes(self):
        track_position("BTC/USDT:USDT", "buy", 50000, 52000, 49000)
        untrack_position("BTC/USDT:USDT")
        assert "BTC/USDT:USDT" not in _tracked_positions

    def test_untrack_nonexistent_is_safe(self):
        untrack_position("NONEXISTENT")


class TestMonitorTradeOutcomes:
    def setup_method(self):
        _tracked_positions.clear()
        config.LIVE_TRADING_ENABLED = True
        config.PHEMEX_API_KEY = "test"
        config.PHEMEX_API_SECRET = "test"

    def teardown_method(self):
        _tracked_positions.clear()
        config.LIVE_TRADING_ENABLED = False
        config.PHEMEX_API_KEY = ""
        config.PHEMEX_API_SECRET = ""

    def test_no_tracked_positions_returns_immediately(self):
        monitor_trade_outcomes()

    @patch('utils.liveTrading.get_authenticated_exchange')
    @patch('utils.liveTrading.get_open_positions')
    @patch('utils.liveTrading._send_outcome_alert')
    def test_detects_closed_position(self, mock_alert, mock_positions, mock_exchange):
        mock_exchange.return_value = MagicMock()
        mock_positions.return_value = []

        track_position("SUI/USDT:USDT", "buy", 1.50, 1.60, 1.45, "trend", "15m")
        assert "SUI/USDT:USDT" in _tracked_positions

        monitor_trade_outcomes()

        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args[0][1] == "SUI/USDT:USDT"
        assert "SUI/USDT:USDT" not in _tracked_positions

    @patch('utils.liveTrading.get_authenticated_exchange')
    @patch('utils.liveTrading.get_open_positions')
    @patch('utils.liveTrading._send_outcome_alert')
    def test_keeps_still_open_position(self, mock_alert, mock_positions, mock_exchange):
        mock_exchange.return_value = MagicMock()
        mock_positions.return_value = [{'symbol': 'SUI/USDT:USDT', 'contracts': 10}]

        track_position("SUI/USDT:USDT", "buy", 1.50, 1.60, 1.45, "trend", "15m")

        monitor_trade_outcomes()

        mock_alert.assert_not_called()
        assert "SUI/USDT:USDT" in _tracked_positions

    @patch('utils.liveTrading.get_authenticated_exchange')
    @patch('utils.liveTrading.get_open_positions')
    @patch('utils.telegramUtils.send_telegram')
    def test_outcome_alert_determines_tp(self, mock_tg, mock_positions, mock_exchange):
        exchange_mock = MagicMock()
        exchange_mock.fetch_ticker.return_value = {'last': 1.59}
        mock_exchange.return_value = exchange_mock
        mock_positions.return_value = []

        track_position("SUI/USDT:USDT", "buy", 1.50, 1.60, 1.45, "trend", "15m")

        monitor_trade_outcomes()

        mock_tg.assert_called_once()
        msg = mock_tg.call_args[0][0]
        assert "TP HIT" in msg
        assert "SUI/USDT:USDT" in msg

    @patch('utils.liveTrading.get_authenticated_exchange')
    @patch('utils.liveTrading.get_open_positions')
    @patch('utils.telegramUtils.send_telegram')
    def test_outcome_alert_determines_sl(self, mock_tg, mock_positions, mock_exchange):
        exchange_mock = MagicMock()
        exchange_mock.fetch_ticker.return_value = {'last': 1.46}
        mock_exchange.return_value = exchange_mock
        mock_positions.return_value = []

        track_position("SUI/USDT:USDT", "buy", 1.50, 1.60, 1.45, "trend", "15m")

        monitor_trade_outcomes()

        mock_tg.assert_called_once()
        msg = mock_tg.call_args[0][0]
        assert "SL HIT" in msg

    @patch('utils.liveTrading.get_authenticated_exchange')
    @patch('utils.liveTrading.get_open_positions')
    @patch('utils.telegramUtils.send_telegram')
    def test_outcome_alert_short_tp(self, mock_tg, mock_positions, mock_exchange):
        exchange_mock = MagicMock()
        exchange_mock.fetch_ticker.return_value = {'last': 1.41}
        mock_exchange.return_value = exchange_mock
        mock_positions.return_value = []

        track_position("SUI/USDT:USDT", "sell", 1.50, 1.40, 1.55, "range", "5m")

        monitor_trade_outcomes()

        mock_tg.assert_called_once()
        msg = mock_tg.call_args[0][0]
        assert "TP HIT" in msg
        assert "sell" in msg.lower() or "SELL" in msg

    @patch('utils.liveTrading.get_authenticated_exchange')
    @patch('utils.liveTrading.get_open_positions')
    @patch('utils.telegramUtils.send_telegram')
    def test_alerts_disabled_skips_telegram(self, mock_tg, mock_positions, mock_exchange):
        exchange_mock = MagicMock()
        mock_exchange.return_value = exchange_mock
        mock_positions.return_value = []

        config.TRADE_OUTCOME_ALERTS_ENABLED = False
        track_position("SUI/USDT:USDT", "buy", 1.50, 1.60, 1.45, "trend", "15m")

        monitor_trade_outcomes()

        mock_tg.assert_not_called()
        assert "SUI/USDT:USDT" not in _tracked_positions
        config.TRADE_OUTCOME_ALERTS_ENABLED = True


class TestAlertsCommand:
    def setup_method(self):
        config.TRADE_OUTCOME_ALERTS_ENABLED = True

    def teardown_method(self):
        config.TRADE_OUTCOME_ALERTS_ENABLED = True

    def test_alerts_shows_status(self):
        from utils.telegramUtils import handle_telegram_command
        response, _ = handle_telegram_command("/alerts")
        assert "Trade Outcome Alerts" in response
        assert "ON" in response

    def test_alerts_on(self):
        from utils.telegramUtils import handle_telegram_command
        config.TRADE_OUTCOME_ALERTS_ENABLED = False
        response, _ = handle_telegram_command("/alerts on")
        assert "ENABLED" in response
        assert config.TRADE_OUTCOME_ALERTS_ENABLED is True

    def test_alerts_off(self):
        from utils.telegramUtils import handle_telegram_command
        response, _ = handle_telegram_command("/alerts off")
        assert "DISABLED" in response
        assert config.TRADE_OUTCOME_ALERTS_ENABLED is False


class TestFlattenOppositePosition:
    def setup_method(self):
        _tracked_positions.clear()
        config.LIVE_TRADING_ENABLED = True
        config.LIVE_TRADING_REVERSE_ON_FLIP = True

    def teardown_method(self):
        _tracked_positions.clear()
        config.LIVE_TRADING_ENABLED = False
        config.LIVE_TRADING_REVERSE_ON_FLIP = True

    @patch("utils.liveTrading.get_open_positions")
    def test_no_position_is_none(self, mock_positions):
        from utils.liveTrading import flatten_opposite_position
        mock_positions.return_value = []
        state, note = flatten_opposite_position(MagicMock(), "ADA/USDT:USDT", "sell")
        assert state == "none"
        assert note is None

    @patch("utils.liveTrading.get_open_positions")
    def test_same_side_skips(self, mock_positions):
        from utils.liveTrading import flatten_opposite_position
        mock_positions.return_value = [{"symbol": "ADA/USDT:USDT", "side": "long", "contracts": 2}]
        state, note = flatten_opposite_position(MagicMock(), "ADA/USDT:USDT", "buy")
        assert state == "same"
        assert "Already in" in note

    @patch("utils.liveTrading.close_position")
    @patch("utils.liveTrading.get_open_positions")
    def test_opposite_flattens(self, mock_positions, mock_close):
        from utils.liveTrading import flatten_opposite_position
        exchange = MagicMock()
        exchange.fetch_open_orders.return_value = []
        mock_positions.return_value = [{"symbol": "ADA/USDT:USDT", "side": "long", "contracts": 2}]
        mock_close.return_value = {"success": True, "pnl": -1.5, "order_id": "x"}
        state, note = flatten_opposite_position(exchange, "ADA/USDT:USDT", "sell")
        assert state == "flattened"
        mock_close.assert_called_once()
        assert "reverse_signal" in str(mock_close.call_args)
        assert "Flattened" in note
