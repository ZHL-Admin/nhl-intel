/**
 * Shared number formatting for the trade tools (UX 3.6: signed deltas with a TRUE minus, colored
 * by the caller). Dollar figures here are PROJECTED-CAP present-value dollars — they grow with the
 * rising cap over a long deal and must NEVER be read as today's dollars. Always pair a displayed
 * dollar figure with CAP_DOLLAR_NOTE (full) or CAP_DOLLAR_TAG (compact) so the basis is explicit.
 */

const MINUS = '−' // true minus, not hyphen

/** Ordinal suffix done right: 1->1st, 2->2nd, 3->3rd, 11/12/13->th, 21->21st, 92->92nd. Use this
 * everywhere a percentile or rank renders so "92th" never ships. */
export function ordinal(n: number): string {
  const v = Math.round(n)
  const d = v % 100
  if (d >= 11 && d <= 13) return `${v}th`
  return `${v}${({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[v % 10] ?? 'th'}`
}

/** Reference-cap basis label for every displayed dollar value/surplus figure. */
export const CAP_DOLLAR_NOTE =
  'Dollar figures are present value across each deal’s remaining term in projected-cap dollars ' +
  '(the cap rises each season — $95.5M in 2025-26, $104.0M in 2026-27, and onward); they are not ' +
  'today’s 2025-26 dollars. Cap-share is the era-neutral efficiency lens.'
/** Compact tag to sit next to a dollar figure. */
export const CAP_DOLLAR_TAG = 'proj-cap $, PV'

function sign(v: number, body: string, signed: boolean): string {
  if (!signed) return body
  return v < 0 ? MINUS + body : '+' + body
}

/** Dollars as $X.YM (millions). signed -> leading +/true-minus. */
export function fmtDollarsM(v: number | null | undefined, signed = false): string {
  if (v == null) return '—'
  const m = Math.abs(v) / 1e6
  const body = `$${m.toFixed(1)}M`
  return sign(v, body, signed)
}

/** Dollars at the right magnitude: $X.YM, or $XXXk under a million. */
export function fmtDollars(v: number | null | undefined, signed = false): string {
  if (v == null) return '—'
  const a = Math.abs(v)
  const body = a >= 1e6 ? `$${(a / 1e6).toFixed(1)}M` : `$${Math.round(a / 1e3)}k`
  return sign(v, body, signed)
}

/** WAR / talent, one decimal, optionally signed with a true minus. */
export function fmtWar(v: number | null | undefined, signed = true): string {
  if (v == null) return '—'
  return sign(v, Math.abs(v).toFixed(1), signed)
}

/** A [low, high] band as "lo – hi" in WAR. */
export function fmtWarBand(lo?: number | null, hi?: number | null): string {
  if (lo == null || hi == null) return ''
  return `${fmtWar(lo)} … ${fmtWar(hi)}`
}

/** Cap share rendered as a percent OF THE CAP (the era-neutral efficiency lens). 0.283 -> +28.3%. */
export function fmtCapShare(v: number | null | undefined, signed = true): string {
  if (v == null) return '—'
  return sign(v, `${(Math.abs(v) * 100).toFixed(1)}%`, signed) + ' of cap'
}

/** Sign class for coloring a delta (positive/negative/neutral data tokens). */
export function deltaClass(v: number | null | undefined): 'pos' | 'neg' | 'zero' {
  if (v == null || Math.abs(v) < 1e-9) return 'zero'
  return v > 0 ? 'pos' : 'neg'
}

/* =============================================================================
   The Sheet Design System — canonical number/date formats (§5.4). New and touched
   surfaces call fmt.* instead of inline toFixed (adopted through DS3). A dash ("—")
   is the single empty marker. Signed formats lead with + or a TRUE minus (−).
   ============================================================================= */
const DASH = '—'
const signed1 = (v: number) => (v < 0 ? MINUS : '+') + Math.abs(v).toFixed(1)

export const fmt = {
  /** WAR / GAR — signed, 1dp. +2.4 */
  war: (v?: number | null) => (v == null ? DASH : signed1(v)),
  /** Ratings — signed, 2dp (per game). +0.68 */
  rating: (v?: number | null) => (v == null ? DASH : (v < 0 ? MINUS : '+') + Math.abs(v).toFixed(2)),
  /** Percentages / shares — 1dp + %. Input is a fraction (0.523 → "52.3%"). */
  pct: (v?: number | null) => (v == null ? DASH : `${(v * 100).toFixed(1)}%`),
  /** Probabilities — whole %, capped so it never reads 0% or 100%. Input is a fraction. */
  prob: (v?: number | null) => {
    if (v == null) return DASH
    const p = Math.round(v * 100)
    if (p >= 100) return '>99%'
    if (p <= 0) return '<1%'
    return `${p}%`
  },
  /** Percentiles — ordinal. 91st */
  ordinal: (v?: number | null) => (v == null ? DASH : ordinal(v)),
  /** xG (single shot / game) — 2dp. 0.34 */
  xg: (v?: number | null) => (v == null ? DASH : v.toFixed(2)),
  /** Time on ice — m:ss from seconds. 18:42 */
  toi: (seconds?: number | null) => {
    if (seconds == null) return DASH
    const s = Math.max(0, Math.round(seconds))
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  },
  /** Luck / deserved deltas — signed, 1dp. +4.2 */
  delta: (v?: number | null) => (v == null ? DASH : signed1(v)),
  /** Dates — "Mon D" (no year, in-season). Accepts an ISO string or a Date. */
  date: (d?: string | Date | null) => {
    if (!d) return DASH
    const dt = typeof d === 'string' ? new Date(`${d.slice(0, 10)}T00:00:00`) : d
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  },
  /** Seasons — YYYY-YY. Accepts a start year (2025) or a season-ish string. */
  season: (startYear?: number | string | null) => {
    if (startYear == null) return DASH
    const y = typeof startYear === 'string' ? parseInt(startYear.slice(0, 4), 10) : startYear
    if (!Number.isFinite(y)) return DASH
    return `${y}-${String((y + 1) % 100).padStart(2, '0')}`
  },
}
