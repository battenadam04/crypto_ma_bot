"""The committed screen must match the live signal knobs.

A file from before walk-forward promotion has research stats and no holdout.
Those pairs must not scan. A fresh screen is what puts pairs back on the feed.
"""

import json
import os

from utils.configUtils import levels_config_matches
from utils.signalLogic import (
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


def test_committed_screen_is_not_live_without_a_holdout():
    data = _load()
    assert not isinstance(data.get("promotion"), dict) or data["promotion"].get("stood_down")
    assert symbols_from_backtest_state(data) == []
