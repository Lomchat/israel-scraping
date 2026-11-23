"""Search several sites at once and get one stream of listings with the same fields."""

from __future__ import annotations

import itertools
import logging
from collections.abc import Iterable, Iterator
from typing import Any

from .errors import BlockedError
from .madlan import Madlan
from .models import Listing, drop_duplicates
from .yad2 import Yad2

SITES = {"yad2": Yad2, "madlan": Madlan}
log = logging.getLogger("israel_listings")


def search_all(
    deal: str,
    city: str | int,
    *,
    sites: Iterable[str] = tuple(SITES),
    dedupe: bool = True,
    max_per_site: int | None = None,
    client_options: dict[str, Any] | None = None,
    **filters: Any,
) -> Iterator[Listing]:
    """Listings for ``deal`` ("sale" or "rent") in ``city`` from every site, one site after the other.

    Filters must mean the same on every site: ``min_price``, ``max_price``, ``min_rooms``,
    ``max_rooms``, ``min_sqm``, ``max_sqm``, ``min_floor``, ``max_floor``, ``parking``,
    ``elevator``, ``balcony``, ``shelter``, ``air_conditioner``, ``accessibility``, ``pets``,
    ``furniture``. With ``dedupe``, a property already seen on another site is skipped. A site
    that keeps refusing is skipped with a warning.
    """
    def per_site() -> Iterator[Listing]:
        for name in sites:
            if name not in SITES:
                raise ValueError(f"unknown site {name!r}; known: {', '.join(SITES)}")
            client = SITES[name](**(client_options or {}))
            found = client.realestate.iter_search(deal, city=city, **filters) if name == "yad2" else \
                client.iter_search(deal, city=city, **filters)
            try:
                yield from itertools.islice(found, max_per_site)
            except BlockedError as exc:
                log.warning("skipping %s: %s", name, exc)

    return drop_duplicates(per_site()) if dedupe else per_site()
