"""Lightweight retrieval over the destination guides (the RAG retriever).

A dependency-free TF-IDF cosine retriever over paragraph-sized chunks of the
markdown guides in data/guides. It is deterministic and runs with no API key,
which keeps retrieval testable on its own. Swap `search_guides` for an embedding
/ vector-store backend later without touching the agent that calls it.
"""

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

_GUIDES_DIR = Path(__file__).resolve().parent.parent / "data" / "guides"
_TOKEN = re.compile(r"[a-z]{2,}")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _load_chunks() -> list[dict]:
    """Each non-empty paragraph becomes a chunk tagged with its source guide."""
    chunks: list[dict] = []
    for path in sorted(_GUIDES_DIR.glob("*.md")):
        source = path.stem
        for para in path.read_text(encoding="utf-8").split("\n\n"):
            if para.lstrip().startswith("#"):
                continue  # skip markdown headings; keep only prose passages
            text = " ".join(para.split())
            if text:
                chunks.append({"source": source, "text": text})
    return chunks


@lru_cache(maxsize=1)
def _index() -> tuple:
    """Build and cache (chunks, idf, chunk_vectors). Cheap for this corpus."""
    chunks = _load_chunks()
    n = len(chunks)
    tokenised = [_tokens(c["text"]) for c in chunks]

    df: Counter = Counter()
    for toks in tokenised:
        df.update(set(toks))
    idf = {term: math.log((n + 1) / (freq + 1)) + 1 for term, freq in df.items()}

    vectors = [{t: tf * idf[t] for t, tf in Counter(toks).items()} for toks in tokenised]
    return chunks, idf, vectors


def _cosine(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    dot = sum(w * b.get(t, 0.0) for t, w in a.items())
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def search_guides(query: str, k: int = 3) -> list[dict]:
    """Retrieve the most relevant destination-guide passages for a query.

    Args:
        query: What the traveller wants to know, e.g. "getting around Kyoto".
        k: Maximum number of passages to return.

    Returns:
        A list of {source, text, score}, most relevant first. `source` is the
        guide to cite (e.g. "kyoto"). Empty if nothing matches.
    """
    chunks, idf, vectors = _index()
    q = {t: tf * idf[t] for t, tf in Counter(_tokens(query)).items() if t in idf}
    scored = [
        {"source": chunks[i]["source"], "text": chunks[i]["text"], "score": round(s, 4)}
        for i, vec in enumerate(vectors)
        if (s := _cosine(q, vec)) > 0
    ]
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[: max(1, k)]
