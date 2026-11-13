"""A simple local reminder store for trip follow-ups.

Reminders are persisted to reminders.json (override with TRIP_CONCIERGE_REMINDERS).
There is no real scheduler here — a production build would hand these to cron or
Cloud Scheduler — but this is a real, testable store the agent can write to and
read back.
"""

import json
import os
from pathlib import Path


def _store_path() -> Path:
    return Path(
        os.getenv("TRIP_CONCIERGE_REMINDERS")
        or Path(__file__).resolve().parent.parent / "reminders.json"
    )


def _load() -> list[dict]:
    path = _store_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def schedule_reminder(message: str, remind_at: str) -> dict:
    """Store a reminder for a trip follow-up.

    Args:
        message: What to be reminded about, e.g. "Check in for the Kyoto flight".
        remind_at: When, as an ISO date or datetime, e.g. "2026-05-01T09:00".

    Returns:
        The stored reminder with its assigned id.
    """
    items = _load()
    item = {"id": len(items) + 1, "message": message, "remind_at": remind_at}
    items.append(item)
    _store_path().write_text(json.dumps(items, indent=2), encoding="utf-8")
    return {"status": "scheduled", **item}


def list_reminders() -> dict:
    """Return all stored reminders."""
    return {"reminders": _load()}
