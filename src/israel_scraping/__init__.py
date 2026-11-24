"""Unofficial clients for Israeli listing sites: Yad2 and Madlan."""

from .combined import SITES, search_all
from .errors import ApiError, BlockedError, ListingsError, Yad2APIError, Yad2Error
from .locations import City, find_city, search_cities
from .madlan import Madlan, MadlanListing
from .models import Listing, Page, drop_duplicates
from .yad2 import (
    CarListing,
    Manufacturer,
    Yad2,
    Yad2Listing,
    Yad2ListingDetail,
    find_manufacturer,
    search_manufacturers,
)

__version__ = "0.3.0"


__all__ = [
    "Yad2",
    "Madlan",
    "SITES",
    "search_all",
    "Listing",
    "Yad2Listing",
    "Yad2ListingDetail",
    "MadlanListing",
    "CarListing",
    "Page",
    "drop_duplicates",
    "City",
    "find_city",
    "search_cities",
    "Manufacturer",
    "find_manufacturer",
    "search_manufacturers",
    "ListingsError",
    "BlockedError",
    "ApiError",
    "Yad2Error",
    "Yad2APIError",
]
