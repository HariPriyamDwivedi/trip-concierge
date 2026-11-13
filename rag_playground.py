"""RAG playground: run the retriever on a few queries, no LLM needed.

    python rag_playground.py
    python rag_playground.py "best time to see autumn leaves"
"""

import sys

from trip_concierge.rag import search_guides

QUERIES = [
    "how do I get around Kyoto",
    "what should I eat in Lisbon",
    "altitude and best season in Mexico City",
]


def show(query: str) -> None:
    print(f"\nQ: {query}")
    for hit in search_guides(query, k=2):
        print(f"  [{hit['source']}] ({hit['score']}) {hit['text'][:90]}...")


if __name__ == "__main__":
    queries = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else QUERIES
    for q in queries:
        show(q)
