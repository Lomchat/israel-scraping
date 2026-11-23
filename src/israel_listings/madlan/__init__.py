"""Madlan (madlan.co.il): real-estate listings through the GraphQL API the website uses.

The website sits behind Cloudflare and PerimeterX, but its API answers plain HTTP requests that
carry the headers the site sends (``x-source: web``). One request returns up to 1,000 listings.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

from ..errors import ApiError
from ..http import HttpClient, log
from ..locations import find_city
from ..models import Page
from . import queries
from .models import MadlanListing

SITE = "https://www.madlan.co.il"
HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/json",
    "Origin": SITE,
    "Referer": SITE + "/",
    # Without these two, the API answers "sorry a1" (or Cloudflare challenges the request).
    "x-source": "web",
    "x-requested-with": "XMLHttpRequest",
}
DEALS = {"sale": "unitBuy", "buy": "unitBuy", "forsale": "unitBuy", "rent": "unitRent"}
SORTS = {
    "date": [{"field": "date", "order": "desc"}],
    "price-asc": [{"field": "price", "order": "asc"}],
    "price-desc": [{"field": "price", "order": "desc"}],
    "size-desc": [{"field": "size", "order": "desc"}],
}
RANGES = {  # filter pairs -> GraphQL range variable
    ("min_price", "max_price"): "priceRange",
    ("min_rooms", "max_rooms"): "roomsRange",
    ("min_sqm", "max_sqm"): "areaRange",
    ("min_floor", "max_floor"): "floorRange",
}
AMENITIES = {  # same names as the Yad2 filters where they mean the same thing
    "parking": "parking", "elevator": "elevator", "balcony": "balcony", "shelter": "secureRoom",
    "air_conditioner": "airConditioner", "accessibility": "accessible", "furniture": "furnished",
    "pets": "unitPetsAllowed", "storage": "storage", "garage": "garage", "pool": "pool", "gym": "gym",
    "doorman": "doorman", "outdoor_space": "outdoorSpace", "roofdeck": "roofdeck",
}
OPTIONS = {"seller_types": "sellerType", "conditions": "generalCondition", "price_drop": "priceDrop",
           "created_within_days": "creationDaysRange", "only_immediate": "onlyImmediate", "no_fee": "noFee"}
FILTERS = sorted({k for pair in RANGES for k in pair} | set(AMENITIES) | set(OPTIONS) | {"sort"})
# The API pages its results in steps of 34 listings, whatever ``offset`` says: the real start is
# (offset // limit) * 34. (The answer's cursor is no help: it says 1000 on the first page, 34 after.)
STEP = 34
OVERLAP = 100  # listings re-read around page boundaries, where the order may shift slightly


def is_blocked(resp: Any) -> bool:
    """Cloudflare (challenge, rate limit) or PerimeterX answered instead of the API."""
    if 300 <= resp.status_code < 400 or resp.status_code == 429:
        return True
    head = (resp.text or "")[:5000]
    if "Just a moment" in head or "challenge-platform" in head or "px-captcha" in head or "_pxAppId" in head:
        return True
    return resp.status_code == 403 and "json" not in (resp.headers.get("content-type") or "")


def build_variables(filters: dict[str, Any]) -> dict[str, Any]:
    """Translate keyword filters into GraphQL variables."""
    unknown = set(filters) - set(FILTERS)
    if unknown:
        raise TypeError(f"unknown filter(s): {', '.join(sorted(unknown))}; known: {', '.join(FILTERS)}")
    variables: dict[str, Any] = {}
    for (low, high), name in RANGES.items():
        if filters.get(low) is not None or filters.get(high) is not None:
            variables[name] = [filters.get(low), filters.get(high)]
    amenities = {AMENITIES[k]: True for k in AMENITIES if filters.get(k)}
    if amenities:
        variables["amenities"] = amenities
    for key, name in OPTIONS.items():
        value = filters.get(key)
        if value is not None and value is not False:
            variables[name] = list(value) if key in ("seller_types", "conditions") else value
    sort = filters.get("sort") or "date"
    variables["sort"] = SORTS[sort] if isinstance(sort, str) else sort
    return variables


class Madlan:
    """Client for Madlan.

    >>> madlan = Madlan()
    >>> for listing in madlan.iter_search("rent", city="raanana", max_price=8000): ...

    Options are those of :class:`israel_listings.http.HttpClient` (``delay``, ``proxy``,
    ``fallback_proxies``, ``block_wait``...).
    """

    site = "madlan"

    def __init__(self, **options: Any):
        options.setdefault("delay", 1.0)
        options.setdefault("block_wait", 20.0)  # Cloudflare's rate limit lasts seconds
        self.http = HttpClient(base_url=SITE, headers=HEADERS, is_blocked=is_blocked, site="madlan", **options)
        self._location_ids: dict[tuple, str | None] = {}

    @property
    def route(self) -> str:
        return self.http.route

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict:
        """Run a GraphQL query against Madlan's API and return its ``data``."""
        body = json.dumps({"query": query, "variables": variables or {}}, ensure_ascii=False)
        answer = self.http.post_json("/api2", body)
        if answer.get("errors"):
            raise ApiError(200, "; ".join(str(e.get("message")) for e in answer["errors"])[:500])
        return answer.get("data") or {}

    def locations(self, text: str, types: Sequence[str] = ("city", "neighbourhood", "street")) -> list[dict]:
        """Places matching a Hebrew name: ``[{"docId", "name", "type", "city"}, ...]``."""
        return self.graphql(queries.LOCATIONS, {"text": text, "completionTypes": list(types)}).get("addresses") or []

    def location_id(self, city: str | int | None = None, neighborhood: str | None = None) -> str | None:
        """Madlan's id for a city (Hebrew or English name, or Yad2 city id) and optional neighborhood
        (Hebrew name). None means the whole country."""
        if city is None and neighborhood is None:
            return None
        key = (str(city), neighborhood)
        if key not in self._location_ids:
            self._location_ids[key] = self._resolve(city, neighborhood)
        return self._location_ids[key]

    def _resolve(self, city: str | int | None, neighborhood: str | None) -> str:
        try:
            city_he = find_city(city).name_he if city is not None else None
        except LookupError:
            city_he = str(city)  # not in the bundled table: let Madlan look it up
        if neighborhood:
            for place in self.locations(neighborhood, ("neighbourhood",)):
                if city_he is None or _same(place.get("city"), city_he):
                    return place["docId"]
            raise LookupError(f"Madlan has no neighborhood {neighborhood!r}" + (f" in {city_he}" if city_he else ""))
        for place in self.locations(city_he, ("city",)):
            if place.get("type") == "city" and _same(place.get("name"), city_he):
                return place["docId"]
        raise LookupError(f"Madlan has no city {city!r}")

    def search(
        self,
        deal: str = "sale",
        *,
        city: str | int | None = None,
        neighborhood: str | None = None,
        location_id: str | None = None,
        page_size: int = 1000,
        start: int = 0,
        **filters: Any,
    ) -> Page[MadlanListing]:
        """One request: up to ``page_size`` listings (max 1,000) from position ``start``.

        :param deal: ``"sale"`` or ``"rent"``.
        :param city: city name (Hebrew or English) or Yad2 city id; none means the whole country.
        :param neighborhood: neighborhood name in Hebrew, e.g. ``"פלורנטין"``.
        :param location_id: a Madlan id (``"רעננה-ישראל"``), instead of city/neighborhood.
        :param filters: ``min_price``, ``max_rooms``, ``parking=True``, ``created_within_days=3``,
            ``sort="price-asc"``... see ``FILTERS``.
        """
        variables = build_variables(filters)
        variables.update(
            dealType=DEALS.get(deal, deal),
            locationDocId=location_id or self.location_id(city, neighborhood),
            limit=page_size,
            offset=(start // STEP) * page_size,
        )
        result = self.graphql(queries.SEARCH, variables).get("searchPoiV2") or {}
        items = [MadlanListing.from_api(p) for p in result.get("poi") or [] if p.get("id")]
        return Page(items, start // STEP + 1, result.get("total"), None)

    def iter_search(
        self,
        deal: str = "sale",
        *,
        city: str | int | None = None,
        neighborhood: str | None = None,
        location_id: str | None = None,
        max_listings: int | None = None,
        page_size: int = 1000,
        **filters: Any,
    ) -> Iterator[MadlanListing]:
        """Every listing of a search (newest first by default), without duplicates."""
        location_id = location_id or self.location_id(city, neighborhood)
        seen: set[str] = set()
        start = 0
        while True:
            # Page boundaries are re-read with some overlap: the order may shift slightly.
            begin = max(0, start - OVERLAP) // STEP * STEP
            page = self.search(deal, location_id=location_id, page_size=page_size, start=begin, **filters)
            new = [x for x in page.items if x.id not in seen]
            for listing in new:
                seen.add(listing.id)
                yield listing
                if max_listings is not None and len(seen) >= max_listings:
                    return
            total = page.total or 0
            if len(seen) >= total:
                return
            if not new:
                log.warning("madlan: stopped at %d of %d listings (did the pagination change?)", len(seen), total)
                return
            start = begin + len(page.items)

    def get(self, *ids: str) -> list[MadlanListing]:
        """Listings by id (the last part of their URL), with all their details."""
        result = self.graphql(queries.BY_IDS, {"ids": [{"id": i, "type": "bulletin"} for i in ids]})
        return [MadlanListing.from_api(p) for p in result.get("poiByIds") or [] if p and p.get("id")]


def _same(a: str | None, b: str | None) -> bool:
    norm = lambda s: "".join((s or "").replace("-", " ").split())  # noqa: E731
    return bool(a) and norm(a) == norm(b)


__all__ = ["Madlan", "MadlanListing", "is_blocked", "build_variables", "FILTERS"]
