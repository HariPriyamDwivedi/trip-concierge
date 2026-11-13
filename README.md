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


The app is split into a **backend** (`backend/`, FastAPI, API only under
`/api`) and a **frontend** (`frontend/`, React + Vite, served by nginx). The UI
pairs a chat with a persistent **trip board** — destination, budget with its
arithmetic, things to do, a day-by-day itinerary, documents, reminders and email
drafts — which the agent fills as it works and which survives reloads.

The web concierge answers questions by **agentic RAG**: it picks a source per
question — the traveller's **uploaded files** (📎: .txt, .md or .pdf up to 5 MB,
private to that trip), the curated **guides**, or the **web via Tavily** (only
when `TAVILY_API_KEY` is set) — judges whether the passages answer the question,
rewrites the query or switches source if not, and answers only from what it
retrieved. Each answer shows the sources it cited.

**Mail and Calendar are connectors**, like in Claude Desktop: switched on per
trip under *Connectors*, and only for the trip — Calendar checks free time around
travel dates (read-only), Mail sends the itinerary (it never reads the inbox).
**Sign in with Google or Microsoft** to use your own calendar and mailbox, with
the smallest scopes (`calendar.freebusy` / `Calendars.Read`, `gmail.send` /
`Mail.Send`); tokens are encrypted with `ENCRYPTION_KEY` and never reach the
browser. Without sign-in they run on demo data (a sample calendar; email drafts
saved to `outbox/`). Until a connector is on, the agent can't use its tool, and it
asks before sending from your own mailbox.

**Trip alerts**: add trains, flights, buses, stays and activities to the trip
(in the UI, or by telling/uploading them to the concierge) and the bell shows the
alerts travel apps like ixigo, ConfirmTkt and hostel apps send — chart prepared
(~4 h before a train), time to board, a wake-up before your stop, web check-in,
check-in/check-out, activity start, and "your trip starts tomorrow". With browser
notifications allowed, they pop up while the app is open.

**Season-wise picks**: the welcome screen shows destinations in season this
month, and the concierge answers "where should I go in December?" from a curated
best-months table (`seasonal_destinations`).

Replies **stream** in as Gemini writes them, with a live "Searching your files…"
style status while tools run.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the tests (no key needed)
python -m pytest

# poke the MCP tools directly, no LLM:
python mcp_playground.py

# see the RAG retriever rank guide passages, no LLM:
python rag_playground.py "how do I get around Kyoto"

# to actually chat, add your key, then:
cp .env.example .env   # fill in GOOGLE_API_KEY
python run.py "3 nights in Kyoto — what should I do and what will it cost?"

# or the ADK dev UI:
adk web

# other variants: pick the agent module with TRIP_AGENT
TRIP_AGENT=trip_concierge.rag_agent python run.py "how do I get around Kyoto?"
```

`run.py` and `uvicorn` don't read `.env` themselves; export it first with
`set -a; source .env; set +a` (Docker Compose loads it for you).

### Web app without Docker (two terminals)

```bash
# terminal 1 — the API
uvicorn backend.app:app --port 8000

# terminal 2 — the UI with hot reload; /api is proxied to :8000
cd frontend && npm install && npm run dev   # then open http://localhost:5173
```

### A2A variant (two terminals)

```bash
# terminal 1 — the budget specialist as an A2A service
uvicorn budget_service:app --host localhost --port 8001

# terminal 2 — a coordinator that calls it remotely
TRIP_AGENT=trip_concierge.a2a_agent python run.py "4 nights in Lisbon for 2, cost?"
```

### Docker Compose

| Service | Port | What |
|---|---|---|
| `frontend` | 8080 | React app (nginx); proxies `/api` to `api` |
| `api` | 8000 | FastAPI backend |
| `budget` | 8001 | A2A budget service |
| `postgres` | 5433 (localhost only) | chat sessions + trip boards (`DatabaseSessionService`) |

`api` and `budget` read `GOOGLE_API_KEY` (and optional `TAVILY_API_KEY`) from
`.env`. Outside Compose, set `SESSION_DB_URL` to use a database; unset, sessions
stay in memory.

```bash
cp .env.example .env              # fill in GOOGLE_API_KEY
docker compose up -d --build      # then open http://localhost:8080

# no key needed
docker compose run --rm --no-deps api python -m pytest
docker compose exec api python mcp_playground.py
docker compose exec api python rag_playground.py "how do I get around Kyoto"
curl localhost:8000/api/health
curl localhost:8001/.well-known/agent-card.json

# needs the key: the UI at http://localhost:8080, or the API directly
curl -X POST localhost:8000/api/upload -F session_id=demo -F file=@booking.pdf
curl -X POST localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"message":"3 nights in Kyoto for 2 — what to do and cost?","session_id":"demo"}'
curl localhost:8000/api/sessions/demo   # messages, trip board, documents, connectors
docker compose exec -e TRIP_AGENT=trip_concierge.a2a_agent api python run.py "4 nights in Lisbon for 2, cost?"

