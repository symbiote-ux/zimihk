"""Download the Jan 2026 wind snapshot from Elexon BMRS into data/*.json.gz.

Run by hand: python backend/fetch_data.py
"""

import gzip
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets/{}/stream?"
OUT = Path(__file__).parent / "data"


def get(dataset: str, **params: str) -> list[dict]:
    with urlopen(BASE.format(dataset) + urlencode(params), timeout=60) as r:
        return json.load(r)


def save(name: str, rows: list) -> None:
    OUT.mkdir(exist_ok=True)
    path = OUT / name
    with gzip.open(path, "wt") as f:
        json.dump(rows, f, separators=(",", ":"))
    print(f"{name}: {len(rows)} rows, {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    actuals = get("FUELHH", settlementDateFrom="2026-01-01", settlementDateTo="2026-02-02", fuelType="WIND")
    save("actuals.json.gz", sorted([r["startTime"], r["generation"]] for r in actuals))

    forecasts = get("WINDFOR", publishDateTimeFrom="2025-12-31T00:00:00Z", publishDateTimeTo="2026-02-02T00:00:00Z")
    # ISO-8601 'Z' strings compare correctly as text; startTime <= publishTime rows are hindcasts.
    save("forecasts.json.gz", sorted(
        [r["publishTime"], r["startTime"], r["generation"]]
        for r in forecasts if r["startTime"] > r["publishTime"]
    ))
