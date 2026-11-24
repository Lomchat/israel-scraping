"""City lookup, so users can write ``city="raanana"`` instead of numeric ids.

The table ships with the package (``data/cities.json``); regenerate it with
``scripts/update_cities.py``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, TypeVar

T = TypeVar("T")


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
    return json.loads(resources.files("israel_scraping").joinpath("data/cities.json").read_text("utf-8"))


@lru_cache(maxsize=1)
def all_cities() -> tuple[City, ...]:
    return tuple(City(*row) for row in _data()["rows"])


def regions() -> dict[int, str]:
    """Region ids and their English names."""
    return {int(k): v for k, v in _data()["regions"].items()}


def rank_matches(
    query: str | int,
    items: Iterable[T],
    ident: Callable[[T], Any],
    names: Callable[[T], Iterable[str]],
    weight: Callable[[T], int],
) -> list[T]:
    """Items whose id or one of whose names matches ``query``: exact matches, then names starting
    with it, then names containing it; most popular first within each group."""
    q = _norm(str(query))
    if not q:
        return []
    exact, prefix, contains = [], [], []
    for item in items:
        normalized = [n for n in (_norm(x) for x in names(item)) if n]
        if q.lstrip("0") == str(ident(item)).lstrip("0").lower() or q in normalized:
            exact.append(item)
        elif any(n.startswith(q) for n in normalized):
            prefix.append(item)
        elif any(q in n for n in normalized):
            contains.append(item)
    return [x for group in (exact, prefix, contains) for x in sorted(group, key=lambda x: -weight(x))]


def search_cities(query: str, limit: int = 10) -> list[City]:
    """Cities whose id, Hebrew or English name matches ``query``, best matches first."""
    found = rank_matches(query, all_cities(), lambda c: c.id, lambda c: (c.name_en, c.name_he),
                         lambda c: c.popularity)
    return found[:limit]


def find_city(query: str | int) -> City:
    """Best matching city for a name (Hebrew or English) or a Yad2 city id.

    :raises LookupError: nothing matches.
    """
    found = search_cities(str(query), limit=1)
    if not found:
        raise LookupError(f"no Yad2 city matches {query!r} (try `yad2 cities {query}`)")
    return found[0]
