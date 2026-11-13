"""Live web search via Tavily, for what the curated data and guides can't know.

Opt-in: the concierge only gets this tool when TAVILY_API_KEY is set, so tests and
keyless runs never touch the network.
"""

import os


async def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web for current travel information (Tavily).

    Use for things that change or that the guides don't cover: opening hours,
    events on given dates, visa rules, weather, or cities outside the guides.

    Args:
        query: A specific search query, e.g. "Kyoto events late November 2026".
        max_results: How many results to return (1-10).

    Returns:
        {"results": [{title, url, content}]} — cite the url for each claim — or
        {"error": ...} if the search could not run.
    """
    from tavily import AsyncTavilyClient  # imported lazily: only needed with a key

    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return {"error": "web search is not configured (TAVILY_API_KEY is unset)"}
    try:
        resp = await AsyncTavilyClient(api_key=key).search(
            query=query, max_results=max(1, min(max_results, 10)), search_depth="basic"
        )
    except Exception as exc:  # network, quota or auth errors: let the agent carry on
        return {"error": f"web search failed: {exc}"}
    return {
        "results": [
            {"title": r.get("title", ""), "url": r["url"], "content": r.get("content", "")[:600]}
            for r in resp.get("results", [])
            if r.get("url")
        ]
    }
