# Wind Forecast Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A React + FastAPI web app that shows a UK day-ahead buyer the wind forecast available at gate closure and quantifies its accuracy against actuals, for January 2026 decisions.

**Architecture:**
- A one-off script downloads Elexon FUELHH (WIND) and WINDFOR into a committed gzipped-JSON snapshot.
- A pure, stdlib-only `core.py` selects forecasts (gate or fixed-horizon mode) and computes error metrics, and FastAPI exposes it.
- The React SPA (Vite + ECharts) renders two pages.
- Docker runs everything as one container locally and in CI. Vercel serves the static build plus FastAPI as a Python function.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, pytest, ruff · React 18, TypeScript, Vite, ECharts · Docker · Vercel · GitHub Actions.

**Spec:** `PLAN.md` (repo root)

## Global Constraints

- Delivery window: **2026-01-02 to 2026-02-01 inclusive** (Europe/London local days), i.e. purchase decisions made 1–31 Jan 2026.
- Default gate (decision cutoff): **09:20 Europe/London on D-1**, user-changeable (`HH:MM`).
- Fixed-horizon mode: `horizon` in hours, integer **0–48**. Pick the latest run with `publish ≤ target − horizon` **and** `publish < target`.
- **No look-ahead:** the history for delivery day D covers delivery days `2026-01-02 … D − 2` (`MIN_HISTORY_DAYS = 3` before a band is shown). The Day-ahead page is driven by a **decision day** (1–31 Jan), where delivery = decision + 1.
- Error is always **forecast − actual** (positive = over-forecast). Metrics: MAE, RMSE, bias, P50/P90/P99 abs error, nMAE, coverage. **No MAPE.**
- Comparison is **hourly**: the forecast at HH:00 against the FUELHH half-hour starting at HH:00. Missing data is never interpolated.
- Forecast rows with `startTime ≤ publishTime` are dropped (they are hindcasts).
- Store and compute in UTC. Day boundaries and display use Europe/London.
- Backend runtime dependencies: **fastapi, uvicorn only**. Dev: pytest, httpx, ruff.
- Frontend dependencies: **react, react-dom, echarts** (+ vite, typescript, @vitejs/plugin-react). No query/state/CSS/date libraries.
- The README must state that AI tools (Claude Code) were used.
- Public repo name must be anonymous (random string). The deploy target is Vercel.

## Review Focus

1. **Clock-change day:** a delivery day spanning a DST change has 23 or 25 hours, and the gate stays at 09:20 *local*. Covered by tests in Task 2.
2. **No run before the cutoff:** that hour gets `forecast=None`. It is excluded from metrics but counted against coverage, and never errors. Task 2.
3. **Missing actuals or empty selection:** stats return `n=0` and `None` metrics, not a ZeroDivisionError or StatisticsError. Tasks 3 and 4.
4. **Run published exactly at the cutoff** is included (`≤`). A run published exactly at the target hour is excluded (`<`). Task 2.
5. **Bad query params** (date outside the window, `start > end`, gate `25:00`, horizon `99`) return **422**, not 500. Task 4.
6. **Look-ahead leak:** the history for delivery D must never include D − 1 or D. On the first days of the window it must be empty or `null` rather than erroring. Tasks 3 and 4.

---

## File Structure

```
requirements.txt          # fastapi, uvicorn (root: Vercel reads it here)
requirements-dev.txt      # -r requirements.txt, pytest, httpx, ruff
backend/
  fetch_data.py           # Elexon → data/*.json.gz (run by hand)
  core.py                 # pure selection + metrics
  app.py                  # FastAPI routes, loads snapshot at import, serves static/ if present
  test_core.py
  test_app.py
  data/actuals.json.gz, forecasts.json.gz
frontend/
  package.json, vite.config.ts, tsconfig.json, index.html
  src/main.tsx, App.tsx, api.ts, Chart.tsx, DayAhead.tsx, Accuracy.tsx, styles.css
api/index.py              # Vercel entrypoint
Dockerfile, docker-compose.yml, vercel.json, .github/workflows/ci.yml, README.md, .gitignore
```

---

### Task 1: Repo init + data snapshot

**Files:**
- Create: `.gitignore`, `requirements.txt`, `requirements-dev.txt`, `backend/fetch_data.py`, `backend/data/*.json.gz`

