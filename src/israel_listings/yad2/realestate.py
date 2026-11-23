"""Real-estate listings: search (paged), full iteration, map markers, single listing."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from ..locations import find_city
from ..models import Page
from .models import Yad2Listing, Yad2ListingDetail
from .models import payload_data as _data

if TYPE_CHECKING:
    from . import Yad2

# Lists of listings inside a feed page, paginated independently (20 per page each). Together they
# hold every result. The page also carries promoted lists (platinum, booster...): those listings
# already appear in these two streams, and they rotate between calls, so they are ignored.
STREAMS = ("private", "agency")

# Python-friendly filter names -> API parameter names (the API rejects unknown parameters).
FILTERS = {
    "area": "area",
    "neighborhood": "neighborhood",
    "street": "street",
    "property_types": "property",
    "min_price": "minPrice",
    "max_price": "maxPrice",
    "min_rooms": "minRooms",
    "max_rooms": "maxRooms",
    "min_sqm": "minSquaremeter",
    "max_sqm": "maxSquaremeter",
    "min_floor": "minFloor",
    "max_floor": "maxFloor",
    "parking": "parking",
    "elevator": "elevator",
    "balcony": "balcony",
    "shelter": "shelter",
    "air_conditioner": "airConditioner",
    "renovated": "renovated",
    "furniture": "furniture",
    "bars": "bars",
    "accessibility": "accessibility",
    "pets": "pets",
    "image_only": "imageOnly",
    "price_only": "priceOnly",
    "price_dropped": "priceDropped",
    "text": "text",
    "sort": "sort",
}


DEAL_FEEDS = {"sale": "forsale", "buy": "forsale", "forsale": "forsale", "rent": "rent"}


def feed_name(deal: str) -> str:
    """Yad2's name for a deal type: ``"sale"`` -> ``"forsale"``."""
    return DEAL_FEEDS.get(deal, deal)


def deal_label(deal: str) -> str:
    """Common name of a deal type: ``"forsale"`` -> ``"sale"``."""
    return {"forsale": "sale", "rent": "rent"}.get(feed_name(deal), deal)


def build_params(city: str | int | None, region: int | None, filters: dict[str, Any]) -> dict[str, Any]:
    """Translate keyword filters to API parameters, resolving ``city`` names to ids."""
    unknown = set(filters) - set(FILTERS)
    if unknown:
        raise TypeError(f"unknown filter(s): {', '.join(sorted(unknown))}; known: {', '.join(FILTERS)}")
    params: dict[str, Any] = {FILTERS[k]: v for k, v in filters.items()}
    if city is not None:
        found = find_city(city)
        params["city"] = found.id
        region = region if region is not None else found.region_id
    if region is None:
        raise ValueError("give a city (name or id) or a region id")
    params["region"] = region
    return params


class RealEstate:
    def __init__(self, client: Yad2):
        self._client = client

    def search(
        self,
        deal: str = "forsale",
        *,
        city: str | int | None = None,
        region: int | None = None,
        page: int = 1,
        **filters: Any,
    ) -> Page[Yad2Listing]:
        """One page of results (up to 20 private and 20 agency listings).

        :param deal: ``"sale"`` (or ``"forsale"``) or ``"rent"``.
        :param city: city name (Hebrew or English) or Yad2 city id, e.g. ``"tel aviv"``, ``8700``.
        :param region: region id; deduced from ``city`` when omitted.
        :param filters: see ``FILTERS``, e.g. ``max_price=8000, min_rooms=3, parking=True``.
        """
        params = build_params(city, region, filters)
        params["page"] = page
        data = _data(self._client.get_json(f"/realestate-feed/{feed_name(deal)}/feed", params))
        items, seen = [], set()
        for stream in STREAMS:
            for raw in data.get(stream) or []:
                if isinstance(raw, dict) and raw.get("token") and raw["token"] not in seen:
                    seen.add(raw["token"])
                    items.append(Yad2Listing.from_api(raw, deal=deal_label(deal)))
        pagination = data.get("pagination") or {}
        return Page(items, page, pagination.get("total"), pagination.get("totalPages"))

    def iter_search(
        self, deal: str = "forsale", *, max_pages: int | None = None, **kwargs: Any
    ) -> Iterator[Yad2Listing]:
        """Every listing of a search, page after page, without duplicates."""
        seen: set[str] = set()
        page = 1
        while True:
            result = self.search(deal, page=page, **kwargs)
            for listing in result.items:
                if listing.token not in seen:
                    seen.add(listing.token)
                    yield listing
            last = result.total_pages or 0
            if page >= last or (max_pages is not None and page >= max_pages):
                return
            page += 1

    def map(
        self,
        deal: str = "forsale",
        *,
        city: str | int | None = None,
        region: int | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        zoom: int | None = None,
        **filters: Any,
    ) -> list[Yad2Listing]:
        """Listings with coordinates, as shown on the site's map (at most 200 per call).

        :param bbox: ``(lat_min, lon_min, lat_max, lon_max)`` to restrict the area. The API ignores
            the box when a city is sent, so with a box the city only serves to find the region.
        """
        params = build_params(city, region, filters)
        if bbox:
            params.pop("city", None)
            params["bBox"] = ",".join(str(x) for x in bbox)
            params["zoom"] = zoom or 13
        data = _data(self._client.get_json(f"/realestate-feed/{feed_name(deal)}/map", params))
        return [Yad2Listing.from_api(m, deal=deal_label(deal)) for m in data.get("markers") or [] if m.get("token")]

    def get(self, token: str) -> Yad2ListingDetail:
        """Full details of a listing (description, dates, features). No seller data."""
        payload = self._client.get_json(f"/realestate-item/{token}")
        return Yad2ListingDetail.from_api(payload.get("data", payload))
