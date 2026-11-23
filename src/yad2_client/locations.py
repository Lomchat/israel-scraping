"""City lookup, so users can write ``city="raanana"`` instead of numeric ids.

The table ships with the package (``data/cities.json``); regenerate it with
``scripts/update_cities.py``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources


@dataclass(frozen=True)
class City:
    id: str
    name_he: str
    name_en: str
    region_id: int | None
    area_id: int | None
    popularity: int = 0


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"[^0-9a-zא-ת]", "", text)


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(resources.files("yad2_client").joinpath("data/cities.json").read_text("utf-8"))


@lru_cache(maxsize=1)
def all_cities() -> tuple[City, ...]:
    return tuple(City(*row) for row in _data()["rows"])


def regions() -> dict[int, str]:
    """Region ids and their English names."""
    return {int(k): v for k, v in _data()["regions"].items()}


def search_cities(query: str, limit: int = 10) -> list[City]:
    """Cities whose id, Hebrew or English name matches ``query``, best matches first."""
    q = _norm(str(query))
    if not q:
        return []
    exact, prefix, contains = [], [], []
    for city in all_cities():
        names = (city.id.lstrip("0").lower(), _norm(city.name_en), _norm(city.name_he))
        if q.lstrip("0") in names[:1] or q in names[1:]:
            exact.append(city)
        elif any(n.startswith(q) for n in names[1:]):
            prefix.append(city)
        elif any(q in n for n in names[1:]):
            contains.append(city)
    ranked = [sorted(group, key=lambda c: -c.popularity) for group in (exact, prefix, contains)]
    return [c for group in ranked for c in group][:limit]


def find_city(query: str | int) -> City:
    """Best matching city for a name (Hebrew or English) or a Yad2 city id.

    :raises LookupError: nothing matches.
    """
    found = search_cities(str(query), limit=1)
    if not found:
        raise LookupError(f"no Yad2 city matches {query!r} (try `yad2 cities {query}`)")
    return found[0]
