# Wind Desk: Requirements Analysis & Design

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

### How a UK supplier buys power
| Stage | When | What happens |
|---|---|---|
| Forward / futures | Months to years ahead | Buy the bulk of expected demand to lock in prices |
| **Day-ahead auction** ← our user | **Once a day, before the D-1 gate** | Top up or sell back for tomorrow, using the latest wind forecast |
| Intraday | On the day, until about 1 h before delivery | Fine-tune as forecasts improve |
| Imbalance settlement | After delivery | Whatever is still short or long is settled at the imbalance price, often very expensive |

### Day-ahead market timing
| Venue | Gate closure (D-1) |
|---|---|
| EPEX SPOT GB day-ahead (hourly) | 10:20 CET = **09:20 UK** |
| Nord Pool N2EX GB day-ahead (hourly) | 10:50 CET = **09:50 UK** |

**Default decision cutoff: D-1 09:20 UK time**, configurable in the UI. All logic is timezone-aware (Europe/London).

### Elexon datasets (public, no API key)
| | FUELHH (actuals) | WINDFOR (forecasts) |
|---|---|---|
| Endpoint | `data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream` | `.../datasets/WINDFOR/stream` |
| Filter | `settlementDateFrom/To`, `fuelType=WIND` | `publishDateTimeFrom/To` |
| Resolution | **30 min** | **60 min** (startTime always on :00) |
| Response time | ~4 s for 62 days | 4–13 s for 65 days (~38k rows, ~4 MB) |

**WINDFOR behaviour:**
- **8 runs per day** at 02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30 and 22:30 UTC.
- Each run covers about 1 day back and up to **~66.5 h ahead**.
  → **Rows where `startTime ≤ publishTime` are hindcasts and are dropped.**
- At the 09:20 gate, the latest usable run is **07:30 on D-1**. For delivery day D that means horizons of 16.5 h to 39.5 h.
- **Each delivery hour is forecast about 20 times**, by successive runs. Choosing the right one is the core of requirement 1.

### Baseline accuracy (January 2026 decisions, hourly)
| Selection rule | MAE (MW) | Bias (fc − actual) | RMSE | P90 abs err |
|---|---|---|---|---|
| Day-ahead gate (D-1 09:20), delivery 2–31 Jan | 2058 | **+1772** | 2532 | 4193 |
| Same, delivery 2 Jan – 1 Feb (app default view) | 2022 | **+1746** | 2497 | 4158 |
| Horizon ≥ 1 h | 1712 | +1500 | 2180 | 3497 |
| Horizon ≥ 24 h | 1976 | +1774 | 2435 | 3911 |
| Horizon ≥ 48 h | 2335 | +1817 | 2906 | 4848 |

**Main finding:** the forecast **over-predicts by about 1.5–1.8 GW, consistently at every horizon**. Because the bias is systematic and doesn't shrink at short horizons, it isn't only weather uncertainty. The working hypothesis is **curtailment**: FUELHH is metered output after balancing actions, while WINDFOR forecasts unconstrained output. *This is presented as a hypothesis, not a fact.*

## 3. Interpretation decisions
1. **"Decisions made in January 2026"** means delivery days **2 Jan – 1 Feb 2026**. This is the **default view** of the app. The brief limits the analysis to this scenario, but the app fetches live data, so any delivery day can be selected.
2. **Latest forecast at decision time:** for target hour *t* on day D, take the run with the largest `publishTime` that is ≤ the cutoff (D-1 09:20 Europe/London) and also < *t*.
3. **Fixed-horizon mode** (analyst view): the latest run with `publishTime ≤ t − H`, with H from 0 to 48 h. This feeds the error-vs-lead-time curve.
4. **Resolution:** compare hourly, at HH:00, against the FUELHH half-hour starting at HH:00.
5. **Missing data** is shown as gaps, never interpolated. Coverage % is reported.
6. **Metrics:** MAE, RMSE, **bias**, P50/P90/P99 absolute error and nMAE. No MAPE, because it blows up at low wind.
7. **No look-ahead.** On decision day X the buyer buys for D = X + 1. The error history behind each decision covers the **last 30 settled delivery days, D−31 … D−2**. Day D−2 is fully settled before the 09:20 gate on D−1.
8. **The user works one day at a time.** The whole app is a single decision day. Accuracy is measured over the 30 settled days before it, so no date range is needed.

## 4. Product scope

### A. Day-ahead brief (requirement 1, home screen)
- Pick a **decision day**. The page shows "Deciding X / Delivering X + 1" and opens on 1 Jan 2026.
- A chart shows the **forecast from the latest run before the gate**. Dashed actuals are overlaid as a hindsight check.
- The forecast is wrapped in a **P10–P90 uncertainty band** built from the 30 settled days before the decision.
- A one-sentence brief states the expected wind energy and range, and how far the forecast has run high or low recently.
- KPI cards: run used, energy (GWh), hourly range, track record (history bias and MAE), and hindsight error.

