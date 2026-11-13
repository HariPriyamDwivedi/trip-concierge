"""The trip timeline (trains, flights, buses, stays, activities) and its alerts.

Items live in the trip's session state (`trip_items`), added by the traveller in
the UI or by the agent (`add_trip_item`, e.g. from an uploaded booking). Alerts
are derived from the items, modelled on what travel apps send: ixigo's wake-up
alarm before your station, ConfirmTkt's chart-prepared update ~4 h before a
train, airline check-in and boarding reminders, and hostel check-in / activity
reminders. Times are the traveller's local time (ISO, no zone), as entered.
"""

import uuid
from datetime import datetime, timedelta
from typing import Literal, Optional

from google.adk.tools.tool_context import ToolContext

ITEMS_KEY = "trip_items"
Kind = Literal["train", "flight", "bus", "stay", "activity"]
KINDS = ("train", "flight", "bus", "stay", "activity")

# (offset from start or end, which end, title, body) per kind; {…} filled per item.
_RULES: dict[str, list[tuple[timedelta, str, str, str]]] = {
    "train": [
        (timedelta(hours=-4), "start", "Chart prepared soon", "Check your PNR{ref}: seat and coach details usually appear about 4 hours before departure."),
        (timedelta(minutes=-30), "start", "Time to board", "{title} leaves {from_place} at {start_time}. Check the platform on the station display."),
        (timedelta(minutes=-30), "end", "Wake up — your stop is near", "{title} reaches {to_place} at {end_time}. Get your bags ready."),
    ],
    "flight": [
        (timedelta(hours=-24), "start", "Web check-in is open", "Check in for {title}{ref_paren}, departing {from_place} at {start_time}."),
        (timedelta(hours=-3), "start", "Leave for the airport", "{title} departs {from_place} at {start_time}."),
        (timedelta(minutes=-45), "start", "Boarding soon", "{title} boards in about 15 minutes. Head to your gate."),
        (timedelta(0), "end", "Landed", "{title} is due in {to_place} at {end_time}."),
    ],
    "bus": [
        (timedelta(minutes=-30), "start", "Time to board", "{title} leaves {from_place} at {start_time}."),
        (timedelta(minutes=-20), "end", "Arriving soon", "{title} reaches {to_place} at {end_time}."),
    ],
    "stay": [
        (timedelta(hours=-3), "start", "Check-in today", "{title}: check-in from {start_time}.{booking}"),
        (timedelta(hours=-2), "end", "Check-out soon", "{title}: check out by {end_time}."),
    ],
    "activity": [
        (timedelta(hours=-1), "start", "Starting in an hour", "{title} at {start_time}{at_place}."),
    ],
}


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value[:19])  # local time as entered; any zone suffix ignored


def new_item(
    kind: str,
    title: str,
    starts_at: str,
    ends_at: Optional[str] = None,
    from_place: Optional[str] = None,
    to_place: Optional[str] = None,
    reference: Optional[str] = None,
) -> dict:
    """A validated timeline item. Raises ValueError for bad input."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if not title.strip():
        raise ValueError("title is required")
    start, end = _parse(starts_at), _parse(ends_at)
    if start is None:
        raise ValueError("starts_at is required, e.g. 2027-03-14T08:15")
    if end and end < start:
        raise ValueError("ends_at is before starts_at")
    return {
        "id": uuid.uuid4().hex[:10],
        "kind": kind,
        "title": title.strip()[:120],
        "starts_at": start.isoformat(timespec="minutes"),
        "ends_at": end.isoformat(timespec="minutes") if end else None,
        "from_place": (from_place or "").strip()[:80] or None,
        "to_place": (to_place or "").strip()[:80] or None,
        "reference": (reference or "").strip()[:40] or None,
    }


def with_item(items: list, item: dict) -> list:
    return sorted([*items, item], key=lambda i: i["starts_at"])


def add_trip_item(
    kind: Kind,
    title: str,
    starts_at: str,
    tool_context: ToolContext,
    ends_at: Optional[str] = None,
    from_place: Optional[str] = None,
    to_place: Optional[str] = None,
    reference: Optional[str] = None,
) -> dict:
    """Add a train, flight, bus, stay or activity to the trip timeline so the
    traveller gets alerts (boarding, arrival wake-up, check-in, start time).

    Use it when the traveller mentions or uploads a booking or a timed plan.

    Args:
        kind: train, flight, bus, stay (hotel/hostel) or activity.
        title: Short name, e.g. "Shatabdi 12002" or "Zostel Manali" or "Old town walk".
        starts_at: Local departure / check-in / start time, ISO like 2027-03-14T08:15.
        ends_at: Local arrival / check-out / end time, if known.
        from_place: Departure station/airport, or the venue for a stay/activity.
        to_place: Arrival station/airport.
        reference: PNR, flight number or booking reference, if any.

    Returns:
        The saved item, or an error explaining what to fix.
    """
    try:
        item = new_item(kind, title, starts_at, ends_at, from_place, to_place, reference)
    except ValueError as exc:
        return {"error": str(exc)}
    tool_context.state[ITEMS_KEY] = with_item(tool_context.state.get(ITEMS_KEY, []), item)
    return {"status": "added", "item": item}


def _fmt(dt: Optional[datetime]) -> str:
    return dt.strftime("%H:%M") if dt else "?"


def notifications(items: list[dict], reminders: list[dict] | None = None) -> list[dict]:
    """Every alert for the trip, soonest first: {id, item_id, kind, title, body, due_at}."""
    out = []
    for item in items:
        start, end = _parse(item["starts_at"]), _parse(item.get("ends_at"))
        fields = {
            "title": item["title"],
            "from_place": item.get("from_place") or "the station",
            "to_place": item.get("to_place") or "your stop",
            "ref": f" {item['reference']}" if item.get("reference") else "",
            "ref_paren": f" ({item['reference']})" if item.get("reference") else "",
            "booking": f" Booking {item['reference']}." if item.get("reference") else "",
            "start_time": _fmt(start),
            "end_time": _fmt(end),
            "at_place": f" at {item['from_place']}" if item.get("from_place") else "",
        }
        for i, (offset, anchor, title, body) in enumerate(_RULES[item["kind"]]):
            base = start if anchor == "start" else end
            if base is None:
                continue
            out.append(
                {
                    "id": f"{item['id']}-{i}",
                    "item_id": item["id"],
                    "kind": item["kind"],
                    "title": title,
                    "body": body.format(**fields),
                    "due_at": (base + offset).isoformat(timespec="minutes"),
                }
            )
    for r in reminders or []:
        when = _parse(r.get("remind_at"))
        if when:
            out.append(
                {
                    "id": f"reminder-{r.get('remind_at')}-{r.get('message')}",
                    "item_id": None,
                    "kind": "reminder",
                    "title": "Reminder",
                    "body": r.get("message", ""),
                    "due_at": when.isoformat(timespec="minutes"),
                }
            )
    if items:  # "upcoming trip" heads-ups before the first item
        first = min(_parse(i["starts_at"]) for i in items)
        for days, label in ((7, "in a week"), (1, "tomorrow")):
            out.append(
                {
                    "id": f"trip-{days}d",
                    "item_id": None,
                    "kind": "trip",
                    "title": f"Your trip starts {label}",
                    "body": f"First up: {min(items, key=lambda i: i['starts_at'])['title']} on {first:%a %d %b at %H:%M}.",
                    "due_at": (first - timedelta(days=days)).isoformat(timespec="minutes"),
                }
            )
    return sorted(out, key=lambda n: n["due_at"])
