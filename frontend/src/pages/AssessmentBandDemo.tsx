import AssessmentBand from '../components/players/AssessmentBand'
import { assessmentSentence } from '../components/players/assessmentSentence'
import type { PlayerAssessment, QualityContext } from '../api/types'

// Static, crafted states for the M3 states demo (spec 10.4 + Amendments). No backend needed.

const prov = (over: Partial<PlayerAssessment['provenance']> = {}): PlayerAssessment['provenance'] => ({
  pool_size: 515, pool_floor_desc: '200+ 5v5 min (skaters) / 15+ games (goalies) in window',
  toi_basis_min: 4215, seasons_present: 3, production_r: 0.66, rapm_r: 0.38, finishing_r: 0.35,
  point_estimator: 'c2_roster_player', model_version: 'assessment_v1', within_one_range_copy: 0.85,
  generated_at: '2026-07-03T18:52:45Z', methodology_slug: 'player-assessment', ...over,
})

const fProbs = (elite: number, first: number, second = 0, rest = 0) => ([
  { tier: 'elite', label: 'Elite', prob: elite },
  { tier: 'first_line', label: 'First-line forward', prob: first },
  { tier: 'second_line', label: 'Second-line forward', prob: second },
  { tier: 'third_line', label: 'Third-line forward', prob: rest },
  { tier: 'fourth_line', label: 'Fourth-line forward', prob: 0 },
  { tier: 'fringe', label: 'Fringe / replacement', prob: 0 },
])

const base = (o: Partial<PlayerAssessment>): PlayerAssessment => ({
  player_id: 1, season_window: '2023-24_2025-26', position: 'F', qualified: true,
  tier: 'elite', tier_label: 'Elite', tier_confidence: 1, confidence_label: 'high',
  tier_prob_within_one: 1, tier_mode: 'rank', tier_probs: fProbs(1, 0),
  assessed_war: 8, war_sd: 1.2, war_p10: 6, war_p90: 10, stability_grade: 'A',
  role_primary: 'Elite Offensive Driver', role_deployment: 'Balanced two-way usage',
  provenance: prov(), ...o,
})

const STATES: Array<{ title: string; note: string; a: PlayerAssessment }> = [
  { title: 'Qualified / full (elite F, high confidence)', note: 'plain tier + confidence word',
    a: base({}) },
  { title: 'Qualified, low confidence (mid-ladder)', note: 'confidence pill reads Low; sentence hedges',
    a: base({ tier: 'third_line', tier_label: 'Third-line forward', tier_confidence: 0.31,
      confidence_label: 'low', tier_prob_within_one: 0.7, stability_grade: 'B',
      tier_probs: [{ tier: 'second_line', label: 'Second-line forward', prob: 0.28 },
        { tier: 'third_line', label: 'Third-line forward', prob: 0.31 },
        { tier: 'fourth_line', label: 'Fourth-line forward', prob: 0.26 }],
      role_primary: 'Bottom-Six Checker', role_deployment: 'Defensive-leaning' }) },
  { title: 'Range-copy straddle (Amendment B)', note: 'raw conf<high AND within-one>=0.85 -> two-tier range',
    a: base({ tier_confidence: 0.538, confidence_label: 'medium', tier_prob_within_one: 0.977,
      tier_probs: fProbs(0.538, 0.439, 0.019, 0.002), role_primary: 'Top-Six Playmaker' }) },
  { title: 'Single-season fallback (corrected — Amendment B)', note: 'own template, NOT a range',
    a: base({ season_window: '2025-26', tier_confidence: 0.9948, confidence_label: 'low',
      tier_prob_within_one: 0.9999, stability_grade: 'C', tier_probs: fProbs(0.9948, 0.005) }) },
  { title: 'Unqualified (insufficient sample)', note: 'muted band',
    a: base({ qualified: false, disqualify_reason: 'insufficient_sample', tier: null, tier_label: null,
      tier_confidence: null, confidence_label: null, tier_prob_within_one: null, tier_probs: [],
      stability_grade: 'D', role_primary: null, role_deployment: null }) },
  { title: 'Inactive (D13)', note: 'Inactive, last played {season}',
    a: base({ position: 'D', qualified: false, disqualify_reason: 'inactive', last_played_season: '2023-24',
      tier: null, tier_label: null, tier_confidence: null, confidence_label: null,
      tier_prob_within_one: null, tier_probs: [], stability_grade: 'D',
      role_primary: null, role_deployment: null }) },
  { title: 'Goalie (ladder + grade cap)', note: 'goalie tiers, grade capped at B',
    a: base({ position: 'G', tier: 'elite_starter', tier_label: 'Elite starter', tier_confidence: 0.78,
      confidence_label: 'high', tier_prob_within_one: 0.93, stability_grade: 'B',
      tier_probs: [{ tier: 'elite_starter', label: 'Elite starter', prob: 0.78 },
        { tier: 'starter', label: 'Starter', prob: 0.15 },
        { tier: 'tandem', label: 'Tandem goalie', prob: 0.02 },
        { tier: 'backup', label: 'Backup', prob: 0.01 },
        { tier: 'fringe', label: 'Fringe / replacement', prob: 0.04 }],
      role_primary: null, role_deployment: null, provenance: prov({ point_estimator: 'goalie_gar' }) }) },
]

// QoC rows: one qualified, one below-floor (null percentiles -> muted)
const QOC: Array<{ name: string; q: QualityContext }> = [
  { name: 'Matchup D (qualified)', q: { season: '2024-25', team_id: 13, pos_group: 'D',
    qoc_war_rate: 0.044, qot_war_rate: 0.065, qoc_pctile: 0.996, qot_pctile: 0.985, toi_5v5_sec: 77594 } },
  { name: 'Depth D (below floor)', q: { season: '2024-25', team_id: 5, pos_group: 'D',
    qoc_war_rate: 0.012, qot_war_rate: 0.001, qoc_pctile: null, qot_pctile: null, toi_5v5_sec: 1043 } },
]

const pct = (p: number | null | undefined) => (p == null ? '—' : `${Math.round(p * 100)}th`)

export default function AssessmentBandDemo() {
  return (
    <div style={{ maxWidth: 920, margin: '0 auto', padding: 'var(--space-6)', display: 'grid', gap: 'var(--space-5)' }}>
      <h1 style={{ margin: 0 }}>Assessment states demo (M3)</h1>
      {STATES.map((s, i) => (
        <div key={i} style={{ display: 'grid', gap: 'var(--space-2)' }}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{s.title}</div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>{s.note}</div>
          <AssessmentBand assessment={s.a} />
          <code style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
            sentence → {assessmentSentence(s.a)}
          </code>
        </div>
      ))}

      <h2 style={{ margin: 'var(--space-4) 0 0' }}>QoC/QoT — null-percentile muting</h2>
      {QOC.map((r, i) => {
        const muted = r.q.qoc_pctile == null
        return (
          <div key={i} style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center',
            opacity: muted ? 0.5 : 1, padding: 'var(--space-3)', border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-lg)' }}>
            <strong style={{ minWidth: 180 }}>{r.name}</strong>
            <span>QoC {pct(r.q.qoc_pctile)} <small style={{ color: 'var(--color-text-tertiary)' }}>(rate {r.q.qoc_war_rate?.toFixed(3)})</small></span>
            <span>QoT {pct(r.q.qot_pctile)}</span>
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--text-xs)' }}>
              {Math.round((r.q.toi_5v5_sec ?? 0) / 60)} 5v5 min {muted ? '· below floor, percentile muted' : ''}
            </span>
          </div>
        )
      })}
    </div>
  )
}