### B. How reliable is this forecast? (requirement 2, same page under A)
- No separate tab or date range: accuracy is measured on the 30 settled days before the chosen decision, at the same gate, so it is exactly the track record the buyer has at decision time.
- Tiles: MAE, bias, P90, RMSE, nMAE and coverage.
- Charts: error by day (bias bars + MAE line), error by hour of day, error vs lead time (lead times behind this decision shaded).

### Out of scope
Demand, prices, other fuels, authentication.

## 5. Architecture

```
Browser (React SPA, Vercel CDN)
   │  GET /api/series?start&end&gate   GET /api/meta
   ▼
Vercel CDN ── 25-min cache per URL (s-maxage=1500) for successful responses
   │  miss
   ▼
FastAPI (Python serverless function on Vercel; same app runs in Docker locally)
   ├── validates input (dates, ≤31 days, gate HH:MM) → 422
   ├── elexon.fetch(first, last) ── FUELHH + WINDFOR in parallel, 25 s timeout → 502 on failure
   └── core.py (pure, stdlib): forecast selection, no-look-ahead history, metrics
```

**Key design choices**
- **Live data per request.** The API fetches exactly the delivery days requested, plus their 30-day history, straight from Elexon. So the tool works for any day, including tomorrow, with no ingestion pipeline to run.
- **Short CDN cache, not an app cache.** Elexon publishes forecasts every 2–4 h and actuals every 30 min, so a 25-minute edge cache keeps data current while repeat views skip the 4–13 s Elexon round trip. Serverless instances share no memory, so the CDN is the right place to cache. Errors are never cached.
- **A pure-function domain layer.** Selection and metrics logic does no I/O and is fully unit-tested. The Elexon client is the only thing that touches the network, and tests replace it with a frozen January 2026 fixture. So tests are offline and their exact numbers are reproducible.
- **Stdlib first.** FastAPI is the only runtime dependency. `urllib`, `concurrent.futures`, `zoneinfo` and `statistics` cover the rest.
- **One app, two runtimes.** The Docker image serves the API and the built UI from one container (local and CI). Vercel serves the UI from its CDN and the same FastAPI app as a function.

### API
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta` | default view (Jan 2026 pilot), selectable range, default gate |
| GET | `/api/series?start&end&gate=HH:MM` | aligned hourly rows, stats, and 30-day history: stats, by day, by hour, by lead time (0, 3, …, 48 h) |

### Repo layout
```
backend/
  core.py         # pure: forecast selection, history, metrics (stdlib only)
  elexon.py       # Elexon client: parallel fetch, timeout, ElexonError
  app.py          # FastAPI routes, validation, error handlers, cache headers
  fetch_data.py   # regenerates the offline test fixture
  data/           # January 2026 test fixture (gzipped JSON)
  test_core.py, test_app.py
