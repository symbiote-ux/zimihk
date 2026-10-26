import { useMemo, useState } from 'react'
import type { EChartsOption } from 'echarts'
import { fmtDay, fmtLondon, getHorizons, getSeries, gw, signedGw, useApi, type Meta } from './api'
import { C, Chart, axis } from './Chart'

const GATE_RE = /^([01]\d|2[0-3]):[0-5]\d$/
const gwFmt = (v: unknown) => (typeof v === 'number' ? `${gw(v, 2)} GW` : '—')
const pct = (v: number | null | undefined) => (v == null ? '—' : (v * 100).toFixed(1))

export default function Accuracy({ meta }: { meta: Meta }) {
  const [start, setStart] = useState(meta.start)
  const [end, setEnd] = useState(meta.end)
  const [mode, setMode] = useState<'gate' | 'horizon'>('gate')
  const [gateInput, setGateInput] = useState(meta.default_gate)
  const [gate, setGate] = useState(meta.default_gate)
  const [horizon, setHorizon] = useState(24)

  const rangeError = start > end ? 'Start date must be on or before the end date.' : null
  const series = useApi(
    () =>
      rangeError
        ? Promise.reject(new Error(rangeError))
        : getSeries(mode === 'gate' ? { start, end, gate } : { start, end, horizon }),
    [start, end, mode, gate, horizon],
  )
  const horizons = useApi(
    () => (rangeError ? Promise.reject(new Error(rangeError)) : getHorizons(start, end)),
    [start, end],
  )
  const s = series.data?.stats
  const rows = series.data?.rows ?? []

  const timeline = useMemo<EChartsOption>(() => ({
    legend: { data: ['Forecast', 'Actual'] },
    grid: { left: 56, right: 16, top: 32, bottom: 72 },
    xAxis: axis({
      type: 'category', boundaryGap: false, data: rows.map((r) => fmtLondon(r.t)),
      axisLabel: { ...axis().axisLabel, formatter: (v: string) => v.split(',')[0] }, splitLine: { show: false },
    }),
    yAxis: axis({ type: 'value' }),
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 22, bottom: 12, borderColor: C.hair, fillerColor: C.band, handleStyle: { color: C.accent } }],
    series: [
      { name: 'Forecast', type: 'line', data: rows.map((r) => r.forecast), symbol: 'none', lineStyle: { color: C.accent, width: 1.5 }, itemStyle: { color: C.accent }, tooltip: { valueFormatter: gwFmt } },
      { name: 'Actual', type: 'line', data: rows.map((r) => r.actual), symbol: 'none', lineStyle: { color: C.ink, width: 1, type: 'dashed' }, itemStyle: { color: C.ink }, tooltip: { valueFormatter: gwFmt } },
    ],
  }), [rows])

  const horizonOpt = useMemo<EChartsOption>(() => {
    const hs = horizons.data ?? []
    return {
      legend: { data: ['MAE', 'Bias'] },
      xAxis: axis({ type: 'category', data: hs.map((h) => `${h.h}h`), name: 'Hours ahead', nameLocation: 'middle', nameGap: 28, splitLine: { show: false } }),
      yAxis: axis({ type: 'value', axisLabel: { ...axis().axisLabel, formatter: (v: number) => gw(v) } }),
      series: [
        { name: 'MAE', type: 'line', data: hs.map((h) => h.mae), symbolSize: 5, lineStyle: { color: C.accent, width: 2 }, itemStyle: { color: C.accent }, tooltip: { valueFormatter: gwFmt } },
        { name: 'Bias', type: 'line', data: hs.map((h) => h.bias), symbolSize: 5, lineStyle: { color: C.amber, width: 1.5 }, itemStyle: { color: C.amber }, tooltip: { valueFormatter: gwFmt } },
      ],
    }
  }, [horizons.data])

  const histOpt = useMemo<EChartsOption>(() => {
    const bins = series.data?.histogram ?? []
    return {
      legend: { show: false },
      tooltip: { trigger: 'axis', valueFormatter: (v) => `${v} hours` },
      xAxis: axis({ type: 'category', data: bins.map((b) => gw(b.lo)), name: 'Forecast − actual, GW', nameLocation: 'middle', nameGap: 28, splitLine: { show: false } }),
      yAxis: axis({ type: 'value' }),
      series: [{
        type: 'bar', name: 'Hours', barCategoryGap: '12%',
        data: bins.map((b) => ({ value: b.count, itemStyle: { color: b.lo >= 0 ? C.amber : C.accent } })),
      }],
    }
  }, [series.data])

  const hourOpt = useMemo<EChartsOption>(() => {
    const hs = series.data?.by_hour ?? []
    return {
      legend: { data: ['MAE', 'Bias'] },
      xAxis: axis({ type: 'category', data: hs.map((h) => String(h.hour).padStart(2, '0')), name: 'Hour of delivery (UK)', nameLocation: 'middle', nameGap: 28, splitLine: { show: false } }),
      yAxis: axis({ type: 'value', axisLabel: { ...axis().axisLabel, formatter: (v: number) => gw(v) } }),
      series: [
        { name: 'MAE', type: 'bar', data: hs.map((h) => h.mae), itemStyle: { color: 'rgba(15, 76, 92, 0.75)' }, barCategoryGap: '30%', tooltip: { valueFormatter: gwFmt } },
        { name: 'Bias', type: 'line', data: hs.map((h) => h.bias), symbolSize: 4, lineStyle: { color: C.amber, width: 1.5 }, itemStyle: { color: C.amber }, tooltip: { valueFormatter: gwFmt } },
      ],
    }
  }, [series.data])

  const over = s?.bias != null && s.bias > 0
  const selection = mode === 'gate' ? `the forecast available at the ${gate} gate` : `forecasts made ${horizon}h ahead`
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Forecast accuracy</div>
          <h1>
            {fmtDay(start)} – {fmtDay(end)}
            <span className="sep">/</span>
            {mode === 'gate' ? `At ${gate} gate` : `${horizon}h ahead`}
          </h1>
        </div>
        <div className="controls">
          <label className="field">
            <span className="label">From</span>
            <input type="date" min={meta.start} max={meta.end} value={start} onChange={(e) => e.target.value && setStart(e.target.value)} />
          </label>
          <label className="field">
            <span className="label">To</span>
            <input type="date" min={meta.start} max={meta.end} value={end} onChange={(e) => e.target.value && setEnd(e.target.value)} />
          </label>
          <div className="field">
            <span className="label">Compare</span>
            <div className="segmented">
              <button aria-pressed={mode === 'gate'} onClick={() => setMode('gate')}>At gate</button>
              <button aria-pressed={mode === 'horizon'} onClick={() => setMode('horizon')}>Fixed horizon</button>
            </div>
          </div>
          {mode === 'gate' ? (
            <label className="field">
              <span className="label">Gate (UK time)</span>
              <input type="time" step={60} value={gateInput} onChange={(e) => {
                setGateInput(e.target.value)
                if (GATE_RE.test(e.target.value)) setGate(e.target.value)
              }} />
            </label>
          ) : (
            <label className="field">
              <span className="label">Hours ahead</span>
              <input type="number" min={0} max={48} step={1} value={horizon} style={{ width: 84 }} onChange={(e) => {
                const v = Number(e.target.value)
                if (Number.isInteger(v) && v >= 0 && v <= 48) setHorizon(v)
              }} />
            </label>
          )}
        </div>
      </div>

      {series.error && <p className="error">{series.error}</p>}

      {s && !series.error && (
        <>
          <div className={`callout${over ? '' : ' neutral'}`}>
            {s.n ? (
              <>
                <p>
                  Forecasts <span className={over ? 'over' : ''}>{over ? 'over' : 'under'}-predicted</span> wind by{' '}
                  <span className="num">{gw(Math.abs(s.bias!), 1)} GW</span> on average, so buying on the raw forecast means
                  systematically <b>{over ? 'under' : 'over'}-buying</b>.
                </p>
                <p className="sub">
                  Typical miss: <span className="num">{gw(s.mae)} GW</span>; 1 hour in 10 off by more than{' '}
                  <span className="num">{gw(s.p90)} GW</span>. Measured on {selection}, {s.n} hours.
                </p>
              </>
            ) : (
              <p>No hours in this selection have both a forecast and an actual.</p>
            )}
          </div>

          <div className="kpis">
            <Tile label="MAE" value={gw(s.mae, 2)} unit="GW" sub="Mean absolute error" />
            <Tile label="RMSE" value={gw(s.rmse, 2)} unit="GW" sub="Penalises large misses" />
            <Tile label="Bias" value={signedGw(s.bias)} unit="GW" sub={s.bias == null ? 'No data' : over ? 'Over-forecast' : 'Under-forecast'} over={over} />
            <Tile label="P90 abs error" value={gw(s.p90, 2)} unit="GW" sub="Exceeded 1 hour in 10" />
            <Tile label="nMAE" value={pct(s.nmae)} unit="%" sub="MAE ÷ mean actual" />
            <Tile label="Coverage" value={pct(s.coverage)} unit="%" sub={`${s.n} of ${rows.length} hours`} />
          </div>

          <section className="section">
            <div className="section-head">
              <h2>Forecast vs actual · MW, UK time</h2>
              <span className="status">{series.loading ? 'Updating…' : 'Drag the slider or scroll to zoom'}</span>
            </div>
            <Chart option={timeline} height={340} />
          </section>

          <div className="grid-2">
            <section className="section">
              <h2>Error grows with lead time</h2>
              <p className="caption">Same delivery days, forecast picked h hours before each hour. Independent of the gate setting.</p>
              <Chart option={horizonOpt} height={280} />
            </section>
            <section className="section">
              <h2>Error distribution</h2>
              <p className="caption">Hours per 0.5 GW bucket. Amber = forecast above actual (over-forecast).</p>
              <Chart option={histOpt} height={280} />
            </section>
          </div>

          <section className="section">
            <h2>Error by hour of day</h2>
            <p className="caption">Where in the day the forecast misses most: plan hedges for those hours first.</p>
            <Chart option={hourOpt} height={260} />
          </section>

          <footer className="note">
            Error = forecast − actual, hourly (forecast at HH:00 vs the FUELHH half-hour starting HH:00). Forecast rows published
            at or after their target time are excluded. Positive bias may partly reflect curtailment: actuals are metered output
            after balancing actions. This is a hypothesis to confirm with the client.
          </footer>
        </>
      )}
    </>
  )
}

function Tile(p: { label: string; value: string; unit: string; sub: string; over?: boolean }) {
  return (
    <div className="kpi">
      <div className="label">{p.label}</div>
      <div className={`value${p.over ? ' over' : ''}`}>
        {p.value}
        <small>{p.unit}</small>
      </div>
      <div className="sub">{p.sub}</div>
    </div>
  )
}
