import gzip
import json
from datetime import date, time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

import core

HERE = Path(__file__).parent


def _read(name: str) -> list:
    with gzip.open(HERE / "data" / name, "rt") as f:
        return json.load(f)


DATA = core.load(_read("actuals.json.gz"), _read("forecasts.json.gz"))  # once per process / cold start

app = FastAPI(title="Wind Desk API")


def _check_range(start: date, end: date) -> None:
    lo, hi = core.WINDOW
    if not (lo <= start <= end <= hi):
        raise HTTPException(422, f"start/end must satisfy {lo} <= start <= end <= {hi}")


def _row(r: core.Row) -> dict:
    return {
        "t": r.t.isoformat(),
        "actual": r.actual,
        "forecast": r.forecast,
        "publish": r.publish and r.publish.isoformat(),
    }


@app.get("/api/meta")
def meta() -> dict:
    lo, hi = core.WINDOW
    return {"start": lo.isoformat(), "end": hi.isoformat(), "default_gate": core.DEFAULT_GATE.strftime("%H:%M")}


@app.get("/api/series")
def series(
    start: date,
    end: date,
    gate: str = Query("09:20", pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
    horizon: int | None = Query(None, ge=0, le=48),
) -> dict:
    _check_range(start, end)
    g = time.fromisoformat(gate)
    rows = core.series(DATA, start, end, gate=g, horizon=horizon)
    hist = core.history_range(start)
    history = None
    if hist:
        history = {
            "start": hist[0].isoformat(),
            "end": hist[1].isoformat(),
            "days": (hist[1] - hist[0]).days + 1,
            "stats": core.stats(core.series(DATA, *hist, gate=g, horizon=horizon)),
        }
    return {
        "rows": [_row(r) for r in rows],
        "stats": core.stats(rows),
        "by_hour": core.by_hour(rows),
        "histogram": core.histogram(rows),
        "history": history,
    }


@app.get("/api/horizons")
def horizons(start: date, end: date) -> list[dict]:
    _check_range(start, end)
    return core.by_horizon(DATA, start, end)


if (HERE / "static").is_dir():  # built SPA, present in the Docker image only
    app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")
