"""Pure domain logic: pick the forecast a buyer could have used, and score it.

All datetimes are tz-aware UTC. Delivery days and the gate are Europe/London.
Error is always forecast - actual (positive = over-forecast).
"""

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from statistics import fmean
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
PILOT = (date(2026, 1, 2), date(2026, 2, 1))  # default view: delivery days for decisions made in Jan 2026
EARLIEST = date(2023, 1, 1)  # oldest delivery day we serve
MAX_DAYS = 31  # longest delivery range per request (bounds the Elexon fetch)
HISTORY_DAYS = 30  # rolling error history behind each decision
DEFAULT_GATE = time(9, 20)  # EPEX GB day-ahead gate closure, UK time, on D-1

Run = tuple[datetime, float]  # (publish time, forecast MW)


def _parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


@dataclass(frozen=True)
class Data:
    actuals: dict[datetime, float]
    runs: dict[datetime, list[Run]]  # target -> runs, oldest publish first


@dataclass(frozen=True)
class Row:
    time: datetime
    actual: float | None
    forecast: float | None
    publish: datetime | None


def load(actual_rows: list[list], forecast_rows: list[list]) -> Data:
    runs: dict[datetime, list[Run]] = {}
    for publish, start, mw in forecast_rows:
        runs.setdefault(_parse_utc(start), []).append((_parse_utc(publish), mw))
    for target_runs in runs.values():
        target_runs.sort()
    return Data({_parse_utc(start): mw for start, mw in actual_rows}, runs)


def _local_midnight(day: date) -> datetime:
    return datetime.combine(day, time(), LONDON).astimezone(UTC)


def targets(start: date, end: date) -> list[datetime]:
    """Every UTC hour whose London-local date is in [start, end] (23 or 25 on clock-change days)."""
    hour, stop = _local_midnight(start), _local_midnight(end + timedelta(days=1))
    hours = []
    while hour < stop:
        hours.append(hour)
        hour += timedelta(hours=1)
    return hours


def gate_cutoff(target: datetime, gate: time) -> datetime:
    decision_day = target.astimezone(LONDON).date() - timedelta(days=1)
    return datetime.combine(decision_day, gate, LONDON).astimezone(UTC)


def pick(runs: list[Run], cutoff: datetime, target: datetime) -> Run | None:
    """Latest run published at/before the cutoff and strictly before the target."""
    best = None
    for publish, mw in runs:  # sorted by publish, so the first miss ends the scan
        if publish > cutoff or publish >= target:
            break
        best = (publish, mw)
    return best


def series(data: Data, start: date, end: date, gate: time | None = None, horizon: int | None = None) -> list[Row]:
    rows = []
    for target in targets(start, end):
        if horizon is not None:
            cutoff = target - timedelta(hours=horizon)
        else:
            cutoff = gate_cutoff(target, gate or DEFAULT_GATE)
        run = pick(data.runs.get(target, []), cutoff, target)
        rows.append(Row(target, data.actuals.get(target), run and run[1], run and run[0]))
    return rows


def history_range(delivery: date) -> tuple[date, date]:
    """Last HISTORY_DAYS delivery days fully settled at the D-1 gate: D-31 .. D-2. No look-ahead."""
    end = delivery - timedelta(days=2)
    return end - timedelta(days=HISTORY_DAYS - 1), end


def latest_delivery() -> date:
    """Tomorrow in UK time: the furthest delivery day a buyer can be deciding on today."""
    return datetime.now(LONDON).date() + timedelta(days=1)


def _errors(rows: list[Row]) -> list[tuple[Row, float]]:
    return [(row, row.forecast - row.actual) for row in rows if row.forecast is not None and row.actual is not None]


def _quantile(sorted_vals: list[float], fraction: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, int(fraction * len(sorted_vals)))]  # nearest rank


def stats(rows: list[Row]) -> dict:
    pairs = _errors(rows)
    count = len(pairs)
    out = {"count": count, "coverage": count / len(rows) if rows else 0}
    if not count:
        return out | dict.fromkeys(["mae", "rmse", "bias", "nmae", "p50", "p90", "p99", "err_p10", "err_p90"])
    errs = sorted(err for _, err in pairs)
    abs_errs = sorted(abs(err) for err in errs)
    mae = fmean(abs_errs)
    mean_actual = fmean(row.actual for row, _ in pairs)
    return out | {
        "mae": mae,
        "rmse": math.sqrt(fmean(err * err for err in errs)),
        "bias": fmean(errs),
        "nmae": mae / mean_actual if mean_actual else None,
        "p50": _quantile(abs_errs, 0.5),
        "p90": _quantile(abs_errs, 0.9),
        "p99": _quantile(abs_errs, 0.99),
        "err_p10": _quantile(errs, 0.1),
        "err_p90": _quantile(errs, 0.9),
    }


def _group(rows: list[Row], key: str, of) -> list[dict]:
    buckets: dict = {}
    for row, err in _errors(rows):
        buckets.setdefault(of(row.time.astimezone(LONDON)), []).append(err)
    return [
        {key: bucket, "count": len(errs), "mae": fmean(map(abs, errs)), "bias": fmean(errs)}
        for bucket, errs in sorted(buckets.items())
    ]


def by_hour(rows: list[Row]) -> list[dict]:
    return _group(rows, "hour", lambda local: local.hour)


def by_day(rows: list[Row]) -> list[dict]:
    """Per delivery day (London date): how wrong was the forecast that day."""
    return _group(rows, "day", lambda local: local.date().isoformat())


def by_horizon(data: Data, start: date, end: date, horizons=range(0, 49, 3)) -> list[dict]:
    out = []
    for hours_ahead in horizons:
        scored = stats(series(data, start, end, horizon=hours_ahead))
        out.append({
            "hours_ahead": hours_ahead,
            "count": scored["count"],
            "mae": scored["mae"],
            "bias": scored["bias"],
            "p90": scored["p90"],
        })
    return out
