"""Send new listings from Yad2 and Madlan to a Telegram chat. Run it every hour or so (cron, systemd timer...).

Setup:
  1. Create a bot with @BotFather and copy its token.
  2. Send any message to your bot, then open https://api.telegram.org/bot<TOKEN>/getUpdates
     and copy the "chat" "id".
  3. Edit SEARCH below, then:

     export TELEGRAM_BOT_TOKEN=123456:ABC... TELEGRAM_CHAT_ID=987654
     python examples/telegram_alerts.py
     # crontab -e:  0 * * * * cd /path/to/folder && python telegram_alerts.py

The first run only remembers the current listings; new ones are sent from the next run on.
Only the standard library and yad2-client are needed.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from israel_scraping import Listing, search_all

DEAL = "rent"  # or "sale"
CITY = "raanana"
FILTERS = {"max_price": 8000, "min_rooms": 3}  # filters both sites understand
STATE = Path(os.environ.get("YAD2_STATE", "seen-telegram.json"))


def send(text: str) -> None:
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text}).encode()
    urllib.request.urlopen(url, data=data, timeout=30).read()


def describe(listing: Listing) -> str:
    price = f"{listing.price:,} ₪" if listing.price else "no price"
    rooms = f"{listing.rooms:g} rooms" if listing.rooms else "? rooms"
    size = f"{listing.square_meters} m²" if listing.square_meters else "? m²"
    street = " ".join(str(x) for x in (listing.street, listing.house_number) if x)
    place = ", ".join(x for x in (street, listing.neighborhood, listing.city) if x)
    return f"🏠 {price} · {rooms} · {size} ({listing.source})\n{place}\n{listing.url}"


def main() -> None:
    first_run = not STATE.exists()
    seen = set() if first_run else set(json.loads(STATE.read_text()))
    new = []
    for listing in search_all(DEAL, CITY, **FILTERS):  # both sites, duplicates dropped
        key = f"{listing.source}:{listing.id}"
        if key not in seen:
            seen.add(key)
            new.append(listing)
    STATE.write_text(json.dumps(sorted(seen)))
    if first_run:
        print(f"{len(seen)} current listings remembered; new ones will be sent from the next run.")
        return
    for listing in new:
        send(describe(listing))
    print(f"{len(new)} new listing(s) sent.")


if __name__ == "__main__":
    main()
