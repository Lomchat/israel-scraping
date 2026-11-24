"""Command line tools: ``yad2``, ``madlan`` and ``israel-scraping`` (both sites at once)."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .combined import SITES, search_all
from .errors import BlockedError, ListingsError
from .locations import regions, search_cities
from .madlan import AMENITIES as MADLAN_AMENITIES
from .madlan import SORTS as MADLAN_SORTS
from .madlan import Madlan
from .models import Listing
from .yad2 import Yad2
from .yad2.realestate import FILTERS as YAD2_FILTERS
from .yad2.vehicles import CATEGORIES, all_manufacturers, search_manufacturers

YAD2_BOOL = {
    "parking", "elevator", "balcony", "shelter", "air_conditioner", "renovated", "furniture",
    "bars", "accessibility", "pets", "image_only", "price_only", "price_dropped",
}
NUMBERS = {
    "min_price": int, "max_price": int, "min_rooms": float, "max_rooms": float, "min_sqm": int,
    "max_sqm": int, "min_floor": int, "max_floor": int,
}
YAD2_NUMBERS = {**NUMBERS, "area": int, "neighborhood": int}
# Filters both sites understand, with the same meaning.
COMMON_BOOL = ["parking", "elevator", "balcony", "shelter", "air_conditioner", "accessibility", "pets", "furniture"]
LISTING_FIELDS = [f.name for f in dataclasses.fields(Listing) if f.name != "raw"]


# ---------------------------------------------------------------- shared pieces


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def _range(text: str) -> tuple[int | None, int | None]:
    """'2018-2022' -> (2018, 2022); '2018-' -> (2018, None); '-2022' is read as an option, use '0-2022'."""
    low, sep, high = text.partition("-")
    if not sep:
        raise argparse.ArgumentTypeError(f"expected MIN-MAX, got {text!r}")
    try:
        return (int(low) if low else None, int(high) if high else None)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected MIN-MAX with integers, got {text!r}") from exc


def _words(text: str) -> list[str]:
    return [w.strip() for w in text.split(",") if w.strip()]


def _add_network_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--version", action="version", version=f"israel-scraping {__version__}")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1)")
    parser.add_argument("--impersonate", default="chrome", help="browser fingerprint (curl_cffi name)")
    parser.add_argument("--proxy", help="proxy URL, e.g. socks5h://127.0.0.1:1080")
    parser.add_argument("--fallback-proxy", action="append", default=[], metavar="URL",
                        help="proxy to switch to when refused, e.g. a local WARP proxy (repeatable)")


def _client_options(args: argparse.Namespace) -> dict[str, Any]:
    return {"delay": args.delay, "impersonate": args.impersonate, "proxy": args.proxy,
            "fallback_proxies": args.fallback_proxy}


def _add_output_args(p: argparse.ArgumentParser, limit: str) -> None:
    g = p.add_argument_group("output")
    if limit == "pages":
        g.add_argument("--pages", type=int, metavar="N", help="read at most N pages (default: all)")
    else:
        g.add_argument("--max", type=int, metavar="N", help="at most N listings (per site)")
    g.add_argument("-f", "--format", choices=["jsonl", "json", "csv"], default="jsonl")
    g.add_argument("-o", "--output", metavar="FILE", help="write to FILE instead of stdout")
    g.add_argument("--raw", action="store_true", help="include the full API payload (jsonl/json)")
    w = p.add_argument_group("watch for new listings")
    w.add_argument("--watch", metavar="STATE_FILE",
                   help="only output listings not seen in previous runs (state kept in STATE_FILE)")
    w.add_argument("--every", type=float, metavar="SECONDS", help="with --watch: repeat every SECONDS")
    w.add_argument("--block-wait", type=float, default=600, metavar="SECONDS",
                   help="with --every: pause after a lasting block (default 600)")


def _add_filter_args(p: argparse.ArgumentParser, numbers: dict[str, type], booleans: Iterable[str]) -> None:
    for name, kind in numbers.items():
        p.add_argument(_flag(name), type=kind)
    for name in booleans:
        p.add_argument(_flag(name), action="store_true", default=None)


def _filters(args: argparse.Namespace, names: Iterable[str]) -> dict[str, Any]:
    return {n: getattr(args, n) for n in names if getattr(args, n, None) is not None}


class _Writer:
    def __init__(self, fmt: str, out: Any, raw: bool, fields: list[str] | None = None):
        self.fmt, self.out, self.raw, self.fields = fmt, out, raw, fields
        self.rows: list[dict] = []

    def write(self, listing: Any) -> None:
        if self.fields:
            row = {k: getattr(listing, k) for k in self.fields}
            if self.raw and self.fmt != "csv":
                row["raw"] = listing.raw
        else:
            row = listing.to_dict(include_raw=self.raw and self.fmt != "csv")
        if self.fmt == "jsonl":
            self.out.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.out.flush()
        else:
            self.rows.append(row)

    def close(self) -> None:
        if self.fmt == "json":
            json.dump(self.rows, self.out, ensure_ascii=False, indent=2)
            self.out.write("\n")
        elif self.fmt == "csv" and self.rows:
            w = csv.DictWriter(self.out, fieldnames=list(self.rows[0]))
            try:
                empty = self.out.tell() == 0
            except (OSError, ValueError):  # stdout
                empty = True
            if empty:
                w.writeheader()
            for row in self.rows:
                w.writerow({k: _cell(v) for k, v in row.items()})
        self.out.flush()


def _cell(value: Any) -> Any:
    if isinstance(value, list):
        return " ".join(json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def _load_state(path: str) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("seen", {})
    except FileNotFoundError:
        return {}


def _save_state(path: str, seen: dict[str, str]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"seen": seen}, fh)
    os.replace(tmp, path)


def _run_once(listings: Iterator[Any], writer: _Writer, state: str | None,
              key: Callable[[Any], str]) -> tuple[int, int]:
    """Output listings (only unseen ones with a state file). Returns (read, written)."""
    seen = _load_state(state) if state else {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    read = written = 0
    try:
        for listing in listings:
            read += 1
            if state and key(listing) in seen:
                continue
            seen[key(listing)] = now
            writer.write(listing)
            written += 1
    finally:
        if state:
            _save_state(state, seen)
    return read, written


def _search(args: argparse.Namespace, make_iter: Callable[[], Iterator[Any]],
            key: Callable[[Any], str] = lambda x: x.id, fields: list[str] | None = None) -> int:
    if args.every and (not args.watch or args.format != "jsonl"):
        print("--every needs --watch STATE_FILE and the jsonl format", file=sys.stderr)
        return 2
    mode = "a" if args.watch else "w"
    out = open(args.output, mode, encoding="utf-8", newline="") if args.output else sys.stdout
    writer = _Writer(args.format, out, args.raw, fields)
    try:
        while True:
            try:
                read, written = _run_once(make_iter(), writer, args.watch, key)
                label = "new" if args.watch else "written"
                print(f"{read} listings read, {written} {label}", file=sys.stderr)
            except BlockedError as exc:
                if not args.every:
                    print(f"error: {exc}", file=sys.stderr)
                    return 3
                print(f"blocked, pausing {args.block_wait:.0f}s: {exc}", file=sys.stderr)
                time.sleep(args.block_wait)
                continue
            if not args.every:
                return 0
            time.sleep(args.every)
    except KeyboardInterrupt:
        return 130
    finally:
        writer.close()
        if out is not sys.stdout:
            out.close()


def _run(handler: Callable[[], int]) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stderr)
    try:
        return handler()
    except BlockedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (ListingsError, LookupError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _print_cities(query: str) -> int:
    names = regions()
    for c in search_cities(query, limit=15):
        region = f"region {c.region_id} ({names.get(c.region_id, '?')})"
        print(f"{c.id:>5}  {c.name_en:<28} {c.name_he:<22} {region}")
    return 0


# ---------------------------------------------------------------- yad2


def build_yad2_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yad2", description="Unofficial client for Yad2 (yad2.co.il): real estate and vehicles.",
        epilog="Example: yad2 realestate rent --city raanana --max-price 8000 --min-rooms 3 -f csv",
    )
    _add_network_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cities", help="find city ids and regions by name")
    p.add_argument("query", help="name in Hebrew or English, or an id")

    p = sub.add_parser("manufacturers", help="find car manufacturer ids by name")
    p.add_argument("query", nargs="?", help="name in Hebrew or English, or an id (default: list all)")

    p = sub.add_parser("realestate", help="search apartments and houses for sale or rent")
    p.add_argument("deal", choices=["forsale", "sale", "rent"])
    p.add_argument("--city", help="city name (Hebrew or English) or id, e.g. 'tel aviv'")
    p.add_argument("--region", type=int, help="region id (deduced from --city when omitted)")
    _add_filter_args(p, {k: v for k, v in YAD2_NUMBERS.items() if k in YAD2_FILTERS},
                     [k for k in YAD2_FILTERS if k in YAD2_BOOL])
    p.add_argument("--street")
    p.add_argument("--text")
    p.add_argument("--sort", choices=["price-asc", "price-desc"])
    p.add_argument("--property-types", metavar="IDS", help="comma-separated property type ids (1 = apartment)")
    _add_output_args(p, "pages")

    p = sub.add_parser("item", help="show one real-estate listing in full (JSON)")
    p.add_argument("token", help="listing id, the last part of its URL")

    p = sub.add_parser("vehicles", help="search cars, motorcycles, scooters, trucks")
    p.add_argument("category", nargs="?", default="cars", choices=CATEGORIES)
    p.add_argument("--manufacturer", help="manufacturer name or id, e.g. toyota (see `yad2 manufacturers`)")
    p.add_argument("--model", type=int, help="model id")
    p.add_argument("--area", type=int, help="area id")
    for name in ("year", "price", "km", "hand"):
        p.add_argument("--" + name, type=_range, metavar="MIN-MAX")
    _add_output_args(p, "pages")
    return parser


build_parser = build_yad2_parser  # name used by yad2-client 0.2


def yad2_main(argv: list[str] | None = None) -> int:
    args = build_yad2_parser().parse_args(argv)
    if args.command == "cities":
        return _print_cities(args.query)
    if args.command == "manufacturers":
        makers = search_manufacturers(args.query, limit=200) if args.query else sorted(
            all_manufacturers(), key=lambda m: -m.listings)
        for m in makers:
            print(f"{m.id:>5}  {m.name_en:<20} {m.name_he:<20} {m.listings:>6} listings")
        return 0

    def handle() -> int:
        client = Yad2(**_client_options(args))
        if args.command == "item":
            detail = client.realestate.get(args.token)
            print(json.dumps(detail.to_dict(include_raw=True), ensure_ascii=False, indent=2))
            return 0
        if args.command == "realestate":
            filters = _filters(args, YAD2_FILTERS)
            if "property_types" in filters:
                filters["property_types"] = _words(filters["property_types"])
            return _search(args, lambda: client.realestate.iter_search(
                args.deal, max_pages=args.pages, city=args.city, region=args.region, **filters))
        filters = _filters(args, ("manufacturer", "model", "area", "year", "price", "km", "hand"))
        return _search(args, lambda: client.vehicles.iter_search(args.category, max_pages=args.pages, **filters))

    return _run(handle)


main = yad2_main  # name used by yad2-client 0.2


# ---------------------------------------------------------------- madlan


def build_madlan_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="madlan", description="Unofficial client for Madlan (madlan.co.il): real-estate listings.",
        epilog="Example: madlan rent --city raanana --max-price 8000 --min-rooms 3 --parking -f csv",
    )
    _add_network_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    for deal in ("sale", "rent"):
        p = sub.add_parser(deal, help=f"search listings for {deal} (newest first)")
        p.add_argument("--city", help="city name (Hebrew or English) or Yad2 city id; none = whole country")
        p.add_argument("--neighborhood", help="neighborhood name in Hebrew, e.g. פלורנטין")
        p.add_argument("--location-id", help="a Madlan location id, e.g. רעננה-ישראל (see `madlan places`)")
        _add_filter_args(p, NUMBERS, MADLAN_AMENITIES)
        p.add_argument("--seller-types", type=_words, metavar="LIST", help="private,agent,developer")
        p.add_argument("--conditions", type=_words, metavar="LIST",
                       help="new,asNew,renovated,preserved,requiresRenovation...")
        p.add_argument("--price-drop", action="store_true", default=None, help="only listings whose price dropped")
        p.add_argument("--created-within-days", type=int, metavar="N", help="only listings from the last N days")
        p.add_argument("--only-immediate", action="store_true", default=None, help="immediate entry only")
        p.add_argument("--no-fee", action="store_true", default=None, help="rent without broker fee")
        p.add_argument("--sort", choices=list(MADLAN_SORTS), default="date")
        _add_output_args(p, "max")

    p = sub.add_parser("item", help="show listings in full (JSON)")
    p.add_argument("ids", nargs="+", help="listing ids, the last part of their URL")

    p = sub.add_parser("places", help="find Madlan location ids (Hebrew names)")
    p.add_argument("text", help="a city, neighborhood or street name in Hebrew")
    return parser


MADLAN_FILTERS = [*NUMBERS, *MADLAN_AMENITIES, "seller_types", "conditions", "price_drop",
                  "created_within_days", "only_immediate", "no_fee", "sort"]


def madlan_main(argv: list[str] | None = None) -> int:
    args = build_madlan_parser().parse_args(argv)

    def handle() -> int:
        client = Madlan(**_client_options(args))
        if args.command == "item":
            items = [x.to_dict(include_raw=True) for x in client.get(*args.ids)]
            print(json.dumps(items, ensure_ascii=False, indent=2))
            return 0
        if args.command == "places":
            for place in client.locations(args.text):
                print(f"{place.get('type', ''):<14} {place.get('docId')}")
            return 0
        filters = _filters(args, MADLAN_FILTERS)
        return _search(args, lambda: client.iter_search(
            args.command, city=args.city, neighborhood=args.neighborhood, location_id=args.location_id,
            max_listings=args.max, **filters))

    return _run(handle)


# ---------------------------------------------------------------- both sites


def build_all_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="israel-scraping",
        description="Search several Israeli listing sites at once (Yad2, Madlan). Same columns for "
                    "every site, with a 'source' column.",
        epilog="Example: israel-scraping rent --city raanana --max-price 8000 --min-rooms 3 -f csv",
    )
    _add_network_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("cities", help="find cities by name (Hebrew or English)")
    p.add_argument("query")
    for deal in ("sale", "rent"):
        p = sub.add_parser(deal, help=f"listings for {deal} on every site")
        p.add_argument("--city", required=True, help="city name (Hebrew or English)")
        p.add_argument("--sites", type=_words, default=list(SITES), metavar="LIST",
                       help=f"sites to search (default: {','.join(SITES)})")
        _add_filter_args(p, NUMBERS, COMMON_BOOL)
        p.add_argument("--keep-duplicates", action="store_true",
                       help="keep a property seen on several sites (by default, only its first listing is "
                            "kept: same address, rooms, price ±3%%)")
        _add_output_args(p, "max")
    return parser


def all_main(argv: list[str] | None = None) -> int:
    args = build_all_parser().parse_args(argv)
    if args.command == "cities":
        return _print_cities(args.query)

    def handle() -> int:
        filters = _filters(args, [*NUMBERS, *COMMON_BOOL])

        return _search(
            args,
            lambda: search_all(args.command, args.city, sites=args.sites, dedupe=not args.keep_duplicates,
                               max_per_site=args.max, client_options=_client_options(args), **filters),
            key=lambda x: f"{x.source}:{x.id}",
            fields=LISTING_FIELDS,
        )

    return _run(handle)


if __name__ == "__main__":
    sys.exit(yad2_main())