**Interfaces:**
- Produces:
  - `backend/data/actuals.json.gz`: JSON list of `[startTimeISO, generationMW]`. FUELHH with `fuelType=WIND`, `settlementDateFrom=2026-01-01`, `settlementDateTo=2026-02-02`.
  - `backend/data/forecasts.json.gz`: JSON list of `[publishTimeISO, startTimeISO, generationMW]`. WINDFOR with `publishDateTimeFrom=2025-12-31T00:00:00Z`, `publishDateTimeTo=2026-02-02T00:00:00Z`. Only rows where `startTime > publishTime` are kept.
  - ISO strings stay exactly as Elexon returns them (`...Z`).

- [ ] **Step 1:** Run `git init`. Create `.gitignore` (`.venv/`, `node_modules/`, `dist/`, `__pycache__/`, `backend/static/`, `.vercel/`). Create the two requirements files as described in File Structure.
- [ ] **Step 2:** Write `backend/fetch_data.py`. Use stdlib `urllib.request` + `json` + `gzip`. The base URL is `https://data.elexon.co.uk/bmrs/api/v1/datasets/{FUELHH|WINDFOR}/stream`. Write to `data/` next to the script.
- [ ] **Step 3:** Run `python backend/fetch_data.py`. Expected: it prints row counts with **actuals ≈ 1584** (33 days × 48) and **forecasts ≈ 13–15k** (≈18.7k raw minus hindcasts). Each file is under 300 KB.
- [ ] **Step 4:** Commit: `chore: init repo and add Jan 2026 Elexon wind snapshot`.

---

### Task 2: Forecast selection (`core.py`)

**Files:**
- Create: `backend/core.py`, `backend/test_core.py`

**Interfaces:**
- Produces (all datetimes are tz-aware UTC):
  - `LONDON = ZoneInfo("Europe/London")`, `WINDOW = (date(2026,1,2), date(2026,2,1))`, `DEFAULT_GATE = time(9,20)`
  - `@dataclass(frozen=True) class Data: actuals: dict[datetime, float]; runs: dict[datetime, list[tuple[datetime, float]]]`. `runs` is keyed by target, and each list is sorted by publish time, oldest first.
  - `load(actual_rows: list[list], forecast_rows: list[list]) -> Data`: takes rows in the Task 1 formats.
  - `targets(start: date, end: date) -> list[datetime]`: every UTC hour whose London-local date is in `[start, end]`.
  - `gate_cutoff(target: datetime, gate: time) -> datetime`: `(London date of target − 1 day) at gate`, London time, converted to UTC.
  - `pick(runs: list[tuple[datetime, float]], cutoff: datetime, target: datetime) -> tuple[datetime, float] | None`: the latest run with `publish ≤ cutoff` and `publish < target`.
  - `@dataclass(frozen=True) class Row: t: datetime; actual: float | None; forecast: float | None; publish: datetime | None`
  - `series(data: Data, start: date, end: date, gate: time | None = None, horizon: int | None = None) -> list[Row]`: exactly one of `gate` or `horizon` is used. If `horizon` is given, cutoff = `t − horizon h`.

- [ ] **Step 1: Write the failing tests** in `backend/test_core.py`. Use a tiny `Data` fixture built with `load()`:

```python
def test_targets_normal_day():
    ts = targets(date(2026,1,2), date(2026,1,2))
    assert len(ts) == 24 and ts[0] == datetime(2026,1,2,0,tzinfo=UTC)

def test_targets_dst_day_has_23_hours():
    assert len(targets(date(2026,3,29), date(2026,3,29))) == 23

def test_gate_cutoff_winter_and_summer():
    assert gate_cutoff(datetime(2026,1,2,5,tzinfo=UTC), time(9,20)) == datetime(2026,1,1,9,20,tzinfo=UTC)
    assert gate_cutoff(datetime(2026,7,2,5,tzinfo=UTC), time(9,20)) == datetime(2026,7,1,8,20,tzinfo=UTC)

def test_pick_latest_before_cutoff_inclusive():
    runs = [(dt("2026-01-01T07:30"), 100.0), (dt("2026-01-01T09:30"), 200.0)]
    t = dt("2026-01-02T05:00")
    assert pick(runs, dt("2026-01-01T09:20"), t) == (dt("2026-01-01T07:30"), 100.0)
    assert pick(runs, dt("2026-01-01T09:30"), t)[1] == 200.0   # equality included
    assert pick(runs, dt("2026-01-01T07:00"), t) is None

def test_horizon_zero_excludes_run_published_at_target():
    # run published exactly at target time must not be used, even with horizon=0
    ...  # one run at 2026-01-02T05:00 for target 05:00 → Row.forecast is None

def test_series_gate_row_has_no_forecast_when_no_run_before_cutoff(): ...
def test_series_actual_none_when_missing(): ...
```

  (`dt(s)` is a test helper: `datetime.fromisoformat(s).replace(tzinfo=UTC)`.)

