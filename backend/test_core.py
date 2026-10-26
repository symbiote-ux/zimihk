from datetime import UTC, date, datetime, time

from core import gate_cutoff, load, pick, series, targets


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
