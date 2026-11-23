"""Command line interface: ``yad2 --help``."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .client import Yad2
from .errors import BlockedError, Yad2Error
from .locations import regions, search_cities
from .realestate import FILTERS as RE_FILTERS
from .vehicles import CATEGORIES

RE_BOOL = {
    "parking", "elevator", "balcony", "shelter", "air_conditioner", "renovated", "furniture",
    "bars", "accessibility", "pets", "image_only", "price_only", "price_dropped",
}
RE_NUMBERS = {
    "min_price": int, "max_price": int, "min_rooms": float, "max_rooms": float, "min_sqm": int,
    "max_sqm": int, "min_floor": int, "max_floor": int, "area": int, "neighborhood": int,
}


def _range(text: str) -> tuple[int | None, int | None]:
    """'2018-2022' -> (2018, 2022); '2018-' -> (2018, None); '-2022' is read as an option, use '0-2022'."""
    low, sep, high = text.partition("-")
    if not sep:
        raise argparse.ArgumentTypeError(f"expected MIN-MAX, got {text!r}")
    try:
        return (int(low) if low else None, int(high) if high else None)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected MIN-MAX with integers, got {text!r}") from exc


def _add_output_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("output")
    g.add_argument("--pages", type=int, metavar="N", help="read at most N pages (default: all)")
    g.add_argument("-f", "--format", choices=["jsonl", "json", "csv"], default="jsonl")
    g.add_argument("-o", "--output", metavar="FILE", help="write to FILE instead of stdout")
    g.add_argument("--raw", action="store_true", help="include the full API payload (jsonl/json)")
    w = p.add_argument_group("watch for new listings")
    w.add_argument("--watch", metavar="STATE_FILE",
                   help="only output listings not seen in previous runs (state kept in STATE_FILE)")
    w.add_argument("--every", type=float, metavar="SECONDS", help="with --watch: repeat every SECONDS")
    w.add_argument("--block-wait", type=float, default=1800, metavar="SECONDS",
                   help="with --every: pause after a block (default 1800)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yad2", description="Unofficial client for Yad2 (yad2.co.il) listings.",
        epilog="Example: yad2 realestate rent --city raanana --max-price 8000 --min-rooms 3 -f csv",
    )
    parser.add_argument("--version", action="version", version=f"yad2-client {__version__}")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1)")
    parser.add_argument("--impersonate", default="chrome", help="browser fingerprint (curl_cffi name)")
    parser.add_argument("--proxy", help="proxy URL, e.g. socks5h://127.0.0.1:1080")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cities", help="find city ids and regions by name")
    p.add_argument("query", help="name in Hebrew or English, or an id")

    p = sub.add_parser("realestate", help="search apartments and houses for sale or rent")
    p.add_argument("deal", choices=["forsale", "rent"])
    p.add_argument("--city", help="city name (Hebrew or English) or id, e.g. 'tel aviv'")
    p.add_argument("--region", type=int, help="region id (deduced from --city when omitted)")
    for name in RE_FILTERS:
        flag = "--" + name.replace("_", "-")
        if name in RE_BOOL:
            p.add_argument(flag, action="store_true", default=None)
        elif name in RE_NUMBERS:
            p.add_argument(flag, type=RE_NUMBERS[name])
        elif name == "sort":
            p.add_argument(flag, choices=["price-asc", "price-desc"])
        elif name == "property_types":
            p.add_argument(flag, metavar="IDS", help="comma-separated property type ids (1 = apartment)")
        else:
            p.add_argument(flag)
    _add_output_args(p)

    p = sub.add_parser("item", help="show one real-estate listing in full (JSON)")
    p.add_argument("token", help="listing token, the last part of its URL")

    p = sub.add_parser("vehicles", help="search cars, motorcycles, scooters, trucks")
    p.add_argument("category", nargs="?", default="cars", choices=CATEGORIES)
    p.add_argument("--manufacturer", type=int, help="manufacturer id (e.g. 19 = Toyota)")
    p.add_argument("--model", type=int, help="model id")
    p.add_argument("--area", type=int, help="area id")
    for name in ("year", "price", "km", "hand"):
        p.add_argument("--" + name, type=_range, metavar="MIN-MAX")
    _add_output_args(p)
    return parser


def _filters(args: argparse.Namespace, names: Iterable[str]) -> dict[str, Any]:
    return {n: getattr(args, n) for n in names if getattr(args, n, None) is not None}


class _Writer:
    def __init__(self, fmt: str, out: Any, raw: bool):
        self.fmt, self.out, self.raw = fmt, out, raw
        self.rows: list[dict] = []

    def write(self, listing: Any) -> None:
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
                w.writerow({k: " ".join(map(str, v)) if isinstance(v, list) else v for k, v in row.items()})
        self.out.flush()


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


def _run_once(listings: Iterator[Any], writer: _Writer, state: str | None) -> tuple[int, int]:
    """Output listings (only unseen ones with a state file). Returns (read, written)."""
    seen = _load_state(state) if state else {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    read = written = 0
    try:
        for listing in listings:
            read += 1
            if state and listing.token in seen:
                continue
            seen[listing.token] = now
            writer.write(listing)
            written += 1
    finally:
        if state:
            _save_state(state, seen)
    return read, written


def _search(args: argparse.Namespace, make_iter: Callable[[], Iterator[Any]]) -> int:
    if args.every and (not args.watch or args.format != "jsonl"):
        print("--every needs --watch STATE_FILE and the jsonl format", file=sys.stderr)
        return 2
    mode = "a" if args.watch else "w"
    out = open(args.output, mode, encoding="utf-8", newline="") if args.output else sys.stdout
    writer = _Writer(args.format, out, args.raw)
    try:
        while True:
            try:
                read, written = _run_once(make_iter(), writer, args.watch)
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "cities":
        names = regions()
        for c in search_cities(args.query, limit=15):
            region = f"region {c.region_id} ({names.get(c.region_id, '?')})"
            print(f"{c.id:>5}  {c.name_en:<28} {c.name_he:<22} {region}")
        return 0

    client = Yad2(delay=args.delay, impersonate=args.impersonate, proxy=args.proxy)
    try:
        if args.command == "item":
            detail = client.realestate.get(args.token)
            print(json.dumps(detail.to_dict(include_raw=True), ensure_ascii=False, indent=2))
            return 0
        if args.command == "realestate":
            filters = _filters(args, RE_FILTERS)
            return _search(args, lambda: client.realestate.iter_search(
                args.deal, max_pages=args.pages, city=args.city, region=args.region, **filters))
        filters = _filters(args, ("manufacturer", "model", "area", "year", "price", "km", "hand"))
        return _search(args, lambda: client.vehicles.iter_search(
            args.category, max_pages=args.pages, **filters))
    except BlockedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (Yad2Error, LookupError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
