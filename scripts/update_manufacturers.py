"""Regenerate src/israel_scraping/data/manufacturers.json (car manufacturers: id, Hebrew and English
names, number of listings).

Ids come from Yad2's public sitemap, Hebrew names from one page of listings per manufacturer
(about 100 requests at the client's default pace), English names from the table below.

Usage: python scripts/update_manufacturers.py [--proxy socks5h://127.0.0.1:40000]
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from curl_cffi import requests  # noqa: E402

from israel_scraping import Yad2  # noqa: E402

SITEMAP = "https://www.yad2.co.il/sitemaps-v3/yad2/vehicles/cars/manufacturers_1.xml"
OUT = pathlib.Path(__file__).resolve().parents[1] / "src" / "israel_scraping" / "data" / "manufacturers.json"

# Hebrew name as shown on Yad2 -> English name (left out when unsure: Hebrew and id still work)
ENGLISH: dict[str, str] = {
    "אאודי": "Audi", "אופל": "Opel", "אינפיניטי": "Infiniti", "איסוזו": "Isuzu",
    "אלפא רומיאו": "Alfa Romeo", "אם ג'י": "MG", "ב מ וו": "BMW", "ביואיק": "Buick",
    "ג'י.אם.סי": "GMC", "ג'יפ": "Jeep", "גרייט וול": "Great Wall", "דאצ'יה": "Dacia",
    "דודג'": "Dodge", "די.אס": "DS", "דייהטסו": "Daihatsu", "האמר": "Hummer", "הונדה": "Honda",
    "וולוו": "Volvo", "טויוטה": "Toyota", "יגואר": "Jaguar", "יונדאי": "Hyundai", "לוטוס": "Lotus",
    "לינקולן": "Lincoln", "לנד רובר": "Land Rover", "לנצ'יה": "Lancia", "לקסוס": "Lexus",
    "מאזדה": "Mazda", "מזראטי": "Maserati", "מיני": "Mini", "מיצובישי": "Mitsubishi",
    "מרצדס-בנץ": "Mercedes-Benz", "ניסאן": "Nissan", "סאאב": "Saab", "סאנגיונג": "SsangYong",
    "סובארו": "Subaru", "סוזוקי": "Suzuki", "סיאט": "Seat", "סיטרואן": "Citroen", "סמארט": "Smart",
    "סקודה": "Skoda", "פולקסווגן": "Volkswagen", "פונטיאק": "Pontiac", "פורד": "Ford",
    "פורשה": "Porsche", "פיאט": "Fiat", "פיג'ו": "Peugeot", "קאדילק": "Cadillac", "קיה": "Kia",
    "קרייזלר": "Chrysler", "רובר": "Rover", "רנו": "Renault", "שברולט": "Chevrolet",
    "אבארט": "Abarth", "אסטון מרטין": "Aston Martin", "בנטלי": "Bentley", "פרארי": "Ferrari",
    "רולס רויס": "Rolls-Royce", "טסלה": "Tesla", "למבורגיני": "Lamborghini", "מקלארן": "McLaren",
    "איווקו": "Iveco", "מאן": "MAN", "דונגפנג": "Dongfeng", "מקסוס": "Maxus", "פיאג'ו": "Piaggio",
    "ראם": "RAM", "קופרה": "Cupra", "ג'נסיס": "Genesis", "ג'י.איי.סי": "GAC", "אלפין": "Alpine",
    "בי.ווי.די": "BYD", "צ׳רי": "Chery", "ג׳ילי": "Geely", "ג׳יי.איי.סי": "JAC", "קארמה": "Karma",
    "אורה": "ORA", "פולסטאר": "Polestar", "ויי": "WEY", "סרס": "Seres", "ניאו": "NIO",
    "אקספנג": "XPeng", "סקייוול": "Skywell", "הונגצ'י": "Hongqi", "ליפמוטור": "Leapmotor",
    "לינק אנד קו": "Lynk & Co", "וויה": "Voyah", "זיקר": "Zeekr", "פורתינג": "Forthing",
    "אווטאר": "Avatr", "קיי גי אם": "KGM", "פוטון": "Foton", "ג'אקו": "Jaecoo", "דיפאל": "Deepal",
    "פאריזון": "Farizon", "אומודה": "Omoda", "איי אם": "IM", "איון": "Aion",
}


def main() -> None:
    proxy = sys.argv[sys.argv.index("--proxy") + 1] if "--proxy" in sys.argv else None
    proxies = {"http": proxy, "https": proxy} if proxy else None
    xml = requests.get(SITEMAP, impersonate="chrome", proxies=proxies, timeout=30).text
    ids = sorted({int(x) for x in re.findall(r"manufacturer=(\d+)", xml)})
    print(f"{len(ids)} manufacturer ids in the sitemap", file=sys.stderr)
    client = Yad2(proxy=proxy)
    rows, unnamed = [], []
    for mid in ids:
        page = client.vehicles.search("cars", manufacturer=mid)
        names = sorted({c.manufacturer for c in page.items if c.manufacturer})
        if not names:
            continue  # no listing right now: no name to show
        he = names[0].strip()
        if he not in ENGLISH:
            unnamed.append(he)
        rows.append([mid, he, ENGLISH.get(he, ""), page.total or 0])
    rows.sort(key=lambda r: -r[3])
    OUT.write_text(
        '{"columns": ["id", "name_he", "name_en", "listings"],\n "rows": [\n'
        + ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in rows)
        + "\n]}\n",
        encoding="utf-8",
    )
    print(f"{len(rows)} manufacturers written to {OUT}", file=sys.stderr)
    if unnamed:
        print("no English name for: " + ", ".join(unnamed), file=sys.stderr)


if __name__ == "__main__":
    main()
