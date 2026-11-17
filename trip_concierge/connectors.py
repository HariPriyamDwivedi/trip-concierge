"""Mail and Calendar connectors, scoped to trip planning.

Like connectors in Claude Desktop, the traveller switches each one on per trip;
until then the concierge cannot use its tools. They exist only for the trip:
Calendar checks free time around travel dates, Mail sends the itinerary. Neither
reads the inbox nor changes the calendar.

The on/off switch lives in ADK session state (so it persists with the trip), and
`guard_connectors` (a before-tool callback) blocks a tool whose connector is off.
Signing in with Google and/or Microsoft (accounts.py, one sign-in per provider)
connects the real calendar(s) and mailbox for both connectors; without it, the
demo providers below apply.
"""

import os
from typing import Any, Optional

from .accounts import PROVIDERS, account_view, available_providers, connected, mail_sender

STATE_PREFIX = "connector_"

CONNECTORS: dict[str, dict] = {
    "calendar": {
        "name": "Calendar",
        "purpose": "Check your free time around travel dates so the plan fits your schedule.",
        "tools": {"free_slots"},
        "limits": "Read-only: never creates, moves or deletes events.",
    },
    "mail": {
        "name": "Mail",
        "purpose": "Email your itinerary to you or your travel companions.",
        "tools": {"send_itinerary"},
        "limits": "Only sends the itinerary; never reads your inbox.",
    },
}


def _provider(connector_id: str) -> dict:
    """Which backend serves the connector, from the server's configuration."""
    if connector_id == "calendar":
        if os.getenv("TRIP_CONCIERGE_CALENDAR") == "google":
            ready = bool(os.getenv("GOOGLE_CALENDAR_TOKEN"))
            return {"provider": "Google Calendar", "mode": "live" if ready else "not configured"}
        return {"provider": "Sample calendar (local stub)", "mode": "demo"}
    if os.getenv("TRIP_CONCIERGE_EMAIL_SEND") == "1" and os.getenv("SMTP_HOST"):
        return {"provider": f"SMTP ({os.environ['SMTP_HOST']})", "mode": "live"}
    return {"provider": "Drafts only (saved locally, nothing is sent)", "mode": "demo"}


def _live(state: dict, cid: str) -> Optional[dict]:
    """Provider line for a connector served by signed-in accounts, else None."""
    if cid == "calendar":
        views = [account_view(state, p) for p in connected(state)]
        if views:
            return {"provider": " + ".join(f"{v['label']} · {v['account']}" for v in views), "mode": "live"}
        return None
    sender = mail_sender(state)
    if sender:
        v = account_view(state, sender)
        return {"provider": f"Sends from {v['account']} ({v['label']})", "mode": "live"}
    return None


def connectors_view(state: dict) -> list[dict]:
    return [
        {
            "id": cid,
            "name": c["name"],
            "purpose": c["purpose"],
            "limits": c["limits"],
            **(_live(state, cid) or _provider(cid)),
            "connected": bool(state.get(STATE_PREFIX + cid)),
        }
        for cid, c in CONNECTORS.items()
    ]


def accounts_view(state: dict) -> dict:
    """Google / Microsoft sign-in status for the Connectors menu (no tokens)."""
    available = available_providers()
    return {
        "providers": [
            {"id": p, "label": PROVIDERS[p]["label"], "available": p in available, "account": account_view(state, p)}
            for p in PROVIDERS
        ],
        "mail_from": mail_sender(state),
    }


def guard_connectors(tool: Any, args: dict, tool_context: Any) -> Optional[dict]:
    """Before-tool callback: refuse a connector tool while its connector is off."""
    name = getattr(tool, "name", "")
    for cid, c in CONNECTORS.items():
        if name in c["tools"] and not tool_context.state.get(STATE_PREFIX + cid):
            return {
                "error": f"The {c['name']} connector is off for this trip. Ask the traveller "
                f"to turn it on under Connectors (top bar) to: {c['purpose'].lower()}"
            }
    return None