frontend/src/     # App, DayAhead, Accuracy, Chart, api.ts, styles.css
api/index.py      # Vercel entrypoint: re-exports app
Dockerfile, docker-compose.yml, vercel.json, README.md
```

### Tech stack
- **Backend:** Python 3.12, FastAPI + uvicorn. Tooling: pytest, ruff.
- **Frontend:** React 18, TypeScript, Vite, Apache ECharts (tree-shaken), plain CSS, `Intl` for UK time.
- **Practices:**
  - Lint (ruff) and type-check (`tsc`) before every deploy.
  - Test-first domain logic.
  - Offline tests.
  - An AI-usage statement in the README.

## 6. Deployment

**Vercel (free), with Docker for local development.** The brief allows Vercel or Heroku. Vercel builds from source rather than running Docker, so Docker covers "please use docker": `docker compose up` runs the whole stack, and CI builds the image.

**Why Vercel**
- It's free, and a pilot shouldn't carry hosting costs.
- It's always available: the UI comes from a global CDN and doesn't sleep.
- It fits the workload: short, stateless requests.
- Its CDN gives us the 25-minute response cache for free.
- Pushes deploy automatically, with a preview URL per change.

**How it works**
- The React build is served as static files.
- FastAPI runs as a Python serverless function (`api/index.py`). `vercel.json` routes `/api/*` to it and allows up to 60 s per request.
- Each request pulls live data from Elexon.

**Trade-offs**
| Trade-off | Impact | Why acceptable / mitigation |
|---|---|---|
| Requests depend on Elexon | Slow (4–13 s on a cache miss); down when Elexon is down | Parallel fetch, 25 s timeout, clean 502 with Retry in the UI, 25-min edge cache |
| No cache in Docker | Locally, every request hits Elexon | Local use is low volume; the edge cache only exists in production |
| Cold starts | +1–2 s after idle | Small dependency set |
| Production doesn't run the Docker image | Minor difference between environments | Same app and dependencies; the image is built and run locally |
| Traffic passes through to Elexon on cache misses | Heavy, varied traffic multiplies Elexon calls | Fine for a pilot. In production, move to scheduled ingestion (below) |

**Production path:** a scheduled job pulls each new WINDFOR run and FUELHH half-hour into Postgres, and the API reads Postgres. Elexon then receives one call per publish no matter how many users there are, responses take milliseconds, and the app survives Elexon outages. Only `elexon.fetch` would change; the domain logic and its tests stay the same.

## 7. Edge cases & limits
**Handled (with tests):**
- Bad input (date before 2023-01-01 or after tomorrow, start > end, range over 31 days, gate `25:00`) → **422**, and Elexon is never called.
- Elexon timeout or error → **502** JSON, "Elexon BMRS is unavailable or slow right now. Please retry shortly."
- Unexpected server error → **500** JSON, with the cause logged.
- Errors are never cached, and the UI shows the message with a **Retry** button.
- Clock-change days (23/25 h), hours with no run before the cutoff, missing actuals and empty selections (n = 0, no crash).
- A run published exactly at the cutoff is included; one published exactly at the target hour is excluded.
- No look-ahead in the history window.
- UI: input changes wait 250 ms, the request being replaced is cancelled, and stale responses can never overwrite newer ones.
- UK time is shown whatever the viewer's timezone.

**Limits (deliberate):**
- **No per-client rate limiting in the app.** Serverless instances share no state, so an in-app counter is meaningless. In production, use Vercel Firewall rate-limit rules or a shared store such as Redis.
- At most 31 delivery days per request, which bounds the Elexon pull and compute.
- Elexon revises FUELHH occasionally; the app always shows the latest values.

## 8. Value proposition (the "why not just use the Elexon API?" answer)

**Elexon publishes data, while the buyer needs a decision. Wind Desk is the layer in between.**

| Step | Raw Elexon | Wind Desk |
|---|---|---|
| 1. Pick the right number | About 20 competing forecasts per hour | The single forecast published before the gate, which the buyer could actually act on |
| 2. Make it comparable | Hourly vs half-hourly, UTC, hindcasts | Aligned hourly, shown in UK time, hindcasts removed |
| 3. Score it | Nothing | MAE, bias, P90, error vs lead time |
| 4. Quantify tomorrow's risk | Nothing | A P10–P90 band from the last 30 settled days (no hindsight) |
| 5. Say what it means | Nothing | "Forecasts run ~1.7 GW high, so buying on the raw number means under-buying" |

**Money line:** a systematic over-forecast means the desk under-buys day-ahead and covers the gap at intraday or imbalance prices, which are usually much more expensive.

**Analogy:** "The Met Office publishes raw model output; people plan their day with an app that picks the relevant forecast and says '70% chance of rain'. We do that for your day-ahead desk."

**Roadmap:**
1. **Bias-corrected forecast.** The quickest win, because the error is systematic.
2. **Add demand.** Net requirement = demand − wind, which turns the screen into "buy X MWh for hour H".
3. **Add prices.** Put a £ value on forecast error.
4. **Better forecasts.** Benchmark our own wind model against Elexon's in the same reliability section.

## 9. Time plan (≈16 h)
| # | Block | Est. |
|---|---|---|
| 1 | Domain research, API exploration, baseline numbers | 1.5 h |
| 2 | Domain layer: selection + metrics + unit tests | 3 h |
| 3 | Elexon client + FastAPI endpoints + error handling + API tests | 2 h |
| 4 | Frontend shell, API client, design system | 1.5 h |
| 5 | Day-ahead brief page | 2 h |
| 6 | Reliability section | 2 h |
| 7 | Docker, Vercel deploy, incognito check | 1.5 h |
| 8 | README, polish | 1 h |
| 9 | Video | 1.5 h |

## 10. Video outline
**Part 1, client pitch (≤5 min):**
1. Your problem: buy before the gate, and wind is uncertain.
2. Live demo of the brief for a high-error day.
3. "The forecast over-states wind by ~1.7 GW, so you are systematically under-buying."
4. The uncertainty band, and how to use P90 for hedging.
5. Next steps: bias correction, demand netting, prices.

**Part 2, tech lead (≤5 min):**
1. Architecture diagram: SPA → CDN cache → FastAPI → Elexon.
2. Data semantics: hindcast filtering, hourly vs half-hourly join, gate logic, rolling no-look-ahead history.
3. The pure domain layer and its offline tests.
4. API, validation and error handling.
5. Docker and Vercel: why Vercel, and why the CDN is the right cache for serverless.
6. Trade-offs and the production path (scheduled ingestion + Postgres).

**Script for the caching / rate-limit question:**
> "Every request pulls live data from Elexon, so the tool works for any day, including tomorrow. Elexon only publishes new forecasts every 2–4 hours, so I cache successful responses at Vercel's edge for 25 minutes. Repeat views are instant and Elexon isn't hammered. Serverless instances share no memory, so an in-app cache or rate limiter would be meaningless; that belongs at the edge. At real scale I'd move to scheduled ingestion into Postgres. Only the Elexon client changes, and the domain logic and tests stay as they are."
