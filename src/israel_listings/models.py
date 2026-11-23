"""Shared data model. Every site returns ``Listing`` subclasses with the same core fields, so results
from several sites can be mixed, compared and exported together."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, fields
from typing import Any, Generic, TypeVar

T = TypeVar("T")


def dig(obj: Any, *path: str) -> Any:
    """``obj[path[0]][path[1]]...``, or None as soon as something is missing."""
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def to_int(value: Any) -> int | None:
    """Ints stay ints, numeric strings become ints, anything else becomes None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


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


def _address_key(listing: Listing) -> tuple | None:
    if not (listing.street and listing.house_number and listing.rooms):
        return None
    street = re.sub(r"[^0-9a-zא-ת]", "", listing.street.lower())
    return listing.deal, street, str(listing.house_number).strip(), float(listing.rooms)


def drop_duplicates(listings: Iterable[Listing], price_tolerance: float = 0.03) -> Iterator[Listing]:
    """Listings without the copies of a property already seen on *another* site: same deal,
    street, house number and rooms, price within ``price_tolerance``. The first one wins."""
    seen: dict[tuple, list[Listing]] = {}
    for listing in listings:
        key = _address_key(listing)
        if key is not None:
            twins = seen.setdefault(key, [])
            if any(t.source != listing.source and _close(t.price, listing.price, price_tolerance) for t in twins):
                continue
            twins.append(listing)
        yield listing


def _close(a: int | None, b: int | None, tolerance: float) -> bool:
    return bool(a and b) and abs(a - b) / max(a, b) <= tolerance


@dataclass
class Listing(_Base):
    """A real-estate listing. Fields shared by every site; site classes add their own."""

    source: str  # "yad2", "madlan"
    id: str
    url: str
    deal: str | None = None  # "sale" or "rent"
    price: int | None = None
    rooms: float | None = None
    square_meters: float | None = None
    floor: int | None = None
    city: str | None = None
    neighborhood: str | None = None
    street: str | None = None
    house_number: str | None = None
    lat: float | None = None
    lon: float | None = None
    images: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)
