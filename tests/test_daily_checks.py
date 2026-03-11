"""Tests for daily loss limit checking."""

import pytest
from unittest.mock import patch

import utils.dailyChecksUtils as daily_checks


class TestCheckDailyLossLimit:
    def setup_method(self):
        daily_checks.start_of_day_balance = None
        daily_checks.loss_triggered = False

    def test_initializes_start_of_day_balance(self):
        with patch('utils.dailyChecksUtils.fetch_balance_and_notify', return_value=1000.0):
            result = daily_checks.check_daily_loss_limit()
        assert result is True
        assert daily_checks.start_of_day_balance == 1000.0

    def test_allows_trade_when_within_limit(self):
        daily_checks.start_of_day_balance = 1000.0
        with patch('utils.dailyChecksUtils.fetch_balance_and_notify', return_value=900.0):
            result = daily_checks.check_daily_loss_limit()
        assert result is True

    def test_blocks_trade_when_loss_exceeds_limit(self):
        daily_checks.start_of_day_balance = 1000.0
        with patch('utils.dailyChecksUtils.fetch_balance_and_notify', return_value=650.0):
            with patch('utils.dailyChecksUtils.send_telegram'):
                result = daily_checks.check_daily_loss_limit()
        assert result is False
        assert daily_checks.loss_triggered is True

    def test_stays_blocked_after_trigger(self):
        daily_checks.loss_triggered = True
        result = daily_checks.check_daily_loss_limit()
        assert result is False

    def test_handles_none_balance(self):
        with patch('utils.dailyChecksUtils.fetch_balance_and_notify', return_value=None):
            result = daily_checks.check_daily_loss_limit()
        assert result is True

    def test_no_loss_when_balance_increases(self):
        daily_checks.start_of_day_balance = 1000.0
        with patch('utils.dailyChecksUtils.fetch_balance_and_notify', return_value=1100.0):
            result = daily_checks.check_daily_loss_limit()
        assert result is True
        assert daily_checks.loss_triggered is False
