/**
 * A labelled list of percentile bars: label, a 0-100 percentile fill, and the raw value
 * (Phase 3.2). Generic so Phase 4 player cards reuse it. For `inverse` metrics (where a
 * higher raw value is worse, e.g. chances allowed) the bar is coloured as a negative.
 */
import './PercentileBarList.css'

export interface PercentileBarItem {
  key: string
  label: string
  percentile?: number | null // 0..1
  value?: number | null
  inverse?: boolean
  formatValue?: (v: number) => string
}

interface PercentileBarListProps {
  items: PercentileBarItem[]
}

// §6 R7: colour by the 7-stop diverging ramp keyed by "goodness" (good→div-1 blue, bad→div-7 red).
function divColor(good: number): string {
  const idx = Math.min(6, Math.max(0, Math.round((1 - good) * 6)))
  return `var(--color-div-${idx + 1})`
}

export default function PercentileBarList({ items }: PercentileBarListProps) {
  return (
    <div className="pct-bar-list">
      {items.map((it) => {
        const p = it.percentile ?? null
        const valStr =
          it.value == null ? '—' : it.formatValue ? it.formatValue(it.value) : it.value.toFixed(3)
        // Bars grow center-out from the 50th percentile: right/blue = above average, left/red = below.
        const good = p == null ? null : (it.inverse ? 1 - p : p)
        const half = good == null ? 0 : Math.abs(good - 0.5) * 100
        const left = good == null ? 50 : good >= 0.5 ? 50 : 50 - half
        return (
          <div className="pct-bar-row" key={it.key}>
            <span className="pct-bar-label" title={it.label}>{it.label}</span>
            <span className="pct-bar-track">
              {good != null && (
                <span className="pct-bar-fill" style={{ left: `${left}%`, width: `${half}%`, background: divColor(good) }} />
              )}
            </span>
            <span className="pct-bar-pctile">{p == null ? '—' : `${Math.round(p * 100)}%`}</span>
            <span className="pct-bar-value">{valStr}</span>
          </div>
        )
      })}
    </div>
  )
}
