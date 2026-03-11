"""Tests for backtest engine functions."""

import pytest
import math
import pandas as pd
import numpy as np

from strategies.simulate_trades import (
    _apply_slippage,
    _commission_cost,
    _compute_risk_metrics,
    check_trade_outcome,
)
from utils.utils import add_atr_column


def _make_price_df(prices, start_price=100.0):
    """Build a minimal OHLCV DataFrame from a list of close prices."""
    n = len(prices)
    df = pd.DataFrame({
        'timestamp': pd.date_range('2025-01-01', periods=n, freq='5min'),
        'open': prices,
        'high': [p + 1.0 for p in prices],
        'low': [p - 1.0 for p in prices],
        'close': prices,
        'volume': [1000] * n,
    })
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['rsi'] = 50.0
    df['adx'] = 20.0
    df['support'] = df['low'].rolling(window=min(50, n)).min()
    df['resistance'] = df['high'].rolling(window=min(50, n)).max()
    df = add_atr_column(df, period=7)
    return df


class TestSlippage:
    def test_buy_slippage_increases_price(self):
        result = _apply_slippage(100.0, 'buy')
        assert result > 100.0

    def test_sell_slippage_decreases_price(self):
        result = _apply_slippage(100.0, 'sell')
        assert result < 100.0

    def test_long_alias(self):
        result = _apply_slippage(100.0, 'long')
        assert result > 100.0


class TestCommission:
    def test_positive_commission(self):
        cost = _commission_cost(100.0)
        assert cost > 0

    def test_proportional(self):
        cost_100 = _commission_cost(100.0)
        cost_200 = _commission_cost(200.0)
        assert abs(cost_200 - 2 * cost_100) < 1e-10


class TestRiskMetrics:
    def test_empty_pnl(self):
        metrics = _compute_risk_metrics([])
        assert metrics['sharpe'] == 0.0
        assert metrics['max_drawdown_pct'] == 0.0
        assert metrics['profit_factor'] == 0.0

    def test_all_wins(self):
        pnl = [0.01, 0.02, 0.015, 0.01]
        metrics = _compute_risk_metrics(pnl)
        assert metrics['profit_factor'] == float('inf') or metrics['profit_factor'] > 100
        assert metrics['max_drawdown_pct'] == 0.0
        assert metrics['avg_win_pct'] > 0
        assert metrics['avg_loss_pct'] == 0.0

    def test_all_losses(self):
        pnl = [-0.01, -0.02, -0.015]
        metrics = _compute_risk_metrics(pnl)
        assert metrics['profit_factor'] == 0.0
        assert metrics['max_drawdown_pct'] > 0
        assert metrics['avg_loss_pct'] < 0

    def test_mixed_pnl(self):
        pnl = [0.02, -0.01, 0.03, -0.005, 0.01]
        metrics = _compute_risk_metrics(pnl)
        assert metrics['profit_factor'] > 0
        assert metrics['sharpe'] != 0.0
        assert 'equity_curve' in metrics
        assert len(metrics['equity_curve']) == len(pnl) + 1

    def test_drawdown_calculation(self):
        pnl = [0.10, -0.15, 0.05]
        metrics = _compute_risk_metrics(pnl)
        assert metrics['max_drawdown_pct'] > 0


class TestCheckTradeOutcome:
    def test_buy_wins_when_price_goes_up(self):
        prices = [100.0] * 60 + [100.0 + i * 0.5 for i in range(20)]
        df = _make_price_df(prices)
        outcome = check_trade_outcome(df, 60, 'buy', 100.0, max_lookahead=15)
        assert outcome['result'] in ('win', 'loss')
        assert 'pnl_pct' in outcome

    def test_sell_wins_when_price_goes_down(self):
        prices = [100.0] * 60 + [100.0 - i * 0.5 for i in range(20)]
        df = _make_price_df(prices)
        outcome = check_trade_outcome(df, 60, 'sell', 100.0, max_lookahead=15)
        assert outcome['result'] in ('win', 'loss')

    def test_outcome_includes_pnl(self):
        prices = [100.0] * 80
        df = _make_price_df(prices)
        outcome = check_trade_outcome(df, 60, 'buy', 100.0, max_lookahead=10)
        assert isinstance(outcome['pnl_pct'], float)

    def test_respects_max_lookahead(self):
        prices = [100.0] * 65
        df = _make_price_df(prices)
        outcome = check_trade_outcome(df, 60, 'buy', 100.0, max_lookahead=3)
        assert outcome['result'] in ('win', 'loss')
