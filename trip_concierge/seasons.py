"""Season-wise destination picks: where is good (and what to avoid) in a month.

A small curated table of popular Indian and international destinations with their
best months and why. It is general guidance; the agent uses web_search (when
configured) for specifics like this year's festival dates or road openings.
"""

import calendar

# name, region, best months (1-12), why it's good then, months to avoid + why
DESTINATIONS = [
    ("Goa", "India", [11, 12, 1, 2], "dry, sunny beach weather and the shacks are open", [6, 7, 8, 9], "monsoon: rough seas, many shacks closed"),
    ("Jaipur", "India", [10, 11, 12, 1, 2, 3], "pleasant days for forts and bazaars", [4, 5, 6], "very hot, often above 40°C"),
    ("Udaipur", "India", [9, 10, 11, 12, 1, 2, 3], "lakes are full after the monsoon, cool evenings", [4, 5, 6], "hot and the lakes run low"),
    ("Kerala", "India", [9, 10, 11, 12, 1, 2, 3], "backwaters and hills after the rains, comfortable heat", [6, 7], "peak monsoon rain"),
    ("Rishikesh", "India", [9, 10, 11, 2, 3, 4], "rafting season and mild weather", [7, 8], "monsoon: rafting closed, landslide risk"),
    ("Manali", "India", [3, 4, 5, 6, 12, 1, 2], "spring–summer for valleys and treks; Dec–Feb for snow", [7, 8], "monsoon landslides on mountain roads"),
    ("Leh-Ladakh", "India", [5, 6, 7, 8, 9], "high passes open, clear skies", [12, 1, 2], "severe cold; many roads shut"),
    ("Darjeeling", "India", [3, 4, 5, 10, 11], "tea gardens in bloom; clear Kanchenjunga views in autumn", [7, 8], "monsoon mist and rain"),
    ("Andaman Islands", "India", [11, 12, 1, 2, 3, 4], "calm seas for diving and ferries", [6, 7, 8, 9], "monsoon: rough seas, ferry cancellations"),
    ("Varanasi", "India", [10, 11, 12, 1, 2, 3], "cool mornings on the ghats; Dev Deepawali in November", [5, 6], "intense heat"),
    ("Kyoto", "Japan", [3, 4, 10, 11], "cherry blossom in spring, maple colour in autumn", [7, 8], "hot and humid"),
    ("Lisbon", "Portugal", [3, 4, 5, 9, 10], "warm but not hot, fewer crowds than summer", [], ""),
    ("Mexico City", "Mexico", [3, 4, 5, 11, 12], "dry season, warm days", [7, 8, 9], "daily afternoon downpours"),
    ("Bali", "Indonesia", [4, 5, 6, 7, 8, 9, 10], "dry season for beaches and rice terraces", [12, 1, 2], "wet season"),
    ("Dubai", "UAE", [11, 12, 1, 2, 3], "warm, comfortable days for the desert and the beach", [6, 7, 8], "extreme heat"),
    ("Swiss Alps (Interlaken)", "Switzerland", [6, 7, 8, 9, 12, 1, 2, 3], "summer hiking or winter skiing", [4, 11], "between seasons: many lifts and huts closed"),
]

SEASONS = {
    "winter": [12, 1, 2],
    "spring": [3, 4, 5],
    "summer": [6, 7, 8],
    "monsoon": [6, 7, 8, 9],
    "autumn": [9, 10, 11],
    "fall": [9, 10, 11],
}
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m} | {
    m.lower(): i for i, m in enumerate(calendar.month_abbr) if m
}


def _months(when: str) -> list[int]:
    key = str(when).strip().lower()
    if key in SEASONS:
        return SEASONS[key]
    if key in _MONTHS:
        return [_MONTHS[key]]
    if key.isdigit() and 1 <= int(key) <= 12:
        return [int(key)]
    raise ValueError("give a month (e.g. November or 11) or a season (winter, spring, summer, monsoon, autumn)")


def seasonal_destinations(when: str) -> dict:
    """Which destinations are in season in a given month or season, and which to avoid.

    Use this when the traveller asks where to go at a certain time of year, or
    whether their dates suit a place.

    Args:
        when: A month (e.g. "November", "nov", "11") or a season ("winter", "spring",
            "summer", "monsoon", "autumn").

    Returns:
        {"months": [...], "in_season": [{name, region, why}], "avoid": [{name, region, why}]}
        from a curated table of popular destinations (general guidance).
    """
    try:
        months = _months(when)
    except ValueError as exc:
        return {"error": str(exc)}
    in_season, avoid = [], []
    for name, region, best, why, bad, bad_why in DESTINATIONS:
        if any(m in best for m in months):
            in_season.append({"name": name, "region": region, "why": why})
        elif any(m in bad for m in months):
            avoid.append({"name": name, "region": region, "why": bad_why})
    return {"months": [calendar.month_name[m] for m in months], "in_season": in_season, "avoid": avoid}
