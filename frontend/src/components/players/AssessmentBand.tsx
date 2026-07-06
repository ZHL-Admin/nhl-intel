import { Link } from 'react-router-dom'
import Tooltip from '../common/Tooltip'
import {
  tierHeadline, confidenceDisplay, confidencePct, sampleLabel, SAMPLE_TIP,
  highlightedTiers, isSingleSeason, TIER_SHORT,
} from './assessmentDisplay'
import type { PlayerAssessment } from '../../api/types'
import './AssessmentBand.css'

interface Props {
  assessment: PlayerAssessment | null
}

/**
 * Layer-1 verdict block (V1-V6). Hierarchy: quiet role eyebrow -> tier/range headline -> meta line
 * (confidence dot+word, sample grade) -> ladder histogram. Color carries ONLY confidence
 * (green/amber/gray); tier is expressed by size/weight; accent blue is data ink (histogram fills).
 * The deterministic sentence is NOT rendered here (it lives in the API/verdict payload).
 */
export default function AssessmentBand({ assessment: a }: Props) {
  if (!a) return null

  // Unqualified: inactive (D13) or insufficient sample. Muted band, no histogram.
  if (!a.qualified) {
    const inactive = a.disqualify_reason === 'inactive'
    return (
      <div className="asmt asmt--muted" role="note">
        <span className={`asmt__flag ${inactive ? 'asmt__flag--inactive' : ''}`}>
          {inactive ? 'Inactive' : 'Unrated'}
        </span>
        <span className="asmt__muted-text">
          {inactive
            ? (a.last_played_season ? `Last played ${a.last_played_season}` : 'No recent NHL games')
            : `Not enough NHL sample to assess (needs ${a.provenance.pool_floor_desc})`}
        </span>
      </div>
    )
  }

  const conf = confidenceDisplay(a)
  const single = isSingleSeason(a)
  const hl = highlightedTiers(a)

  return (
    <div className="asmt">
      {/* eyebrow: quiet role line (V1) */}
      {(a.role_primary || a.role_deployment) && (
        <div className="asmt__eyebrow">
          {a.role_primary && (
            <Link to={`/learn/archetypes?type=${encodeURIComponent(a.role_primary)}`} className="asmt__eyebrow-link">
              {a.role_primary}
            </Link>
          )}
          {a.role_deployment && <span>{a.role_primary ? ' · ' : ''}{a.role_deployment}</span>}
        </div>
      )}

      {/* headline: tier (or range when range-copy fires) */}
      <h2 className="asmt__headline">{tierHeadline(a)}</h2>

      {/* meta line: confidence dot + word, sample grade (V3/V4/V5) */}
      <div className="asmt__meta">
        <Tooltip content={`Probability mass in the assigned tier: ${confidencePct(a.tier_confidence)}`}>
          <span className="asmt__conf">
            <span className={`asmt__dot asmt__dot--${conf.tone}`} />
            {single ? 'Low confidence, single-season window' : `${conf.word} confidence`}
          </span>
        </Tooltip>
        {a.stability_grade && (
          <Tooltip content={SAMPLE_TIP[a.stability_grade] ?? ''}>
            <span className="asmt__sample">· {sampleLabel(a.stability_grade)}</span>
          </Tooltip>
        )}
        <Link className="asmt__how" to={`/learn/${a.provenance.methodology_slug}`}>How we know</Link>
      </div>

      {/* ladder histogram (V2): one column per tier in ladder order, fill = probability */}
      {a.tier_probs.length > 0 && (
        <div className="asmt__ladder" aria-label="Tier probability distribution">
          {a.tier_probs.map((p) => {
            const on = hl.has(p.tier)
            return (
              <div key={p.tier} className="asmt__col">
                <div className="asmt__col-pct">{p.prob >= 0.05 ? `${Math.round(p.prob * 100)}%` : ''}</div>
                <div className="asmt__well">
                  <div
                    className={`asmt__fill ${on ? 'is-on' : ''}`}
                    style={{ height: `${Math.max(p.prob * 100, on ? 4 : 0)}%` }}
                  />
                </div>
                <div className={`asmt__col-label ${on ? 'is-on' : ''}`}>{TIER_SHORT[p.tier] ?? p.label}</div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
