/**
 * Tilt (Handoff 7 §5) — the page's signature motif at three scales. A track centered on an even line
 * that fills toward the winner by the realized margin, with the uncertainty band on the same track so a
 * band crossing center reads as "too close to call". Used full (leaf/marquee), compact (best/worst,
 * deal list), and sparkline (leaderboard rows, partner list). Math is identical at every size.
 *
 * Signed margin convention: negative = left side won, positive = right side won.
 */
import { useEffect, useState } from 'react'
import './trades.css'

const WAR_DOMAIN = 12
const xPct = (v: number) => 50 + (Math.max(-WAR_DOMAIN, Math.min(WAR_DOMAIN, v)) / WAR_DOMAIN) * 50

export default function Tilt({ signed, bandHw, color, tooClose, incomplete, size = 'full', animate = true }: {
  signed: number; bandHw: number; color: string
  tooClose: boolean; incomplete: boolean; size?: 'full' | 'compact' | 'sparkline'; animate?: boolean
}) {
  const [shown, setShown] = useState(!animate)
  useEffect(() => { if (animate) { const id = requestAnimationFrame(() => setShown(true)); return () => cancelAnimationFrame(id) } }, [animate])

  const lo = xPct(signed - bandHw)
  const hi = xPct(signed + bandHw)
  const tick = xPct(signed)
  const neutral = tooClose || incomplete
  const bandLeft = shown ? Math.min(lo, hi) : 50
  const bandWidth = shown ? Math.abs(hi - lo) : 0

  return (
    <div className={`tilt tilt--${size} ${incomplete ? 'tilt--incomplete' : ''}`}
      role="img" aria-label={tooClose ? 'too close to call' : `tilts ${signed >= 0 ? 'right' : 'left'} by ${Math.abs(signed).toFixed(1)} WAR`}>
      <span className="tilt__center" />
      <span className="tilt__band" style={{
        left: `${bandLeft}%`, width: `${bandWidth}%`,
        background: neutral ? 'transparent' : `color-mix(in srgb, ${color} 22%, transparent)`,
        border: neutral ? '0.5px dashed var(--color-border-strong)' : 'none',
      }} />
      <span className="tilt__tick" style={{
        left: `${shown ? tick : 50}%`,
        background: neutral ? 'var(--color-text-muted)' : color,
      }} />
    </div>
  )
}
