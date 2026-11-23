"""Madlan payloads as typed objects."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Listing, dig, to_int
from ..privacy import redact_phones

SITE = "https://www.madlan.co.il"
IMAGES = "https://images2.madlan.co.il/t:nonce:v=2"
DEALS = {"unitBuy": "sale", "unitRent": "rent"}


def image_url(path: str | None) -> str | None:
    if not path:
        return None
    return path if path.startswith("http") else IMAGES + path


@dataclass
class MadlanListing(Listing):
    """A Madlan listing ("bulletin"), with Madlan's extra data."""

    floors: int | None = None  # floors in the building
    price_per_sqm: int | None = None
    # [{"date": ..., "price": ..., "event": "new" | "priceDrop" | ...}], oldest first
    price_history: list[dict] = field(default_factory=list)
    first_seen: str | None = None
    updated_at: str | None = None
    condition: str | None = None  # new, asNew, renovated, preserved, requiresRenovation...
    building_year: int | None = None
    monthly_taxes: int | None = None  # arnona
    common_charges: int | None = None  # va'ad bayit
    available_date: str | None = None
    description: str | None = None
    amenities: list[str] = field(default_factory=list)  # names of the amenities present
    floor_plans: list[str] = field(default_factory=list)
    city_doc_id: str | None = None
    neighborhood_doc_id: str | None = None

    @classmethod
    def from_api(cls, item: dict) -> MadlanListing:
        address = item.get("addressDetails") or {}
        images = item.get("images") or []
        description = redact_phones(item.get("description"))
        raw = {**item, "description": description}
        return cls(
            source="madlan",
            id=item["id"],
            url=f"{SITE}/listings/{item['id']}",
            deal=DEALS.get(item.get("dealType"), item.get("dealType")),
            price=item.get("price") or None,
            rooms=item.get("beds"),
            square_meters=item.get("area"),
            floor=to_int(item.get("floor")),
            city=address.get("city"),
            neighborhood=address.get("neighbourhood"),
            street=address.get("streetName"),
            house_number=address.get("streetNumber"),
            lat=dig(item, "locationPoint", "lat"),
            lon=dig(item, "locationPoint", "lng"),
            images=[u for u in (image_url(i.get("imageUrl")) for i in images if not i.get("isFloorplan")) if u],
            raw=raw,
            floors=to_int(item.get("floors")),
            price_per_sqm=item.get("ppm"),
            price_history=[
                {"date": e.get("date"), "price": e.get("price"), "event": e.get("eventType")}
                for e in item.get("eventsHistory") or [] if isinstance(e, dict)
            ],
            first_seen=item.get("firstTimeSeen"),
            updated_at=item.get("lastUpdated"),
            condition=item.get("generalCondition"),
            building_year=item.get("buildingYear"),
            monthly_taxes=item.get("monthlyTaxes"),
            common_charges=item.get("commonCharges"),
            available_date=item.get("availableDate"),
            description=description,
            amenities=sorted(k for k, v in (item.get("amenities") or {}).items() if v is True),
            floor_plans=[u for u in (image_url(i.get("imageUrl")) for i in images if i.get("isFloorplan")) if u],
            city_doc_id=address.get("cityDocId"),
            neighborhood_doc_id=address.get("neighbourhoodDocId"),
        )
