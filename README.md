# yad2-client

[![CI](https://github.com/Lomchat/yad2-client/actions/workflows/ci.yml/badge.svg)](https://github.com/Lomchat/yad2-client/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Unofficial Python library and command line tool to collect listings from
[Yad2](https://www.yad2.co.il), Israel's largest classifieds site: apartments and houses for sale
or rent, cars, motorcycles. Export to CSV/JSON, or get only the new listings on each run (alerts).

**Why this one works when most Yad2 scrapers stopped:**

- **No browser, no HTML.** It reads the JSON API the Yad2 website itself uses: 40 listings per
  request, with coordinates, photos, rooms, size, floor.
- **Gets past the bot protection** (Radware) by presenting a real browser's TLS fingerprint with
  [curl_cffi](https://github.com/lexiforest/curl_cffi). Plain `requests`, `curl`, Scrapy and
  headless browsers are refused.
- **Stays under the radar**: Yad2 refuses a session after ~450 requests, so the client renews it
  every 300. Result: 0 refusals in 7,000+ requests at the default pace and at 3 requests/second.
- **Measured limits**, not guesses: see [Rate limits](#rate-limits-measured).
- **Handles refusals**: replaces a refused session at once, waits out a refused IP, or switches
  to a free fallback route (Cloudflare WARP) and comes back when the block is over.
- **No personal data**: seller names, ids and phone numbers are never returned.

> Not affiliated with Yad2. The API is undocumented and may change. See [Responsible use](#responsible-use).

### בעברית

ספריית פייתון וכלי שורת פקודה בקוד פתוח (לא רשמיים) לאיסוף מודעות מיד2: נדל״ן למכירה ולהשכרה
ורכבים, עם ייצוא ל-CSV או JSON. אפשר לקבל בכל הרצה רק את המודעות החדשות, למשל להתראות בטלגרם.

```bash
pip install git+https://github.com/Lomchat/yad2-client
yad2 realestate rent --city רעננה --max-price 8000 --min-rooms 3 -f csv -o raanana.csv
```

## Install

```bash
pip install git+https://github.com/Lomchat/yad2-client
```

Python 3.10+, Linux, macOS or Windows. The only dependency is `curl_cffi`.

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

# Toyota cars from 2018 to 2022, first or second hand
yad2 vehicles cars --manufacturer toyota --year 2018-2022 --hand 0-2 --pages 3
yad2 manufacturers toy        # find manufacturer ids
```

`yad2 realestate --help` lists every filter.

### Alerts: only new listings

`--watch FILE` remembers what was already seen and only outputs new listings:

```bash
# from cron, e.g. every hour
yad2 realestate rent --city raanana --max-price 8000 --watch seen.json >> new.jsonl

# or keep it running
yad2 realestate rent --city raanana --max-price 8000 --watch seen.json --every 3600
```

The first run outputs every current listing (send it to `/dev/null` to start fresh). With
`--every`, a lasting block pauses the loop (`--block-wait`, 10 min by default) instead of
stopping it. For Telegram alerts, see [examples/telegram_alerts.py](examples/telegram_alerts.py).

## Python

```python
from yad2_client import Yad2

yad2 = Yad2()  # one request per second by default

# One page: up to 20 private and 20 agency listings
page = yad2.realestate.search("rent", city="raanana", max_price=8000, min_rooms=3)
print(page.total, "results in", page.total_pages, "pages")
for listing in page.items:
    print(listing.price, listing.rooms, listing.square_meters, listing.street, listing.url)

# Every result, page after page, without duplicates
for listing in yad2.realestate.iter_search("forsale", city="tel aviv", parking=True):
    ...

# Full details of one listing
detail = yad2.realestate.get("2zijxipe")
print(detail.description, detail.features)

# Map markers (coordinates, at most 200 per call), for a city or inside a bounding box
markers = yad2.realestate.map("rent", city="tel aviv")
markers = yad2.realestate.map("rent", city="tel aviv", bbox=(32.07, 34.77, 32.08, 34.78))

# Vehicles
for car in yad2.vehicles.iter_search("cars", manufacturer="toyota", year=(2018, 2022), max_pages=2):
    print(car.year, car.model, car.hand, car.price, car.url)
```

Every object has typed fields, `to_dict()`, and `raw`: the full API payload, minus personal data.
More in [examples/](examples): Telegram alerts, price per m² by neighborhood.

### Real-estate filters

| Filter | Meaning |
|---|---|
| `city`, `region` | City name (Hebrew/English) or id; the region is deduced from the city |
| `area`, `neighborhood`, `street` | Ids, as used on the site |
| `min_price`, `max_price` | Price in ₪ |
| `min_rooms`, `max_rooms` | Rooms (half rooms allowed) |
| `min_sqm`, `max_sqm` | Surface in m² |
| `min_floor`, `max_floor` | Floor |
| `property_types` | Property type ids: 1 apartment, 3 garden apartment, 4 studio/loft, 5 house, 6 penthouse, 7 duplex, 11 housing unit… |
| `parking`, `elevator`, `balcony`, `shelter`, `air_conditioner`, `renovated`, `furniture`, `bars`, `accessibility`, `pets` | `True` to require it |
| `image_only`, `price_only`, `price_dropped` | Only listings with photos / a price / a price drop |
| `text` | Free text |
| `sort` | `"price-asc"` or `"price-desc"` (default: the site's order) |

### Vehicle filters

`manufacturer` (name or id), `model`, `area`, `engine_type`, `gearbox`, `seats`, `family_type`,
`price_only`, and ranges given as `(min, max)` tuples (`None` for an open bound): `year`,
`price`, `km`, `hand`. Categories: `cars`, `motorcycles`, `scooters`, `trucks`.

## Rate limits, measured

Measured on 23 November 2026 from a datacenter server in the Netherlands, with
[`scripts/benchmark.py`](scripts/benchmark.py). One request is one page of search results:
40 listings.

| Pace | Route | Duration | Requests OK | Refused | Per hour |
|---|---|---|---|---|---|
| 1 req/s (the default) | direct | 29 min | 1,732 | **0** | ~3,600 requests ≈ 144,000 listings |
| 1 req/s | Cloudflare WARP | 29 min | 1,740 | **0** | same |
| 3 req/s (3 threads) | direct | 20 min | 3,601 | **0** | ~10,800 requests ≈ 432,000 listings |
| As fast as possible (16 threads) | direct | 54 s | 1,779 (33 req/s) | then the IP | — |
| 1 req/s, *without* session renewal | direct and WARP | 7.5 min | ~455 each | then all | — |

What this means:

- **Sessions are limited, not speed.** Yad2 refuses a session after about 450 requests at any
  pace. Renewing it, which the client does every 300 requests, removes the problem: compare the
  last line with the first two.
- **The IP itself was only refused after bursts** (about 1,800 requests within a minute or two)
  or a day of heavy testing. Those IP blocks lasted from a few seconds to about 20 minutes (17
  minutes after the burst above), longer after repeated abuse. A fallback route (below) keeps you
  going meanwhile.
- **Real needs are far below that.** All of Tel Aviv for sale (10,000+ listings) is 490 requests;
  Tel Aviv and Ra'anana, for sale and for rent (16,000 listings), 725 requests: about 12 minutes
  at the default pace, which one IP can repeat every hour.

Measure your own IP or proxy (it pauses on any refusal, so it never hammers a blocked IP):

```bash
python scripts/benchmark.py --rate 1 --minutes 10
python scripts/benchmark.py --threads 16 --stop-on-block   # where does your IP get refused?
python scripts/benchmark.py --rate 1 --minutes 10 --proxy socks5h://127.0.0.1:40000
```

## Free fallback route: Cloudflare WARP

When the bot protection refuses your IP, the client can switch to another route at once and come
back after `route_cooldown` (10 min). [Cloudflare WARP](https://1.1.1.1/) is free and works well
for this. Start it as a local SOCKS5 proxy, without root and without touching your network setup:

```bash
scripts/warp-proxy.sh          # downloads wgcf + wireproxy (checksums verified), Ctrl-C to stop
yad2 --fallback-proxy socks5h://127.0.0.1:40000 realestate rent --city raanana --watch seen.json --every 3600
```

```python
yad2 = Yad2(fallback_proxies=["socks5h://127.0.0.1:40000"])
```

On a desktop, the official WARP client does the same: `warp-cli registration new`,
`warp-cli mode proxy`, `warp-cli connect` (SOCKS5 on port 40000). Any other proxy works too
(`--proxy` for the main route, `--fallback-proxy` repeatable).

## How it works

Yad2's website loads its listings from a JSON API on `gw.yad2.co.il`. The whole site sits behind
Radware Bot Manager plus a firewall. What we found:

- **TLS fingerprint decides first.** `requests`, `curl` and most HTTP libraries are redirected to a
  captcha page whatever their headers; the same request with a browser's TLS/HTTP2 fingerprint
  passes. The `User-Agent` itself is not checked on the API.
- **Send what the site sends.** With a Chrome fingerprint, a request without `Referer` is refused.
- **Limits are per session first.** Radware tracks its cookies (`__uzma`…`uzmx`): one session is
  refused after about 450 requests, whatever the pace (we got 451 at 2 req/s and ~455 at 1 req/s),
  and stays refused, while a fresh session from the same IP passes at once. yad2-client renews
  its session every 300 requests (`session_max_requests`) and right after a refusal. IP-level
  blocks exist too, but take much more.
- **The API is far more lenient than the HTML pages.** A headless Chrome usually gets a captcha by
  its second page (or the first, once the IP is known), while the API keeps answering. No browser
  is needed at all.
- **Refusals come in four shapes**: a redirect to `validate.perfdrive.com`, a "Radware" HTML page,
  a firewall "403 Forbidden" HTML page, and a firewall stub served as valid JSON
  (`{"_event_transid": ...}`). The last one looks like an empty result; yad2-client detects all
  four and raises `BlockedError` (or switches route) instead of returning nothing.
- **Unknown parameters are rejected** (`"foo is not allowed"`), so filters are validated before
  sending.
- Search results come in two lists (private and agency, 20 each per page) that together hold every
  listing; promoted listings repeat them and rotate on each call, so they are ignored.

## Responsible use

- Yad2's terms of use restrict automated access. You are responsible for how you use this tool.
  Personal, reasonable use (your apartment hunt, an alert for a car model, research) is what it
  is designed for.
- Keep the default pace. One request per second is 40 listings per second, more than enough to
  follow a whole city every hour, and it never got us refused (see the measurements).
- Listings are public, but the people behind them are not: yad2-client strips seller names, ids,
  phone numbers and free-text fields that contain them, and does not fetch phone numbers.
  Israeli privacy law applies to whatever you store.

## Troubleshooting

- **`BlockedError`**: the client already waited (`block_retries=2`, `block_wait=60` s). Slow
  down, wait 10 to 20 minutes, or add a fallback route (WARP).
- **`no Yad2 city matches`**: try `yad2 cities <part of the name>`, or pass the numeric id.
- **`Yad2APIError: ... is not allowed`**: the API rejected a parameter; check the filter name.
- **Empty results** where the site shows some: open an issue with the command.

## Development

```bash
pip install -e ".[dev]"
pytest                               # offline tests, under a second
ruff check .
python scripts/update_cities.py      # refresh the bundled city table
python scripts/benchmark.py --help   # measure the limits from your IP
```

Contributions are welcome, especially when Yad2 changes its API: open an issue with the failing
command and the error.

## License

MIT
