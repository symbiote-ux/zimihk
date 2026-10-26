import { useEffect, useState } from 'react'

export type Row = { t: string; actual: number | null; forecast: number | null; publish: string | null }
export type Stats = {
  n: number
  coverage: number
  mae: number | null
  rmse: number | null
  bias: number | null
  nmae: number | null
  p50: number | null
  p90: number | null
  p99: number | null
  err_p10: number | null
  err_p90: number | null
}
export type History = { start: string; end: string; days: number; stats: Stats } | null
export type SeriesResponse = {
  rows: Row[]
  stats: Stats
  by_hour: { hour: number; n: number; mae: number; bias: number }[]
  histogram: { lo: number; count: number }[]
  history: History
}
export type HorizonPoint = { h: number; n: number; mae: number | null; bias: number | null; p90: number | null }
export type Meta = { start: string; end: string; default_gate: string }

async function get<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined) qs.set(k, String(v))
  const res = await fetch(`/api/${path}?${qs}`)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

export const getMeta = () => get<Meta>('meta')
export const getSeries = (p: { start: string; end: string; gate?: string; horizon?: number }) =>
  get<SeriesResponse>('series', p)
export const getHorizons = (start: string, end: string) => get<HorizonPoint[]>('horizons', { start, end })

/** Runs an async loader whenever deps change; ignores responses that arrive after a newer request. */
export function useApi<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true })
  useEffect(() => {
    let live = true
    setState((s) => ({ ...s, loading: true }))
    load().then(
      (data) => live && setState({ data, loading: false }),
      (e) => live && setState({ error: e instanceof Error ? e.message : String(e), loading: false }),
    )
    return () => {
      live = false
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  return state
}

const london = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', ...opts })
const dtFmt = london({ weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const hourFmt = london({ hour: '2-digit', minute: '2-digit' })
const dayFmt = london({ weekday: 'short', day: 'numeric', month: 'short' })

export const fmtLondon = (iso: string) => dtFmt.format(new Date(iso))
export const fmtHour = (iso: string) => hourFmt.format(new Date(iso))
/** 'YYYY-MM-DD' (a calendar date) → 'Thu 15 Jan' */
export const fmtDay = (d: string) => dayFmt.format(new Date(`${d}T12:00:00Z`))
export const addDays = (d: string, n: number) => {
  const x = new Date(`${d}T00:00:00Z`)
  x.setUTCDate(x.getUTCDate() + n)
  return x.toISOString().slice(0, 10)
}
export const gw = (mw: number | null | undefined, digits = 1) => (mw == null ? '—' : (mw / 1000).toFixed(digits))
export const signedGw = (mw: number | null | undefined) => (mw == null ? '—' : `${mw > 0 ? '+' : ''}${gw(mw, 2)}`)
