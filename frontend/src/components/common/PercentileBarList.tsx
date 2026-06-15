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

function tone(pctile: number, inverse?: boolean): string {
  // for normal metrics high percentile = good; inverse flips it
  const good = inverse ? 1 - pctile : pctile
  if (good >= 0.66) return 'pct-bar--good'
  if (good <= 0.33) return 'pct-bar--bad'
  return 'pct-bar--mid'
}

export default function PercentileBarList({ items }: PercentileBarListProps) {
  return (
    <div className="pct-bar-list">
      {items.map((it) => {
        const p = it.percentile ?? null
        const fill = p == null ? 0 : Math.round(p * 100)
        const valStr =
          it.value == null ? '—' : it.formatValue ? it.formatValue(it.value) : it.value.toFixed(3)
        return (
          <div className="pct-bar-row" key={it.key}>
            <span className="pct-bar-label" title={it.label}>{it.label}</span>
            <span className="pct-bar-track">
              {p != null && (
                <span className={`pct-bar-fill ${tone(p, it.inverse)}`} style={{ width: `${fill}%` }} />
              )}
            </span>
            <span className="pct-bar-pctile">{p == null ? '—' : `${fill}%`}</span>
            <span className="pct-bar-value">{valStr}</span>
          </div>
        )
      })}
    </div>
  )
}
