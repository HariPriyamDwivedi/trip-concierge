"""Multi-agent trip concierge built on Google ADK.

A coordinator routes a traveller's request to one of three specialists:
  - guide:   suggests things to do (find_attractions tool)
  - budget:  estimates cost (estimate_trip_cost tool)
  - planner: assembles a day-by-day itinerary from the above

`root_agent` is the entry point ADK looks for (`adk run` / `adk web`).
"""

import os

from google.adk.agents import Agent

from .tools import estimate_trip_cost, find_attractions

# Default model; override with TRIP_CONCIERGE_MODEL. Needs a Gemini API key
# (GOOGLE_API_KEY) at run time — see .env.example.
MODEL = os.getenv("TRIP_CONCIERGE_MODEL", "gemini-2.0-flash")

guide_agent = Agent(
    name="guide",
    model=MODEL,
    description="Suggests attractions and things to do in a destination.",
    instruction=(
        "You are a local guide. Use find_attractions to list things to do for "
        "the traveller's city, then highlight the two or three you'd prioritise "
        "and why. If the city isn't supported, say so and name the ones that are."
    ),
    tools=[find_attractions],
)

budget_agent = Agent(
    name="budget",
    model=MODEL,
    description="Estimates the rough cost of a trip.",
    instruction=(
        "You estimate trip budgets. Call estimate_trip_cost with the city, "
        "nights and number of travellers, then explain the figure in one or two "
        "sentences. Ask for any missing detail before estimating."
    ),
    tools=[estimate_trip_cost],
)

planner_agent = Agent(
    name="planner",
    model=MODEL,
    description="Builds a simple day-by-day itinerary for a destination.",
    instruction=(
        "You plan trips. Use find_attractions to gather options, then lay out a "
        "concise day-by-day itinerary across the traveller's number of nights, "
        "grouping nearby stops on the same day."
    ),
    tools=[find_attractions],
)

root_agent = Agent(
    name="trip_concierge",
    model=MODEL,
    description="A trip concierge that coordinates guide, budget and planning help.",
    instruction=(
        "You are a trip concierge. Understand what the traveller needs and "
        "delegate: use the 'guide' specialist for what-to-do questions, the "
        "'budget' specialist for cost questions, and the 'planner' specialist to "
        "build an itinerary. For broad requests, gather what you need from the "
        "specialists and give one combined answer. Keep replies warm and brief."
    ),
    sub_agents=[guide_agent, budget_agent, planner_agent],
)
