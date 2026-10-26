from datetime import UTC, date, datetime, time

import pytest

from core import Row, by_day, by_horizon, by_hour, gate_cutoff, history_range, load, pick, series, stats, targets


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


TARGET = "2026-01-02T05:00:00Z"
DATA = load(
    [[TARGET, 900]],
    [
        ["2026-01-01T07:30:00Z", TARGET, 1000],
        ["2026-01-01T09:30:00Z", TARGET, 1100],
        [TARGET, TARGET, 1200],  # published at the target hour: never usable
    ],
)


def at_target(rows: list[Row]) -> Row:
    return next(row for row in rows if row.time == utc(TARGET))


def test_targets_normal_day():
    hours = targets(date(2026, 1, 2), date(2026, 1, 2))
    assert len(hours) == 24 and hours[0] == datetime(2026, 1, 2, 0, tzinfo=UTC)


def test_targets_dst_day_has_23_hours():
    assert len(targets(date(2026, 3, 29), date(2026, 3, 29))) == 23


def test_gate_cutoff_winter_and_summer():
    assert gate_cutoff(datetime(2026, 1, 2, 5, tzinfo=UTC), time(9, 20)) == datetime(2026, 1, 1, 9, 20, tzinfo=UTC)
    assert gate_cutoff(datetime(2026, 7, 2, 5, tzinfo=UTC), time(9, 20)) == datetime(2026, 7, 1, 8, 20, tzinfo=UTC)


def test_pick_latest_before_cutoff_inclusive():
    runs = [(utc("2026-01-01T07:30"), 100.0), (utc("2026-01-01T09:30"), 200.0)]
    target = utc("2026-01-02T05:00")
    assert pick(runs, utc("2026-01-01T09:20"), target) == (utc("2026-01-01T07:30"), 100.0)
    assert pick(runs, utc("2026-01-01T09:30"), target)[1] == 200.0
    assert pick(runs, utc("2026-01-01T07:00"), target) is None


def test_series_gate_picks_run_before_gate():
    row = at_target(series(DATA, date(2026, 1, 2), date(2026, 1, 2), gate=time(9, 20)))
    assert (row.forecast, row.actual, row.publish) == (1000, 900, utc("2026-01-01T07:30"))


def test_horizon_zero_excludes_run_published_at_target():
    row = at_target(series(DATA, date(2026, 1, 2), date(2026, 1, 2), horizon=0))
    assert row.forecast == 1100


def test_series_gate_row_has_no_forecast_when_no_run_before_cutoff():
    row = at_target(series(DATA, date(2026, 1, 2), date(2026, 1, 2), gate=time(7, 0)))
    assert row.forecast is None and row.publish is None


def test_series_actual_none_when_missing():
    rows = series(DATA, date(2026, 1, 2), date(2026, 1, 2), gate=time(9, 20))
    assert len(rows) == 24 and sum(row.actual is not None for row in rows) == 1


PUBLISH = utc("2026-01-01T07:30")
ROWS = [
    Row(utc("2026-01-02T00:00"), 8, 10, PUBLISH),
    Row(utc("2026-01-02T01:00"), 25, 20, PUBLISH),
    Row(utc("2026-01-02T02:00"), 30, 30, PUBLISH),
    Row(utc("2026-01-02T03:00"), 5, None, None),
]  # errors: +2, -5, 0


def test_stats_basic():
    scored = stats(ROWS)
    assert scored["count"] == 3 and scored["coverage"] == 0.75
    assert scored["mae"] == pytest.approx(7 / 3)
    assert scored["bias"] == pytest.approx(-1)
    assert scored["rmse"] == pytest.approx((29 / 3) ** 0.5)
    assert scored["nmae"] == pytest.approx((7 / 3) / 21)
    assert (scored["err_p10"], scored["err_p90"]) == (-5, 2)


def test_stats_empty_is_none_not_error():
    scored = stats([Row(utc("2026-01-02T00:00"), None, 10, PUBLISH)])
    assert scored["count"] == 0 and scored["mae"] is None and scored["p90"] is None
    assert stats([])["coverage"] == 0


def test_history_range_is_last_30_settled_days_no_lookahead():
    assert history_range(date(2026, 1, 16)) == (date(2025, 12, 16), date(2026, 1, 14))
    assert history_range(date(2026, 1, 2)) == (date(2025, 12, 2), date(2025, 12, 31))


def test_by_day_groups_errors_by_london_date():
    out = by_day(ROWS + [Row(utc("2026-07-01T23:00"), 10, 12, PUBLISH)])  # 23:00Z in BST is 00:00 on 2 Jul
    assert [entry["day"] for entry in out] == ["2026-01-02", "2026-07-02"]
    assert out[0]["count"] == 3 and out[0]["mae"] == pytest.approx(7 / 3) and out[0]["bias"] == pytest.approx(-1)


def test_by_hour_uses_london_hour():
    out = by_hour([Row(utc("2026-07-01T23:00"), 10, 12, PUBLISH)])
    assert out == [{"hour": 0, "count": 1, "mae": 2, "bias": 2}]


def test_by_horizon_returns_one_entry_per_lead_time():
    out = by_horizon(DATA, date(2026, 1, 2), date(2026, 1, 2))
    assert [entry["hours_ahead"] for entry in out] == list(range(0, 49, 3))
    assert out[0]["count"] == 1 and out[0]["bias"] == 200  # 1100 forecast vs 900 actual
