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

A **RAG** destination expert (`trip_concierge/rag_agent.py`) answers from a small
set of curated guides in `data/guides/`, retrieving passages with a
dependency-free TF-IDF retriever (`trip_concierge/rag.py`) and citing the source
of each claim.

A fuller concierge (`trip_concierge/concierge_agent.py`) adds **calendar, email
and reminders**. Everything is safe by default: the email tool **dry-runs** to
`outbox/` and sends nothing unless you explicitly opt in with SMTP creds; the
calendar reads a local stub unless you configure real **Google OAuth**
(`trip_concierge/oauth.py`, opt-in); reminders persist to a local JSON store.

Finally, a small **FastAPI backend + browser chat UI** (`web/`) makes the whole
thing demoable: `uvicorn web.app:app --port 8000`, then open
`http://localhost:8000`.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the smoke + MCP tests (no key needed)
pytest

# poke the MCP tools directly, no LLM:
python mcp_playground.py

# see the RAG retriever rank guide passages, no LLM:
python rag_playground.py "how do I get around Kyoto"

# to actually chat, add your key, then:
cp .env.example .env   # fill in GOOGLE_API_KEY
python run.py "3 nights in Kyoto — what should I do and what will it cost?"

# or the ADK dev UI:
adk web

# or the web app (chat UI in the browser):
uvicorn web.app:app --port 8000   # then open http://localhost:8000
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
  rag_agent.py  # destination expert answering from guides, with citations
  rag.py        # dependency-free TF-IDF retriever (search_guides)
  concierge_agent.py  # Phase 5: itinerary + calendar + email + reminders
  calendar.py   # free/busy (local stub default, Google OAuth opt-in)
  notifications.py    # itinerary email (dry-run by default, never auto-sends)
  reminders.py  # local reminder store
  oauth.py      # testable OAuth 2.0 helper (opt-in Google flow)
  tools.py      # find_attractions, estimate_trip_cost + the seed dataset
data/guides/    # the RAG corpus (curated markdown destination guides)
data/calendar_stub.json  # sample busy slots for the calendar stub
mcp_server/
  server.py     # FastMCP server exposing the two tools over stdio
budget_service.py  # budget agent served as an A2A service (to_a2a)
web/
  app.py        # FastAPI backend (injectable reply) + routes
  agent_runner.py  # session-aware ADK runner for the web layer
  static/index.html  # dependency-free browser chat UI
run.py          # minimal CLI runner
mcp_playground.py  # list + call the MCP tools directly, no LLM
rag_playground.py  # rank guide passages for a query, no LLM
tests/          # structure, tool, MCP, A2A, RAG, Phase 5, and web tests
```

## Roadmap

- [x] Phase 1 — multi-agent core (coordinator + specialists)
- [x] Phase 2 — MCP server + MCP-consuming agent + playground
- [x] Phase 3 — A2A-served budget specialist
- [x] Phase 4 — RAG over destination guides (TF-IDF retriever + cited answers)
- [x] Phase 5 — calendar OAuth, itinerary email (dry-run) + reminders
- [x] Phase 6 — FastAPI backend + browser chat UI
