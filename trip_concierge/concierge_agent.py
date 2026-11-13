"""The web concierge: plan and price a trip, answer questions by agentic RAG,
check the calendar, draft the email, set a reminder.

Agentic RAG: the agent itself picks a source (the traveller's uploaded files, the
curated guides, or the web via Tavily), judges whether the passages answer the
question, rewrites the query and retries or switches source if not, and answers
only from what it retrieved, citing each claim.

Email is a dry run by default (nothing is sent), the calendar reads a local stub
unless real OAuth is configured, and reminders persist locally. Web search is only
offered when TAVILY_API_KEY is set.

`root_agent` is an alternative entry point (`TRIP_AGENT=trip_concierge.concierge_agent python run.py`).
"""

import os

from google.adk.agents import Agent

from .agent import MODEL
from .calendar import free_slots
from .documents import search_my_documents
from .notifications import send_itinerary
from .rag import search_guides
from .reminders import schedule_reminder
from .tools import estimate_trip_cost, find_attractions
from .websearch import web_search

WEB_SEARCH_ENABLED = bool(os.getenv("TAVILY_API_KEY"))

_RETRIEVAL = (
    "Answering questions (agentic retrieval). For any factual question about a "
    "destination or the traveller's own trip, retrieve before you answer:\n"
    "1. Choose the source: search_my_documents for anything about the traveller's "
    "uploaded files (bookings, tickets, notes, or whenever they mention a file); "
    "search_guides for curated destination advice"
    + (
        "; web_search for current or changing facts (opening hours, events on given "
        "dates, visas, weather) and places the guides don't cover"
        if WEB_SEARCH_ENABLED
        else ""
    )
    + ".\n"
    "2. Judge the passages. If they are empty, off-topic or don't actually answer "
    "the question, rewrite the query (more specific, or other words) and search "
    "again, or try the next source. Use at most 4 searches per question.\n"
    "3. Answer only from retrieved passages and tool results, citing each claim "
    "inline: [file: <name>], [guide: <source>]"
    + (", or the result's URL" if WEB_SEARCH_ENABLED else "")
    + ". If nothing relevant turns up, say so plainly instead of guessing."
)

root_agent = Agent(
    name="trip_concierge_plus",
    model=MODEL,
    description=(
        "Plans and prices a trip, answers from the traveller's files, guides and the "
        "web, checks free time, drafts the itinerary email, and sets reminders."
    ),
    instruction=(
        "You are a trip concierge. Use find_attractions to shape the itinerary, "
        "estimate_trip_cost for budget questions (ask for any missing city, "
        "nights or travellers first), "
        "free_slots to find open time on a given date, send_itinerary to prepare "
        "the itinerary email, and schedule_reminder for follow-ups. "
        "send_itinerary only drafts a dry run by default — tell the traveller the "
        "email is a draft for them to review and never say it was sent unless the "
        "tool result status is 'sent'. Keep replies warm and brief.\n\n" + _RETRIEVAL
    ),
    tools=[
        find_attractions,
        estimate_trip_cost,
        free_slots,
        send_itinerary,
        schedule_reminder,
        search_my_documents,
        search_guides,
        *([web_search] if WEB_SEARCH_ENABLED else []),
    ],
)
