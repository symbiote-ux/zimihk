"""Pure domain logic: pick the forecast a buyer could have used, and score it.

All datetimes are tz-aware UTC. Delivery days and the gate are Europe/London.
Error is always forecast - actual (positive = over-forecast).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
WINDOW = (date(2026, 1, 2), date(2026, 2, 1))  # delivery days for decisions made in Jan 2026
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