- [ ] **Step 2:** Run `pytest backend/test_core.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement the interfaces in `backend/core.py`. Use stdlib only: `zoneinfo`, `bisect`, `dataclasses`.
- [ ] **Step 4:** Run `pytest backend/test_core.py -v`. Expected: all PASS.
- [ ] **Step 5:** Commit: `feat(core): gate and horizon forecast selection`.

---

### Task 3: Metrics (`core.py`)

**Files:**
- Modify: `backend/core.py`, `backend/test_core.py`

**Interfaces:**
- Consumes: `Row`, `Data`, `series` (Task 2)
- Produces:
  - `stats(rows: list[Row]) -> dict`. Keys: `n, coverage, mae, rmse, bias, nmae, p50, p90, p99, err_p10, err_p90`.
    - Only rows with both values count. `coverage = n / len(rows)`.
    - `p*` are quantiles of **absolute** error. `err_p10` and `err_p90` are quantiles of **signed** error (used for the uncertainty band).
    - When `n == 0`, every metric except `n` and `coverage` is `None`.
  - Quantile rule (nearest rank, sorted list `v`): `v[min(len(v)-1, int(p*len(v)))]`.
  - `by_hour(rows) -> list[dict]`: `[{hour: 0..23 London, n, mae, bias}]`, only for hours that have data.
  - `histogram(rows, width: int = 500) -> list[dict]`: `[{lo, count}]`, where `lo = floor(err/width)*width`, sorted by `lo`.
  - `by_horizon(data: Data, start: date, end: date, horizons=range(0, 49, 3)) -> list[dict]`: `[{h, n, mae, bias, p90}]`.
  - `MIN_HISTORY_DAYS = 3`
  - `history_range(delivery: date) -> tuple[date, date] | None`: returns `(WINDOW[0], delivery − 2 days)`, or `None` when that end date is before `WINDOW[0]`.

- [ ] **Step 1: Write the failing tests:**

```python
ROWS = [Row(T0, 8, 10, P), Row(T1, 25, 20, P), Row(T2, 30, 30, P), Row(T3, 5, None, None)]
# errors: +2, -5, 0

def test_stats_basic():
    s = stats(ROWS)
    assert s["n"] == 3 and s["coverage"] == 0.75
    assert s["mae"] == pytest.approx(7/3)
    assert s["bias"] == pytest.approx(-1)
    assert s["rmse"] == pytest.approx((29/3) ** 0.5)
    assert s["nmae"] == pytest.approx((7/3) / 21)

def test_stats_empty_is_none_not_error():
    s = stats([Row(T0, None, 10, P)])
    assert s["n"] == 0 and s["mae"] is None and s["p90"] is None

def test_histogram_bins():
    assert histogram(ROWS, 500) == [{"lo": -500, "count": 1}, {"lo": 0, "count": 2}]

def test_history_range_no_lookahead():
    assert history_range(date(2026,1,16)) == (date(2026,1,2), date(2026,1,14))
    assert history_range(date(2026,1,4)) == (date(2026,1,2), date(2026,1,2))
    assert history_range(date(2026,1,3)) is None and history_range(date(2026,1,2)) is None

def test_by_hour_uses_london_hour(): ...   # a BST row at 23:00Z lands in hour 0
def test_by_horizon_returns_one_entry_per_h(): ...  # len == 17 for default range
```

- [ ] **Step 2:** Run `pytest backend/test_core.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement the functions. Use `statistics.fmean` and `math.floor`.
- [ ] **Step 4:** Run `pytest backend -v`. Expected: all PASS.
- [ ] **Step 5:** Smoke-check against the real data:

  ```bash
  python -c "import core,json,gzip; ..."
  ```

  `stats(series(..., gate=time(9,20)))` over the full window must give **MAE ≈ 2058, bias ≈ +1772, n = 720** (the values in the PLAN.md baseline table). Small differences are fine only if explained.
- [ ] **Step 6:** Commit: `feat(core): error metrics`.

