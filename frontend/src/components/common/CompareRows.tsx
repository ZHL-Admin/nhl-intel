/**
 * CompareRows (Blueprint P4) — the one grammar for any A-vs-B. Center-out diverging rows: label
 * centered above, values at the outer edges (tabular), bars grow from the midline. Side identity is a
 * 100%-saturation team-colour dot at each bar end; the bar FILL is neutral ice (winner) / ice-light
 * (other) for good/bad metrics, or the team colours when the metric is purely descriptive. Never two
 * stacked full-width bars.
 */
import './CompareRows.css'

export interface CompareRow {
  label: string
  aValue: number
  bValue: number
  aDisplay?: string
  bDisplay?: string
  /** For valence colouring: is a higher value better? (default true). Ignored when descriptive. */
  higherIsBetter?: boolean
  /** Descriptive metric (no good/bad) → colour bars by team instead of valence. */
  descriptive?: boolean
}

interface CompareRowsProps {
  rows: CompareRow[]
  aColor?: string
  bColor?: string
}

export default function CompareRows({ rows, aColor = 'var(--color-data-1)', bColor = 'var(--color-data-2)' }: CompareRowsProps) {
  return (
    <div className="cmp-rows">
      {rows.map((r) => {
        // V2: shared per-metric scale; bars grow center-out, filled directly in each team's colour
        // (2 vs 0 → full-left vs nothing). No neutral fill, no end dots.
        const max = Math.max(Math.abs(r.aValue), Math.abs(r.bValue), 1e-6)
        const aw = (Math.abs(r.aValue) / max) * 100
        const bw = (Math.abs(r.bValue) / max) * 100
        return (
          <div className="cmp-row" key={r.label}>
            <div className="cmp-row__label">{r.label}</div>
            <div className="cmp-row__track">
              <span className="cmp-row__val cmp-row__val--a mono">{r.aDisplay ?? r.aValue}</span>
              <span className="cmp-row__bars">
                <span className="cmp-row__half cmp-row__half--a">
                  <span className="cmp-row__bar" style={{ width: `${aw}%`, background: aColor }} />
                </span>
                <span className="cmp-row__half cmp-row__half--b">
                  <span className="cmp-row__bar" style={{ width: `${bw}%`, background: bColor }} />
                </span>
              </span>
              <span className="cmp-row__val cmp-row__val--b mono">{r.bDisplay ?? r.bValue}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
