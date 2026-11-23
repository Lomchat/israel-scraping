"""Typed views of API payloads. Every object keeps the (scrubbed) payload in ``raw``."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Generic, TypeVar

from .client import SITE
from .privacy import scrub

T = TypeVar("T")


def payload_data(payload: Any) -> dict:
    """The ``data`` object of an API answer, empty when the API sends nothing usable."""
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def _get(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


class _Base:
    raw: dict

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        """Flat dict of the typed fields (``raw`` only if asked)."""
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)  # type: ignore[arg-type]
            if include_raw or f.name != "raw"
        }


@dataclass
class Page(Generic[T]):
    items: list[T]
    page: int
    total: int | None
    total_pages: int | None


@dataclass
class Listing(_Base):
    """A real-estate listing, as returned by search results and the map."""

    token: str
    url: str
    ad_type: str | None = None
    price: int | None = None
    property_type: str | None = None
    rooms: float | None = None
    square_meters: int | None = None
    floor: int | None = None
    city: str | None = None
    city_id: int | None = None
    neighborhood: str | None = None
    neighborhood_id: int | None = None
    street: str | None = None
    house_number: str | None = None
    lat: float | None = None
    lon: float | None = None
    cover_image: str | None = None
    images: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    agency_name: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def _common(cls, item: dict) -> dict[str, Any]:
        address = item.get("address") or {}
        details = item.get("additionalDetails") or {}
        meta = item.get("metaData") or {}
        number = _get(address, "house", "number")
        return {
            "token": item["token"],
            "url": f"{SITE}/realestate/item/{item['token']}",
            "ad_type": item.get("adType"),
            "price": item.get("price") or None,
            "property_type": _get(details, "property", "text"),
            "rooms": details.get("roomsCount"),
            "square_meters": details.get("squareMeter"),
            "floor": _get(address, "house", "floor"),
            "city": _get(address, "city", "text"),
            "city_id": _get(address, "city", "id"),
            "neighborhood": _get(address, "neighborhood", "text"),
            "neighborhood_id": _get(address, "neighborhood", "id"),
            "street": _get(address, "street", "text"),
            "house_number": str(number) if number is not None else None,
            "lat": _get(address, "coords", "lat"),
            "lon": _get(address, "coords", "lon"),
            "cover_image": meta.get("coverImage"),
            "images": list(meta.get("images") or []),
            "tags": [t.get("name") for t in item.get("tags") or [] if t.get("name")],
            "agency_name": _get(item, "customer", "agencyName"),
            "raw": scrub(item),
        }

    @classmethod
    def from_api(cls, item: dict) -> Listing:
        return cls(**cls._common(item))


@dataclass
class ListingDetail(Listing):
    """A single real-estate listing with its full description."""

    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    features: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_api(cls, item: dict) -> ListingDetail:
        dates = item.get("dates") or {}
        return cls(
            **cls._common(item),
            description=_get(item, "metaData", "description"),
            created_at=dates.get("createdAt"),
            updated_at=dates.get("updatedAt"),
            features={k: v for k, v in (item.get("inProperty") or {}).items() if isinstance(v, bool)},
        )


@dataclass
class CarListing(_Base):
    """A vehicle listing (cars, motorcycles, scooters, trucks)."""

    token: str
    url: str
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

    @classmethod
    def from_api(cls, item: dict) -> CarListing:
        meta = item.get("metaData") or {}
        return cls(
            token=item["token"],
            url=f"{SITE}/vehicles/item/{item['token']}",
            ad_type=item.get("adType"),
            price=item.get("price") or None,
            manufacturer=_get(item, "manufacturer", "text"),
            manufacturer_id=_get(item, "manufacturer", "id"),
            model=_get(item, "model", "text"),
            model_id=_get(item, "model", "id"),
            sub_model=_get(item, "subModel", "text"),
            year=_get(item, "vehicleDates", "yearOfProduction"),
            hand=_get(item, "hand", "id"),
            engine_type=_get(item, "engineType", "text"),
            engine_volume=item.get("engineVolume"),
            area=_get(item, "address", "area", "text"),
            cover_image=meta.get("coverImage"),
            images=list(meta.get("images") or []),
            tags=[t.get("name") for t in item.get("tags") or [] if t.get("name")],
            agency_name=_get(item, "customer", "agencyName"),
            raw=scrub(item),
        )
