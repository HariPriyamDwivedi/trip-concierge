"""Phase 5 concierge: plan, check the calendar, draft the email, set a reminder.

Ties the itinerary tools together. Email is a dry run by default (nothing is
sent), the calendar reads a local stub unless real OAuth is configured, and
reminders persist locally. The agent must not claim an email was sent when it was
only drafted.

`root_agent` is an alternative entry point (`adk run trip_concierge.concierge_agent`).
"""

import os

from google.adk.agents import Agent

from .calendar import free_slots
from .notifications import send_itinerary
from .reminders import schedule_reminder
from .tools import find_attractions

MODEL = os.getenv("TRIP_CONCIERGE_MODEL", "gemini-2.0-flash")

root_agent = Agent(
    name="trip_concierge_plus",
    model=MODEL,
    description="Plans a trip, checks free time, drafts the itinerary email, and sets reminders.",
    instruction=(
        "You are a trip concierge. Use find_attractions to shape the itinerary, "
        "free_slots to find open time on a given date, send_itinerary to prepare "
        "the itinerary email, and schedule_reminder for follow-ups. "
        "send_itinerary only drafts a dry run by default — tell the traveller the "
        "email is a draft for them to review and never say it was sent unless the "
        "tool result status is 'sent'. Keep replies warm and brief."
    ),
    tools=[find_attractions, free_slots, send_itinerary, schedule_reminder],
)
