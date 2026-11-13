"""Retriever tests: relevance ranking, citations, and the k limit (no API key)."""

from trip_concierge.rag import search_guides


def test_retrieves_the_right_guide():
    # City-specific queries should surface that city's guide first.
    assert search_guides("how do I get around Kyoto")[0]["source"] == "kyoto"
    assert search_guides("what should I eat in Lisbon")[0]["source"] == "lisbon"
    assert search_guides("altitude in Mexico City")[0]["source"] == "mexico_city"


def test_results_carry_a_citable_source_and_score():
    hits = search_guides("temples and shrines", k=3)
    assert hits
    for hit in hits:
        assert hit["source"] and hit["text"]
        assert hit["score"] > 0


def test_respects_k_limit():
    assert len(search_guides("Lisbon tram food fado", k=2)) <= 2


def test_no_match_returns_empty():
    assert search_guides("quantum chromodynamics spreadsheet") == []
