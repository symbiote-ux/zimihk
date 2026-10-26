"""Regenerate the January 2026 test fixture in data/*.json.gz from Elexon.

The app fetches live from Elexon; this frozen snapshot only feeds the offline tests.
Run by hand: python backend/fetch_data.py
"""

import gzip
import json
from pathlib import Path

from elexon import get

OUT = Path(__file__).parent / "data"


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
    save("forecasts.json.gz", sorted(
        [r["publishTime"], r["startTime"], r["generation"]]
        for r in forecasts if r["startTime"] > r["publishTime"]
    ))
