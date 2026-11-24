"""Yad2 payloads as typed objects. ``raw`` keeps the payload, minus personal data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import Listing, _Base, dig
from ..privacy import scrub

SITE = "https://www.yad2.co.il"
DEALS_BY_SUBCATEGORY = {1: "sale", 2: "rent"}


def payload_data(payload: Any) -> dict:
    """The ``data`` object of an API answer, empty when the API sends nothing usable."""
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


@dataclass
class Yad2Listing(Listing):
    """A Yad2 real-estate listing (search results and map)."""

    ad_type: str | None = None  # private, agency, commercial...
    property_type: str | None = None
    city_id: int | None = None
    neighborhood_id: int | None = None
    cover_image: str | None = None
    tags: list[str] = field(default_factory=list)
    agency_name: str | None = None

    @property
    def token(self) -> str:
        """Yad2's name for the listing id (last part of its URL)."""
        return self.id

    @classmethod
    def _common(cls, item: dict) -> dict[str, Any]:
        address = item.get("address") or {}
        details = item.get("additionalDetails") or {}
        meta = item.get("metaData") or {}
        number = dig(address, "house", "number")
        return {
            "source": "yad2",
            "id": item["token"],
            "url": f"{SITE}/realestate/item/{item['token']}",
            "deal": DEALS_BY_SUBCATEGORY.get(item.get("subcategoryId")),
            "price": item.get("price") or None,
            "rooms": details.get("roomsCount"),
            "square_meters": details.get("squareMeter"),
            "floor": dig(address, "house", "floor"),
            "city": dig(address, "city", "text"),
            "neighborhood": dig(address, "neighborhood", "text"),
            "street": dig(address, "street", "text"),
            "house_number": str(number) if number is not None else None,
            "lat": dig(address, "coords", "lat"),
            "lon": dig(address, "coords", "lon"),
            "images": list(meta.get("images") or []),
            "raw": scrub(item),
            "ad_type": item.get("adType"),
            "property_type": dig(details, "property", "text"),
            "city_id": dig(address, "city", "id"),
            "neighborhood_id": dig(address, "neighborhood", "id"),
            "cover_image": meta.get("coverImage"),
            "tags": [t.get("name") for t in item.get("tags") or [] if t.get("name")],
            "agency_name": dig(item, "customer", "agencyName"),
        }

    @classmethod
    def from_api(cls, item: dict, deal: str | None = None) -> Yad2Listing:
        """``deal`` ("sale"/"rent") comes from the search; the payload only hints at it."""
        fields = cls._common(item)
        if deal:
            fields["deal"] = deal
        return cls(**fields)


@dataclass
class Yad2ListingDetail(Yad2Listing):
    """A single Yad2 real-estate listing with its full description."""

    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    features: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_api(cls, item: dict) -> Yad2ListingDetail:
        dates = item.get("dates") or {}
        return cls(
            **cls._common(item),
            description=dig(item, "metaData", "description"),
            created_at=dates.get("createdAt"),
            updated_at=dates.get("updatedAt"),
            features={k: v for k, v in (item.get("inProperty") or {}).items() if isinstance(v, bool)},
        )


@dataclass
class CarListing(_Base):
    """A Yad2 vehicle listing (cars, motorcycles, scooters, trucks)."""

    id: str
    url: str
    source: str = "yad2"
    ad_type: str | None = None
    price: int | None = None
    manufacturer: str | None = None
    manufacturer_id: int | None = None
    model: str | None = None
    model_id: int | None = None
    sub_model: str | None = None
    year: int | None = None
    hand: int | None = None
    engine_type: str | None = None
    engine_volume: int | None = None
    area: str | None = None
    cover_image: str | None = None
    images: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    agency_name: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def token(self) -> str:
        return self.id

    @classmethod
    def from_api(cls, item: dict) -> CarListing:
        meta = item.get("metaData") or {}
        return cls(
            id=item["token"],
            url=f"{SITE}/vehicles/item/{item['token']}",
            ad_type=item.get("adType"),
            price=item.get("price") or None,
            manufacturer=dig(item, "manufacturer", "text"),
            manufacturer_id=dig(item, "manufacturer", "id"),
            model=dig(item, "model", "text"),
            model_id=dig(item, "model", "id"),
            sub_model=dig(item, "subModel", "text"),
            year=dig(item, "vehicleDates", "yearOfProduction"),
            hand=dig(item, "hand", "id"),
            engine_type=dig(item, "engineType", "text"),
            engine_volume=item.get("engineVolume"),
            area=dig(item, "address", "area", "text"),
            cover_image=meta.get("coverImage"),
            images=list(meta.get("images") or []),
            tags=[t.get("name") for t in item.get("tags") or [] if t.get("name")],
            agency_name=dig(item, "customer", "agencyName"),
            raw=scrub(item),
        )
