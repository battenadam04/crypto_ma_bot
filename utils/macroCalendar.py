"""
US high-impact macro calendar pause.

Fetches official US release times (CPI, NFP, FOMC, GDP) and pauses signal
scanning around those windows so temporary risk-off spikes don't poison setups.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import config
from utils.utils import log_event

_lock = threading.Lock()
_cache: dict[str, Any] = {
    "fetched_at": 0.0,
    "events": [],
}
# Last event key we notified as "paused" (so we don't spam).
_active_pause_key: Optional[str] = None
_was_paused: bool = False


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_remaining(seconds: float) -> str:
    secs = max(0, int(seconds))
    hours, rem = divmod(secs, 3600)
    minutes, rem = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m"
    return f"{rem}s"


def _fetch_events_uncached() -> list[dict]:
    url = getattr(
        config,
        "MACRO_CALENDAR_URL",
        "https://xoomar.com/api/markets/calendar?importance=high",
    )
    timeout = float(getattr(config, "MACRO_CALENDAR_TIMEOUT_SEC", 15))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "crypto-ma-bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
        log_event(f"Macro calendar fetch failed: {e}")
        return []

    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []

    events = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        importance = str(row.get("importance") or "").strip().lower()
        if importance and importance not in ("high", "h"):
            continue
        scheduled = _parse_iso(row.get("scheduledAt") or row.get("scheduled_at") or "")
        if scheduled is None:
            continue
        name = str(row.get("eventName") or row.get("name") or "US macro release").strip()
        events.append({
            "name": name,
            "scheduled_at": scheduled,
            "source": str(row.get("source") or ""),
            "period": str(row.get("periodLabel") or row.get("period") or ""),
            "actual": row.get("actual"),
        })
    events.sort(key=lambda e: e["scheduled_at"])
    return events


def get_macro_events(*, force_refresh: bool = False) -> list[dict]:
    """Return cached high-impact US events (UTC datetimes)."""
    ttl = float(getattr(config, "MACRO_CALENDAR_CACHE_SEC", 6 * 3600))
    now = time.time()
    with _lock:
        age = now - float(_cache.get("fetched_at") or 0)
        if not force_refresh and _cache.get("events") is not None and age < ttl:
            return list(_cache["events"])
        events = _fetch_events_uncached()
        # Keep previous cache if fetch fails mid-pause.
        if events or not _cache.get("events"):
            _cache["events"] = events
            _cache["fetched_at"] = now
        return list(_cache["events"])


def _pause_window(event: dict) -> tuple[datetime, datetime]:
    before = timedelta(minutes=float(getattr(config, "MACRO_PAUSE_BEFORE_MIN", 30)))
    after = timedelta(minutes=float(getattr(config, "MACRO_PAUSE_AFTER_MIN", 120)))
    release = event["scheduled_at"]
    return release - before, release + after


def _event_key(event: dict) -> str:
    return f"{event['scheduled_at'].isoformat()}|{event['name']}"


def active_macro_pause(now: Optional[datetime] = None) -> Optional[dict]:
    """
    If currently inside a configured pause window, return pause details:
      name, release_at, pause_start, resume_at, remaining_sec, before_release, event_key
    Otherwise None.
    """
    if not getattr(config, "MACRO_PAUSE_ENABLED", False):
        return None
    if not getattr(config, "MACRO_PAUSE_ARMED", False):
        return None

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    # Look a bit past "after" window so near events still evaluate.
    horizon = now + timedelta(days=3)
    lookback = now - timedelta(hours=12)

    for event in get_macro_events():
        release = event["scheduled_at"]
        if release < lookback or release > horizon:
            continue
        start, end = _pause_window(event)
        if start <= now < end:
            remaining = (end - now).total_seconds()
            return {
                "name": event["name"],
                "release_at": release,
                "pause_start": start,
                "resume_at": end,
                "remaining_sec": remaining,
                "before_release": now < release,
                "event_key": _event_key(event),
                "period": event.get("period") or "",
                "source": event.get("source") or "",
            }
    return None


def should_skip_cycle_for_macro_pause(now: Optional[datetime] = None) -> bool:
    return active_macro_pause(now) is not None


def format_pause_telegram(pause: dict) -> str:
    """Telegram HTML for entering / ongoing a macro pause."""
    release = pause["release_at"].strftime("%Y-%m-%d %H:%M UTC")
    resume = pause["resume_at"].strftime("%Y-%m-%d %H:%M UTC")
    remaining = _format_remaining(pause["remaining_sec"])
    after_min = int(getattr(config, "MACRO_PAUSE_AFTER_MIN", 120))
    before_min = int(getattr(config, "MACRO_PAUSE_BEFORE_MIN", 30))
    period = pause.get("period") or ""
    period_bit = f" ({period})" if period else ""

    if pause.get("before_release"):
        phase = (
            f"Release is scheduled at <b>{release}</b>. "
            f"Scanning is paused from {before_min}m before until {after_min}m after."
        )
    else:
        phase = (
            f"Data released at <b>{release}</b>. "
            f"Waiting {after_min}m for the temporary crypto reaction to settle."
        )

    return (
        f"⏸️ <b>Macro pause</b>\n"
        f"Event: <b>{pause['name']}</b>{period_bit}\n"
        f"{phase}\n"
        f"Resume at: <code>{resume}</code>\n"
        f"Time left: <b>~{remaining}</b>\n\n"
        f"<i>Signals paused so US data volatility doesn't create bad setups. "
        f"Use /macro off to disarm.</i>"
    )


def format_resume_telegram(pause_name: str = "US macro release") -> str:
    return (
        f"✅ <b>Macro pause ended</b>\n"
        f"Event: <b>{pause_name}</b>\n"
        f"Scanning resumed — post-release window complete."
    )


def next_upcoming_event(now: Optional[datetime] = None) -> Optional[dict]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    for event in get_macro_events():
        _, end = _pause_window(event)
        if end > now:
            start, _ = _pause_window(event)
            return {
                **event,
                "pause_start": start,
                "resume_at": end,
            }
    return None


def notify_macro_pause_transitions(send_fn, now: Optional[datetime] = None) -> Optional[dict]:
    """
    Send Telegram alerts when entering or leaving a macro pause.
    Returns the active pause dict (or None).
    """
    global _active_pause_key, _was_paused

    pause = active_macro_pause(now)
    notify = bool(getattr(config, "MACRO_PAUSE_NOTIFY", True))

    if pause:
        key = pause["event_key"]
        if notify and (not _was_paused or _active_pause_key != key):
            try:
                send_fn(format_pause_telegram(pause), parse_mode="HTML", bypass_rate_limit=True)
            except Exception as e:
                log_event(f"Macro pause notify failed: {e}")
        _active_pause_key = key
        _was_paused = True
        return pause

    if _was_paused and notify:
        name = "US macro release"
        if _active_pause_key and "|" in _active_pause_key:
            name = _active_pause_key.split("|", 1)[1]
        try:
            send_fn(format_resume_telegram(name), parse_mode="HTML", bypass_rate_limit=True)
        except Exception as e:
            log_event(f"Macro resume notify failed: {e}")
    _was_paused = False
    _active_pause_key = None
    return None


def reset_pause_notify_state():
    """Test helper."""
    global _active_pause_key, _was_paused
    _active_pause_key = None
    _was_paused = False
    with _lock:
        _cache["fetched_at"] = 0.0
        _cache["events"] = []
