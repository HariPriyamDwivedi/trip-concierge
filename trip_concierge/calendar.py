"""Calendar free/busy lookup used when scheduling an itinerary.

Default provider is a local stub (data/calendar_stub.json) so this runs with no
credentials. Set TRIP_CONCIERGE_CALENDAR=google to use a real Google Calendar
access token (obtained via oauth.py) — opt-in, and it fails clearly if no token
is configured. The Google HTTP call takes an injectable transport so the wiring
is testable without network or real credentials.
"""

import json
import os
import urllib.request
from pathlib import Path
from typing import Callable, Optional

_STUB = Path(__file__).resolve().parent.parent / "data" / "calendar_stub.json"
# Candidate hour slots for a day: 09:00 through 17:00.
WORKDAY = [f"{h:02d}:00" for h in range(9, 18)]

# transport(url, json_body, access_token) -> parsed JSON response
GoogleTransport = Callable[[str, dict, str], dict]


def _busy_from_stub(date: str) -> set[str]:
    data = json.loads(_STUB.read_text(encoding="utf-8"))
    return set(data.get(date, []))


def _freebusy_post(url: str, body: dict, token: str) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - fixed Google endpoint
        return json.loads(resp.read().decode())


def _busy_from_google(
    date: str, token: str, *, transport: GoogleTransport = _freebusy_post
) -> set[str]:
    resp = transport(
        "https://www.googleapis.com/calendar/v3/freeBusy",
        {
            "timeMin": f"{date}T00:00:00Z",
            "timeMax": f"{date}T23:59:59Z",
            "items": [{"id": "primary"}],
        },
        token,
    )
    periods = resp["calendars"]["primary"]["busy"]
    # Map each busy period's start hour to a WORKDAY slot (e.g. "10:00").
    return {f"{p['start'][11:13]}:00" for p in periods}


def free_slots(date: str) -> dict:
    """Return the free hour slots (09:00-17:00) on a date.

    Args:
        date: The day to check, as YYYY-MM-DD.

    Returns:
        A dict with the date, the list of free slots, and which provider answered.
    """
    provider = os.getenv("TRIP_CONCIERGE_CALENDAR", "stub")
    if provider == "google":
        token = os.getenv("GOOGLE_CALENDAR_TOKEN")
        if not token:
            return {
                "error": "Google calendar selected but GOOGLE_CALENDAR_TOKEN is "
                "unset. Run the OAuth flow in oauth.py first.",
            }
        busy = _busy_from_google(date, token)
    else:
        busy = _busy_from_stub(date)
    free = [slot for slot in WORKDAY if slot not in busy]
    return {"date": date, "provider": provider, "free_slots": free}
