# Changelog

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
