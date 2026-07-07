/**
 * Tilt (Handoff 7 §5) — the page's signature motif at three scales. A track centered on an even line
 * that fills toward the winner by the realized margin, with the uncertainty band on the same track so a
 * band crossing center reads as "even". Used full (leaf/marquee), compact (best/worst, deal list), and
 * sparkline (leaderboard rows, partner list). Math is identical at every size.
 *
 * Signed margin convention: negative = left side won, positive = right side won.
 */
import { useEffect, useState } from 'react'
import './trades.css'

const WAR_DOMAIN = 12
const xPct = (v: number) => 50 + (Math.max(-WAR_DOMAIN, Math.min(WAR_DOMAIN, v)) / WAR_DOMAIN) * 50

export default function Tilt({ signed, bandHw, color, even, edge = false, incomplete, size = 'full', animate = true }: {
  signed: number; bandHw: number; color: string
  even: boolean; edge?: boolean; incomplete: boolean; size?: 'full' | 'compact' | 'sparkline'; animate?: boolean
}) {
  const [shown, setShown] = useState(!animate)
  useEffect(() => { if (animate) { const id = requestAnimationFrame(() => setShown(true)); return () => cancelAnimationFrame(id) } }, [animate])

  const lo = xPct(signed - bandHw)
  const hi = xPct(signed + bandHw)
  const tick = xPct(signed)
  // neutral = no directional fill (even or still-maturing). An EDGE keeps the winner's color but faint,
  // and ALWAYS keeps the band drawn so the band crossing centre stays visible ("tilts this way, but the
  // band is wide").
  const neutral = even || incomplete
  const tickColor = neutral ? 'var(--color-text-muted)'
    : edge ? `color-mix(in srgb, ${color} 55%, var(--color-bg-elevated))` : color
  // §S6: the winning band fills in the winner's team color at 60% (decisive); an edge stays faint.
  const bandFill = neutral ? 'transparent'
    : `color-mix(in srgb, ${color} ${edge ? 20 : 60}%, transparent)`
  const bandLeft = shown ? Math.min(lo, hi) : 50
  const bandWidth = shown ? Math.abs(hi - lo) : 0

  return (
    <div className={`tilt tilt--${size} ${incomplete ? 'tilt--incomplete' : ''} ${edge ? 'tilt--edge' : ''}`}
      role="img" aria-label={even ? 'even'
        : `${edge ? 'slight edge' : 'tilts'} ${signed >= 0 ? 'right' : 'left'} by ${Math.abs(signed).toFixed(1)} WAR`}>
      <span className="tilt__center" />
      <span className="tilt__band" style={{
        left: `${bandLeft}%`, width: `${bandWidth}%`,
        background: bandFill,
        border: neutral ? '0.5px dashed var(--color-border-strong)' : 'none',
      }} />
      <span className="tilt__tick" style={{
        left: `${shown ? tick : 50}%`,
        background: tickColor,
      }} />
    </div>
  )
}
