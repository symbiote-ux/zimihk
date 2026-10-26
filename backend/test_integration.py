"""Integration tests against the live Elexon API. Run with: pytest -m integration"""

from datetime import UTC, date, datetime, time

import pytest
from fastapi.testclient import TestClient

import core
import elexon
from app import app

pytestmark = pytest.mark.integration


def test_live_elexon_has_the_0730_gate_run_for_15_jan():
    data = elexon.fetch(date(2026, 1, 15), date(2026, 1, 15))
    assert len(data.actuals) == 48  # half-hourly FUELHH
    rows = core.series(data, date(2026, 1, 15), date(2026, 1, 15), gate=time(9, 20))
    assert len(rows) == 24
    assert {r.publish for r in rows} == {datetime(2026, 1, 14, 7, 30, tzinfo=UTC)}


def test_live_api_matches_known_january_baseline():
    r = TestClient(app).get("/api/series", params={"start": "2026-01-02", "end": "2026-01-31"})
    assert r.status_code == 200
    s = r.json()["stats"]
    assert (s["n"], round(s["mae"]), round(s["bias"])) == (720, 2058, 1772)
