// Formatting for the Power Ratings tables + Home rail.

/** Signed 2-dp: +0.86 / -0.05. */
export function fmtSigned(n: number | null | undefined): string {
  if (n == null) return '—'
  return (n >= 0 ? '+' : '') + n.toFixed(2)
}

/** Luck in points, signed 1-dp: +13.8 / -6.7. */
export function fmtLuck(n: number | null | undefined): string {
  if (n == null) return '—'
  return (n >= 0 ? '+' : '') + n.toFixed(1)
}

/** ISO date → "Jun 17, 2026" (the rt-stamp CSS uppercases it). */
export function fmtStamp(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[(m ?? 1) - 1]} ${d}, ${y}`
}

/** Dollars → compact "$4.2M" / "$850K" / "—". */
export function fmtDollars(n: number | null | undefined): string {
  if (n == null) return '—'
  const sign = n < 0 ? '-' : ''
  const a = Math.abs(n)
  if (a >= 1_000_000) return `${sign}$${(a / 1_000_000).toFixed(1)}M`
  if (a >= 1_000) return `${sign}$${Math.round(a / 1_000)}K`
  return `${sign}$${a}`
}
