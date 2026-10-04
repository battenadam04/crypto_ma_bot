"""Halt new alerts when recent posted signals lose money.

This is the signals-product circuit breaker: existing TP/SL posts still go
out, and new setups wait until the rolling window recovers or the next
successful promotion clears the outcome log.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

import config
from utils.utils import log_event

_LOCK = threading.Lock()
_DIR = os.path.join(os.path.dirname(__file__), "..")
_OUTCOMES_FILE = os.path.join(_DIR, "signal_outcomes.json")
_BOOK_FILE = os.path.join(_DIR, "book_status.json")


def _parse_ts(raw) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _read_json(path, default):
    try:
        if os.path.isfile(path):
            with open(path, "r") as f:
                data = json.load(f)
            return data if data is not None else default
    except Exception as e:
        log_event(f"Feed halt read failed ({os.path.basename(path)}): {e}")
    return default


def _write_json(path, data) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception as e:
        log_event(f"Feed halt write failed ({os.path.basename(path)}): {e}")


def _outcomes() -> list:
    data = _read_json(_OUTCOMES_FILE, [])
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def note_resolved_outcome(
    pnl_pct: float,
    symbol: str,
    result: str,
    when: Optional[datetime] = None,
) -> None:
    """Record a closed win or loss. Expired setups are not a resolved trade."""
    if result not in ("win", "loss"):
        return
    ts = when or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    row = {
        "timestamp": ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "symbol": symbol,
        "result": result,
        "pnl_pct": float(pnl_pct),
    }
    with _LOCK:
        rows = _outcomes()
        rows.append(row)
        if len(rows) > 200:
            rows = rows[-200:]
        _write_json(_OUTCOMES_FILE, rows)


def clear_resolved_outcomes() -> None:
    """A new promoted book starts with a clean intraweek record."""
    with _LOCK:
        _write_json(_OUTCOMES_FILE, [])


def new_signals_blocked(now: Optional[datetime] = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    rows = [
        row for row in _outcomes()
        if row.get("result") in ("win", "loss") and _parse_ts(row.get("timestamp")) is not None
    ]
    window_days = int(getattr(config, "FEED_HALT_WINDOW_DAYS", 7))
    cutoff = now - timedelta(days=window_days)
    recent = [row for row in rows if _parse_ts(row["timestamp"]) >= cutoff]
    if recent and sum(float(row.get("pnl_pct") or 0) for row in recent) <= 0:
        return True, f"Last {window_days} days of resolved signals are net negative."

    n = int(getattr(config, "FEED_HALT_RECENT_TRADES", 20))
    last = rows[-n:]
    if len(last) >= n:
        pnls = [float(row.get("pnl_pct") or 0) for row in last]
        gross_win = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        if gross_loss <= 0:
            pf = float("inf") if gross_win > 0 else 0.0
        else:
            pf = gross_win / gross_loss
        if pf < 1.0:
            return True, f"Last {n} resolved signals have profit factor below 1."
    return False, ""


def note_book_status(stood_down: bool, reason: str = "") -> None:
    with _LOCK:
        _write_json(
            _BOOK_FILE,
            {"stood_down": bool(stood_down), "reason": str(reason or "")},
        )


def book_status() -> tuple[bool, str]:
    data = _read_json(_BOOK_FILE, {})
    if not isinstance(data, dict):
        return False, ""
    return bool(data.get("stood_down")), str(data.get("reason") or "")


def reset_feed_state_for_tests() -> None:
    with _LOCK:
        for path in (_OUTCOMES_FILE, _BOOK_FILE):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except Exception:
                pass
