"""Agentic-RAG pieces: upload text extraction, searching uploaded files, Tavily
web search (faked), and the concierge's tool wiring. No API key or network needed.
"""

import asyncio
import os
import sys
import types as pytypes

import pytest
from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService

from trip_concierge import websearch
from trip_concierge.concierge_agent import root_agent
from trip_concierge.documents import chunk, extract_text, search_my_documents
from web.agent_runner import APP, ConciergeRunner


def _pdf_with_text(text: str) -> bytes:
    """A minimal one-page PDF with `text`, offsets computed so any reader accepts it."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def test_extract_text_txt_pdf_and_rejections():
    assert extract_text("notes.md", b"Hotel check-in 3pm") == "Hotel check-in 3pm"
    assert "Flight JL123" in extract_text("ticket.pdf", _pdf_with_text("Flight JL123 to Osaka"))
    for name, data in [("x.exe", b"MZ"), ("empty.txt", b"  \n"), ("bad.pdf", b"not a pdf")]:
        with pytest.raises(ValueError):
            extract_text(name, data)


def test_chunk_splits_long_paragraphs():
    text = " ".join(f"w{i}" for i in range(300))  # one 300-word paragraph, like a PDF page
    parts = chunk("doc.pdf", text)
    assert [len(p["text"].split()) for p in parts] == [120, 120, 60]
    assert {p["source"] for p in parts} == {"doc.pdf"}


class _FakeToolContext:
    """Just the artifact calls search_my_documents uses."""

    def __init__(self, files: dict[str, str]):
        from google.genai import types

        self._parts = {
            n: types.Part.from_bytes(data=t.encode(), mime_type="text/plain") for n, t in files.items()
        }

    async def list_artifacts(self):
        return list(self._parts)

    async def load_artifact(self, name):
        return self._parts.get(name)


def test_search_my_documents_ranks_uploaded_files():
    ctx = _FakeToolContext(
        {
            "hotel.txt": "Ryokan Sakura. Check-in from 3pm, breakfast included.",
            "flight.md": "Flight JL123 departs Tokyo Haneda at 08:15.",
        }
    )
    got = asyncio.run(search_my_documents("what time is check-in", ctx))
    assert set(got["documents"]) == {"hotel.txt", "flight.md"}
    assert got["passages"][0]["source"] == "hotel.txt"
    assert asyncio.run(search_my_documents("anything", _FakeToolContext({})))["passages"] == []


def test_upload_is_stored_for_that_session_only():
    artifacts = InMemoryArtifactService()
    runner = ConciergeRunner(InMemorySessionService(), artifacts)
    stored = asyncio.run(runner.upload("web-a", "hotel.txt", "Check-in 3pm"))
    assert stored["filename"] == "hotel.txt"

    async def keys(client):
        return await artifacts.list_artifact_keys(app_name=APP, user_id=client, session_id=client)

    assert asyncio.run(keys("web-a")) == ["hotel.txt"]
    assert asyncio.run(keys("web-b")) == []


def test_web_search_without_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert "error" in asyncio.run(websearch.web_search("kyoto events"))


def _fake_tavily(monkeypatch, search):
    class Client:
        def __init__(self, api_key):
            assert api_key == "tvly-test"

        async def search(self, **kwargs):
            return await search(**kwargs)

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setitem(sys.modules, "tavily", pytypes.SimpleNamespace(AsyncTavilyClient=Client))


def test_web_search_shapes_results(monkeypatch):
    async def search(query, max_results, search_depth):
        assert max_results == 10  # clamped from 50
        return {"results": [{"title": "Gion", "url": "https://x.test/gion", "content": "c" * 900, "score": 0.9}]}

    _fake_tavily(monkeypatch, search)
    got = asyncio.run(websearch.web_search("kyoto", max_results=50))
    assert got == {"results": [{"title": "Gion", "url": "https://x.test/gion", "content": "c" * 600}]}


def test_web_search_reports_failures(monkeypatch):
    async def search(**_):
        raise RuntimeError("quota exceeded")

    _fake_tavily(monkeypatch, search)
    assert "quota exceeded" in asyncio.run(websearch.web_search("kyoto"))["error"]


def test_concierge_retrieval_tools():
    names = {getattr(t, "__name__", "") for t in root_agent.tools}
    assert {"search_my_documents", "search_guides"} <= names
    # Web search is offered only when a Tavily key is configured.
    assert ("web_search" in names) == bool(os.getenv("TAVILY_API_KEY"))
