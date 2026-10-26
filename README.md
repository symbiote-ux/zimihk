# Wind Desk

A pilot tool for a UK utility's **day-ahead power-purchase desk**. It shows the national wind forecast that was actually available before the day-ahead auction gate, and measures how accurate those forecasts have been. The buyer can then size purchases knowing the typical error.

**Live app:** _added after deployment_ · Data: Elexon BMRS (FUELHH wind actuals, WINDFOR forecasts) for purchase decisions made in January 2026.

## What it does

| Page | Question it answers |
|---|---|
| **Day-ahead brief** | "It's the morning of decision day X. What does the latest forecast say about tomorrow, and how wrong has it tended to be?" It shows the forecast run published before the gate (default 09:20 UK, editable), with a P10–P90 band built **only from days already settled before the decision**. |
| **Forecast accuracy** | "How good are these forecasts?" It covers MAE, RMSE, bias, P90 error, nMAE and coverage, error vs lead time, the error distribution and error by hour of day, for any date range at the gate or at a fixed horizon (0–48 h). |

The headline finding: across January 2026 the forecast available at the 09:20 gate **over-predicted wind by ~1.75 GW on average** (MAE 2.02 GW, 1 hour in 10 off by more than 4.2 GW). A buyer trusting the raw number would systematically under-buy. Curtailment is a plausible cause, because actuals are metered output after balancing actions; this is a hypothesis to confirm.

## Run it

**Docker (one container serving API and UI):**
```bash
docker compose up --build        # → http://localhost:8000
```

**Local development:**
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app:app --app-dir backend --reload          # API on :8000 (docs at /docs)
cd frontend && npm ci && npm run dev                          # UI on :5173, proxies /api → :8000
```

**Tests and lint:** `cd backend && ../.venv/bin/pytest -q` and `.venv/bin/ruff check backend`. CI runs these, the frontend type-check and build, and a Docker build.

**Refresh the data snapshot:** `python3 backend/fetch_data.py`. This re-downloads from Elexon; no API key is needed.

## Files and directories

```
backend/
  fetch_data.py     one-off Elexon download → data/*.json.gz (stdlib only)
  data/             committed snapshot: actuals (FUELHH WIND) + forecasts (WINDFOR, hindcasts dropped)
  core.py           pure domain logic: forecast selection (gate / horizon), no-look-ahead history, metrics
  app.py            FastAPI: /api/meta, /api/series, /api/horizons; serves the built UI if backend/static exists
  test_core.py      unit tests for selection + metrics (DST day, cutoff equality, empty sets, look-ahead)
  test_app.py       API tests incl. 422 validation
frontend/src/
  App.tsx           shell + tabs
  DayAhead.tsx      Day-ahead brief page
  Accuracy.tsx      Forecast accuracy page
  Chart.tsx         thin ECharts wrapper + shared chart styling
  api.ts            typed API client, useApi hook, London-time formatting
  styles.css        design tokens and layout (light theme)
api/index.py        Vercel serverless entrypoint (re-exports backend/app.py)
Dockerfile          multi-stage: node build → python runtime
docker-compose.yml  one service on :8000
vercel.json         static UI + Python function for /api/*
PLAN.md             requirements analysis, domain research, design decisions and trade-offs
docs/superpowers/   implementation plan the build followed
```

## Key definitions

- **Decision window:** decisions made 1–31 Jan 2026, so **delivery days 2 Jan – 1 Feb 2026**.
- **Forecast at the gate:** for each delivery hour, the latest WINDFOR run with `publishTime ≤ gate on D-1` (Europe/London) and `publishTime < target`. The default gate, 09:20, is EPEX GB day-ahead closure.
- **No look-ahead:** the uncertainty band and track record for delivery day D use only delivery days 2 Jan … D-2, which are fully settled before the gate on D-1. A band appears after 3 settled days.
- **Resolution:** WINDFOR is hourly and FUELHH half-hourly. The comparison is at HH:00 against the FUELHH half-hour starting HH:00. Missing data is never interpolated, and coverage is reported.
- **Error** = forecast − actual (positive = over-forecast). There is no MAPE, because it blows up at low wind; nMAE is used instead.

## Architecture and trade-offs

FastAPI is the backend's only dependency. The domain logic is pure standard-library Python, and the January data (~17k rows) is a committed snapshot loaded once per process. That keeps the app deterministic, fast and immune to Elexon outages.

On **Vercel** (free, CDN-served UI, nothing to keep running), the UI is static and the API runs as a Python serverless function. **Docker** gives the same app as a single container for local use and CI.

The trade-offs are no runtime data refresh, possible cold starts, and production not running the Docker image. They are acceptable because January 2026 is fixed history. A live version would add a scheduled ingest into Postgres and run the same image on a container host; only the data-loading code would change. See [PLAN.md §6](PLAN.md).

## AI tools

This project was built with **Claude Code** (Anthropic) as a pair programmer: domain research, planning, code and tests. All results were checked against the live Elexon API and reproduced numerically. Design decisions and their reasoning are recorded in `PLAN.md`.
