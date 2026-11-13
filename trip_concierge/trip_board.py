"""The trip board: structured trip data kept in ADK session state.

Tools stay plain functions; `record_trip_state` (an after-tool callback on the web
concierge) copies the useful part of each tool result into session state, and
`save_itinerary` lets the agent store its day-by-day plan. Because session state
lives with the session (Postgres in compose), the board survives restarts.

State keys are top-level and always reassigned, never mutated in place, so ADK
records every change.
"""

from typing import Any, Optional

from google.adk.tools.tool_context import ToolContext
from pydantic import BaseModel

PREFIX = "trip_"


class DayPlan(BaseModel):
    title: str
    stops: list[str]


def save_itinerary(city: str, days: list[DayPlan], tool_context: ToolContext) -> dict:
    """Save the day-by-day itinerary so it appears on the traveller's trip board.

    Call this whenever you propose or change a day-by-day plan.

    Args:
        city: The destination city.
        days: One entry per day, in order: a short title and the stops in visiting order.

    Returns:
        A confirmation with the number of days saved.
    """
    plan = [d.model_dump() if isinstance(d, BaseModel) else dict(d) for d in days]
    tool_context.state[PREFIX + "itinerary"] = {"city": city, "days": plan}
    return {"status": "saved", "days": len(plan)}


def record_trip_state(tool: Any, args: dict, tool_context: Any, tool_response: Any) -> Optional[dict]:
    """After-tool callback: mirror tool results onto the trip board (never alters them)."""
    if not isinstance(tool_response, dict) or "error" in tool_response:
        return None
    state = tool_context.state
    name = getattr(tool, "name", "")
    if name == "find_attractions" and tool_response.get("found"):
        state[PREFIX + "city"] = tool_response["city"]
        state[PREFIX + "attractions"] = {
            "city": tool_response["city"],
            "items": tool_response["attractions"],
        }
    elif name == "estimate_trip_cost":
        state[PREFIX + "city"] = tool_response["city"]
        state[PREFIX + "budget"] = tool_response
    elif name == "schedule_reminder":
        reminder = {k: tool_response[k] for k in ("message", "remind_at") if k in tool_response}
        state[PREFIX + "reminders"] = [*state.get(PREFIX + "reminders", []), reminder]
    elif name == "send_itinerary":
        email = {k: tool_response.get(k) for k in ("to", "subject", "status")}
        state[PREFIX + "emails"] = [*state.get(PREFIX + "emails", []), email]
    return None


def trip_view(state: dict) -> dict:
    """The board as the API returns it: {city, budget, attractions, itinerary, ...}."""
    return {k[len(PREFIX) :]: v for k, v in state.items() if k.startswith(PREFIX)}
