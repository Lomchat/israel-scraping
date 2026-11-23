"""Measure how many requests Yad2 accepts from your IP (or through a proxy).

Each request reads one page of real-estate search results (about 40 listings). On a refusal from
the bot protection, every thread pauses (``--pause``) so the benchmark never hammers a blocked IP.

Examples:
  python scripts/benchmark.py --rate 1 --minutes 60          # gentle: the library's default pace
  python scripts/benchmark.py --rate 3 --threads 3 --minutes 30
  python scripts/benchmark.py --threads 16 --stop-on-block   # burst: as fast as possible
  python scripts/benchmark.py --rate 1 --minutes 60 --proxy socks5h://127.0.0.1:40000
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yad2_client import BlockedError, Yad2, Yad2Error  # noqa: E402

SEARCHES = [
    ("forsale", "tel aviv"), ("rent", "tel aviv"), ("forsale", "jerusalem"), ("rent", "jerusalem"),
    ("forsale", "haifa"), ("rent", "haifa"), ("forsale", "raanana"), ("rent", "raanana"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rate", type=float, default=0, help="target requests/second overall (0 = no limit)")
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--pause", type=float, default=60, help="seconds every thread waits after a refusal")
    ap.add_argument("--stop-on-block", action="store_true", help="stop at the first refusal")
    ap.add_argument("--proxy", help="e.g. socks5h://127.0.0.1:40000")
    ap.add_argument("--impersonate", default="chrome")
    args = ap.parse_args()

    searches = itertools.cycle(SEARCHES)
    last_page = {s: 40 for s in SEARCHES}  # lowered to the real page count once known
    cursor = {s: 0 for s in SEARCHES}

    def next_request() -> tuple[str, str, int]:
        search = next(searches)
        cursor[search] = cursor[search] % last_page[search] + 1
        return (*search, cursor[search])

    lock = threading.Lock()
    # "empty" counts answers without any listing: on existing pages it should stay at 0.
    # "sessions_replaced": used sessions refused and replaced by the client without failing.
    stats = {"ok": 0, "refused": 0, "errors": 0, "listings": 0, "empty": 0, "pauses": 0,
             "sessions_replaced": 0}

    class CountReplacements(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if "session refused" in record.getMessage():
                with lock:
                    stats["sessions_replaced"] += 1

    client_log = logging.getLogger("yad2_client")
    client_log.setLevel(logging.INFO)
    client_log.addHandler(CountReplacements())
    latencies: list[float] = []
    first_refusal: dict = {}
    clock = {"next_slot": time.monotonic(), "pause_until": 0.0}
    start = time.monotonic()
    end = start + args.minutes * 60
    stop = threading.Event()

    def take_slot() -> bool:
        """Wait for this thread's turn (rate limit, pause after a refusal). False when time is up."""
        while not stop.is_set():
            with lock:
                now = time.monotonic()
                if now >= end:
                    return False
                paused = clock["pause_until"] - now
                if paused <= 0:
                    slot = max(now, clock["next_slot"]) if args.rate > 0 else now
                    clock["next_slot"] = slot + (1 / args.rate if args.rate > 0 else 0)
            if paused > 0:
                time.sleep(min(paused, 5))
                continue
            time.sleep(max(0.0, slot - time.monotonic()))
            return True
        return False

    def worker() -> None:
        client = Yad2(delay=0, retries=1, block_retries=0, proxy=args.proxy, impersonate=args.impersonate)
        while take_slot():
            with lock:
                deal, city, page = next_request()
            t0 = time.monotonic()
            try:
                result = client.realestate.search(deal, city=city, page=page)
            except BlockedError:
                with lock:
                    stats["refused"] += 1
                    if not first_refusal:
                        first_refusal.update(after_requests=stats["ok"],
                                             after_seconds=round(time.monotonic() - start))
                    if args.stop_on_block:
                        stop.set()
                    elif clock["pause_until"] <= time.monotonic():
                        clock["pause_until"] = time.monotonic() + args.pause
                        stats["pauses"] += 1
                        print(f"{_now()} refused -> all threads pause {args.pause:.0f}s", flush=True)
                continue
            except Yad2Error:
                with lock:
                    stats["errors"] += 1
                continue
            with lock:
                stats["ok"] += 1
                stats["listings"] += len(result.items)
                stats["empty"] += not result.items
                latencies.append(time.monotonic() - t0)
                if result.total_pages:
                    last_page[(deal, city)] = min(40, result.total_pages)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.threads)]
    for t in threads:
        t.start()
    last_ok = 0
    while any(t.is_alive() for t in threads):
        minute = time.monotonic() + 60
        while time.monotonic() < minute and any(t.is_alive() for t in threads):
            time.sleep(1)
        with lock:
            ok, refused = stats["ok"], stats["refused"]
        print(f"{_now()} +{ok - last_ok} ok this minute | total {ok} ok, {refused} refused", flush=True)
        last_ok = ok

    elapsed = time.monotonic() - start
    lat = sorted(latencies)
    summary = {
        "date": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "route": args.proxy or "direct",
        "target_rate": args.rate or "unlimited",
        "threads": args.threads,
        "minutes": round(elapsed / 60, 1),
        **stats,
        "first_refusal": first_refusal or None,
        "ok_per_second": round(stats["ok"] / elapsed, 2),
        "ok_per_hour": round(stats["ok"] / elapsed * 3600),
        "latency_p50": round(statistics.median(lat), 2) if lat else None,
        "latency_p95": round(lat[int(len(lat) * 0.95) - 1], 2) if lat else None,
    }
    print(json.dumps(summary), flush=True)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


if __name__ == "__main__":
    main()
