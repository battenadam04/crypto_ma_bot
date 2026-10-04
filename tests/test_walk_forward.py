"""Walk-forward promotion, the intraweek halt, and persisted daily signals."""

from datetime import datetime, timedelta, timezone

import utils.signalTracker as tracker
from utils.feedHalt import (
    book_status,
    clear_resolved_outcomes,
    new_signals_blocked,
    note_book_status,
    note_resolved_outcome,
    reset_feed_state_for_tests,
)
from utils.signalLogic import symbols_from_backtest_state
from utils.signalTracker import get_daily_signals, record_signal, reset_daily_signals
from utils.walkForward import (
    holdout_result_qualifies,
    in_entry_window,
    promote_from_results,
    promotion_windows,
)


def _holdout(net=2.0, trades=10, pf=1.4):
    return {
        "win_rate": 50.0,
        "total_trades": trades,
        "profit_factor": pf,
        "net_pnl_pct": net,
    }


def _research():
    return {
        "win_rate": 40.0,
        "total_trades": 40,
        "profit_factor": 1.3,
        "holdout": _holdout(),
    }


class TestPromotionWindows:
    def test_embargo_is_twice_the_label_horizon(self):
        import config

        lookahead_hours = int(config.BACKTEST_LOOKAHEAD) * 15 / 60
        windows = promotion_windows(datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc))
        gap = windows["test_start"] - windows["train_end"]
        assert gap == timedelta(hours=windows["embargo_hours"])
        assert windows["embargo_hours"] >= 2 * lookahead_hours
        assert windows["train_days"] == 30
        assert windows["test_days"] == 7
        assert windows["train_end"] < windows["test_start"] < windows["test_end"]

    def test_entry_window_is_half_open(self):
        start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        end = datetime(2026, 10, 8, tzinfo=timezone.utc)
        assert in_entry_window(start, start, end) is True
        assert in_entry_window(end - timedelta(minutes=15), start, end) is True
        assert in_entry_window(end, start, end) is False
        assert in_entry_window(start - timedelta(minutes=15), start, end) is False


class TestPromote:
    def test_research_pass_with_losing_holdout_stays_off(self):
        row = _research()
        row["holdout"] = _holdout(net=-3.0, pf=0.6)
        pairs, promotion = promote_from_results(
            {"ENA/USDT:USDT": row},
            {"net_pnl_pct": -3.0, "profit_factor": 0.6, "trades": 10},
        )
        assert pairs == []
        assert promotion["stood_down"] is True

    def test_positive_pairs_with_losing_book_stand_down(self):
        pairs, promotion = promote_from_results(
            {"DOGE/USDT:USDT": _research(), "GRAM/USDT:USDT": _research()},
            {"net_pnl_pct": -1.2, "profit_factor": 0.8, "trades": 20},
        )
        assert pairs == []
        assert promotion["stood_down"] is True
        assert "not net positive" in promotion["reason"]

    def test_positive_holdout_book_is_live(self):
        pairs, promotion = promote_from_results(
            {"DOGE/USDT:USDT": _research()},
            {"net_pnl_pct": 4.0, "profit_factor": 1.5, "trades": 12},
        )
        assert pairs == ["DOGE/USDT:USDT"]
        assert promotion["stood_down"] is False

    def test_thin_holdout_does_not_qualify(self):
        assert holdout_result_qualifies(_holdout(trades=3, net=5.0, pf=2.0)) is False

    def test_stood_down_file_scans_nothing(self):
        data = {
            "promotion": {"stood_down": True, "reason": "Combined holdout is not net positive."},
            "pairs": ["DOGE/USDT:USDT"],
            "results": {"DOGE/USDT:USDT": _research()},
        }
        assert symbols_from_backtest_state(data) == []


class TestFeedHalt:
    def setup_method(self):
        reset_feed_state_for_tests()

    def teardown_method(self):
        reset_feed_state_for_tests()

    def test_negative_week_blocks_new_signals(self):
        now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        note_resolved_outcome(-0.55, "ENA/USDT:USDT", "loss", now - timedelta(hours=2))
        blocked, reason = new_signals_blocked(now)
        assert blocked is True
        assert "7 days" in reason

    def test_positive_week_stays_open(self):
        now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        note_resolved_outcome(1.2, "DOGE/USDT:USDT", "win", now - timedelta(hours=1))
        note_resolved_outcome(-0.4, "DOGE/USDT:USDT", "loss", now - timedelta(minutes=30))
        assert new_signals_blocked(now) == (False, "")

    def test_last_twenty_losing_factor_blocks(self):
        now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        for i in range(20):
            pnl = 1.0 if i < 5 else -1.0
            result = "win" if pnl > 0 else "loss"
            note_resolved_outcome(pnl, "SUI/USDT:USDT", result, now - timedelta(days=8, minutes=i))
        blocked, reason = new_signals_blocked(now)
        assert blocked is True
        assert "20" in reason

    def test_clear_releases_the_halt(self):
        now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        note_resolved_outcome(-1.0, "ENA/USDT:USDT", "loss", now)
        clear_resolved_outcomes()
        assert new_signals_blocked(now) == (False, "")

    def test_book_status_round_trip(self):
        note_book_status(True, "Combined holdout is not net positive.")
        assert book_status() == (True, "Combined holdout is not net positive.")


class TestDailyPersistence:
    def setup_method(self):
        reset_daily_signals()

    def teardown_method(self):
        reset_daily_signals()

    def test_reload_keeps_todays_signals(self):
        record_signal("DOGE/USDT:USDT", "long", "trend", 0.1, 0.11, 0.09)
        tracker._daily_signals.clear()
        tracker._daily_loaded = False
        restored = get_daily_signals()
        assert len(restored) == 1
        assert restored[0]["symbol"] == "DOGE/USDT:USDT"
