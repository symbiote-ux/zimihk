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


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(UTC)


@dataclass(frozen=True)
class Data:
    actuals: dict[datetime, float]
    runs: dict[datetime, list[Run]]  # target -> runs, oldest publish first


@dataclass(frozen=True)
class Row:
    t: datetime
    actual: float | None
    forecast: float | None
    publish: datetime | None


def load(actual_rows: list[list], forecast_rows: list[list]) -> Data:
    runs: dict[datetime, list[Run]] = {}
    for publish, start, gen in forecast_rows:
        runs.setdefault(_ts(start), []).append((_ts(publish), gen))
    for lst in runs.values():
        lst.sort()
    return Data({_ts(s): g for s, g in actual_rows}, runs)


def _local_midnight(d: date) -> datetime:
    return datetime.combine(d, time(), LONDON).astimezone(UTC)


def targets(start: date, end: date) -> list[datetime]:
    """Every UTC hour whose London-local date is in [start, end] (23 or 25 on clock-change days)."""
    t, stop = _local_midnight(start), _local_midnight(end + timedelta(days=1))
    out = []
    while t < stop:
        out.append(t)
        t += timedelta(hours=1)
    return out


def gate_cutoff(target: datetime, gate: time) -> datetime:
    d = target.astimezone(LONDON).date() - timedelta(days=1)
    return datetime.combine(d, gate, LONDON).astimezone(UTC)


def pick(runs: list[Run], cutoff: datetime, target: datetime) -> Run | None:
    """Latest run published at/before the cutoff and strictly before the target."""
    best = None
    for publish, gen in runs:  # sorted by publish, so the first miss ends the scan
        if publish > cutoff or publish >= target:
            break
        best = (publish, gen)
    return best


def series(data: Data, start: date, end: date, gate: time | None = None, horizon: int | None = None) -> list[Row]:
    rows = []
    for t in targets(start, end):
        cutoff = t - timedelta(hours=horizon) if horizon is not None else gate_cutoff(t, gate or DEFAULT_GATE)
        hit = pick(data.runs.get(t, []), cutoff, t)
        rows.append(Row(t, data.actuals.get(t), hit and hit[1], hit and hit[0]))
    return rows


def history_range(delivery: date) -> tuple[date, date]:
    """Last HISTORY_DAYS delivery days fully settled at the D-1 gate: D-31 .. D-2. No look-ahead."""
    end = delivery - timedelta(days=2)
    return end - timedelta(days=HISTORY_DAYS - 1), end


def latest_delivery() -> date:
    """Tomorrow in UK time: the furthest delivery day a buyer can be deciding on today."""
    return datetime.now(LONDON).date() + timedelta(days=1)


def _errors(rows: list[Row]) -> list[tuple[Row, float]]:
    return [(r, r.forecast - r.actual) for r in rows if r.forecast is not None and r.actual is not None]


def _q(sorted_vals: list[float], p: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, int(p * len(sorted_vals)))]  # nearest rank


def stats(rows: list[Row]) -> dict:
    pairs = _errors(rows)
    n = len(pairs)
    out = {"n": n, "coverage": n / len(rows) if rows else 0}
    if not n:
        return out | dict.fromkeys(["mae", "rmse", "bias", "nmae", "p50", "p90", "p99", "err_p10", "err_p90"])
    errs = sorted(e for _, e in pairs)
    abs_errs = sorted(abs(e) for e in errs)
    mae = fmean(abs_errs)
    mean_actual = fmean(r.actual for r, _ in pairs)
    return out | {
        "mae": mae,
        "rmse": math.sqrt(fmean(e * e for e in errs)),
        "bias": fmean(errs),
        "nmae": mae / mean_actual if mean_actual else None,
        "p50": _q(abs_errs, 0.5),
        "p90": _q(abs_errs, 0.9),
        "p99": _q(abs_errs, 0.99),
        "err_p10": _q(errs, 0.1),
        "err_p90": _q(errs, 0.9),
    }


def _group(rows: list[Row], key: str, of) -> list[dict]:
    buckets: dict = {}
    for r, e in _errors(rows):
        buckets.setdefault(of(r.t.astimezone(LONDON)), []).append(e)
    return [{key: k, "n": len(es), "mae": fmean(map(abs, es)), "bias": fmean(es)} for k, es in sorted(buckets.items())]


def by_hour(rows: list[Row]) -> list[dict]:
    return _group(rows, "hour", lambda t: t.hour)


def by_day(rows: list[Row]) -> list[dict]:
    """Per delivery day (London date): how wrong was the forecast that day."""
    return _group(rows, "day", lambda t: t.date().isoformat())



def by_horizon(data: Data, start: date, end: date, horizons=range(0, 49, 3)) -> list[dict]:
    out = []
    for h in horizons:
        s = stats(series(data, start, end, horizon=h))
        out.append({"h": h, "n": s["n"], "mae": s["mae"], "bias": s["bias"], "p90": s["p90"]})
    return out
