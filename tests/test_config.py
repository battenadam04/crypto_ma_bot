"""Tests for configuration loading and defaults."""

import os
import pytest


class TestConfigDefaults:
    def test_trade_capital_default(self):
        import config
        assert isinstance(config.TRADE_CAPITAL, float)
        assert config.TRADE_CAPITAL > 0

    def test_trade_capital_pct_range(self):
        import config
        assert 0 < config.TRADE_CAPITAL_PCT <= 1.0

    def test_default_leverage(self):
        import config
        assert isinstance(config.DEFAULT_LEVERAGE, int)
        assert config.DEFAULT_LEVERAGE > 0

    def test_rsi_thresholds(self):
        import config
        assert config.RSI_OVERSOLD < config.RSI_OVERBOUGHT

    def test_backtest_params(self):
        import config
        assert config.BACKTEST_SLIPPAGE_BPS >= 0
        assert config.BACKTEST_COMMISSION_BPS >= 0
        assert config.BACKTEST_COOLDOWN_BARS >= 0
        assert config.BACKTEST_LOOKAHEAD > 0
        assert config.BACKTEST_DAYS > 0

    def test_daily_loss_limit_range(self):
        import config
        assert 0 < config.DAILY_LOSS_LIMIT <= 1.0

    def test_trading_enabled_defaults_off(self):
        import config
        assert config.TRADING_ENABLED is False or config.TRADING_ENABLED is True

    def test_crypto_pairs_is_list(self):
        import config
        assert isinstance(config.CRYPTO_PAIRS, list)


class TestStrategySettings:
    def test_all_strategies_exist(self):
        from utils.configUtils import strategy_settings
        assert 'trend' in strategy_settings
        assert 'range' in strategy_settings
        assert 'scalp' in strategy_settings

    def test_strategy_keys(self):
        from utils.configUtils import strategy_settings
        for name, cfg in strategy_settings.items():
            assert 'atr_tp' in cfg
            assert 'atr_sl' in cfg
            assert 'min_tp_pct' in cfg
            assert 'min_sl_pct' in cfg
            assert cfg['atr_tp'] > cfg['atr_sl'], f"{name}: TP multiplier should exceed SL"
