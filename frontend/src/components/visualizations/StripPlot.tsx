/**
 * StripPlot (Phase 4.3): a 1-D distribution of values as jittered dots on a horizontal axis,
 * with a mean line and optional threshold markers. Used for a player's game-score spread;
 * reusable for any per-event distribution.
 *
 * FIGURE KIT (RINK THEORY rebuild §4.3/§5.3) — RESERVED, NO LIVE IMPORTER.
 * Carried over unmodified from the removed dashboard surface (its old home,
 * PlayerProfile, is gone). Kept as a candidate note figure for future MDX notes;
 * nothing in the site currently imports it. Do not delete during teardown.
 */
import './StripPlot.css'

interface StripPlotProps {
  values: number[]
  mean?: number
  /** vertical reference markers, e.g. good-game / no-show thresholds */
  markers?: { value: number; label: string }[]
  height?: number
  color?: string
}

const W = 600
const PAD = 28

export default function StripPlot({ values, mean, markers = [], height = 90, color = 'var(--color-ice-600)' }: StripPlotProps) {
  if (!values.length) return <div className="strip-plot__empty">No games</div>
  const lo = Math.min(...values, ...(markers.map((m) => m.value)))
  const hi = Math.max(...values, ...(markers.map((m) => m.value)))
  const span = hi - lo || 1
  const x = (v: number) => PAD + ((v - lo) / span) * (W - 2 * PAD)
  // deterministic vertical jitter so dots don't fully overlap
  const jitter = (i: number) => (height - 34) * (0.5 + 0.42 * Math.sin(i * 2.399)) + 8

  return (
    <div className="strip-plot">
      <svg viewBox={`0 0 ${W} ${height}`} className="strip-plot__svg" preserveAspectRatio="none">
        <line x1={PAD} y1={height - 16} x2={W - PAD} y2={height - 16} className="strip-plot__axis" />
        {markers.map((m) => (
          <g key={m.label}>
            <line x1={x(m.value)} y1={6} x2={x(m.value)} y2={height - 16} className="strip-plot__marker" />
            <text x={x(m.value)} y={height - 4} textAnchor="middle" className="strip-plot__marker-label">{m.label}</text>
          </g>
        ))}
        {values.map((v, i) => (
          <circle key={i} cx={x(v)} cy={jitter(i)} r={2.5} fill={color} fillOpacity={0.55} />
        ))}
        {mean != null && (
          <line x1={x(mean)} y1={2} x2={x(mean)} y2={height - 16} className="strip-plot__mean" />
        )}
      </svg>
    </div>
  )
}
