"""Tests for Telegram command handling."""

import pytest
import os
import json
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from utils.telegramUtils import handle_telegram_command, _rate_limited, _send_timestamps


class TestHandleTelegramCommand:
    def setup_method(self):
        config.TRADING_ENABLED = False

    def test_on_enables_trading(self):
        response, mode = handle_telegram_command("/on")
        assert config.TRADING_ENABLED is True
        assert "ENABLED" in response

    def test_on_already_enabled(self):
        config.TRADING_ENABLED = True
        response, mode = handle_telegram_command("/on")
        assert "already" in response

    def test_off_disables_trading(self):
        config.TRADING_ENABLED = True
        response, mode = handle_telegram_command("/off")
        assert config.TRADING_ENABLED is False
        assert "DISABLED" in response

    def test_off_already_disabled(self):
        config.TRADING_ENABLED = False
        response, mode = handle_telegram_command("/off")
        assert "already" in response

    def test_status_returns_state(self):
        config.TRADING_ENABLED = True
        response, mode = handle_telegram_command("/status")
        assert "ON" in response
        assert mode == 'HTML'

    def test_status_disabled(self):
        config.TRADING_ENABLED = False
        response, mode = handle_telegram_command("/status")
        assert "OFF" in response

    def test_help_returns_commands(self):
        response, mode = handle_telegram_command("/help")
        assert "/balance" in response
        assert "/positions" in response
        assert "/pnl" in response
        assert mode == 'HTML'

    def test_unknown_command_returns_help(self):
        response, mode = handle_telegram_command("foobar")
        assert "/help" in response or "/balance" in response

    def test_config_command(self):
        response, mode = handle_telegram_command("/config")
        assert "Configuration" in response
        assert mode == 'HTML'

    def test_case_insensitive(self):
        response, _ = handle_telegram_command("/ON")
        assert "ENABLED" in response

    def test_whitespace_stripped(self):
        response, _ = handle_telegram_command("  /off  ")
        assert "DISABLED" in response


class TestPairsCommand:
    def test_no_backtest_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            'utils.telegramUtils.BACKTEST_STATE_FILE',
            str(tmp_path / 'nonexistent.json')
        )
        response, mode = handle_telegram_command("/pairs")
        assert "No backtest" in response

    def test_with_backtest_file(self, tmp_path, monkeypatch):
        state_file = tmp_path / 'last_backtest.json'
        state_file.write_text(json.dumps({
            'pairs': ['BTC/USDT'],
            'results': {'BTC/USDT': {'win_rate': 65.0, 'total_trades': 42}}
        }))
        monkeypatch.setattr(
            'utils.telegramUtils.BACKTEST_STATE_FILE',
            str(state_file)
        )
        response, mode = handle_telegram_command("/pairs")
        assert "BTC/USDT" in response
        assert "65" in response


class TestBacktestCommand:
    def test_no_backtest_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            'utils.telegramUtils.BACKTEST_STATE_FILE',
            str(tmp_path / 'nonexistent.json')
        )
        response, mode = handle_telegram_command("/backtest")
        assert "No backtest" in response

    def test_with_backtest_data(self, tmp_path, monkeypatch):
        state_file = tmp_path / 'last_backtest.json'
        state_file.write_text(json.dumps({
            'pairs': ['ETH/USDT'],
            'run_at': '2025-01-01T00:00:00',
            'win_rate_threshold': 55,
            'results': {'ETH/USDT': {'win_rate': 60.0, 'total_trades': 30}},
            'portfolio_win_rate': 58.5,
        }))
        monkeypatch.setattr(
            'utils.telegramUtils.BACKTEST_STATE_FILE',
            str(state_file)
        )
        response, mode = handle_telegram_command("/backtest")
        assert "ETH/USDT" in response
        assert "58.5" in response


class TestRateLimiting:
    def setup_method(self):
        _send_timestamps.clear()

    def test_not_limited_initially(self):
        assert _rate_limited() is False

    def test_limited_after_burst(self):
        import time
        now = time.time()
        _send_timestamps.clear()
        _send_timestamps.extend([now] * 20)
        assert _rate_limited() is True
