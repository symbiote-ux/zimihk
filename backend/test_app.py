import pytest
from fastapi.testclient import TestClient

from app import app

c = TestClient(app)
FULL = {"start": "2026-01-02", "end": "2026-02-01"}


def day(d: str, **kw) -> dict:
    return c.get("/api/series", params={"start": d, "end": d, **kw}).json()


def test_meta():
    assert c.get("/api/meta").json() == {"start": "2026-01-02", "end": "2026-02-01", "default_gate": "09:20"}


def test_series_one_day_gate():
    r = day("2026-01-15")
    assert len(r["rows"]) == 24 and r["stats"]["n"] == 24
    assert all(row["publish"].startswith("2026-01-14T07:30") for row in r["rows"])


def test_series_custom_gate_uses_later_run():
    assert day("2026-01-15", gate="10:00")["rows"][0]["publish"].startswith("2026-01-14T09:30")


def test_series_history_has_no_lookahead():
    h = day("2026-01-16")["history"]
    assert h["start"] == "2026-01-02" and h["end"] == "2026-01-14" and h["days"] == 13
    assert h["stats"]["n"] > 0
    assert day("2026-01-02")["history"] is None


def test_series_horizon_mode():
    rows = day("2026-01-15", horizon=0)["rows"]
    assert all(r["publish"] < r["t"] for r in rows if r["publish"])


@pytest.mark.parametrize("params", [
    {"start": "2025-12-01", "end": "2026-01-05"},
    {"start": "2026-01-10", "end": "2026-01-05"},
    {"start": "2026-01-02", "end": "2026-01-02", "gate": "25:00"},
    {"start": "2026-01-02", "end": "2026-01-02", "horizon": "99"},
])
def test_bad_params_422(params):
    assert c.get("/api/series", params=params).status_code == 422


def test_horizons_len():
    assert len(c.get("/api/horizons", params=FULL).json()) == 17
