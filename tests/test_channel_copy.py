"""Channel feed copy must not instruct read-only members to run admin commands."""

from datetime import datetime, timedelta, timezone

from utils.channelHeartbeat import build_heartbeat_message
from utils.macroCalendar import format_morning_warn_telegram, format_pause_telegram, format_resume_telegram
from utils.signalTracker import build_quiet_day_eod_message

_ADMIN_CMD_HINTS = (
    "/macro",
    "/night",
    "/on",
    "/off",
    "/live",
    "/status",
    "/backtest",
    "/timeframe",
    "/tf",
    "/config",
    "/close",
    "/guards",
    "/alerts",
    "/positions",
)


def _assert_no_admin_cmds(text: str):
    lower = text.lower()
    for hint in _ADMIN_CMD_HINTS:
        assert hint not in lower, f"channel copy should not mention {hint}: {text}"


class TestChannelCopyNoAdminCommands:
    def test_macro_pause(self):
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        msg = format_pause_telegram(
            {
                "name": "CPI",
                "release_at": release,
                "pause_start": release - timedelta(minutes=30),
                "resume_at": release + timedelta(minutes=120),
                "remaining_sec": 3600,
                "before_release": True,
                "period": "August 2026",
            }
        )
        _assert_no_admin_cmds(msg)

    def test_macro_resume(self):
        _assert_no_admin_cmds(format_resume_telegram("CPI"))

    def test_macro_morning(self):
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        msg = format_morning_warn_telegram(
            {"name": "NFP", "scheduled_at": release, "period": "August"}
        )
        _assert_no_admin_cmds(msg)

    def test_heartbeat(self):
        _assert_no_admin_cmds(build_heartbeat_message())

    def test_quiet_eod(self):
        _assert_no_admin_cmds(build_quiet_day_eod_message())
