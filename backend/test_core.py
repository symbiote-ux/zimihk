from datetime import UTC, date, datetime, time

import pytest

from core import Row, by_horizon, by_hour, gate_cutoff, histogram, history_range, load, pick, series, stats, targets


def dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


T = "2026-01-02T05:00:00Z"
DATA = load(
    [[T, 900]],
    [
        ["2026-01-01T07:30:00Z", T, 1000],
        ["2026-01-01T09:30:00Z", T, 1100],
        [T, T, 1200],  # published at the target hour: never usable
    ],
)


def test_targets_normal_day():
    ts = targets(date(2026, 1, 2), date(2026, 1, 2))
    assert len(ts) == 24 and ts[0] == datetime(2026, 1, 2, 0, tzinfo=UTC)


def test_targets_dst_day_has_23_hours():
    assert len(targets(date(2026, 3, 29), date(2026, 3, 29))) == 23


def test_gate_cutoff_winter_and_summer():
    assert gate_cutoff(datetime(2026, 1, 2, 5, tzinfo=UTC), time(9, 20)) == datetime(2026, 1, 1, 9, 20, tzinfo=UTC)
    assert gate_cutoff(datetime(2026, 7, 2, 5, tzinfo=UTC), time(9, 20)) == datetime(2026, 7, 1, 8, 20, tzinfo=UTC)


def test_pick_latest_before_cutoff_inclusive():
    runs = [(dt("2026-01-01T07:30"), 100.0), (dt("2026-01-01T09:30"), 200.0)]
    t = dt("2026-01-02T05:00")
    assert pick(runs, dt("2026-01-01T09:20"), t) == (dt("2026-01-01T07:30"), 100.0)
    assert pick(runs, dt("2026-01-01T09:30"), t)[1] == 200.0
    assert pick(runs, dt("2026-01-01T07:00"), t) is None


def test_series_gate_picks_run_before_gate():
    row = next(r for r in series(DATA, date(2026, 1, 2), date(2026, 1, 2), gate=time(9, 20)) if r.t == dt(T))
    assert (row.forecast, row.actual, row.publish) == (1000, 900, dt("2026-01-01T07:30"))


def test_horizon_zero_excludes_run_published_at_target():
    row = next(r for r in series(DATA, date(2026, 1, 2), date(2026, 1, 2), horizon=0) if r.t == dt(T))
    assert row.forecast == 1100


def test_series_gate_row_has_no_forecast_when_no_run_before_cutoff():
    row = next(r for r in series(DATA, date(2026, 1, 2), date(2026, 1, 2), gate=time(7, 0)) if r.t == dt(T))
    assert row.forecast is None and row.publish is None


def test_series_actual_none_when_missing():
    rows = series(DATA, date(2026, 1, 2), date(2026, 1, 2), gate=time(9, 20))
    assert len(rows) == 24 and sum(r.actual is not None for r in rows) == 1


P = dt("2026-01-01T07:30")
ROWS = [
    Row(dt("2026-01-02T00:00"), 8, 10, P),
    Row(dt("2026-01-02T01:00"), 25, 20, P),
    Row(dt("2026-01-02T02:00"), 30, 30, P),
    Row(dt("2026-01-02T03:00"), 5, None, None),
]  # errors: +2, -5, 0


def test_stats_basic():
    s = stats(ROWS)
    assert s["n"] == 3 and s["coverage"] == 0.75
    assert s["mae"] == pytest.approx(7 / 3)
    assert s["bias"] == pytest.approx(-1)
    assert s["rmse"] == pytest.approx((29 / 3) ** 0.5)
    assert s["nmae"] == pytest.approx((7 / 3) / 21)
    assert (s["err_p10"], s["err_p90"]) == (-5, 2)


def test_stats_empty_is_none_not_error():
    s = stats([Row(dt("2026-01-02T00:00"), None, 10, P)])
    assert s["n"] == 0 and s["mae"] is None and s["p90"] is None
    assert stats([])["coverage"] == 0


def test_histogram_bins():
    assert histogram(ROWS, 500) == [{"lo": -500, "count": 1}, {"lo": 0, "count": 2}]


def test_history_range_no_lookahead():
    assert history_range(date(2026, 1, 16)) == (date(2026, 1, 2), date(2026, 1, 14))
    assert history_range(date(2026, 1, 4)) == (date(2026, 1, 2), date(2026, 1, 2))
    assert history_range(date(2026, 1, 3)) is None and history_range(date(2026, 1, 2)) is None


def test_by_hour_uses_london_hour():
    out = by_hour([Row(dt("2026-07-01T23:00"), 10, 12, P)])
    assert out == [{"hour": 0, "n": 1, "mae": 2, "bias": 2}]


def test_by_horizon_returns_one_entry_per_h():
    out = by_horizon(DATA, date(2026, 1, 2), date(2026, 1, 2))
    assert [o["h"] for o in out] == list(range(0, 49, 3))
    assert out[0]["n"] == 1 and out[0]["bias"] == 200  # 1100 forecast vs 900 actual
