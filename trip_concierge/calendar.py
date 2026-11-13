"""Calendar free/busy lookup used when scheduling an itinerary.

When the traveller has signed in to the Calendar connector (Google or Microsoft,
see accounts.py), free_slots reads that calendar's busy times. Otherwise it uses
a local stub (data/calendar_stub.json), or a Google token from the environment
when TRIP_CONCIERGE_CALENDAR=google. HTTP calls take injectable transports so the
wiring is testable without network or real credentials. Times are UTC.
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from google.adk.tools.tool_context import ToolContext

from .accounts import PROVIDERS, access_token, api_request

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
    return _busy_hours(date, [(p["start"], p.get("end")) for p in periods])


def _busy_from_microsoft(date: str, token: str, *, transport=None) -> set[str]:
    query = urllib.parse.urlencode(
        {
            "startDateTime": f"{date}T00:00:00Z",
            "endDateTime": f"{date}T23:59:59Z",
            "$select": "start,end,showAs",
            "$top": "200",
        }
    )
    resp = (transport or api_request)("GET", f"https://graph.microsoft.com/v1.0/me/calendarView?{query}", token, None)
    return _busy_hours(
        date,
        [
            (e["start"]["dateTime"], e["end"]["dateTime"])
            for e in resp.get("value", [])
            if e.get("showAs") != "free"
        ],
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value[:19])  # drop zone suffix / extra fraction digits; UTC


def _busy_hours(date: str, periods: list[tuple[str, Optional[str]]]) -> set[str]:
    """WORKDAY slots on `date` that overlap any busy (start, end) period."""
    day = datetime.fromisoformat(date)
    busy = set()
    for start, end in periods:
        s = _parse_utc(start)
        e = _parse_utc(end) if end else s + timedelta(hours=1)
        for slot in WORKDAY:
            slot_start = day.replace(hour=int(slot[:2]))
            if s < slot_start + timedelta(hours=1) and e > slot_start:
                busy.add(slot)
    return busy


def free_slots(date: str, tool_context: Optional[ToolContext] = None) -> dict:
    """Return the free hour slots (09:00-17:00 UTC) on a date.

    Args:
        date: The day to check, as YYYY-MM-DD.

    Returns:
        A dict with the date, the list of free slots, and which calendar answered.
    """
    if tool_context is not None:
        try:
            account = access_token(tool_context.state, "calendar")
            if account:
                provider, token, who = account
                read = _busy_from_google if provider == "google" else _busy_from_microsoft
                busy = read(date, token)
                return {
                    "date": date,
                    "provider": f"{PROVIDERS[provider]['label']} Calendar ({who})",
                    "timezone": "UTC",
                    "free_slots": [slot for slot in WORKDAY if slot not in busy],
                }
        except Exception as exc:  # expired sign-in, network, API error
            return {"error": f"Couldn't read the connected calendar: {exc}"}
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
