/**
 * Impact (RAPM) vs Value (GAR) — the two headline value lenses for a skater, on the SAME
 * percentile-within-position scale so they're directly comparable. Impact = repeatable
 * play-driving ("what tends to repeat"); Value = actual goals above replacement ("what
 * happened"), which inherits shooting luck by design. The centerpiece is the GAP and a
 * deterministic, asymmetric read of it.
 *
 * The Value bar carries a prominent uncertainty band + an exact "± WAR" figure — a finisher's
 * GAR has real shooting variance, and the band is the visual honest-signal that the gap may be
 * partly noise. The read's "least repeatable" claim traces to the measured stability r-values,
 * shown at the bottom (consistency rule): the same statement in two registers.
 *
 * Reuses the actual-vs-expected motif from deserved standings (team) and GSAx-vs-Edge (goalie).
 */
import { useContext } from 'react'
import { PlayerValue } from '../../api/types'
import { PageCardContext } from './PageCard'
import './ImpactValuePanel.css'

const pctText = (p?: number | null) => (p == null ? '—' : `${Math.round(p * 100)}`)

function Lens({ label, sublabel, pct, tone, band, chip }: {
  label: string; sublabel: string; pct?: number | null
  tone: 'impact' | 'value'; band?: number; chip?: string
}) {
  const x = pct == null ? 0 : Math.max(0, Math.min(1, pct)) * 100
  const half = band ? Math.min(22, band) : 0   // band half-width in percentile points (visual proxy)
  return (
    <div className={`ivp-lens ivp-lens--${tone}`}>
      <div className="ivp-lens__top">
        <span className="ivp-lens__label">{label}</span>
        <span className="ivp-lens__sub">{sublabel}</span>
        <span className="ivp-lens__pct">{pctText(pct)}<small>pctile</small></span>
      </div>
      <div className="ivp-lens__track">
        {pct != null && band ? (
          <span className="ivp-lens__band" style={{ left: `${Math.max(0, x - half)}%`, right: `${Math.max(0, 100 - Math.min(100, x + half))}%` }} />
        ) : null}
        {pct != null && <span className="ivp-lens__marker" style={{ left: `${x}%` }} />}
      </div>
      {chip && <span className="ivp-lens__chip">{chip}</span>}
    </div>
  )
}

export default function ImpactValuePanel({ value, name }: { value: PlayerValue; name: string }) {
  const ranked = value.value_percentile != null && value.impact_percentile != null
  const gap = value.gap_percentile_points ?? null
  const warBand = value.war_sd ? value.war_sd * 4 : 0   // ±WAR -> ~percentile-point band (proxy)
  const last = name.split(' ').slice(-1)[0]
  const insidePageCard = useContext(PageCardContext)

  return (
    <div className={`ivp${insidePageCard ? ' ivp--flat' : ''}`}>
      <div className="ivp__head">
        <h2 className="ivp__title">Impact vs Value</h2>
        <span className="ivp__tag">RAPM (repeats) vs GAR (happened)</span>
      </div>

      <div className="ivp__bars">
        <Lens label="Impact" sublabel="play-driving · what repeats" pct={value.impact_percentile} tone="impact" />
        <Lens label="Value" sublabel="actual goals · what happened" pct={value.value_percentile} tone="value"
          band={warBand}
          chip={`${value.gar >= 0 ? '+' : ''}${value.gar.toFixed(1)} GAR · ${value.war >= 0 ? '+' : ''}${value.war.toFixed(1)} ± ${value.war_sd.toFixed(1)} WAR`} />
        <div className="ivp__scale"><span>0</span><span>50</span><span>100</span></div>
      </div>

      {ranked && gap != null && (
        <div className={`ivp__gap ivp__gap--${value.read?.case ?? 'aligned'}`}>
          <span className="ivp__gap-num">{gap > 0 ? '+' : ''}{Math.round(gap)}</span>
          <span className="ivp__gap-lbl">percentile-point gap{gap > 0 ? ' · Value over Impact' : gap < 0 ? ' · Impact over Value' : ' · aligned'}</span>
        </div>
      )}

      {value.read ? (
        <div className="ivp__read">
          <h3 className="ivp__read-head">{value.read.headline}</h3>
          <p className="ivp__read-body">{value.read.body}</p>
        </div>
      ) : (
        <p className="ivp__muted">{last} hasn’t the minutes to rank within position this season; GAR shown without a percentile read.</p>
      )}

      <div className="ivp__stab" title="Year-over-year correlation; from the GAR methodology.">
        <span className="ivp__stab-lbl">Year-to-year stability</span>
        <span className="ivp__stab-item">production <strong>r={value.production_r.toFixed(2)}</strong></span>
        <span className="ivp__stab-item">RAPM rate <strong>r={value.rapm_r.toFixed(2)}</strong></span>
        <span className="ivp__stab-item ivp__stab-item--key">finishing <strong>r={value.finishing_r.toFixed(2)}</strong></span>
      </div>
    </div>
  )
}
