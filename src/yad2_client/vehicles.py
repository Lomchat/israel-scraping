"""Vehicle listings: cars, motorcycles, scooters, trucks."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import TYPE_CHECKING, Any

from .locations import rank_matches
from .models import CarListing, Page
from .models import payload_data as _data

if TYPE_CHECKING:
    from .client import Yad2

CATEGORIES = ("cars", "motorcycles", "scooters", "trucks")


@dataclass(frozen=True)
class Manufacturer:
    id: int
    name_he: str
    name_en: str
    listings: int = 0  # number of car listings when the table was built


@lru_cache(maxsize=1)
def all_manufacturers() -> tuple[Manufacturer, ...]:
    raw = json.loads(resources.files("yad2_client").joinpath("data/manufacturers.json").read_text("utf-8"))
    return tuple(Manufacturer(*row) for row in raw["rows"])


def search_manufacturers(query: str, limit: int = 10) -> list[Manufacturer]:
    """Manufacturers whose id, Hebrew or English name matches ``query``, best matches first."""
    found = rank_matches(query, all_manufacturers(), lambda m: m.id, lambda m: (m.name_en, m.name_he),
                         lambda m: m.listings)
    return found[:limit]


def find_manufacturer(query: str | int) -> Manufacturer:
    """Best matching manufacturer for a name (Hebrew or English) or an id.

    :raises LookupError: nothing matches.
    """
    found = search_manufacturers(str(query), limit=1)
    if not found:
        raise LookupError(f"no manufacturer matches {query!r} (try `yad2 manufacturers {query}`)")
    return found[0]

# Python-friendly filter names -> API parameter names.
FILTERS = {
    "manufacturer": "manufacturer",
    "model": "model",
    "area": "area",
    "engine_type": "engineType",
    "gearbox": "gearBox",
    "seats": "seats",
    "family_type": "carFamilyType",
    "price_only": "priceOnly",
    # ranges: give a (min, max) tuple, None for an open bound
    "year": "year",
    "price": "price",
    "km": "km",
    "hand": "hand",
}
RANGES = {"year", "price", "km", "hand"}


def _range(value: Any) -> Any:
    if isinstance(value, (tuple, list)):
        low, high = value
        return f"{-1 if low is None else low}-{-1 if high is None else high}"
    return value


def build_params(filters: dict[str, Any]) -> dict[str, Any]:
    unknown = set(filters) - set(FILTERS)
    if unknown:
        raise TypeError(f"unknown filter(s): {', '.join(sorted(unknown))}; known: {', '.join(FILTERS)}")
    maker = filters.get("manufacturer")
    if isinstance(maker, str) and not maker.isdigit():
        filters = {**filters, "manufacturer": find_manufacturer(maker).id}
    return {FILTERS[k]: (_range(v) if k in RANGES else v) for k, v in filters.items()}


class Vehicles:
    def __init__(self, client: Yad2):
        self._client = client

    def search(self, category: str = "cars", *, page: int = 1, **filters: Any) -> Page[CarListing]:
        """One page of results (40 listings).

        :param category: ``"cars"``, ``"motorcycles"``, ``"scooters"`` or ``"trucks"``.
        :param filters: see ``FILTERS``, e.g. ``manufacturer="toyota", year=(2018, 2022), hand=(0, 2)``.
        """
        params = build_params(filters)
        params["page"] = page
        data = _data(self._client.get_json(f"/vehicles-feed/{category}", params))
        items = [CarListing.from_api(a) for a in data.get("ads") or [] if a.get("token")]
        pagination = data.get("pagination") or {}
        return Page(items, page, pagination.get("total"), pagination.get("totalPages"))

    def iter_search(
        self, category: str = "cars", *, max_pages: int | None = None, **filters: Any
    ) -> Iterator[CarListing]:
        """Every listing of a search, page after page, without duplicates."""
        seen: set[str] = set()
        page = 1
        while True:
            result = self.search(category, page=page, **filters)
            for listing in result.items:
                if listing.token not in seen:
                    seen.add(listing.token)
                    yield listing
            if page >= (result.total_pages or 0) or (max_pages is not None and page >= max_pages):
                return
            page += 1
