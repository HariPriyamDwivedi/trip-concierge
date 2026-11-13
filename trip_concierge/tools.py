"""Tools for the trip concierge agents.

These run fully offline against a small curated dataset so the project is
demoable without any external API keys. Swap the dataset for a real places /
pricing API later without changing the agent wiring.
"""

# Per-city seed data: a few attractions and a rough daily cost (USD) for a
# mid-range traveller. Intentionally small and hand-authored.
_CITIES: dict[str, dict] = {
    "lisbon": {
        "attractions": [
            "Belém Tower and the Jerónimos Monastery",
            "Tram 28 through Alfama",
            "Time Out Market for dinner",
            "A day trip to Sintra",
        ],
        "daily_cost_usd": 110,
    },
    "kyoto": {
        "attractions": [
            "Fushimi Inari's torii gate trail",
            "Arashiyama bamboo grove",
            "Kinkaku-ji (the Golden Pavilion)",
            "An evening walk in Gion",
        ],
        "daily_cost_usd": 140,
    },
    "mexico city": {
        "attractions": [
            "Teotihuacan pyramids",
            "Frida Kahlo Museum in Coyoacán",
            "Chapultepec Castle and park",
            "Street tacos in Roma Norte",
        ],
        "daily_cost_usd": 85,
    },
}


def find_attractions(city: str) -> dict:
    """Look up notable attractions for a city.

    Args:
        city: The destination city name, e.g. "Kyoto".

    Returns:
        A dict with the matched city and a list of attractions, or a list of
        supported cities when the destination is not in the dataset.
    """
    key = city.strip().lower()
    entry = _CITIES.get(key)
    if entry is None:
        return {
            "found": False,
            "city": city,
            "supported_cities": sorted(c.title() for c in _CITIES),
        }
    return {"found": True, "city": city.title(), "attractions": entry["attractions"]}


def estimate_trip_cost(city: str, nights: int, travelers: int) -> dict:
    """Estimate a rough total trip cost from per-city daily rates.

    Args:
        city: The destination city name.
        nights: Number of nights staying.
        travelers: Number of travellers sharing the trip.

    Returns:
        A dict with the per-day rate and estimated total in USD, or an error
        when inputs are invalid or the city is unknown.
    """
    if nights < 1 or travelers < 1:
        return {"error": "nights and travelers must both be at least 1"}
    entry = _CITIES.get(city.strip().lower())
    if entry is None:
        return {
            "error": f"no pricing data for {city!r}",
            "supported_cities": sorted(c.title() for c in _CITIES),
        }
    daily = entry["daily_cost_usd"]
    total = daily * nights * travelers
    return {
        "city": city.title(),
        "daily_cost_usd": daily,
        "nights": nights,
        "travelers": travelers,
        "estimated_total_usd": total,
    }
