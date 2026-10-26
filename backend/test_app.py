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
    with gzip.open(Path(__file__).parent / "data" / name, "rt") as f:
        return json.load(f)


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


c = TestClient(appmod.app, raise_server_exceptions=False)
FULL = {"start": "2026-01-02", "end": "2026-02-01"}


def day(d: str, **kw) -> dict:
    return c.get("/api/series", params={"start": d, "end": d, **kw}).json()


def test_meta():
    m = c.get("/api/meta").json()
    assert (m["start"], m["end"], m["default_gate"]) == ("2026-01-02", "2026-02-01", "09:20")
    assert (m["min"], m["max"], m["max_days"]) == ("2023-01-01", core.latest_delivery().isoformat(), 31)


def test_series_one_day_gate():
    r = day("2026-01-15")
    assert len(r["rows"]) == 24 and r["stats"]["n"] == 24
    assert all(row["publish"].startswith("2026-01-14T07:30") for row in r["rows"])


def test_series_custom_gate_uses_later_run():
    assert day("2026-01-15", gate="10:00")["rows"][0]["publish"].startswith("2026-01-14T09:30")


def test_series_history_is_last_30_settled_days_and_fetched_once():
    h = day("2026-01-16")["history"]
    assert (h["start"], h["end"], h["days"]) == ("2025-12-16", "2026-01-14", 30)
    assert h["stats"]["n"] > 0
    assert calls == [(date(2025, 12, 16), date(2026, 1, 16))]


def test_series_horizon_mode():
    rows = day("2026-01-15", horizon=0)["rows"]
    assert all(r["publish"] < r["t"] for r in rows if r["publish"])


@pytest.mark.parametrize("params", [
    {"start": "2022-12-31", "end": "2023-01-05"},  # before EARLIEST
    {"start": "2026-01-10", "end": "2026-01-05"},  # start > end
    {"start": "2026-01-01", "end": "2026-02-05"},  # 36 days > MAX_DAYS
    {"start": "2099-01-01", "end": "2099-01-01"},  # after tomorrow
    {"start": "2026-01-02", "end": "2026-01-02", "gate": "25:00"},
    {"start": "2026-01-02", "end": "2026-01-02", "horizon": "99"},
])
def test_bad_params_422_without_calling_elexon(params):
    assert c.get("/api/series", params=params).status_code == 422
    assert calls == []


def test_horizons_len():
    assert len(c.get("/api/horizons", params=FULL).json()) == 17
    assert calls == [(date(2026, 1, 2), date(2026, 2, 1))]


def test_elexon_down_is_502_json(monkeypatch):
    def down(*_):
        raise elexon.ElexonError("timeout")

    monkeypatch.setattr(appmod.elexon, "fetch", down)
    r = c.get("/api/series", params=FULL)
    assert r.status_code == 502 and "Elexon" in r.json()["detail"]
    assert "s-maxage" not in r.headers.get("cache-control", "")


def test_unexpected_error_is_500_json(monkeypatch):
    def boom(*_):
        raise RuntimeError("bug")

    monkeypatch.setattr(appmod.elexon, "fetch", boom)
    r = c.get("/api/series", params=FULL)
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error"}
    assert "s-maxage" not in r.headers.get("cache-control", "")


def test_success_cached_25_min_at_cdn():
    assert "s-maxage=1500" in c.get("/api/series", params=FULL).headers["cache-control"]
