import type { PlayerAssessment } from '../../api/types'

// Range-copy trigger keys on RAW tier_confidence (mirrors config.ASSESSMENT.CONFIDENCE_CUTS.high).
const HIGH_CONF = 0.55

// Short tier labels for the ladder histogram axis, by tier key (F / D / G ladders).
export const TIER_SHORT: Record<string, string> = {
  elite: 'Elite', first_line: '1st', second_line: '2nd', third_line: '3rd', fourth_line: '4th',
  number_one: '#1', top_pair: 'Top', second_pair: '2nd pr', third_pair: '3rd pr',
  elite_starter: 'Elite', starter: 'Starter', tandem: 'Tandem', backup: 'Backup', fringe: 'Fringe',
}

const CONF_WORD: Record<string, string> = { high: 'High', medium: 'Medium', low: 'Low' }

const stripPos = (label: string) =>
  label.replace(/\s+(forward|defenseman|goalie|starter)$/i, '').toLowerCase()

function rangeTiers(a: PlayerAssessment): [string, string] | null {
  const conf = a.tier_confidence ?? 0
  const within = a.tier_prob_within_one ?? 0
  const threshold = a.provenance.within_one_range_copy ?? 0.85
  if (conf >= HIGH_CONF || within < threshold) return null
  const order = a.tier_probs.map((p) => p.tier)
  const idx = order.indexOf(a.tier ?? '')
  const probOf = (t: string) => a.tier_probs.find((p) => p.tier === t)?.prob ?? 0
  const neighbors = [idx - 1, idx + 1]
    .filter((j) => j >= 0 && j < order.length)
    .sort((x, y) => probOf(order[y]) - probOf(order[x]))
  if (!neighbors.length) return null
  return [a.tier ?? '', order[neighbors[0]]]
}

/** The set of tier keys the histogram highlights (assigned tier, plus the neighbor when range fires). */
export function highlightedTiers(a: PlayerAssessment): Set<string> {
  const set = new Set<string>()
  if (a.tier) set.add(a.tier)
  const r = rangeTiers(a)
  if (r) r.forEach((t) => set.add(t))
  return set
}

/** V1: the card headline. Range when the range-copy rule fires; else the assigned tier label. */
export function tierHeadline(a: PlayerAssessment): string {
  if (!a.qualified) return a.disqualify_reason === 'inactive' ? 'Inactive' : 'Not enough NHL sample'
  const tierLabel = a.tier_label ?? a.tier ?? '—'
  const singleSeason = !a.season_window.includes('_')
  if (singleSeason) return tierLabel
  const r = rangeTiers(a)
  if (r) {
    const labelOf = (t: string) => a.tier_probs.find((p) => p.tier === t)?.label ?? t
    return `${tierLabel} or ${stripPos(labelOf(r[1]))}`
  }
  return tierLabel
}

/** V4: confidence caps at >99% (never 100%). */
export function confidencePct(conf: number | null | undefined): string {
  if (conf == null) return '—'
  return conf >= 0.995 ? '>99%' : `${Math.round(conf * 100)}%`
}

export interface ConfidenceDisplay { word: string; tone: string }
export function confidenceDisplay(a: PlayerAssessment): ConfidenceDisplay {
  const cl = a.confidence_label ?? 'low'
  return { word: CONF_WORD[cl] ?? cl, tone: cl }   // tone: high | medium | low
}

/** V4/V5: sample-grade label ("Sample A") and its tooltip. Field/API name stays stability_grade. */
export const SAMPLE_TIP: Record<string, string> = {
  A: 'Sample A = 3 seasons, 3000+ 5v5 minutes in the window',
  B: 'Sample B = 2 seasons, 2000+ 5v5 minutes',
  C: 'Sample C = one season (the qualified floor)',
  D: 'Sample D = below the qualifying floor',
}
export const sampleLabel = (grade: string | null | undefined) => (grade ? `Sample ${grade}` : '')

/** V5: single-season meta line copy. */
export const isSingleSeason = (a: PlayerAssessment) => !a.season_window.includes('_')