---

### Task 4: API (`app.py`)

**Files:**
- Create: `backend/app.py`, `backend/test_app.py`

**Interfaces:**
- Consumes: everything in `core`.
- Produces HTTP:
  - `GET /api/meta` → `{"start":"2026-01-02","end":"2026-02-01","default_gate":"09:20"}`
  - `GET /api/series?start=YYYY-MM-DD&end=YYYY-MM-DD&gate=HH:MM&horizon=N`
    - If `horizon` is present it wins, otherwise `gate` is used (default 09:20).
    - Returns `{rows:[{t, actual, forecast, publish}], stats, by_hour, histogram, history}`.
    - `t` and `publish` are ISO UTC strings.
    - `history = {start, end, days, stats}` is `stats` over `history_range(start)` with the same mode. It is `null` when `history_range` returns `None`.
    - The UI draws the band as `forecast − err_p90 … forecast − err_p10`, only when `days ≥ 3`.
  - `GET /api/horizons?start&end` → the `by_horizon` list.
  - Static: if `backend/static/` exists, mount it at `/` with `html=True`.
- The snapshot is loaded once at module import into `DATA`, with paths relative to `__file__`.

- [ ] **Step 1: Write the failing tests** in `backend/test_app.py` with `fastapi.testclient.TestClient`:

```python
def test_meta(): assert c.get("/api/meta").json()["default_gate"] == "09:20"
def test_series_one_day_gate():
    r = c.get("/api/series", params={"start":"2026-01-15","end":"2026-01-15"}).json()
    assert len(r["rows"]) == 24 and r["stats"]["n"] == 24
    assert all(row["publish"].startswith("2026-01-14T07:30") for row in r["rows"])
def test_series_history_has_no_lookahead():
    h = c.get("/api/series", params={"start":"2026-01-16","end":"2026-01-16"}).json()["history"]
    assert h["start"] == "2026-01-02" and h["end"] == "2026-01-14" and h["days"] == 13
    first = c.get("/api/series", params={"start":"2026-01-02","end":"2026-01-02"}).json()
    assert first["history"] is None
def test_series_horizon_mode(): ...  # horizon=0 → publish < t for every row
@pytest.mark.parametrize("params", [
    {"start":"2025-12-01","end":"2026-01-05"}, {"start":"2026-01-10","end":"2026-01-05"},
    {"start":"2026-01-02","end":"2026-01-02","gate":"25:00"},
    {"start":"2026-01-02","end":"2026-01-02","horizon":"99"}])
def test_bad_params_422(params): assert c.get("/api/series", params=params).status_code == 422
def test_horizons_len(): assert len(c.get("/api/horizons", params=FULL).json()) == 17
```

