"""Unit tests for the Elexon client, with the network replaced."""

import io
from datetime import date
from urllib.error import URLError

import pytest

import elexon


def test_fetch_asks_for_the_right_windows_and_drops_hindcasts(monkeypatch):
    seen = {}

    def fake_get(dataset, **params):
        seen[dataset] = params
        if dataset == "FUELHH":
            return [{"startTime": "2026-01-15T05:00:00Z", "generation": 900}]
        return [
            {"publishTime": "2026-01-14T07:30:00Z", "startTime": "2026-01-15T05:00:00Z", "generation": 1000},
            {"publishTime": "2026-01-15T05:00:00Z", "startTime": "2026-01-15T05:00:00Z", "generation": 1},  # hindcast
        ]

    monkeypatch.setattr(elexon, "get", fake_get)
    data = elexon.fetch(date(2026, 1, 15), date(2026, 1, 15))

    assert seen["FUELHH"] == {"settlementDateFrom": "2026-01-15", "settlementDateTo": "2026-01-15", "fuelType": "WIND"}
    # runs reach ~66 h ahead, so look back 3 days; horizon 0 needs runs up to the end of the last day
    assert seen["WINDFOR"] == {
        "publishDateTimeFrom": "2026-01-12T00:00:00Z",
        "publishDateTimeTo": "2026-01-16T00:00:00Z",
    }
    assert [mw for runs in data.runs.values() for _, mw in runs] == [1000]
    assert list(data.actuals.values()) == [900]


@pytest.mark.parametrize("exc", [URLError("dns failure"), TimeoutError("read timed out")])
def test_get_wraps_network_failures(monkeypatch, exc):
    def boom(*_, **__):
        raise exc

    monkeypatch.setattr(elexon, "urlopen", boom)
    with pytest.raises(elexon.ElexonError):
        elexon.get("WINDFOR")


def test_get_wraps_non_json_response(monkeypatch):
    monkeypatch.setattr(elexon, "urlopen", lambda *_, **__: io.BytesIO(b"<html>maintenance</html>"))
    with pytest.raises(elexon.ElexonError):
        elexon.get("WINDFOR")
