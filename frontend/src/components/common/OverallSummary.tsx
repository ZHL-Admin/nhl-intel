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

const NOTE = 'A within-position summary that averages and re-percentiles the component lenses, ' +
  'shown only with its parts; never as a ranking.'

function toneClass(p: number): string {
  if (p >= 0.66) return 'ovr-mini--good'
  if (p <= 0.33) return 'ovr-mini--bad'
  return 'ovr-mini--mid'
}

interface Props {
  overall: OverallData
  /** Optional Impact-vs-Value read (skaters) — reused verbatim to explain a divergence. */
  read?: ValueGapRead | null
  /** 'card' (default, tall) or 'strip' (condensed horizontal band for the detail-card header). */
  variant?: 'card' | 'strip'
  /** Optional value readout (e.g. WAR/GAR) rendered to the right in 'strip' mode. */
  aside?: React.ReactNode
  /** Show the Impact-vs-Value read even when the lenses agree (card variant), so it can fill a
   *  fixed-height column instead of leaving the build bars floating. Default only-on-divergence. */
  showReadAlways?: boolean
}

export default function OverallSummary({ overall, read, variant = 'card', aside, showReadAlways }: Props) {
  const comps = overall.components ?? []
  // HARD RULE: no components -> render nothing (never the number alone).
  if (comps.length === 0) return null

  const pct = Math.round((overall.overall_percentile ?? 0) * 100)
  const posNoun = POS_NOUN[overall.pos_group ?? ''] ?? 'their position'

  // ---- condensed strip: a compact bordered card. Row 1 = lead percentile + inline component
  //      bars; row 2 = the value (WAR/GAR) readout. Never the number without its components. ----
  if (variant === 'strip') {
    return (
      <div className="ovr ovr--strip">
        <div className="ovr__strip-top">
          <div className="ovr__lead">
            <span className="ovr__pct">{ordinal(pct)}</span>
            <span className="ovr__lead-sub">
              percentile overall · among {posNoun}
              <span className="ovr__info" tabIndex={0} role="note" aria-label={NOTE} title={NOTE}>ⓘ</span>
            </span>
          </div>
          <div className="ovr__minis">
            {comps.map((c) => {
              const p = c.percentile
              const w = p == null ? 0 : Math.round(p * 100)
              return (
                <div className="ovr-mini" key={c.key}>
                  <span className="ovr-mini__label" title={c.label}>{c.label}</span>
                  <span className="ovr-mini__track">
                    {p != null && <span className={`ovr-mini__fill ${toneClass(p)}`} style={{ width: `${w}%` }} />}
                  </span>
                  <span className="ovr-mini__pct">{p == null ? '—' : w}</span>
                </div>
              )
            })}
          </div>
        </div>
        {aside && <div className="ovr__aside">{aside}</div>}
      </div>
    )
  }

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

      {(diverges || showReadAlways) && read && (
        <p className="ovr__read"><strong>{read.headline}</strong> {read.body}</p>
      )}
      <p className="ovr__note">
        A within-position summary that averages and re-percentiles the lenses above, shown only
        with its parts; never as a ranking.
      </p>
    </div>
  )
}
