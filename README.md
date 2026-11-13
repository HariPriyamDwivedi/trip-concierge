# Trip Concierge

A small multi-agent trip-planning assistant built on [Google ADK](https://google.github.io/adk-docs/).
A coordinator agent understands what a traveller needs and delegates to three
specialists:

| Agent | Does | Tool |
|-------|------|------|
| `guide` | Suggests things to do | `find_attractions` |
| `budget` | Estimates trip cost | `estimate_trip_cost` |
| `planner` | Builds a day-by-day itinerary | `find_attractions` |

The tools run offline against a small curated dataset, so the structure and
logic are demoable without any API key. Running the agents (which call Gemini)
needs a `GOOGLE_API_KEY`.

The same two tools are also served over **MCP** (`mcp_server/`), so any MCP
client can use them. An alternative agent (`trip_concierge/mcp_agent.py`)
consumes them over MCP via ADK's `McpToolset` instead of in-process.

The budget specialist can also run as its own **A2A** service
(`budget_service.py`); `trip_concierge/a2a_agent.py` is a coordinator that calls
it remotely via `RemoteA2aAgent` while keeping `guide` and `planner` local.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the smoke + MCP tests (no key needed)
pytest

# poke the MCP tools directly, no LLM:
python mcp_playground.py

# to actually chat, add your key, then:
cp .env.example .env   # fill in GOOGLE_API_KEY
python run.py "3 nights in Kyoto — what should I do and what will it cost?"

# or the ADK dev UI:
adk web
```

### A2A variant (two terminals)

```bash
# terminal 1 — the budget specialist as an A2A service
uvicorn budget_service:app --host localhost --port 8001

# terminal 2 — a coordinator that calls it remotely
adk run trip_concierge.a2a_agent
```

## Layout

```
trip_concierge/
  agent.py      # coordinator + guide / budget / planner sub-agents (root_agent)
  mcp_agent.py  # same concierge, tools consumed over MCP (McpToolset)
  a2a_agent.py  # coordinator calling the budget specialist over A2A
  tools.py      # find_attractions, estimate_trip_cost + the seed dataset
mcp_server/
  server.py     # FastMCP server exposing the two tools over stdio
budget_service.py  # budget agent served as an A2A service (to_a2a)
run.py          # minimal CLI runner
mcp_playground.py  # list + call the MCP tools directly, no LLM
tests/          # structure, tool, MCP, and A2A tests
```

## Roadmap

- [x] Phase 1 — multi-agent core (coordinator + specialists)
- [x] Phase 2 — MCP server + MCP-consuming agent + playground
- [x] Phase 3 — A2A-served budget specialist
- [ ] Phase 4 — RAG over destination guides
- [ ] Phase 5 — calendar OAuth, itinerary email + reminders
- [ ] Phase 6 — web frontend
