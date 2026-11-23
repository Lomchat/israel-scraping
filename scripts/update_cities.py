"""Regenerate src/yad2_client/data/cities.json from Yad2's address service.

Usage: python scripts/update_cities.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from yad2_client import Yad2  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "src" / "yad2_client" / "data" / "cities.json"


def main() -> None:
    client = Yad2()
    rows, page = [], 1
    while True:
        data = client.get_json(
            "/address-master/cities", {"result_type": "extended", "limit": 1000, "page": page}
        )["data"]
        rows += data["data"]
        if page >= data["paginator"]["total_pages"]:
            break
        page += 1
    cities = sorted(
        (
            [
                r["city_id"],
                r.get("city_heb") or "",
                r.get("city_eng") or "",
                r.get("region_id"),
                r.get("area_id"),
                r.get("popularity") or 0,
            ]
            for r in rows
        ),
        key=lambda c: -c[5],
    )
    regions = {r["region_id"]: r.get("region_eng") or r.get("region_heb") for r in rows if r.get("region_id")}
    OUT.write_text(
        '{"regions": '
        + json.dumps({str(k): regions[k] for k in sorted(regions)}, ensure_ascii=False)
        + ',\n "columns": ["id", "name_he", "name_en", "region_id", "area_id", "popularity"],\n "rows": [\n'
        + ",\n".join("  " + json.dumps(c, ensure_ascii=False) for c in cities)
        + "\n]}\n",
        encoding="utf-8",
    )
    print(f"{len(cities)} cities written to {OUT}")


if __name__ == "__main__":
    main()