- [ ] **Step 2:** Run `pytest backend -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `app.py`.
  - Validate `gate` with `Query(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")` and `horizon` with `Query(ge=0, le=48)`.
  - Check the window and ordering in code, raising `HTTPException(422)` on failure.
- [ ] **Step 4:** Run `pytest backend -v`, then `uvicorn app:app --app-dir backend` and `curl localhost:8000/api/meta`. Expected: PASS, and the JSON prints.
- [ ] **Step 5:** Commit: `feat(api): series, horizons and meta endpoints`.

---

### Task 5: Frontend shell (`App`, `api.ts`, `Chart`)

**Files:**
- Create: `frontend/` (Vite React-TS template, trimmed), `src/api.ts`, `src/Chart.tsx`, `src/App.tsx`, `src/styles.css`

**Interfaces:**
- Consumes: the HTTP API from Task 4.
- Produces:
  - `api.ts`: TypeScript types `Row`, `Stats`, `SeriesResponse`, `HorizonPoint`, `Meta` that mirror the API. Functions `getMeta()`, `getSeries(p: {start, end, gate?, horizon?})` and `getHorizons(start, end)`. Each is a plain `fetch` that throws on `!res.ok`.
  - `Chart.tsx`: `<Chart option={EChartsOption} height={number} />`. It calls `echarts.init` on mount, `setOption(option, true)` when `option` changes, resizes on window resize, and disposes on unmount.
  - `App.tsx`: two tab buttons ("Day-ahead brief", "Forecast accuracy"), with the selection held in `useState`. It loads `getMeta()` once and passes it down.
  - `fmtLondon(iso: string): string`, exported from `api.ts`. It uses `Intl.DateTimeFormat('en-GB', {timeZone:'Europe/London', ...})`.
- `vite.config.ts` proxies `/api` to `http://localhost:8000`.

- [ ] **Step 1:** Scaffold with `npm create vite@latest frontend -- --template react-ts`, then `npm i echarts`. Delete the demo assets.
- [ ] **Step 2:** Implement the files above in `styles.css`, using `:root` tokens and **light theme only**. The direction is "premium, not AI-generated": closer to an FT or Bloomberg terminal than a SaaS template.
  - **Palette:** paper `#FAFAF7` (warm off-white page), surface `#FFFFFF`, ink `#14161A`, muted `#6B6F76`, hairline `#E4E2DC`.
    - One accent, deep petrol `#0F4C5C`, used for the forecast line, the active tab and focus rings.
    - Signal amber `#B4530A` only for over-forecast and bias call-outs.
    - Actuals in ink, shown as a dashed line.
    - The band is the accent at 12% opacity.
  - **Type:** IBM Plex Sans for UI (Google Fonts, 400/500/600) and IBM Plex Mono with tabular figures for every number.
    - A small uppercase, letter-spaced label sits above each KPI.
    - KPI values are 28 px mono.
  - **Layout:**
    - Left-aligned, max width 1180 px, an 8 px spacing grid.
    - Sections are separated by 1 px hairlines rather than floating cards: radius 2–4 px, no drop shadows.
    - The header is a single line with the product name ("Wind Desk"), the tabs as underlined text and the data-as-of note on the right.
  - **Avoid (AI tells):** gradients, glassmorphism, emoji or icon-in-circle cards, pill badges everywhere, centred hero text, purple or indigo, big rounded shadows, "✨".
  - Must stay readable at 375 px wide (KPIs wrap 2-up, charts full width).
- [ ] **Step 3:** Run `npm run build`. Expected: `tsc` and the Vite build succeed. With uvicorn and `npm run dev` both running, the tabs render and the browser network panel shows `/api/meta` returning 200.
- [ ] **Step 4:** Commit: `feat(web): app shell, api client, chart wrapper`.

---

### Task 6: Day-ahead brief page

**Files:**
- Create: `frontend/src/DayAhead.tsx`

**Interfaces:**
- Consumes: `getSeries`, `Chart`, `Meta`, `fmtLondon`.

- [ ] **Step 1:** Add the controls:
  - A **decision day** `<input type="date">` bounded by `meta.start − 1 day` … `meta.end − 1 day` (1–31 Jan), defaulting to the first day.
  - A heading line: "Deciding on {X} · Delivering {X + 1}".
  - `<input type="time">` defaulting to `meta.default_gate`.
  - The page fetches `getSeries({start: D, end: D, gate})`, where D = X + 1, whenever either input changes.
- [ ] **Step 2:** Add the KPI cards:
  - Forecast run used (`fmtLondon(rows[0].publish)`, or "no forecast available").
  - Forecast energy for the day: `Σ forecast` MWh, shown in GWh.
  - Min/max hourly forecast.
  - **Track record so far:** `history.stats` MAE and bias, e.g. "over-forecast by 1.8 GW across 13 settled days". Shows "building history (n days)" when `history` is `null` or `days < 3`.
  - Hindsight: the day's MAE and bias against actuals, labelled "known after delivery".
- [ ] **Step 3:** Add the chart:
  - Forecast line, plus the actual line drawn dashed and labelled "Actual (hindsight)".
  - A shaded P10–P90 band using two stacked lines: lower = `forecast − err_p90`, then a stacked area of `err_p90 − err_p10`. It is drawn only when `history.days ≥ 3`.
  - x-axis in London time; y-axis in MW.
  - Caption: "Band = P10–P90 forecast error over {days} settled days before this decision (2 Jan – {history.end})".
- [ ] **Step 4:** Check in the browser that **decision day 14 Jan (delivering 15 Jan) at the 09:20 gate shows run 14 Jan 07:30**, with the band caption ending "12 settled days (2 Jan – 13 Jan)". Changing the gate to 10:00 should switch the run to 09:30, and decision day 1 Jan should show "building history". Run `npm run build` and confirm it passes.
- [ ] **Step 5:** Commit: `feat(web): day-ahead brief`.

---

### Task 7: Forecast accuracy page

**Files:**
- Create: `frontend/src/Accuracy.tsx`

**Interfaces:**
- Consumes: `getSeries`, `getHorizons`, `Chart`.

- [ ] **Step 1:** Add the controls:
  - Start and end date inputs (defaulting to the full window).
  - A mode toggle: "At gate" with a time input, or "Fixed horizon" with a number input from 0 to 48.
- [ ] **Step 2:** Add a **headline insight callout** at the top of the page, built from `stats.bias` and `stats.mae` for the current filters:
  - When bias > 0: "Forecasts **over-predicted** wind by **{bias/1000:.1f} GW** on average, so buying on the raw forecast means systematically **under-buying**."
  - When bias < 0: the over-buying wording.
  - Always add the line: "Typical miss: {mae/1000:.1f} GW; 1 hour in 10 off by more than {p90/1000:.1f} GW."

  Below the callout, add metric tiles for MAE, RMSE, bias (signed, labelled "over-forecast" when > 0), P90, nMAE % and coverage %.
- [ ] **Step 3:** Add four charts:
  1. Forecast vs actual over time, with dataZoom.
  2. MAE and bias vs horizon (from `getHorizons`).
  3. Error histogram.
  4. MAE and bias by hour of day.
- [ ] **Step 4:** Check in the browser that the full window at gate 09:20 shows **MAE ≈ 2.06 GW and bias ≈ +1.77 GW**, and that the callout reads "over-predicted … 1.8 GW". Also check and that MAE in the horizon chart rises from h=0 to h=48. Run `npm run build` and confirm it passes.
- [ ] **Step 5:** Commit: `feat(web): accuracy dashboard`.

---

### Task 8: Docker

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`

- [ ] **Step 1:** Write the multi-stage `Dockerfile`:
  - Stage 1: `node:20-alpine` runs `npm ci && npm run build` in `frontend/`.
  - Stage 2: `python:3.12-slim` runs `pip install -r requirements.txt`, copies `backend/` and copies `dist` to `backend/static/`.
  - Command: `CMD uvicorn app:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}`.
- [ ] **Step 2:** Write `docker-compose.yml` with one service, `build: .`, on port `8000:8000`.
- [ ] **Step 3:** Run `docker compose up --build`, then `curl localhost:8000/api/meta` and open `localhost:8000`. Expected: JSON, and the SPA loads both pages.
- [ ] **Step 4:** Commit: `build: docker image serving API and SPA`.

---

### Task 9: Vercel, CI, README

**Files:**
- Create: `api/index.py`, `vercel.json`, `.github/workflows/ci.yml`, `README.md`

- [ ] **Step 1:** Write `api/index.py`. It inserts `backend/` into `sys.path`, then `from app import app`.
- [ ] **Step 2:** Write `vercel.json`:
  - `buildCommand`: `cd frontend && npm ci && npm run build`
  - `outputDirectory`: `frontend/dist`
  - `rewrites`: `{"source":"/api/(.*)","destination":"/api/index"}`
  - `functions."api/index.py".includeFiles`: `"backend/**"`
- [ ] **Step 3:** Run `vercel deploy`. Open the preview URL **in incognito**. Expected: `/api/meta` returns JSON and both pages render.
  - If FastAPI receives `/api/index` instead of the original path, fix it by making the rewrite keep the path. Do not add routes.
- [ ] **Step 4:** Write `.github/workflows/ci.yml` with two jobs:
  - Python: `pip install -r requirements-dev.txt && ruff check backend && pytest backend`.
  - Web: `npm ci && npm run build` in `frontend`, then `docker build .`.
- [ ] **Step 5:** Write `README.md` covering:
  - What the app does (two sentences) and the live link.
  - The files and directories present.
  - How to run it with Docker, and locally (uvicorn + `npm run dev`).
  - How to refresh the data (`python backend/fetch_data.py`).
  - Data semantics: the gate, the delivery window, the hourly join, hindcasts dropped, and the in-sample band.
  - Deployment trade-offs (one paragraph, linking to PLAN.md).
  - **AI tools used: Claude Code.**
- [ ] **Step 6:** Run `vercel --prod`. Verify the production URL in incognito. Push to a public GitHub repo with a random name and confirm CI is green.
- [ ] **Step 7:** Commit: `ci, vercel deploy and README`.

---

## After Task 9 (not part of this plan)

Record the video using the outline in PLAN.md §9. Optional extras, in order:
1. Forecast evolution chart.
2. Bias-correction toggle.
3. CSV export.

Each extra needs its own small plan.
