import gzip
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as appmod
import core
import elexon


def _read(name: str) -> list:
    with gzip.open(Path(__file__).parent / "data" / name, "rt") as fixture:
        return json.load(fixture)


# January 2026 snapshot stands in for Elexon so tests never touch the network.
SNAP = core.load(_read("actuals.json.gz"), _read("forecasts.json.gz"))
calls: list[tuple[date, date]] = []


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    calls.clear()

    def fake(first: date, last: date) -> core.Data:
        calls.append((first, last))
        return SNAP

    monkeypatch.setattr(appmod.elexon, "fetch", fake)


client = TestClient(appmod.app, raise_server_exceptions=False)
FULL = {"start": "2026-01-02", "end": "2026-02-01"}


def day(delivery: str, **params) -> dict:
    return client.get("/api/series", params={"start": delivery, "end": delivery, **params}).json()


def test_meta():
    meta = client.get("/api/meta").json()
    assert (meta["start"], meta["end"], meta["default_gate"]) == ("2026-01-02", "2026-02-01", "09:20")
    assert (meta["min"], meta["max"]) == ("2023-01-01", core.latest_delivery().isoformat())


def test_series_one_day_gate():
    result = day("2026-01-15")
    assert len(result["rows"]) == 24 and result["stats"]["count"] == 24
    assert all(row["publish"].startswith("2026-01-14T07:30") for row in result["rows"])


def test_series_custom_gate_uses_later_run():
    assert day("2026-01-15", gate="10:00")["rows"][0]["publish"].startswith("2026-01-14T09:30")


def test_series_history_is_last_30_settled_days_and_fetched_once():
    history = day("2026-01-16")["history"]
    assert (history["start"], history["end"], history["days"]) == ("2025-12-16", "2026-01-14", 30)
    assert history["stats"]["count"] > 0
    assert calls == [(date(2025, 12, 16), date(2026, 1, 16))]


def test_history_carries_the_accuracy_breakdowns():
    history = day("2026-02-01")["history"]  # D-31..D-2 = 1-30 Jan, all inside the fixture
    assert (history["start"], history["end"]) == ("2026-01-01", "2026-01-30")
    assert len(history["by_day"]) == 30 and history["by_day"][0]["day"] == "2026-01-01"
    assert len(history["by_hour"]) == 24
    assert [entry["hours_ahead"] for entry in history["by_horizon"]] == list(range(0, 49, 3))


@pytest.mark.parametrize("params", [
    {"start": "2022-12-31", "end": "2023-01-05"},  # before EARLIEST
    {"start": "2026-01-10", "end": "2026-01-05"},  # start > end
    {"start": "2026-01-01", "end": "2026-02-05"},  # 36 days > MAX_DAYS
    {"start": "2099-01-01", "end": "2099-01-01"},  # after tomorrow
    {"start": "2026-01-02", "end": "2026-01-02", "gate": "25:00"},
])
def test_bad_params_422_without_calling_elexon(params):
    assert client.get("/api/series", params=params).status_code == 422
    assert calls == []


def test_elexon_down_is_502_json(monkeypatch):
    def down(*_):
        raise elexon.ElexonError("timeout")

    monkeypatch.setattr(appmod.elexon, "fetch", down)
    response = client.get("/api/series", params=FULL)
    assert response.status_code == 502 and "Elexon" in response.json()["detail"]
    assert "s-maxage" not in response.headers.get("cache-control", "")


def test_unexpected_error_is_500_json(monkeypatch):
    def boom(*_):
        raise RuntimeError("bug")

    monkeypatch.setattr(appmod.elexon, "fetch", boom)
    response = client.get("/api/series", params=FULL)
    assert response.status_code == 500 and response.json() == {"detail": "Internal server error"}
    assert "s-maxage" not in response.headers.get("cache-control", "")


def test_success_cached_25_min_at_cdn():
    assert "s-maxage=1500" in client.get("/api/series", params=FULL).headers["cache-control"]
