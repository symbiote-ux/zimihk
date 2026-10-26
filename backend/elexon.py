"""Elexon BMRS client: live wind actuals (FUELHH) and forecasts (WINDFOR). Public API, no key."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import core

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets/{}/stream?"
TIMEOUT = 25  # seconds; a 62-day pull usually takes 4-13 s


class ElexonError(Exception):
    """Elexon unreachable, slow or returned something unusable."""


def get(dataset: str, **params: str) -> list[dict]:
    try:
        with urlopen(BASE.format(dataset) + urlencode(params), timeout=TIMEOUT) as response:
            return json.load(response)
    except (URLError, TimeoutError, ValueError) as err:  # HTTPError is a URLError; bad JSON is a ValueError
        raise ElexonError(f"{dataset}: {err}") from err


def fetch(first: date, last: date) -> core.Data:
    """Actuals for delivery days first..last, plus every forecast run that could target them."""
    with ThreadPoolExecutor(2) as pool:  # the two datasets in parallel: ~4 s instead of ~8 s
        actuals = pool.submit(
            get, "FUELHH", settlementDateFrom=first.isoformat(), settlementDateTo=last.isoformat(), fuelType="WIND"
        )
        forecasts = pool.submit(
            get, "WINDFOR",
            publishDateTimeFrom=f"{first - timedelta(days=3)}T00:00:00Z",  # runs reach ~66 h ahead
            publishDateTimeTo=f"{last + timedelta(days=1)}T00:00:00Z",
        )
        actual_rows, forecast_rows = actuals.result(), forecasts.result()
    return core.load(
        [[row["startTime"], row["generation"]] for row in actual_rows],
        # startTime <= publishTime rows are hindcasts, not forecasts
        [
            [row["publishTime"], row["startTime"], row["generation"]]
            for row in forecast_rows
            if row["startTime"] > row["publishTime"]
        ],
    )
