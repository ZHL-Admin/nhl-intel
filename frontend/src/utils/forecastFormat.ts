// Number formatting + small derivations for the Offseason Forecast page.
// Per DESIGN/UX 3.6: true minus character (U+2212), signed, fixed precision, no silent dashes.

export const MINUS = '−'

/** Signed number with `d` decimals using the true minus glyph. */
export function fmtSigned(v: number | null | undefined, d: number): string {
  if (v == null || Number.isNaN(v)) return '—'
  const r = v.toFixed(d)
  if (r.startsWith('-')) return MINUS + r.slice(1)
  return '+' + r
}

/** Ratings & changes: signed, two decimals. */
export const fmtRating = (v: number | null | undefined) => fmtSigned(v, 2)
/** WAR: signed, one decimal. */
export const fmtWar = (v: number | null | undefined) => fmtSigned(v, 1)
/** Band endpoints share the underlying metric's precision; rendered "{lo} to {hi}". */
export const fmtBand = (lo: number, hi: number, d: number) => `${fmtSigned(lo, d)} to ${fmtSigned(hi, d)}`
export const fmtRank = (n: number | null | undefined) => (n == null ? '—' : `#${n}`)

export type Tier = 'Contender' | 'Middle' | 'Rebuild'
/** League tier from projected rank. Cutoffs: 1–8 Contender, 9–22 Middle, 23–32 Rebuild. */
export function tierForRank(rank: number | null | undefined): Tier {
  if (rank == null) return 'Middle'
  if (rank <= 8) return 'Contender'
  if (rank <= 22) return 'Middle'
  return 'Rebuild'
}

/** Quiet offseason: no logged moves, or a sub-threshold net change. Mirrors backend `negligible`. */
export function isQuiet(opts: { n_moves: number; delta: number; negligible?: boolean }): boolean {
  if (opts.negligible != null) return opts.negligible
  return opts.n_moves === 0 || Math.abs(opts.delta) < 0.03
}

/** The "..made them worse / better / no net effect" phrase under the change hero cell. */
export function changeWords(delta: number): string {
  if (Math.abs(delta) < 0.03) return 'no net effect'
  return delta > 0 ? 'the moves made them better' : 'the moves made them worse'
}

/** Season after a "YYYY-YY->YYYY-YY" transition string, e.g. "2026-27". */
export function nextSeasonOf(transition: string): string {
  const parts = transition.split('->')
  return parts.length === 2 ? parts[1] : transition
}
