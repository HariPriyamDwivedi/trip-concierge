"""The traveller's uploaded files: text extraction and the search tool over them.

Uploads are stored as ADK artifacts of the chat session (see web/agent_runner.py),
already converted to plain text, so `search_my_documents` only reads the files of
the conversation it runs in. Ranking reuses the guides' TF-IDF retriever.
"""

import io
from pathlib import Path

from google.adk.tools.tool_context import ToolContext

from .rag import rank_passages

ALLOWED_SUFFIXES = {".txt", ".md", ".pdf"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 50  # bounds the work a hostile or huge PDF can cause
_WINDOW_WORDS = 120


def extract_text(filename: str, data: bytes) -> str:
    """Plain text of an uploaded .txt / .md / .pdf file. Raises ValueError if unusable."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported file type {suffix or '(none)'}; use .txt, .md or .pdf")
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            pages = PdfReader(io.BytesIO(data)).pages[:MAX_PDF_PAGES]
            text = "\n\n".join(page.extract_text() or "" for page in pages)
        except Exception as exc:  # pypdf raises many types for broken files
            raise ValueError(f"could not read PDF: {exc}") from exc
    else:
        text = data.decode("utf-8", errors="replace")
    if not text.strip():
        raise ValueError("no readable text in file (scanned PDFs are not supported)")
    return text


def chunk(source: str, text: str) -> list[dict]:
    """Paragraphs, with long ones (common in PDFs) cut into ~120-word windows."""
    chunks = []
    for para in text.split("\n\n"):
        words = para.split()
        for i in range(0, len(words), _WINDOW_WORDS):
            chunks.append({"source": source, "text": " ".join(words[i : i + _WINDOW_WORDS])})
    return chunks


async def search_my_documents(query: str, tool_context: ToolContext, k: int = 3) -> dict:
    """Search the files the traveller uploaded in this chat (bookings, tickets, notes).

    Args:
        query: What to look for, e.g. "hotel check-in time" or "flight number".
        k: Maximum number of passages to return.

    Returns:
        The uploaded file names and the most relevant passages ({source, text,
        score}); cite `source` as the file name. Empty passages mean no match.
    """
    names = await tool_context.list_artifacts()
    chunks: list[dict] = []
    for name in names:
        part = await tool_context.load_artifact(name)
        if part and part.inline_data and part.inline_data.data:
            chunks.extend(chunk(name, part.inline_data.data.decode("utf-8", errors="replace")))
    return {"documents": names, "passages": rank_passages(chunks, query, k)}
