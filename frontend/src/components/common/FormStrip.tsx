/**
 * FormStrip — a compact recent-form row: one colored pip per result + an optional record label.
 * Shared (Overview hero hero, league table rows, the Players trending strip). Results are
 * chronological oldest-first; rendered left-to-right so the newest result sits at the right edge.
 * Renders nothing when given no results (parent omits the strip — never placeholder zeros).
 */
import './FormStrip.css'

export type GameResult = 'W' | 'L' | 'OTL'

interface FormStripProps {
  results: GameResult[]
  showRecord?: boolean
  label?: string
  size?: 'sm' | 'md'
  className?: string
}

export default function FormStrip({ results, showRecord = true, label, size = 'md', className }: FormStripProps) {
  if (!results || results.length === 0) return null

  const w = results.filter((r) => r === 'W').length
  const l = results.filter((r) => r === 'L').length
  const otl = results.filter((r) => r === 'OTL').length
  const record = otl > 0 ? `${w}-${l}-${otl}` : `${w}-${l}`
  const head = label ?? `Last ${results.length}`
  const aria = `last ${results.length}: ${w} wins, ${l} losses${otl ? `, ${otl} overtime losses` : ''}`

  return (
    <div className={`form-strip form-strip--${size}${className ? ' ' + className : ''}`} aria-label={aria}>
      <span className="form-strip__pips">
        {results.map((r, i) => (
          <span key={i} className={`form-strip__pip form-strip__pip--${r.toLowerCase()}`} aria-hidden="true" />
        ))}
      </span>
      {showRecord && <span className="form-strip__record">{head} · {record}</span>}
    </div>
  )
}
