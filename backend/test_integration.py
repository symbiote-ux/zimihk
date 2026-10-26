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
    assert {row.publish for row in rows} == {datetime(2026, 1, 14, 7, 30, tzinfo=UTC)}


def test_live_api_matches_known_january_baseline():
    response = TestClient(app).get("/api/series", params={"start": "2026-01-02", "end": "2026-01-31"})
    assert response.status_code == 200
    scored = response.json()["stats"]
    assert (scored["count"], round(scored["mae"]), round(scored["bias"])) == (720, 2058, 1772)
