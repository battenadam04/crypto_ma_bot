"""Channel quiet-period heartbeats — silence as intentional selectivity."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

import config
from utils.utils import log_event

_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "channel_activity.json")
_lock = threading.Lock()

_last_signal_at: datetime | None = None
_last_heartbeat_at: datetime | None = None
_loaded = False


def _parse_iso(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_state() -> None:
    global _last_signal_at, _last_heartbeat_at, _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        try:
            if os.path.isfile(_STATE_FILE):
                with open(_STATE_FILE, "r") as f:
                    data = json.load(f) or {}
                _last_signal_at = _parse_iso(data.get("last_signal_at"))
                _last_heartbeat_at = _parse_iso(data.get("last_heartbeat_at"))
        except Exception as e:
            log_event(f"channel heartbeat state load failed: {e}")
        _loaded = True


def _persist_state() -> None:
    tmp = _STATE_FILE + ".tmp"
    data = {
        "last_signal_at": _iso(_last_signal_at),
        "last_heartbeat_at": _iso(_last_heartbeat_at),
    }
    try:
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, _STATE_FILE)
    except Exception as e:
        log_event(f"channel heartbeat state save failed: {e}")


def note_signal_sent(when: datetime | None = None) -> None:
    """Call whenever a real setup is posted to the channel."""
    global _last_signal_at
    _load_state()
    ts = when or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    with _lock:
        _last_signal_at = ts.astimezone(timezone.utc)
        _persist_state()


def last_signal_at() -> datetime | None:
    _load_state()
    return _last_signal_at


def last_heartbeat_at() -> datetime | None:
    _load_state()
    return _last_heartbeat_at


def _hours_since(ts: datetime | None, now: datetime) -> float | None:
    if ts is None:
        return None
    return max(0.0, (now - ts).total_seconds() / 3600.0)


def _fmt_quiet_hours(hours: float | None) -> str:
    if hours is None:
        return "since this instance started watching"
    if hours < 1:
        mins = max(1, int(hours * 60))
        return f"{mins}m"
    if hours < 24:
        return f"{hours:.0f}h"
    days = hours / 24.0
    if days < 2:
        return f"{days:.1f}d"
    return f"{days:.0f}d"


def should_send_heartbeat(now: datetime | None = None) -> bool:
    """True when scanning is on, quiet long enough, and interval has elapsed."""
    if not getattr(config, "CHANNEL_HEARTBEAT_ENABLED", True):
        return False
    if not config.TRADING_ENABLED:
        return False
    # Don't nag overnight while the scanner itself is paused.
    if config.should_skip_cycle_for_night_quiet():
        return False

    _load_state()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    after_quiet = float(getattr(config, "CHANNEL_HEARTBEAT_AFTER_QUIET_HOURS", 8))
    every = float(getattr(config, "CHANNEL_HEARTBEAT_EVERY_HOURS", 8))

    quiet_h = _hours_since(_last_signal_at, now)
    # No signal yet this process/file lifetime — treat boot as start of quiet window
    # using BOT_STARTED_AT if available, else require after_quiet from first check via heartbeat clock.
    if quiet_h is None:
        boot = _parse_iso(getattr(config, "BOT_STARTED_AT_UTC", None))
        quiet_h = _hours_since(boot, now)
        if quiet_h is None:
            quiet_h = 0.0

    if quiet_h < after_quiet:
        return False

    since_hb = _hours_since(_last_heartbeat_at, now)
    if since_hb is not None and since_hb < every:
        return False
    return True


def build_heartbeat_message(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    _load_state()

    quiet_h = _hours_since(_last_signal_at, now)
    if quiet_h is None:
        boot = _parse_iso(getattr(config, "BOT_STARTED_AT_UTC", None))
        quiet_h = _hours_since(boot, now)

    quiet_label = _fmt_quiet_hours(quiet_h)
    tf = config.TIMEFRAME
    extra = ""
    if getattr(config, "MULTI_TF_ENABLED", False) and getattr(config, "MULTI_TF_EXTRA", None):
        extra = " + " + "/".join(config.MULTI_TF_EXTRA)

    return "\n".join(
        [
            "📡 <b>Still scanning — no setups right now</b>",
            "",
            "No alert for a while can be a <b>good</b> sign. The filters are rejecting "
            "weak or high-risk setups so you are not pushed into forced trades.",
            "",
            f"Quiet for: <b>{quiet_label}</b>",
            f"Timeframes: <code>{tf}{extra}</code>",
            "Status: <b>online and selective</b>",
            "",
            "<i>No signal ≠ offline. Patience is part of the edge.</i>",
        ]
    )


def maybe_send_quiet_heartbeat(send_fn, now: datetime | None = None) -> bool:
    """Send a channel reassurance message if due. Returns True if sent."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    if not should_send_heartbeat(now):
        return False

    global _last_heartbeat_at
    msg = build_heartbeat_message(now)
    try:
        send_fn(msg, parse_mode="HTML", bypass_rate_limit=True)
    except TypeError:
        # Tests / simple callables may only accept text.
        send_fn(msg)
    except Exception as e:
        log_event(f"Quiet heartbeat send failed: {e}")
        return False

    with _lock:
        _last_heartbeat_at = now
        _persist_state()
    log_event("Quiet-period channel heartbeat sent.")
    return True


def reset_heartbeat_state_for_tests() -> None:
    """Test helper — clear in-memory + optional file state."""
    global _last_signal_at, _last_heartbeat_at, _loaded
    with _lock:
        _last_signal_at = None
        _last_heartbeat_at = None
        _loaded = True
        try:
            if os.path.isfile(_STATE_FILE):
                os.remove(_STATE_FILE)
        except Exception:
            pass
