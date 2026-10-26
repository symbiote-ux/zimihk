# Wind Desk

A decision-support tool for a UK utility's **day-ahead power-purchase desk**. It shows the national wind forecast that was actually available before the day-ahead auction gate, and measures how accurate those forecasts have been. The buyer can then size purchases knowing the typical error.

**Live app:** https://zimihk.vercel.app · Data: live from Elexon BMRS (FUELHH wind actuals, WINDFOR forecasts). The app opens on the brief's scenario, purchase decisions made in January 2026, and any delivery day from 2023 up to tomorrow can be selected.

## What it does

A day-ahead buyer must decide, before the 09:20 gate, how much power to buy for tomorrow. Wind covers part of demand, so the buyer needs to know how much wind to count on and how far to trust that number. One page, driven by two inputs (decision day and gate time), answers both:

| Section | Question it answers |
|---|---|
| **Day-ahead brief** | "What does the latest forecast before the gate say about tomorrow?" It shows the forecast run published before the gate (default 09:20 UK, editable), with a P10–P90 band built **only from days already settled before the decision** (last 7, 14 or 30; default 30). |
| **How reliable is this forecast?** | "How wrong has that same forecast been recently?" Over the last 7, 14 or 30 settled days before the decision (History switch, default 30): MAE, bias, P90 error, RMSE, nMAE and coverage; error by day; error by hour of day; error vs lead time, with the lead times behind this decision shaded. |

The headline finding: for January 2026 decisions, the forecast available at the 09:20 gate **over-predicted wind by ~1.75 GW on average** (MAE 2.02 GW, 1 hour in 10 off by more than 4.2 GW). A buyer trusting the raw number would systematically under-buy. Curtailment is a plausible cause, because actuals are metered output after balancing actions; this is a hypothesis to confirm.

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

## Tests

| Layer | What | Command |
|---|---|---|
| Unit (backend) | Forecast selection, no-look-ahead history, metrics (`test_core.py`); Elexon client request windows, hindcast filter, error mapping, with the network faked (`test_elexon.py`) | `cd backend && ../.venv/bin/pytest` |
| API (backend) | FastAPI endpoints with Elexon replaced by a frozen January 2026 fixture: validation (422), Elexon down (502), unexpected error (500), cache headers (`test_app.py`) | (same command) |
| Integration | Live Elexon API: the real 07:30 gate run, and the full API reproducing the January baseline exactly (`test_integration.py`) | `cd backend && ../.venv/bin/pytest -m integration` |
| Unit (frontend) | Date maths, UK-time formatting under a UTC+14 viewer timezone, number formatting, API error parsing (`src/api.test.ts`) | `cd frontend && npm test` |

Lint: `.venv/bin/ruff check backend`. Type-check: `cd frontend && npm run build`.

## Deploy

`vercel deploy --prod` from the repo root (the project is linked in `.vercel/`). The UI is built from `frontend/`, and `api/index.py` becomes the Python function.

## Files and directories

```
backend/
  core.py              pure domain logic: forecast selection at the gate, 7/14/30-day no-look-ahead history,
                       metrics (MAE, RMSE, bias, nMAE, P50/P90/P99) and breakdowns by day, hour and lead time
  elexon.py            Elexon BMRS client: FUELHH + WINDFOR fetched in parallel, hindcasts dropped,
                       25 s timeout, ElexonError
  app.py               FastAPI: /api/meta, /api/series; validation (422), JSON errors (502/500),
                       25-min CDN cache header; serves the built UI if backend/static exists (Docker)
  fetch_data.py        regenerates the offline test fixture from Elexon
  data/                January 2026 test fixture: actuals.json.gz, forecasts.json.gz
  test_core.py         clock-change days, gate in winter/summer, cutoff equality, hindcast exclusion,
                       metrics, empty sets, no-look-ahead window, breakdowns grouped in UK time
  test_app.py          API with Elexon faked: meta, gate run selection, history window fetched once,
                       history breakdowns, 422 without calling Elexon, 502, 500, cache header
  test_elexon.py       Elexon client with the network faked: request windows, hindcast filter, error mapping
  test_integration.py  live Elexon tests (pytest -m integration)
  pytest.ini           registers the integration marker; live tests skipped by default
frontend/
  index.html           page shell, IBM Plex fonts
  vite.config.ts       dev proxy /api -> :8000; Vitest config
  package.json         scripts: dev, build, test (runs under UTC+14 to prove UK-time formatting)
  src/main.tsx         React entry point
  src/App.tsx          masthead + loads /api/meta, renders the page
  src/DayAhead.tsx     the page: decision day + gate inputs, day-ahead brief, forecast reliability section
  src/Chart.tsx        thin ECharts wrapper (tree-shaken) + shared colours and axis styling
  src/api.ts           typed API client; useApi hook (debounce, cancel, retry); UK-time and GW formatting
  src/api.test.ts      Vitest unit tests: UK-time formatting, number formatting, error messages
  src/styles.css       design tokens and layout (light theme, mobile breakpoint)
api/index.py           Vercel serverless entrypoint (re-exports backend/app.py)
requirements.txt       runtime: fastapi, uvicorn
requirements-dev.txt   + pytest, httpx, ruff
ruff.toml              lint config (line length 120)
Dockerfile             multi-stage: node build -> python runtime
docker-compose.yml     one service on :8000
.dockerignore          keeps node_modules, venvs and build output out of the image
vercel.json            static UI + Python function for /api/* (60 s max)
PLAN.md                requirements analysis, domain research, design decisions, trade-offs, video outline
```

