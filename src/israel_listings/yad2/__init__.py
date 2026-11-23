"""Yad2 (yad2.co.il): real estate and vehicles, through the JSON API the website uses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http import HttpClient
from .models import CarListing, Yad2Listing, Yad2ListingDetail
from .realestate import RealEstate
from .vehicles import Manufacturer, Vehicles, find_manufacturer, search_manufacturers

API_BASE = "https://gw.yad2.co.il"
SITE = "https://www.yad2.co.il"

# The API refuses some clients that do not look like the site itself calling it
# (e.g. a Chrome TLS fingerprint without a Referer), so always send what the site sends.
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": SITE,
    "Referer": SITE + "/",
}


def is_blocked(resp: Any) -> bool:
    """Radware and the firewall refuse in four ways; all of them must be caught."""
    # The API never redirects: Radware redirects blocked clients to validate.perfdrive.com.
    if 300 <= resp.status_code < 400:
        return True
    head = (resp.text or "")[:5000]
    # A firewall stub served as valid JSON: {"_event_transid": ..., "_event_clientip": ...}.
    # Taken as data, it would look like "no results".
    if "_event_transid" in head:
        return True
    if "json" in (resp.headers.get("content-type") or ""):
        return False
    # The API answers its own errors in JSON; an HTML 403 comes from the firewall.
    return resp.status_code == 403 or "perfdrive" in head or "Radware" in head


class Yad2:
    """Client for Yad2.

    >>> yad2 = Yad2()
    >>> page = yad2.realestate.search("rent", city="raanana", max_price=8000)

    Options are those of :class:`israel_listings.http.HttpClient`: ``delay`` (1 s by default),
    ``proxy``, ``fallback_proxies``, ``session_max_requests`` (300: Yad2 refuses a session after
    about 450 requests), ``block_retries``, ``block_wait``, ``route_cooldown``, ``impersonate``...
    """

    site = "yad2"

    def __init__(self, **options: Any):
        options.setdefault("delay", 1.0)
        options.setdefault("block_wait", 60.0)
        self.http = HttpClient(base_url=API_BASE, headers=HEADERS, is_blocked=is_blocked, site="yad2", **options)
        self.realestate = RealEstate(self)
        self.vehicles = Vehicles(self)

    @property
    def route(self) -> str:
        return self.http.route

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET a path of the Yad2 API (``https://gw.yad2.co.il``) and return the JSON answer."""
        return self.http.get_json(path, params)


__all__ = [
    "Yad2",
    "Yad2Listing",
    "Yad2ListingDetail",
    "CarListing",
    "Manufacturer",
    "find_manufacturer",
    "search_manufacturers",
    "is_blocked",
]
