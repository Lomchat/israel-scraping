"""Median asking price per m² by neighborhood, for apartments for sale in one city.

  python examples/price_per_sqm.py raanana
  python examples/price_per_sqm.py "tel aviv"     # ~250 requests, about 4 minutes
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict

from yad2_client import Yad2

city = sys.argv[1] if len(sys.argv) > 1 else "raanana"
prices: dict[str, list[float]] = defaultdict(list)
for listing in Yad2().realestate.iter_search("forsale", city=city, property_types=[1], price_only=True):
    if listing.price and listing.square_meters and listing.square_meters >= 25 and listing.neighborhood:
        prices[listing.neighborhood].append(listing.price / listing.square_meters)

rows = sorted(
    ((statistics.median(v), len(v), hood) for hood, v in prices.items() if len(v) >= 3), reverse=True
)
for median, count, hood in rows:
    print(f"{median:>9,.0f} ₪/m²  {count:>4} listings  {hood}")