## Key definitions

- **Default view:** decisions made 1–31 Jan 2026, so **delivery days 2 Jan – 1 Feb 2026**.
- **Forecast at the gate:** for each delivery hour, the latest WINDFOR run with `publishTime ≤ gate on D-1` (Europe/London) and `publishTime < target`. The default gate, 09:20, is EPEX GB day-ahead closure.
- **No look-ahead:** the uncertainty band and track record for delivery day D use only delivery days D-31 … D-2. All of them are settled before the gate on D-1.
- **Resolution:** WINDFOR is hourly and FUELHH half-hourly. The comparison is at HH:00 against the FUELHH half-hour starting HH:00. Missing data is never interpolated, and coverage is reported.
- **Error** = forecast − actual (positive = over-forecast). There is no MAPE, because it blows up at low wind; nMAE is used instead.

## Architecture

```
React SPA (Vercel CDN) → Vercel edge cache (25 min) → FastAPI function → Elexon BMRS (live)
```

- Each API request fetches exactly the delivery days it needs, plus their 7–30-day history, from Elexon. The two datasets are pulled in parallel, and the pure `core.py` computes the result.
- FastAPI is the only backend dependency.
- On **Vercel** (free, allowed by the brief), the UI is served from the CDN and the API runs as a Python function.
- **Docker** runs the same app as a single container for local use and CI.

See [PLAN.md](PLAN.md) for the reasoning and trade-offs.

## Edge cases & limits

**Handled:**
- **Invalid input → 422 with a readable message, and Elexon is never called.** This covers:
  - dates before 2023-01-01 or after tomorrow;
  - start after end;
  - ranges over 31 days;
  - a malformed gate (`25:00`).
- **Elexon slow or down → 502** JSON: "Elexon BMRS is unavailable or slow right now. Please retry shortly." The client has a 25 s timeout per dataset.
- **Unexpected server error → 500** JSON `{"detail": "Internal server error"}`, with the stack trace logged server-side. Internals are never leaked.
- **The UI shows every error with a Retry button**, and loading states say data is coming live from Elexon.
- **Repeat requests are cached for 25 minutes**: successful responses carry `Cache-Control: s-maxage=1500`, so Vercel's CDN answers repeat views without calling Elexon. Forecasts publish every 2–4 h and actuals every 30 min, so data stays current. Errors are sent `no-store` and never cached.
- **Fewer requests from the UI:** it waits 250 ms after the last input change, cancels the request being replaced, and never lets a stale response overwrite a newer one.
- **Data edge cases:**
  - clock-change days (23/25 hours);
  - hours with no forecast before the cutoff (counted against coverage);
  - missing actuals, and empty selections (n = 0, no crash);
  - a run published exactly at the cutoff (included) or exactly at the target hour (excluded);
  - hindcast rows (dropped).
- **Times are shown in UK time** whatever the viewer's timezone.

**Known limits (deliberate for a pilot):**
- **No per-client rate limiting in the app.** Serverless instances share no state, so an in-process limiter would be meaningless. In production, use Vercel Firewall rate-limit rules or a shared store such as Redis.
- **On a cache miss, a request takes as long as Elexon does** (typically 4–13 s), and the app depends on Elexon being up. Heavy, varied traffic passes through to Elexon.
  - The production design is a scheduled job that ingests each new forecast run into Postgres, with the API reading from Postgres. That gives millisecond responses, one Elexon call per publish, and resilience to Elexon outages. Only `elexon.py` would change.
- **No cache when running in Docker locally** (there's no CDN).
- **Elexon occasionally revises actuals**; the app always shows the latest values.

## AI tools

This project was built with **Claude Code** (Anthropic) as a pair programmer: domain research, planning, code and tests. All results were checked against the live Elexon API and reproduced numerically. Design decisions and their reasoning are recorded in `PLAN.md`.
