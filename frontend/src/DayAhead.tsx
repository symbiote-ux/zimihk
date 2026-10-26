import { useMemo, useState } from 'react'
import type { EChartsOption } from 'echarts'
import { addDays, fmtDay, fmtHour, fmtLondon, getSeries, gw, signedGw, useApi, type Meta, type SeriesResponse } from './api'
import { COLORS, Chart, axis } from './Chart'

const GATE_RE = /^([01]\d|2[0-3]):[0-5]\d$/
const HISTORY_CHOICES = [7, 14, 30] // mirrors core.HISTORY_CHOICES

export default function DayAhead({ meta }: { meta: Meta }) {
  const first = addDays(meta.start, -1) // Jan 2026 pilot: decision 1 Jan → delivery 2 Jan
  const [decision, setDecision] = useState(first)
  const [gateInput, setGateInput] = useState(meta.default_gate)
  const [gate, setGate] = useState(meta.default_gate)
  const [historyDays, setHistoryDays] = useState(30)
  const delivery = addDays(decision, 1)

  const { data, error, loading, retry } = useApi(
    (signal) => getSeries({ start: delivery, end: delivery, gate, history_days: historyDays }, signal),
    [delivery, gate, historyDays],
  )

  const rows = data?.rows ?? []
  const forecastMw = rows.flatMap((row) => (row.forecast == null ? [] : [row.forecast]))
  const totalMw = forecastMw.reduce((sum, mw) => sum + mw, 0)
  const run = rows.find((row) => row.publish)?.publish
  const hist = data?.history
  const histOk = !!hist && hist.stats.count > 0
  const hindsight = data?.stats

  const option = useMemo<EChartsOption>(() => {
    // Band = forecast − err_p90 … forecast − err_p10, floored at 0 (generation can't be negative).
    const band = (row: (typeof rows)[number]) => {
      if (!histOk || row.forecast == null) return null
      const lo = Math.max(0, row.forecast - hist!.stats.err_p90!)
      return { lo, hi: Math.max(lo, row.forecast - hist!.stats.err_p10!) }
    }
    return {
      legend: { data: ['Forecast at gate', 'Actual (hindsight)', ...(histOk ? ['P10–P90 range'] : [])] },
      tooltip: {
        trigger: 'axis',
        formatter: (points: any) => {
          const row = rows[points[0].dataIndex]
          const parts = [`<b>${fmtHour(row.time)}</b>`]
          if (row.forecast != null) parts.push(`Forecast ${gw(row.forecast, 2)} GW`)
          const range = band(row)
          if (range) parts.push(`Range ${gw(range.lo, 2)}–${gw(range.hi, 2)} GW`)
          if (row.actual != null) parts.push(`Actual ${gw(row.actual, 2)} GW`)
          return parts.join('<br/>')
        },
      },
      xAxis: axis({ type: 'category', boundaryGap: false, data: rows.map((row) => fmtHour(row.time)), splitLine: { show: false } }),
      yAxis: axis({ type: 'value' }),
      series: [
        ...(histOk
          ? [
              // stackStrategy 'all': default 'samesign' won't stack a width onto a base at/below 0
              { name: 'band-base', type: 'line', stack: 'band', stackStrategy: 'all', data: rows.map((row) => band(row)?.lo ?? null), symbol: 'none', lineStyle: { opacity: 0 }, silent: true },
              {
                name: 'P10–P90 range', type: 'line', stack: 'band', stackStrategy: 'all', symbol: 'none', silent: true,
                data: rows.map((row) => { const range = band(row); return range ? range.hi - range.lo : null }),
                lineStyle: { opacity: 0 }, areaStyle: { color: COLORS.band }, itemStyle: { color: 'rgba(15, 76, 92, 0.35)' },
              },
            ]
          : []),
        {
          name: 'Forecast at gate', type: 'line', data: rows.map((row) => row.forecast), symbol: 'none',
          lineStyle: { color: COLORS.accent, width: 2 }, itemStyle: { color: COLORS.accent },
        },
        {
          name: 'Actual (hindsight)', type: 'line', data: rows.map((row) => row.actual), symbol: 'none',
          lineStyle: { color: COLORS.ink, width: 1.25, type: 'dashed' }, itemStyle: { color: COLORS.ink },
        },
      ] as EChartsOption['series'],
    }
  }, [rows, histOk, hist])

  const bias = histOk ? hist!.stats.bias : null // no settled history → no verdict, neutral styling
  const reliability = useReliabilityCharts(data, run)
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Day-ahead brief</div>
          <h1>
            Deciding {fmtDay(decision)}
            <span className="sep">/</span>
            Delivering {fmtDay(delivery)}
          </h1>
          <p className="lede">
            For the day-ahead buyer: before the {gate} gate on {fmtDay(decision)}, decide how much power to buy for{' '}
            {fmtDay(delivery)}. Wind covers part of demand; whatever it doesn't must be bought, so this page shows how
            much wind to count on and how far to trust that number.
          </p>
        </div>
        <div className="controls">
          <label className="field">
            <span className="label">Decision day</span>
            <input type="date" min={addDays(meta.min, -1)} max={addDays(meta.max, -1)} value={decision}
              onChange={(event) => event.target.value && setDecision(event.target.value)} />
          </label>
          <label className="field">
            <span className="label">Gate (UK time)</span>
            <input type="time" step={60} value={gateInput}
              onChange={(event) => {
                setGateInput(event.target.value)
                if (GATE_RE.test(event.target.value)) setGate(event.target.value)
              }} />
          </label>
          <div className="field">
            <span className="label">History</span>
            <div className="segmented" role="group" aria-label="History window">
              {HISTORY_CHOICES.map((days) => (
                <button key={days} type="button" aria-pressed={historyDays === days} onClick={() => setHistoryDays(days)}>
                  {days} days
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {error && <p className="error">Could not load this day: {error} <button className="retry" onClick={retry}>Retry</button></p>}
      {!data && !error && <p className="status">Loading live data from Elexon…</p>}

      {data && (
        <>
          <div className={`callout${bias != null && bias > 0 ? '' : ' neutral'}`}>
            {forecastMw.length ? (
              <p>
                The last forecast before the {gate} gate expects{' '}
                <span className="num">{gw(totalMw, 0)} GWh</span> of wind for {fmtDay(delivery)}, between{' '}
                <span className="num">{gw(Math.min(...forecastMw))}</span> and <span className="num">{gw(Math.max(...forecastMw))} GW</span>.
              </p>
            ) : (
              <p>No forecast was published before the {gate} gate for {fmtDay(delivery)}.</p>
            )}
            <p className="sub">
              {histOk ? (
                <>
                  Across the {hist!.days} settled days before this decision, the same forecast ran{' '}
                  <span className={bias! > 0 ? 'over' : ''}>
                    {bias! > 0 ? 'high' : 'low'} by {gw(Math.abs(bias!), 2)} GW
                  </span>{' '}
                  on average. Buying on the raw number risks {bias! > 0 ? 'under' : 'over'}-procuring.
                </>
              ) : (
                <>No settled history is available before this decision.</>
              )}
            </p>
          </div>

          <div className="kpis">
            <Kpi label="Forecast run used" text value={run ? fmtLondon(run) : 'None before gate'} sub={`Latest publish ≤ ${gate} on ${fmtDay(decision)}`} />
            <Kpi label="Wind energy, D" value={gw(totalMw, 0)} unit="GWh" sub={`${forecastMw.length} hourly points`} />
            <Kpi label="Hourly range" value={forecastMw.length ? `${gw(Math.min(...forecastMw))}–${gw(Math.max(...forecastMw))}` : '—'} unit="GW" sub="Forecast min – max" />
            <Kpi label="Track record" value={histOk ? signedGw(bias) : '—'} unit={histOk ? 'GW bias' : ''}
              sub={histOk ? `MAE ${gw(hist!.stats.mae, 2)} GW · ${hist!.days} settled days` : 'No history'} over={histOk && bias! > 0} />
            <Kpi label="Hindsight, D" value={hindsight?.count ? gw(hindsight.mae, 2) : '—'} unit={hindsight?.count ? 'GW MAE' : ''}
              sub={hindsight?.count ? `Bias ${signedGw(hindsight.bias)} GW · known after delivery` : 'Actuals not yet known'} />
          </div>

          <section className="section">
            <div className="section-head">
              <h2>Wind generation, {fmtDay(delivery)} · MW, UK time</h2>
              <span className="status">{loading ? 'Updating…' : ''}</span>
            </div>
            <Chart option={option} height={360} />
            <p className="caption">
              {histOk
                ? `Band = P10–P90 forecast error over ${hist!.days} settled days before this decision (${fmtDay(hist!.start)} – ${fmtDay(hist!.end)}). No information from after the gate is used.`
                : 'No settled history is available, so no uncertainty band.'}{' '}
              Dashed actuals are shown for hindsight only; they were unknown at decision time.
            </p>
          </section>

          {histOk && (
            <>
              <div className="section-intro">
                <div className="eyebrow">How reliable is this forecast?</div>
                <p className="caption">
                  Measured on the {hist!.days} settled days before this decision ({fmtDay(hist!.start)} – {fmtDay(hist!.end)}),
                  using the forecast available at the {gate} gate each day. Error = forecast − actual; positive means
                  more wind was forecast than arrived.
                </p>
              </div>
              <div className="kpis">
                <Kpi label="MAE" value={gw(hist!.stats.mae, 2)} unit="GW" sub="Typical miss per hour" />
                <Kpi label="Bias" value={signedGw(bias)} unit="GW" sub={bias! > 0 ? 'Over-forecast' : 'Under-forecast'} over={bias! > 0} />
                <Kpi label="P90 abs error" value={gw(hist!.stats.p90, 2)} unit="GW" sub="Exceeded 1 hour in 10" />
                <Kpi label="RMSE" value={gw(hist!.stats.rmse, 2)} unit="GW" sub="Penalises large misses" />
                <Kpi label="nMAE" value={pct(hist!.stats.nmae)} unit="%" sub="MAE ÷ mean actual" />
                <Kpi label="Coverage" value={pct(hist!.stats.coverage)} unit="%" sub={`${hist!.stats.count} hours compared`} />
              </div>

              <section className="section">
                <h2>Error by day</h2>
                <p className="caption">Bars: that day's average error (amber = forecast too high). Line: that day's typical miss (MAE).</p>
                <Chart option={reliability.daily} height={280} />
              </section>
              <div className="grid-2">
                <section className="section">
                  <h2>Error by hour of day</h2>
                  <p className="caption">Where in the day the forecast misses most: hedge those hours first.</p>
                  <Chart option={reliability.hourly} height={260} />
                </section>
                <section className="section">
                  <h2>Error vs lead time</h2>
                  <p className="caption">Forecasts made closer to delivery miss less. Shaded: the lead times behind this decision.</p>
                  <Chart option={reliability.lead} height={260} />
                </section>
              </div>
              <footer className="note">
                Hourly comparison: forecast at HH:00 vs the FUELHH half-hour starting HH:00. Forecast rows published at or
                after their target time are excluded. A persistent positive bias may partly reflect curtailment (actuals are
                metered output after balancing actions); this is a hypothesis to confirm.
              </footer>
            </>
          )}
        </>
      )}
    </>
  )
}

const gwFmt = (value: unknown) => (typeof value === 'number' ? `${gw(value, 2)} GW` : '—')
const pct = (ratio: number | null | undefined) => (ratio == null ? '—' : (ratio * 100).toFixed(1))
const gwAxis = () => axis({ type: 'value', axisLabel: { ...axis().axisLabel, formatter: (mw: number) => gw(mw) } })
const biasColor = (bias: number) => (bias > 0 ? COLORS.amber : COLORS.accent)
const HOUR_MS = 3.6e6

/** Accuracy charts for the 30 settled days behind the decision. */
function useReliabilityCharts(data: SeriesResponse | undefined, run: string | null | undefined) {
  return useMemo(() => {
    const history = data?.history
    const days = history?.by_day ?? []
    const hours = history?.by_hour ?? []
    const leads = history?.by_horizon ?? []

    // Lead times behind this decision: from the run used to the first/last delivery hour, snapped to the 3 h grid.
    const deliveryTimes = (data?.rows ?? []).map((row) => Date.parse(row.time))
    const span = run && deliveryTimes.length
      ? [(Math.min(...deliveryTimes) - Date.parse(run)) / HOUR_MS, (Math.max(...deliveryTimes) - Date.parse(run)) / HOUR_MS]
      : null
    const snap = (hoursAhead: number, round: (value: number) => number) => `${Math.min(48, round(hoursAhead / 3) * 3)}h`

    const daily: EChartsOption = {
      legend: { data: ['Bias', 'MAE'] },
      xAxis: axis({
        type: 'category', data: days.map((entry) => entry.day),
        axisLabel: { ...axis().axisLabel, formatter: (day: string) => fmtDay(day).split(' ').slice(1).join(' ') },
        splitLine: { show: false },
      }),
      yAxis: gwAxis(),
      series: [
        { name: 'Bias', type: 'bar', data: days.map((entry) => ({ value: entry.bias, itemStyle: { color: biasColor(entry.bias) } })), itemStyle: { color: COLORS.amber }, barCategoryGap: '25%', tooltip: { valueFormatter: gwFmt } },
        { name: 'MAE', type: 'line', data: days.map((entry) => entry.mae), symbolSize: 4, lineStyle: { color: COLORS.ink, width: 1.25 }, itemStyle: { color: COLORS.ink }, tooltip: { valueFormatter: gwFmt } },
      ],
    }
    const hourly: EChartsOption = {
      legend: { data: ['MAE', 'Bias'] },
      xAxis: axis({ type: 'category', data: hours.map((entry) => String(entry.hour).padStart(2, '0')), name: 'Hour (UK)', nameLocation: 'middle', nameGap: 28, splitLine: { show: false } }),
      yAxis: gwAxis(),
      series: [
        { name: 'MAE', type: 'bar', data: hours.map((entry) => entry.mae), itemStyle: { color: 'rgba(15, 76, 92, 0.75)' }, barCategoryGap: '30%', tooltip: { valueFormatter: gwFmt } },
        { name: 'Bias', type: 'line', data: hours.map((entry) => entry.bias), symbolSize: 4, lineStyle: { color: COLORS.amber, width: 1.5 }, itemStyle: { color: COLORS.amber }, tooltip: { valueFormatter: gwFmt } },
      ],
    }
    const lead: EChartsOption = {
      legend: { data: ['MAE', 'Bias'] },
      xAxis: axis({ type: 'category', data: leads.map((entry) => `${entry.hours_ahead}h`), name: 'Hours ahead', nameLocation: 'middle', nameGap: 28, splitLine: { show: false } }),
      yAxis: gwAxis(),
      series: [
        {
          name: 'MAE', type: 'line', data: leads.map((entry) => entry.mae), symbolSize: 5, lineStyle: { color: COLORS.accent, width: 2 }, itemStyle: { color: COLORS.accent }, tooltip: { valueFormatter: gwFmt },
          markArea: span ? { silent: true, itemStyle: { color: COLORS.band }, data: [[{ xAxis: snap(span[0], Math.floor) }, { xAxis: snap(span[1], Math.ceil) }]] } : undefined,
        },
        { name: 'Bias', type: 'line', data: leads.map((entry) => entry.bias), symbolSize: 5, lineStyle: { color: COLORS.amber, width: 1.5 }, itemStyle: { color: COLORS.amber }, tooltip: { valueFormatter: gwFmt } },
      ],
    }
    return { daily, hourly, lead }
  }, [data, run])
}

function Kpi({ label, value, unit, sub, text, over }: {
  label: string; value: string; unit?: string; sub?: string; text?: boolean; over?: boolean
}) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value${text ? ' text' : ''}${over ? ' over' : ''}`}>
        {value}
        {unit && <small>{unit}</small>}
      </div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}
