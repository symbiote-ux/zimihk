// Runs with TZ=Pacific/Kiritimati (UTC+14): UK-time formatting must not depend on the viewer's timezone.
import { describe, expect, it } from 'vitest'
import { addDays, daysBetween, errorMessage, fmtDay, fmtHour, fmtLondon, gw, signedGw } from './api'

describe('date helpers', () => {
  it('adds days across month and year boundaries', () => {
    expect(addDays('2026-01-31', 1)).toBe('2026-02-01')
    expect(addDays('2026-01-01', -1)).toBe('2025-12-31')
  })

  it('counts days between calendar dates', () => {
    expect(daysBetween('2026-01-02', '2026-02-01')).toBe(30)
  })
})

describe('UK-time formatting, independent of viewer timezone', () => {
  it('formats a calendar date as the same UK day', () => {
    expect(fmtDay('2026-01-15')).toBe('Thu 15 Jan')
  })

  it('formats a winter instant in GMT', () => {
    expect(fmtLondon('2026-01-14T07:30:00+00:00')).toBe('Wed 14 Jan, 07:30')
  })

  it('formats a summer instant in BST (UTC+1)', () => {
    expect(fmtHour('2026-07-01T23:00:00+00:00')).toBe('00:00')
  })
})

describe('number formatting', () => {
  it('shows MW as GW with a placeholder for missing values', () => {
    expect(gw(1772)).toBe('1.8')
    expect(gw(null)).toBe('—')
  })

  it('signs bias explicitly', () => {
    expect(signedGw(1746)).toBe('+1.75')
    expect(signedGw(-430)).toBe('-0.43')
  })
})

describe('errorMessage', () => {
  const res = (body: string, status: number) => new Response(body, { status })

  it('reads a FastAPI string detail', async () => {
    expect(await errorMessage(res('{"detail":"Elexon BMRS is unavailable"}', 502))).toBe('Elexon BMRS is unavailable')
  })

  it('joins FastAPI validation errors', async () => {
    expect(await errorMessage(res('{"detail":[{"msg":"bad gate"},{"msg":"bad date"}]}', 422))).toBe('bad gate; bad date')
  })

  it('falls back to the status for non-JSON bodies', async () => {
    expect(await errorMessage(res('<html>Bad gateway</html>', 504))).toBe('Request failed (504)')
  })
})
