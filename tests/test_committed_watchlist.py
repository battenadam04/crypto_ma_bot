"""The committed screen must match the live signal knobs and list real pairs.

A PR that changes signal, level, or pair-gate settings has to refresh
last_backtest.json with `python strategies/simulate_trades.py` (then re-apply
the live gate if the threshold moved). Hand-edited win rates will fail the
profit-factor and sample checks below.
"""

import json
import os

from utils.configUtils import levels_config_matches
from utils.signalLogic import (
    backtest_result_qualifies,
    signal_config_matches,
    symbols_from_backtest_state,
)

_STATE = os.path.join(os.path.dirname(__file__), "..", "last_backtest.json")


def _load():
    with open(_STATE) as f:
        data = json.load(f)
    assert isinstance(data, dict)
    return data


def test_committed_screen_matches_live_config():
    data = _load()
    assert data.get("run_at"), "last_backtest.json has no run_at; rerun the backtest"
    assert signal_config_matches(data.get("signal_config")), (
        "last_backtest.json was produced with different signal knobs. "
        "Rerun `python strategies/simulate_trades.py` and commit the file."
    )
    assert levels_config_matches(data.get("levels_config"))


def test_committed_pairs_clear_the_live_gate():
    data = _load()
    pairs = data.get("pairs") or []
    results = data.get("results") or {}
    # Six pairs cleared the 2026-09-28 trend-only screen. Fewer than five means
    # the book is too thin to ship; rerun the screen instead of padding symbols.
    assert len(pairs) >= 5, pairs
    for sym in pairs:
        assert backtest_result_qualifies(results.get(sym)), sym
    assert symbols_from_backtest_state(data) == pairs
    assert data.get("portfolio_trades", 0) >= 30
    assert float(data.get("portfolio_profit_factor") or 0) >= 1.15
