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
/** start/end = default pilot view (Jan 2026); min/max = selectable delivery days. */
export type Meta = { start: string; end: string; min: string; max: string; max_days: number; default_gate: string }

/** FastAPI errors are {detail: string} or, for validation, {detail: [{msg}]}. */
export async function errorMessage(res: Response): Promise<string> {
  try {
    const { detail } = await res.json()
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ')
  } catch {
    /* not JSON: fall through */
  }
  return `Request failed (${res.status})`
}

async function get<T>(path: string, params: Record<string, string | number | undefined>, signal?: AbortSignal): Promise<T> {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined) qs.set(k, String(v))
  const res = await fetch(`/api/${path}?${qs}`, { signal })
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json()
}

export const getMeta = (signal?: AbortSignal) => get<Meta>('meta', {}, signal)
export const getSeries = (p: { start: string; end: string; gate?: string; horizon?: number }, signal?: AbortSignal) =>
  get<SeriesResponse>('series', p, signal)
export const getHorizons = (start: string, end: string, signal?: AbortSignal) =>
  get<HorizonPoint[]>('horizons', { start, end }, signal)

const DEBOUNCE_MS = 250 // each request costs a live Elexon pull: wait for inputs to settle

/**
 * Runs an async loader when deps change: waits for inputs to settle, cancels the request it replaces,
 * and never lets a stale response overwrite a newer one. `retry` re-runs the current request.
 */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const ctrl = new AbortController()
    setState((s) => ({ ...s, error: undefined, loading: true }))
    const timer = setTimeout(() => {
      load(ctrl.signal).then(
        (data) => !ctrl.signal.aborted && setState({ data, loading: false }),
        (e) => {
          if (ctrl.signal.aborted) return
          setState((s) => ({ ...s, error: e instanceof Error ? e.message : String(e), loading: false }))
        },
      )
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [...deps, attempt]) // eslint-disable-line react-hooks/exhaustive-deps
  return { ...state, retry: () => setAttempt((n) => n + 1) }
}

export const daysBetween = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000)

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
