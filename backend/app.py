import logging
from datetime import date, time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import core
import elexon

HERE = Path(__file__).parent
log = logging.getLogger("wind-desk")
# Vercel's CDN keeps each successful URL for 25 min: Elexon publishes forecasts every 2-4 h and actuals
# every 30 min, so data stays current while repeat views skip the ~4 s Elexon round trip.
CACHE_OK = "public, max-age=0, s-maxage=1500"

app = FastAPI(title="Wind Desk API")


@app.exception_handler(elexon.ElexonError)
async def elexon_unavailable(_: Request, err: elexon.ElexonError) -> JSONResponse:
    log.warning("Elexon unavailable: %s", err)
    return JSONResponse({"detail": "Elexon BMRS is unavailable or slow right now. Please retry shortly."}, 502)


@app.exception_handler(Exception)
async def unexpected(_: Request, _err: Exception) -> JSONResponse:
    log.exception("Unhandled error")
    return JSONResponse({"detail": "Internal server error"}, 500)


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = CACHE_OK if response.status_code == 200 else "no-store"
    return response


def _check_range(start: date, end: date) -> None:
    latest = core.latest_delivery()
    if not (core.EARLIEST <= start <= end <= latest):
        raise HTTPException(422, f"Dates must satisfy {core.EARLIEST} <= start <= end <= {latest}")
    if (end - start).days + 1 > core.MAX_DAYS:
        raise HTTPException(422, f"At most {core.MAX_DAYS} delivery days per request")


def _row(row: core.Row) -> dict:
    return {
        "time": row.time.isoformat(),
        "actual": row.actual,
        "forecast": row.forecast,
        "publish": row.publish and row.publish.isoformat(),
    }


@app.get("/api/meta")
def meta() -> dict:
    pilot_start, pilot_end = core.PILOT
    return {
        "start": pilot_start.isoformat(),
        "end": pilot_end.isoformat(),
        "min": core.EARLIEST.isoformat(),
        "max": core.latest_delivery().isoformat(),
        "default_gate": core.DEFAULT_GATE.strftime("%H:%M"),
    }


@app.get("/api/series")
def series(
    start: date,
    end: date,
    gate: str = Query("09:20", pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
    history_days: int = core.HISTORY_DAYS,
) -> dict:
    _check_range(start, end)
    if history_days not in core.HISTORY_CHOICES:
        raise HTTPException(422, f"history_days must be one of {core.HISTORY_CHOICES}")
    gate_time = time.fromisoformat(gate)
    hist_start, hist_end = core.history_range(start, history_days)
    data = elexon.fetch(hist_start, end)  # one Elexon pull covers both the history and the selection
    rows = core.series(data, start, end, gate=gate_time)
    past = core.series(data, hist_start, hist_end, gate=gate_time)
    return {
        "rows": [_row(row) for row in rows],
        "stats": core.stats(rows),  # hindsight: known only after delivery
        "history": {  # the quantified error available at decision time
            "start": hist_start.isoformat(),
            "end": hist_end.isoformat(),
            "days": history_days,
            "stats": core.stats(past),
            "by_day": core.by_day(past),
            "by_hour": core.by_hour(past),
            "by_horizon": core.by_horizon(data, hist_start, hist_end),
        },
    }


if (HERE / "static").is_dir():  # built SPA, present in the Docker image only
    app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")
