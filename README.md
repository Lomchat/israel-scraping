# yad2-client

Unofficial Python client and command line tool for [Yad2](https://www.yad2.co.il), Israel's largest
classifieds site. Search real-estate (for sale, for rent) and vehicle listings, export them to
CSV/JSON, and get only the new ones on each run.

- **No browser needed.** It talks to the JSON API that the Yad2 website itself uses.
- **Gets past the bot protection** by presenting a real browser's TLS fingerprint
  ([curl_cffi](https://github.com/lexiforest/curl_cffi)), the thing that blocks `requests`, `curl`
  and most scrapers.
- **Polite by default**: one request per second, clear error when Yad2 pushes back.
- **No personal data**: seller names, ids and phone numbers are never returned.

> Not affiliated with Yad2. The API is undocumented and may change without notice. See
> [Responsible use](#responsible-use).

## Install

```bash
pip install git+https://github.com/Lomchat/yad2-client
```

Python 3.10+. The only dependency is `curl_cffi`.

## Command line

```bash
# Find a city (Hebrew or English)
yad2 cities raanana

# Apartments for rent in Ra'anana, up to 8,000 ₪, 3 rooms or more, as CSV
yad2 realestate rent --city raanana --max-price 8000 --min-rooms 3 -f csv -o raanana.csv

# Everything for sale in Tel Aviv with parking and an elevator (JSON lines, one listing per line)
yad2 realestate forsale --city "tel aviv" --parking --elevator > tlv.jsonl

# One listing in full (description, dates, features)
yad2 item 2zijxipe

# Toyota (19) cars from 2018 to 2022, first or second hand
yad2 vehicles cars --manufacturer 19 --year 2018-2022 --hand 0-2 --pages 3
```

### Get only new listings

`--watch FILE` remembers what was already seen and only outputs new listings. Run it from cron,
or let it loop with `--every`:

```bash
# from cron, e.g. every hour
yad2 realestate rent --city raanana --max-price 8000 --watch seen.json >> new.jsonl

# or keep it running
yad2 realestate rent --city raanana --max-price 8000 --watch seen.json --every 3600
```

The first run outputs every current listing (redirect it to `/dev/null` to start from scratch).
With `--every`, a block from Yad2 pauses the loop (`--block-wait`, 30 min by default) instead of
stopping it.

Run `yad2 realestate --help` for all filters.

## Python

```python
from yad2_client import Yad2

yad2 = Yad2()  # one request per second by default

# One page (up to 20 private and 20 agency listings)
page = yad2.realestate.search("rent", city="raanana", max_price=8000, min_rooms=3)
print(page.total, "results in", page.total_pages, "pages")
for listing in page.items:
    print(listing.price, listing.rooms, listing.street, listing.url)

# Every result, page after page, without duplicates
for listing in yad2.realestate.iter_search("forsale", city="tel aviv", parking=True):
    ...

# Full details of one listing
detail = yad2.realestate.get("2zijxipe")
print(detail.description, detail.features)

# Map markers (coordinates, at most 200 per call), for a city or inside a bounding box
# (lat_min, lon_min, lat_max, lon_max); with a box, the city only serves to find the region
markers = yad2.realestate.map("rent", city="tel aviv")
markers = yad2.realestate.map("rent", city="tel aviv", bbox=(32.07, 34.77, 32.08, 34.78))

# Vehicles
for car in yad2.vehicles.iter_search("cars", manufacturer=19, year=(2018, 2022), max_pages=2):
    print(car.year, car.model, car.price, car.url)
```

Every object has typed fields, `to_dict()`, and `raw` with the full API payload (minus personal
data).

### Real-estate filters

| Filter | Meaning |
|---|---|
| `city`, `region` | City name/id (region deduced from the city), or a region id |
| `area`, `neighborhood`, `street` | Ids, as used on the site |
| `min_price`, `max_price` | Price in ₪ |
| `min_rooms`, `max_rooms` | Rooms (half rooms allowed) |
| `min_sqm`, `max_sqm` | Surface in m² |
| `min_floor`, `max_floor` | Floor |
| `property_types` | List of property type ids (1 = apartment, 3 = garden apartment, 5 = house, 6 = penthouse…) |
| `parking`, `elevator`, `balcony`, `shelter`, `air_conditioner`, `renovated`, `furniture`, `bars`, `accessibility`, `pets` | `True` to require it |
| `image_only`, `price_only`, `price_dropped` | Only listings with photos / a price / a price drop |
| `text` | Free text |
| `sort` | `"price-asc"` or `"price-desc"` (default: the site's order) |

### Vehicle filters

`manufacturer`, `model`, `area`, `engine_type`, `gearbox`, `seats`, `family_type`, `price_only`,
and ranges given as `(min, max)` tuples (`None` for an open bound): `year`, `price`, `km`, `hand`.

### Errors

- `BlockedError`: Yad2's bot protection answered instead of the API. The blocks we have seen
  lasted less than an hour; wait and slow down.
- `Yad2APIError`: the API rejected the request (it refuses unknown parameters, for instance).
- `LookupError`: unknown city name.

## How it works

Yad2's website loads its listings from a JSON API on `gw.yad2.co.il`. The whole site sits behind
Radware Bot Manager, which mostly judges the client's **TLS fingerprint**: `requests` and `curl` are
redirected to a captcha page, while the same request made with a browser's fingerprint goes
through. yad2-client uses `curl_cffi` to present that fingerprint, sends the headers the site
sends (`Origin`, `Referer`), and never needs a headless browser, which Radware watches much
more closely on the HTML pages.

## Responsible use

- Yad2's terms of use restrict automated access. You are responsible for how you use this tool;
  personal, low-volume use (your own apartment hunt, an alert for a car model) is what it is
  designed for.
- Keep the default pace or slower. Do not hammer the site, and back off when blocked.
- Listings are public, but people behind them are not: yad2-client strips seller names, ids,
  phone numbers and free-text fields that contain them, and does not fetch phone numbers at all.
  Israeli privacy law applies to whatever you store.

## Development

```bash
pip install -e ".[dev]"
pytest          # offline tests, a few seconds
ruff check .
python scripts/update_cities.py   # refresh the bundled city table
```

Contributions are welcome, especially when Yad2 changes its API: open an issue with the failing
command and the error.

## License

MIT
