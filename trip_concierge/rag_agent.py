"""A destination expert that answers from the guides, grounded with citations.

Phase 4: retrieval-augmented generation. The agent must answer only from what
search_guides returns and cite the source guide for each claim, so answers stay
grounded in the corpus rather than the model's own recollection.

`root_agent` is an alternative entry point (`adk run trip_concierge.rag_agent`).
"""

import os

from google.adk.agents import Agent

from .rag import search_guides

MODEL = os.getenv("TRIP_CONCIERGE_MODEL", "gemini-2.0-flash")

root_agent = Agent(
    name="destination_expert",
    model=MODEL,
    description="Answers destination questions from curated guides, with citations.",
    instruction=(
        "You answer traveller questions using only the destination guides. "
        "Always call search_guides first, then answer strictly from the passages "
        "it returns — do not add facts from your own knowledge. Cite the source "
        "of each claim inline like [kyoto]. If the passages don't cover the "
        "question, say so plainly instead of guessing."
    ),
    tools=[search_guides],
)