docker compose exec api ls outbox  # dry-run itinerary emails land here
docker compose exec postgres psql -U trip -d trip_concierge -c "select user_id, id from sessions"
docker compose down                # add -v to also delete stored sessions and uploads
```

## API

| Route | Does |
|---|---|
| `GET /api/health` | liveness |
| `GET /api/sessions/{id}` | `{messages, trip, documents, connectors, notifications}` — everything the UI shows |
| `POST /api/chat` | `{session_id, message}` → `{reply, sources, trip}` |
| `POST /api/chat/stream` | same body; server-sent events `tool`, `delta`, `done` (or `error`) |
| `POST /api/upload` | multipart `session_id`, `file` → `{filename, chars, documents}` |
| `PUT /api/sessions/{id}/connectors/{calendar\|mail}` | `{connected}` → connectors |
| `DELETE /api/sessions/{id}/connectors/{connector}/account` | sign out of Google/Microsoft |
| `GET /api/oauth/{google\|microsoft}/start?session_id=&connector=` | redirect to the provider's sign-in |
| `GET /oauth/callback` | provider redirect (nginx → `/api/oauth/callback`) |
| `POST /api/sessions/{id}/items` | add a train/flight/bus/stay/activity → `{trip, notifications}` |
| `DELETE /api/sessions/{id}/items/{item_id}` | remove it |
| `GET /api/seasonal?when=November` | destinations in season / to avoid (month or season) |

## Layout

```
trip_concierge/
  agent.py      # coordinator + guide / budget / planner sub-agents (root_agent)
  mcp_agent.py  # same concierge, tools consumed over MCP (McpToolset)
  a2a_agent.py  # coordinator calling the budget specialist over A2A
  rag_agent.py  # destination expert answering from guides, with citations
  rag.py        # dependency-free TF-IDF retriever (search_guides, rank_passages)
  documents.py  # upload text extraction + search_my_documents tool
  websearch.py  # Tavily web_search tool (opt-in via TAVILY_API_KEY)
  concierge_agent.py  # web concierge: itinerary, cost, agentic RAG, connectors, reminders
  trip_board.py # trip board state: save_itinerary + after-tool callback
  connectors.py # Mail / Calendar connectors: per-trip switch + tool guard
  accounts.py   # Google / Microsoft sign-in (PKCE), encrypted tokens, refresh
  timeline.py   # trip timeline (add_trip_item) and the alerts derived from it
  seasons.py    # best-months table + seasonal_destinations tool
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
backend/
  app.py        # FastAPI API (/api/...), injectable service for tests
  agent_runner.py  # ADK runner: sessions (Postgres or memory), uploads, trip view
frontend/       # React + Vite UI; Dockerfile builds it and serves it with nginx
  src/components/  # Chat, TripBoard, Timeline, Notifications, Connectors
run.py          # minimal CLI runner
mcp_playground.py  # list + call the MCP tools directly, no LLM
rag_playground.py  # rank guide passages for a query, no LLM
tests/          # structure, tools, MCP, A2A, RAG, API, sessions, trip board, connectors
```

## How a request flows

> **"Plan 3 nights in Kyoto for 2 — what should we do and what will it cost?"**

```
Browser (React)         nginx (frontend)     FastAPI (backend)       ADK runner                Gemini + tools
 1. POST /api/chat ──────▶ proxy /api ───────▶ chat() ──────────────▶ run_async(concierge) ────▶ model plans
                                                                       │◀── find_attractions("Kyoto")
                                                                       │◀── estimate_trip_cost("Kyoto", 3, 2)
                                                                       │◀── save_itinerary(...)
                                                                  2. after-tool callback writes
                                                                     budget / attractions / days
                                                                     into session state (Postgres)
                                                                  3. messages + cited sources rebuilt
                                                                     from the stored events
 4. {reply, sources, trip} ◀────────────────────────────────────────┘
 5. chat shows the reply + source chips; the trip board re-renders from `trip`
```

On reload the UI calls `GET /api/sessions/{id}` and gets the same conversation,
board and connector switches back. Side-effecting actions stay safe:
`schedule_reminder` writes to a local store, `send_itinerary` **dry-runs to
`outbox/`**, and both mail and calendar tools need their connector switched on.

## Roadmap

- [x] Phase 1 — multi-agent core (coordinator + specialists)
- [x] Phase 2 — MCP server + MCP-consuming agent + playground
- [x] Phase 3 — A2A-served budget specialist
- [x] Phase 4 — RAG over destination guides (TF-IDF retriever + cited answers)
- [x] Phase 5 — calendar OAuth, itinerary email (dry-run) + reminders
- [x] Phase 6 — FastAPI backend + browser chat UI
- [x] Phase 7 — agentic RAG (files, guides, Tavily), uploads, Postgres sessions
- [x] Phase 8 — separate React frontend with trip board, Mail/Calendar connectors
- [x] Phase 9 — streaming replies, Google/Microsoft sign-in for connectors,
  trip alerts (boarding, arrival, check-in, activities), season-wise picks
- [ ] Next — push alerts when the app is closed (service worker + Web Push), live
  PNR / train running status from a rail data API
