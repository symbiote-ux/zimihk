import { useEffect, useState } from 'react'

export type Row = { time: string; actual: number | null; forecast: number | null; publish: string | null }
export type Stats = {
  count: number
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
type Breakdown = { count: number; mae: number; bias: number }
export type HorizonPoint = { hours_ahead: number; count: number; mae: number | null; bias: number | null; p90: number | null }
/** Accuracy over the settled days before the decision (no look-ahead). */
export type History = {
  start: string
  end: string
  days: number
  stats: Stats
  by_day: (Breakdown & { day: string })[]
  by_hour: (Breakdown & { hour: number })[]
  by_horizon: HorizonPoint[]
} | null
export type SeriesResponse = {
  rows: Row[]
  stats: Stats
  history: History
}
/** start/end = default pilot view (Jan 2026); min/max = selectable delivery days. */
export type Meta = { start: string; end: string; min: string; max: string; default_gate: string }

/** FastAPI errors are {detail: string} or, for validation, {detail: [{msg}]}. */
export async function errorMessage(res: Response): Promise<string> {
  try {
    const { detail } = await res.json()
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((issue) => issue.msg).join('; ')
  } catch {
    /* not JSON: fall through */
  }
  return `Request failed (${res.status})`
}

async function get<T>(path: string, params: Record<string, string | number | undefined>, signal?: AbortSignal): Promise<T> {
  const query = new URLSearchParams()
  for (const [name, value] of Object.entries(params)) if (value !== undefined) query.set(name, String(value))
  const res = await fetch(`/api/${path}?${query}`, { signal })
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json()
}

export const getMeta = (signal?: AbortSignal) => get<Meta>('meta', {}, signal)
export const getSeries = (params: { start: string; end: string; gate?: string }, signal?: AbortSignal) =>
  get<SeriesResponse>('series', params, signal)

const DEBOUNCE_MS = 250 // each request costs a live Elexon pull: wait for inputs to settle

/**
 * Runs an async loader when deps change: waits for inputs to settle, cancels the request it replaces,
 * and never lets a stale response overwrite a newer one. `retry` re-runs the current request.
 */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setState((prev) => ({ ...prev, error: undefined, loading: true }))
    const timer = setTimeout(() => {
      load(controller.signal).then(
        (data) => !controller.signal.aborted && setState({ data, loading: false }),
        (err) => {
          if (controller.signal.aborted) return
          setState((prev) => ({ ...prev, error: err instanceof Error ? err.message : String(err), loading: false }))
        },
      )
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [...deps, attempt]) // eslint-disable-line react-hooks/exhaustive-deps
  return { ...state, retry: () => setAttempt((count) => count + 1) }
}

const london = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', ...opts })
const dateTimeFmt = london({ weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const hourFmt = london({ hour: '2-digit', minute: '2-digit' })
const dayFmt = london({ weekday: 'short', day: 'numeric', month: 'short' })

export const fmtLondon = (iso: string) => dateTimeFmt.format(new Date(iso))
export const fmtHour = (iso: string) => hourFmt.format(new Date(iso))
/** 'YYYY-MM-DD' (a calendar date) → 'Thu 15 Jan' */
export const fmtDay = (day: string) => dayFmt.format(new Date(`${day}T12:00:00Z`))
export const addDays = (day: string, days: number) => {
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}
export const gw = (mw: number | null | undefined, digits = 1) => (mw == null ? '—' : (mw / 1000).toFixed(digits))
export const signedGw = (mw: number | null | undefined) => (mw == null ? '—' : `${mw > 0 ? '+' : ''}${gw(mw, 2)}`)
