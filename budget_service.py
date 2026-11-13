"""Run the budget specialist as a standalone A2A service.

Reuses the Phase 1 budget agent and exposes it over A2A so the coordinator can
call it across the network instead of in-process.

    uvicorn budget_service:app --host localhost --port 8001

Its agent card is then at
    http://localhost:8001/.well-known/agent-card.json
"""

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from trip_concierge.agent import make_budget

# Serve a fresh (unparented) budget agent. to_a2a returns a Starlette ASGI app;
# `host`/`port` only set the advertised card URL — the actual bind address is
# chosen by the uvicorn command above.
app = to_a2a(make_budget(), host="localhost", port=8001)
