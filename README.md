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

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the offline smoke tests (no key needed)
pytest

# to actually chat, add your key, then:
cp .env.example .env   # fill in GOOGLE_API_KEY
python run.py "3 nights in Kyoto — what should I do and what will it cost?"

# or the ADK dev UI:
adk web
```

## Layout

```
trip_concierge/
  agent.py    # coordinator + guide / budget / planner sub-agents (root_agent)
  tools.py    # find_attractions, estimate_trip_cost + the seed dataset
run.py        # minimal CLI runner
tests/        # structure + tool smoke tests
```

## Roadmap

This is Phase 1 (multi-agent core). Planned next: an MCP server exposing the
tools, an A2A-served budget specialist, RAG over destination guides, calendar
OAuth, itinerary email + reminders, and a small web frontend.
