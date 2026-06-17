/**
 * OverallSummary — the per-player Overall, a WITHIN-POSITION percentile SUMMARY for the player
 * detail card ONLY (never a leaderboard sort key; there is no /rankings/overall).
 *
 * HARD RULE (encoded, not just documented): Overall must NEVER be shown without the component
 * percentiles it summarises — it summarises, it must not hide the divergence. This component takes
 * the whole `OverallSummary` object and renders the number AND its components together in one
 * block; if components are missing it renders nothing at all, so a future refactor cannot split
 * the headline number away from its parts.
 *
 * Reuses PercentileBarList for the component bars and the existing Impact-vs-Value `read` text
 * (passed in, not rebuilt) to explain the gap when the two lenses diverge.
 */
import { OverallSummary as OverallData, ValueGapRead } from '../../api/types'
import PercentileBarList from './PercentileBarList'
import type { PercentileBarItem } from './PercentileBarList'
import './OverallSummary.css'

const POS_NOUN: Record<string, string> = { F: 'forwards', D: 'defensemen', G: 'goalies' }

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

interface Props {
  overall: OverallData
  /** Optional Impact-vs-Value read (skaters) — reused verbatim to explain a divergence. */
  read?: ValueGapRead | null
}

export default function OverallSummary({ overall, read }: Props) {
  const comps = overall.components ?? []
  // HARD RULE: no components -> render nothing (never the number alone).
  if (comps.length === 0) return null

  const pct = Math.round((overall.overall_percentile ?? 0) * 100)
  const posNoun = POS_NOUN[overall.pos_group ?? ''] ?? 'their position'

  const items: PercentileBarItem[] = comps.map((c) => ({
    key: c.key,
    label: c.label,
    percentile: c.percentile ?? null,
    value: null,
  }))

  // surface the gap only when the components genuinely diverge (>= ~15 pctile points)
  const ps = comps.map((c) => c.percentile).filter((p): p is number => p != null)
  const diverges = ps.length >= 2 && Math.max(...ps) - Math.min(...ps) >= 0.15

  return (
    <div className="ovr">
      <div className="ovr__head">
        <div className="ovr__num">
          <span className="ovr__pct">{ordinal(pct)}</span>
          <span className="ovr__pct-unit">percentile</span>
        </div>
        <div className="ovr__caption">
          <span className="ovr__title">Overall</span>
          <span className="ovr__among">among {posNoun}</span>
        </div>
      </div>

      <div className="ovr__bar" aria-hidden="true">
        <span className="ovr__bar-fill" style={{ width: `${pct}%` }} />
      </div>

      <div className="ovr__components">
        <div className="ovr__components-label">Built from</div>
        <PercentileBarList items={items} />
      </div>

      {diverges && read && (
        <p className="ovr__read"><strong>{read.headline}</strong> {read.body}</p>
      )}
      <p className="ovr__note">
        A within-position summary that averages and re-percentiles the lenses above — shown only
        with its parts, never as a ranking.
      </p>
    </div>
  )
}
