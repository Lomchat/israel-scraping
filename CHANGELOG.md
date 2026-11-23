# Changelog

## 0.3.0 (2026-11-23): israel-listings, Madlan

The project becomes **israel-listings** (repository, package `israel-listings`, import
`israel_listings`): several Israeli sites, one data model.

- **Madlan** (`Madlan`, `madlan` command): search sale and rent listings through Madlan's GraphQL
  API, up to 1,000 per request (all of Madlan, 45,000 listings, in about 6 minutes). Filters
  aligned with Yad2's, plus seller type, condition, price drops, listings of the last N days,
  neighborhoods by Hebrew name. Price history of each listing. The API's odd paging (steps of 34
  whatever the offset) is handled: every listing is returned once.
- **Both sites at once**: `search_all()` and the `israel-listings` command, same columns with a
  `source` field, and a property listed on both sites kept once (`drop_duplicates`).
- **Common model**: every real-estate listing is a `Listing` (`source`, `id`, `url`, `deal`,
  `price`, `rooms`, `square_meters`, `floor`, address, coordinates, images); `Yad2Listing` and
  `MadlanListing` add each site's extras.
- Phone numbers typed into descriptions are replaced by `[phone removed]`.
- Shared HTTP layer (`HttpClient`): sessions, fallback routes, retries and refusal detection for
  every site.
- Breaking changes: Yad2 listings expose `id` (`.token` still works in Python, but JSON/CSV
  outputs now have an `id` column); `Yad2Error`/`Yad2APIError` are aliases of
  `ListingsError`/`ApiError`; Yad2's `deal` is `"sale"`/`"rent"` (`"forsale"` still accepted).
- `scripts/benchmark.py --site madlan`; the Telegram example watches both sites.

## 0.2.0 (2026-11-23)

- **Session renewal**: Yad2 refuses a session (its cookies) after about 450 requests, whatever
  the pace. The client now starts a fresh session every 300 requests (`session_max_requests`)
  and right after a refusal, which removes most refusals. `session=` is replaced by
  `session_factory=`.
- **Fallback routes**: `fallback_proxies` / `--fallback-proxy`. A refused route rests
  (`route_cooldown`, 10 min) while the next one is used, then the client comes back to it.
- **`scripts/warp-proxy.sh`**: a free Cloudflare WARP SOCKS5 proxy in one command (user space,
  no root, checksums verified).
- **Firewall stub detection**: a `{"_event_transid": ...}` answer served as valid JSON is now a
  `BlockedError`, not an empty page of results.
- **Refusals are waited out** (`block_retries=2`, `block_wait=60`) instead of failing at once.
- **Car manufacturers by name**: `manufacturer="toyota"`, `yad2 manufacturers`.
- **`scripts/benchmark.py`** and measured rate limits in the README.
- Examples: Telegram alerts, price per m² by neighborhood.
- Release workflow for PyPI (trusted publishing).

## 0.1.0 (2026-11-23)

First release: real-estate search (filters, full iteration, map, listing details), vehicles,
city lookup, CLI with CSV/JSON/JSONL output and `--watch`, personal data stripped.
