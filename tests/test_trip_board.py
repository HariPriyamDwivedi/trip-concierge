"""Trip board: tool results mirrored into session state, the saved itinerary, and
chat messages (with cited sources) rebuilt from stored events. No API key needed.
"""

from types import SimpleNamespace

from google.adk.events import Event
from google.genai import types

from backend.agent_runner import turns_from_events
from trip_concierge.trip_board import DayPlan, record_trip_state, save_itinerary, trip_view


def _ctx():
    return SimpleNamespace(state={})


def _record(ctx, name, response):
    record_trip_state(SimpleNamespace(name=name), {}, ctx, response)


def test_tool_results_land_on_the_board():
    ctx = _ctx()
    _record(ctx, "find_attractions", {"found": True, "city": "Kyoto", "attractions": ["Gion"]})
    _record(ctx, "estimate_trip_cost", {"city": "Kyoto", "nights": 3, "travelers": 2,
                                        "daily_cost_usd": 140, "estimated_total_usd": 840})
    _record(ctx, "schedule_reminder", {"status": "scheduled", "id": 1, "message": "Book", "remind_at": "2027-03-01"})
    _record(ctx, "schedule_reminder", {"status": "scheduled", "id": 2, "message": "Pack", "remind_at": "2027-03-13"})
    _record(ctx, "send_itinerary", {"status": "dry_run", "to": "a@b.test", "subject": "Kyoto", "saved_to": "/x"})
    _record(ctx, "estimate_trip_cost", {"error": "nights and travelers must both be at least 1"})  # ignored
    _record(ctx, "find_attractions", {"found": False, "city": "Atlantis"})  # ignored

    board = trip_view(ctx.state)
    assert board["city"] == "Kyoto"
    assert board["attractions"] == {"city": "Kyoto", "items": ["Gion"]}
    assert board["budget"]["estimated_total_usd"] == 840
    assert [r["message"] for r in board["reminders"]] == ["Book", "Pack"]
    assert board["emails"] == [{"to": "a@b.test", "subject": "Kyoto", "status": "dry_run"}]  # no file path


def test_save_itinerary_accepts_models_and_dicts():
    ctx = _ctx()
    days = [DayPlan(title="Temples", stops=["Fushimi Inari", "Kinkaku-ji"]), {"title": "Gion", "stops": ["Gion"]}]
    assert save_itinerary("Kyoto", days, ctx) == {"status": "saved", "days": 2}
    assert trip_view(ctx.state)["itinerary"]["days"][0] == {"title": "Temples", "stops": ["Fushimi Inari", "Kinkaku-ji"]}


def _ev(author, inv, *parts):
    return Event(author=author, invocation_id=inv, content=types.Content(role="user" if author == "user" else "model", parts=list(parts)))


def test_turns_keep_only_cited_sources():
    guide_hits = {"result": [{"source": "kyoto", "text": "buses", "score": 0.3}, {"source": "lisbon", "text": "trams", "score": 0.1}]}
    web_hits = {"results": [{"title": "JNTO", "url": "https://jnto.test/visa", "content": "..."}]}
    events = [
        _ev("user", "i1", types.Part(text="How do I get around, and do I need a visa?")),
        _ev("concierge", "i1", types.Part(function_call=types.FunctionCall(name="search_guides", args={"query": "x"}))),
        _ev("concierge", "i1", types.Part(function_response=types.FunctionResponse(name="search_guides", response=guide_hits))),
        _ev("concierge", "i1", types.Part(function_response=types.FunctionResponse(name="web_search", response=web_hits))),
        _ev("concierge", "i1", types.Part(text="Take buses [guide: kyoto]. Visa: yes [https://jnto.test/visa].")),
        _ev("user", "i2", types.Part(text="thanks")),
        _ev("concierge", "i2", types.Part(text="You're welcome!")),
    ]
    msgs = turns_from_events(events)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[1]["sources"] == [
        {"kind": "guide", "label": "kyoto"},  # lisbon was retrieved but not cited
        {"kind": "web", "label": "JNTO", "url": "https://jnto.test/visa"},
    ]
    assert msgs[3] == {"role": "assistant", "text": "You're welcome!", "sources": []}
