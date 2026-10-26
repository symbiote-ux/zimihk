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
async def elexon_unavailable(_: Request, e: elexon.ElexonError) -> JSONResponse:
    log.warning("Elexon unavailable: %s", e)
    return JSONResponse({"detail": "Elexon BMRS is unavailable or slow right now. Please retry shortly."}, 502)


@app.exception_handler(Exception)
async def unexpected(_: Request, e: Exception) -> JSONResponse:
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


def _row(r: core.Row) -> dict:
    return {
        "t": r.t.isoformat(),
        "actual": r.actual,
        "forecast": r.forecast,
        "publish": r.publish and r.publish.isoformat(),
    }


@app.get("/api/meta")
def meta() -> dict:
    lo, hi = core.PILOT
    return {
        "start": lo.isoformat(),
        "end": hi.isoformat(),
        "min": core.EARLIEST.isoformat(),
        "max": core.latest_delivery().isoformat(),
        "max_days": core.MAX_DAYS,
        "default_gate": core.DEFAULT_GATE.strftime("%H:%M"),
    }


@app.get("/api/series")
def series(
    start: date,
    end: date,
    gate: str = Query("09:20", pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
    horizon: int | None = Query(None, ge=0, le=48),
) -> dict:
    _check_range(start, end)
    g = time.fromisoformat(gate)
    hist = core.history_range(start)
    data = elexon.fetch(hist[0], end)  # one Elexon pull covers both the history and the selection
    rows = core.series(data, start, end, gate=g, horizon=horizon)
    return {
        "rows": [_row(r) for r in rows],
        "stats": core.stats(rows),
        "by_hour": core.by_hour(rows),
        "histogram": core.histogram(rows),
        "history": {
            "start": hist[0].isoformat(),
            "end": hist[1].isoformat(),
            "days": core.HISTORY_DAYS,
            "stats": core.stats(core.series(data, *hist, gate=g, horizon=horizon)),
        },
    }


@app.get("/api/horizons")
def horizons(start: date, end: date) -> list[dict]:
    _check_range(start, end)
    return core.by_horizon(elexon.fetch(start, end), start, end)


if (HERE / "static").is_dir():  # built SPA, present in the Docker image only
    app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")
