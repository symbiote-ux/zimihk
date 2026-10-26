# Wind Forecast Monitor: Requirements Analysis & Development Plan

> Status: v1 built and deployed (https://zimihk.vercel.app). Target budget is 16 hours or less.

---

## 1. Context

**The product (Wind Desk).** A decision-support tool for energy buyers. It closes a simple loop: **predict** (show the forecast the buyer could actually act on at decision time) and **learn** (measure how good that forecast turned out to be, and carry the error into the next decision). Every number traces back to a specific forecast run and its publish time, so results are auditable.

**The user.** A UK utility's day-ahead power-purchase desk. Each day (D-1) they buy power for delivery day D before the auction gate closes. Wind is weather-driven, so:

> **Net requirement ≈ consumer demand − renewable (wind) generation.** Everything not covered by wind has to be bought, for example from thermal plants.

If wind is over-forecast, they **under-buy**. They then pay for the shortfall at expensive imbalance or intraday prices. If wind is under-forecast, they over-buy and sell back at a loss. A buyer needs two things:
1. **What is the latest forecast I can actually use right now?** (requirement 1)
2. **How much should I trust it?** That means a quantified error, ideally as a range (requirement 2).

## 2. Domain facts (researched and verified against the live API)

### Day-ahead market timing
| Venue | Gate closure (D-1) | Notes |
|---|---|---|
| EPEX SPOT GB day-ahead (hourly) | 10:20 CET = **09:20 UK** | |
| Nord Pool N2EX GB day-ahead (hourly) | 10:50 CET = **09:50 UK** | moved from 11:00 after Brexit |
| GB half-hourly auction | 15:30 CET = 14:30 UK | secondary |

In January, UK local time is GMT, which equals UTC. The code must still be timezone-aware and use Europe/London.
**Default decision cutoff: D-1 09:20 UK time** (configurable in the UI).

### Elexon datasets (public, no API key)
| | FUELHH (actuals) | WINDFOR (forecasts) |
|---|---|---|
| Endpoint | `data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream` | `.../datasets/WINDFOR/stream` |
| Filter | `settlementDateFrom/To`, `fuelType=WIND` | `publishDateTimeFrom/To` |
| Resolution | **30 min** | **60 min** (startTime always on :00) |
| Volume (Jan 2026) | ~1.6k rows | ~19k rows |

**WINDFOR behaviour, measured on Jan 2026 data:**
- **8 runs per day** at fixed times: 02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30 and 22:30 UTC. Gaps between runs are 2 to 4 hours.
- Each run covers about 1 day back and up to **~66.5 h ahead** (horizon −25.5 h to +66.5 h).
  → **Rows where `startTime ≤ publishTime` are past hours (hindcasts), not forecasts, and must be dropped.**
- At a 09:20 gate, the latest usable run is **07:30 on D-1**. For delivery day D it covers horizons of **16.5 h to 39.5 h**.
- The 48 h+ horizon does not cover every hour (570 of 720 target hours in January).

### Baseline accuracy (Jan 2026 delivery, hourly, quick prototype script)
| Selection rule | MAE (MW) | Bias (fc − actual) | RMSE | P90 abs err | Max |
|---|---|---|---|---|---|
| Day-ahead gate (D-1 09:20) | 2058 | **+1772** | 2532 | 4193 | 6894 |
| Horizon ≥ 1 h | 1712 | +1500 | 2180 | 3497 | 7305 |
| Horizon ≥ 24 h | 1976 | +1774 | 2435 | 3911 | 6804 |
| Horizon ≥ 48 h | 2335 | +1817 | 2906 | 4848 | 9506 |

Actual wind ranged from **1.7 to 17.8 GW**.

**Main finding for the pitch:** the forecast **over-predicts by about 1.5–1.8 GW, and it does so consistently at every horizon**. Error grows with horizon, as expected. Because the bias is systematic and does not shrink at short horizons, the cause is not only weather uncertainty. The working hypothesis is **curtailment and constraint actions**: FUELHH is metered output after balancing actions, while WINDFOR forecasts unconstrained output. *This must be presented as a hypothesis, not a fact.* Even so, a buyer who simply subtracts the historical bias would roughly halve the error. That is a strong demo moment.

## 3. Interpretation decisions (made explicit so a reviewer can challenge them)
1. **"Decisions made in January 2026"** means delivery days **2 Jan to 1 Feb 2026**, decided on 1 to 31 Jan.
   The data fetched is forecasts published 31 Dec to 31 Jan and actuals for 1 Jan to 2 Feb. A small buffer is kept for context.
2. **Latest forecast at decision time:** for target hour *t* on day D, take the forecast with the largest `publishTime` that is ≤ the decision cutoff (D-1 09:20 Europe/London) and also < *t*.
3. **Fixed-horizon mode** is a secondary analyst view. It uses the latest forecast with `publishTime ≤ t − H`, with H from 0 to 48 h. It is used for the accuracy-by-horizon curves.
4. **Resolution mismatch:** compare at **hourly** points by matching the actual's half-hour that starts on the hour, the same convention Elexon uses. Averaging the two half-hours is a possible later option, documented but not the default.
5. **Missing data** is shown as gaps. It is never interpolated, and coverage % is reported next to every metric.
6. **Metrics:** use MAE, RMSE, **bias (mean signed error)**, P50/P90/P99 absolute error, and nMAE (% of mean actual). Plain MAPE is avoided because it blows up when wind output is low.
7. **No look-ahead: the app only uses what the buyer knew at decision time.** The buyer decides daily: on decision day X they buy for delivery day D = X + 1. The error history available at the gate covers **delivery days from 2 Jan up to D − 2**. Day D − 2 is fully settled by midnight, before the 09:20 gate on D − 1. Example: deciding on 15 Jan for 16 Jan uses errors from 2 to 14 Jan. The history is an expanding window within the scope. The uncertainty band and track record appear only once **3 or more settled days** exist; before that the app shows "building history (n days)".
8. **"January 2026" is a data scope, not a screen.** The brief limits which data to use. The user works one day at a time, so the main screen is a single decision day. Date ranges appear only on the Accuracy page, because measuring accuracy needs many days.

## 4. Product scope

### MVP (must have)
**A. Day-ahead brief** (requirement 1, home screen)
This page mirrors the buyer's morning routine: "it's decision day X, what do I know about tomorrow?"
- Pick a **decision day** (1 to 31 Jan); the page shows "Delivering: X + 1".
- A chart shows the **forecast from the latest run before the gate**. Actuals are overlaid as a hindsight check, visually marked as unknown at decision time.
- The forecast is wrapped in an **uncertainty band**: P10–P90 signed errors from **settled days only** (item 7 above), so it contains no look-ahead. This connects requirements 1 and 2.
- KPI cards: run used (publish time), expected wind energy for the day (MWh), min and max hourly wind, and the **track record so far** (history MAE and bias, e.g. "over-forecast by 1.8 GW across the last 13 days").

**B. Forecast accuracy** (requirement 2)
- Pick a date range and a mode (gate or fixed horizon).
- Metric tiles: MAE, RMSE, bias, P90 and coverage.
- Charts:
  - error vs horizon
  - error distribution histogram
  - error by hour of day
  - daily error time series
  - forecast vs actual scatter

### Stretch (only if time allows, in this order)
- **Forecast evolution:** every run's forecast for one target day as a "spaghetti" chart, showing how the forecast converged.
- Bias-corrected forecast toggle ("what if we subtract the trailing 7-day bias?").
- CSV export, plus a shareable URL state (filters stored in query params).

### Out of scope
Demand forecasts, prices, other fuels, auth, and real-time streaming. Data beyond Elexon wind is excluded by the brief.

## 5. Architecture

```
┌────────── Docker image (single container) ───────────┐
│  FastAPI (uvicorn)                                    │
│   ├── /api/*      JSON API                            │
│   └── /*          React build (static, SPA fallback)  │
│                                                       │
│  app.py   loads data/*.json.gz once at import         │
│  core.py  gate/horizon selection + metrics (pure,     │
│           stdlib only)                                │
│                                                       │
│  fetch_data.py (run by hand) ──► Elexon ──► data/     │
└───────────────────────────────────────────────────────┘
```

**Key design choices**
- **Committed data snapshot + refresh script.** January 2026 is in the past, so the data is fixed and small. Shipping a snapshot makes the demo deterministic, fast and resilient to Elexon outages. `scripts/fetch_data.py` regenerates it, and the API can optionally refresh on startup.
- **Pure-function domain layer.** Selection and metrics logic does no I/O. It is fully unit-tested with tiny hand-built fixtures, and it is the part a tech lead will scrutinise.
- **Compute on request with plain Python.** The data is about 20k rows, so dict lookups and `statistics` answer in milliseconds. There is no database, no pandas and no cache. Add pandas or `lru_cache` only if profiling shows it is needed.
- **A single container** serves both the API and the static frontend. That gives one deploy, no CORS and simple Docker. Local development uses `docker compose` with a Vite dev server and hot reload.

### API (typed with Pydantic, documented automatically at `/docs`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness |
| GET | `/api/meta` | data window, runs list, snapshot timestamp, gate default |
| GET | `/api/series?start&end&mode=gate\|horizon&horizon_h&gate_time` | aligned hourly `{t, actual, forecast, publish_time, horizon_h}` |
| GET | `/api/metrics?start&end&mode&...` | summary + by-horizon + by-hour + histogram |
| GET | `/api/runs?target_date` | every forecast run for one delivery day (stretch) |

### Repo layout
```
backend/
  app.py          # FastAPI routes; loads snapshot once at import
  core.py         # pure: forecast selection + metrics (stdlib only)
  test_core.py    # pytest: gate/horizon edge cases, metrics checked by hand
  fetch_data.py   # one-shot Elexon download (urllib) → data/*.json.gz
  data/
frontend/
  src/App.tsx, DayAhead.tsx, Accuracy.tsx, api.ts
api/index.py      # Vercel entrypoint: re-exports app
Dockerfile, docker-compose.yml, vercel.json, .github/workflows/ci.yml, README.md
```

### Tech stack
- **Backend:** Python 3.12, FastAPI + uvicorn. That is the only runtime dependency. `zoneinfo`, `statistics`, `urllib` and `json` come from the stdlib. Tooling: pytest, ruff.
- **Frontend:** React 18, TypeScript, Vite, and **Apache ECharts**, the one library that earns its place because of zoom and confidence bands. Data loading uses `fetch` + `useEffect`. Styling is plain CSS. Dates use `Intl.DateTimeFormat` with `timeZone: 'Europe/London'`.
- **Dev practices:** GitHub Actions CI (ruff, pytest, `tsc`, Docker build) and an **AI-usage statement in the README** (required by the brief).
- **Skipped on purpose:**
  - pandas: stdlib covers 20k rows, and leaving it out removes the Vercel size worry.
  - httpx and tenacity: the fetch script runs by hand and is simply rerun if it fails.
  - pydantic-settings: the gate time is a query parameter, not configuration.
  - TanStack Query: two pages don't need it.
  - Tailwind and dayjs: plain CSS and `Intl` cover what we need.
  - mypy, pre-commit and Vitest: CI already covers the essentials.
  - **Add any of these only when a real need shows up.**

## 6. Deployment
**Decision: Vercel (free).** Vercel builds from the source and never runs Docker. Docker serves the "please use docker" requirement for **local development and reproducibility**: a Dockerfile plus `docker compose up` brings up the whole stack. CI also builds the image, which proves it works.

### Why Vercel
- **Free.** For a pilot or demo, hosting costs nothing. Heroku has no free tier any more; an Eco/Basic dyno costs ~$5–7 a month.
- **Always available and fast to open.** Static files come from a global CDN. Free Heroku-style dynos sleep, while Vercel serves the frontend instantly. That matters because reviewers will open the link in incognito at a random time.
- **Fits the workload.** The app only reads a small, fixed dataset (January 2026), so it needs no database, background jobs or long-running server. Short serverless requests are enough.
- **Low ops effort.** Every push to GitHub deploys automatically, each PR gets a preview URL, and HTTPS is built in.

### How it works (talking points for the explanation)
- **Deployment:** the React app is served as static files, and the FastAPI backend runs as a Vercel Python serverless function. A small `api/index.py` points Vercel at the same app Docker runs, so the code is identical in both places.
- **Data:** a serverless function can't refresh data while running, which is fine for fixed January 2026 data. The saved January data stays in the repo, and `scripts/fetch_data.py` regenerates it when needed.
- **Size limit:** Vercel caps Python functions at about 250 MB. With FastAPI as the only dependency and the data stored as gzipped JSON, the bundle is a few MB.
- **Repo layout:** `heroku.yml` is replaced by `vercel.json`.

### Trade-offs (what we give up, and why it's acceptable here)
| Trade-off | Impact | Why acceptable now / mitigation |
|---|---|---|
| **Production doesn't run the Docker image** | Local and prod environments differ slightly ("works in Docker" ≠ "works on Vercel") | The same FastAPI app and the same pinned dependencies run in both. CI runs the tests and builds the image, and a Vercel preview deploy checks the serverless path before merging. |
| **Stateless and read-only** | No live data refresh or in-memory cache that survives between requests | January 2026 data is historical and fixed. The snapshot is regenerated by a script and committed, which also makes the demo reproducible. |
| **Cold starts** | The first request after a quiet period takes ~1–3 s (Python + pandas start-up) | Keep dependencies lean, load the snapshot once per instance, and show loading states in the UI. |
| **Bundle size (~250 MB) and timeout limits** | Heavy libraries (pyarrow, scipy) and long computations are ruled out | Data is about 20k rows and every response takes milliseconds. Use compressed CSV/JSON, and drop pandas if needed. |
| **No background jobs or schedulers** | The app can't pull new Elexon data on a timer | Not needed for a fixed historical window. In production, a scheduled job (e.g. GitHub Actions cron or a cloud scheduler) would write to a database. |
| **Vendor-specific config** | `vercel.json` and `api/index.py` tie deployment to Vercel | Both are thin. The app itself is standard ASGI and still runs anywhere the Docker image can (Heroku, Render, Fly, Cloud Run). |

### What would change for production (the "next step" story)
A live version would forecast the next day every day, so it would need fresh data. That means a scheduled ingestion job writing to a database such as Postgres, with the API reading from it. At that point it makes sense to run the **same Docker image** as a long-running container (Cloud Run, Fly, Render or Heroku). The current design makes this an easy move: the domain logic is pure functions, and the data store is the only part that changes.

| Layer | Locally (Docker) | On Vercel |
|---|---|---|
| Frontend | Vite dev server / built static files | Static build served from the CDN |
| Backend | uvicorn container | FastAPI as a **Python serverless function** (`api/index.py` → ASGI app); `/api/*` routed there via `vercel.json` |
| Data | `data/snapshot/` mounted | Snapshot bundled into the function (read-only) |

**What Vercel means for the code:**
- **Stateless and read-only:** no live refresh at runtime. The snapshot is regenerated with `scripts/fetch_data.py` and committed, which suits fixed January 2026 data.
- **Bundle-size limit (~250 MB unzipped for Python):** keep dependencies lean. The snapshot is stored as gzipped CSV/JSON rather than parquet, to avoid pyarrow. pandas + numpy fit, but if the bundle gets tight, the domain logic can drop to pure Python because the data is only about 20k rows.
- **Cold starts:** load the snapshot once per function instance (module-level cache), which keeps them small.
- The same FastAPI app is used in both places. Only the entrypoint differs (`uvicorn app.main:app` in Docker, while `api/index.py` re-exports `app` for Vercel).

## 7. Time plan (≈16 h)
| # | Block | Est. |
|---|---|---|
| 1 | Data fetch script + snapshot + exploration notebook (confirm findings above) | 1.5 h |
| 2 | Domain layer: selection + metrics + unit tests | 3 h |
| 3 | FastAPI endpoints + schemas + API tests | 1.5 h |
| 4 | Frontend shell, API client, filters, URL state | 1.5 h |
| 5 | Day-ahead brief page (chart + band + KPIs) | 2 h |
| 6 | Accuracy page (tiles + 5 charts) | 2.5 h |
| 7 | Docker, compose, CI, Heroku deploy, incognito check | 1.5 h |
| 8 | README, polish, empty/error/loading states | 1 h |
| 9 | Video: script, 5-min client pitch + 5-min tech walkthrough | 1.5 h |

**Milestones:** M1 = data + domain tests green (end of block 2). M2 = API complete. M3 = both pages working locally. M4 = deployed. M5 = video submitted.

## 8. Risks
- **Elexon API change or outage:** handled by the committed snapshot.
- **Timezone or BST bugs:** handled by storing UTC, displaying Europe/London, and unit-testing a BST date even though January doesn't need it.
- **Bias hypothesis is wrong:** framed as a hypothesis in the pitch, backed only by the numbers.
- **Scope creep:** stretch items happen only after M4 (deployed).

## 8b. Value proposition (the "why not just use the Elexon API?" answer)

**Elexon publishes data, while the buyer needs a decision. Wind Desk is the layer in between.**

At 09:15 on decision day, the raw API gives the buyer:
- About 20 competing forecasts for every hour of tomorrow. There are 8 runs a day, each looking about 2.8 days ahead, and some were published after the gate.
- Hindcast rows mixed in with real forecasts, all in UTC JSON.
- Hourly forecasts set against half-hourly actuals, so the two don't line up.
- No measure of how reliable any of it is.

| Step | Raw Elexon | Wind Desk |
|---|---|---|
| 1. Pick the right number | About 20 competing forecasts per hour | The single forecast published before the gate, which the buyer could actually act on |
| 2. Make it comparable | Hourly vs half-hourly, UTC, hindcasts | Aligned hourly, shown in UK time, hindcasts removed |
| 3. Score it | Nothing | MAE, bias, P90, error vs lead time |
| 4. Quantify tomorrow's risk | Nothing | A P10–P90 band from settled days only (no hindsight) |
| 5. Say what it means | Nothing | "Forecasts run ~1.7 GW high, so buying on the raw number means under-buying" |

**Money line:** a systematic over-forecast means the desk under-buys day-ahead and covers the gap at intraday or imbalance prices, which are usually much more expensive. Nobody spots that pattern by reading JSON.

**Analogy for the pitch:** "The Met Office publishes raw model output; people plan their day with an app that picks the relevant forecast and says '70% chance of rain'. We do that for your day-ahead desk."

**Roadmap (shows the bigger value for the client):**
1. **Bias-corrected forecast.** This is the quickest win, because the error is systematic.
2. **Add demand.** Net requirement = demand − wind, which turns the screen into "buy X MWh for hour H".
3. **Add prices.** Put a £ value on forecast error, e.g. the imbalance cost of last month's bias.
4. **Better forecasts.** Benchmark our own wind forecast model against Elexon's on the same accuracy page.

## 9. Video outline
**Part 1, client pitch (≤5 min):**
1. Your problem: buy before the gate, wind is uncertain.
2. Live demo of the brief for a high-error day.
3. "The forecast over-states wind by ~1.7 GW, so you are systematically under-buying."
4. The uncertainty band and how to use P90 for hedging.
5. Next steps: demand netting, prices, bias correction.

**Part 2, tech lead (≤5 min):**
1. Architecture diagram.
2. Data semantics: hindcast filtering, the hourly vs half-hourly join, gate logic.
3. The pure domain layer and its tests.
4. API and frontend structure.
5. CI, Docker and deploy: why Vercel (free, always on, fits a read-only workload), with Docker for local work and CI.
6. Trade-offs: production doesn't run Docker, stateless snapshot, cold starts and size limits. Then what comes next: scheduled ingestion plus a database, running the same Docker image as a container.

**Script for the "snapshot vs live" point (say it, don't build it):**
> "January 2026 is historical, so I saved a snapshot. That makes the demo fast, free and immune to Elexon outages. A production version would add a scheduled job that pulls new forecasts after each run (8 times a day) into Postgres. The API would read from Postgres, and the same Docker image would run on a container host. Only the data-loading part of the code changes. The forecast selection and metrics logic stays the same."

Back it up by showing `scripts/fetch_data.py` re-downloading from Elexon with one command. That proves the app can pull real data without running a live system.
