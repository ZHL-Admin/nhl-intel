import type { PlayerAssessment } from '../../api/types'

// Mirrors config.ASSESSMENT.CONFIDENCE_CUTS.high — the range-copy trigger keys on the RAW
// tier_confidence, not the (possibly forced-low) confidence_label. See spec 10.1, Amendment B.
const HIGH_CONF = 0.55

const CONF_WORD: Record<string, string> = { high: 'high', medium: 'moderate', low: 'low' }

/**
 * One deterministic sentence from returned fields only (spec 10.1, Amendment B + D13).
 * Evaluated in order:
 *   1. inactive (D13)          -> "Inactive, last played {season}."
 *   2. otherwise unqualified   -> insufficient-sample copy.
 *   3. single-season window    -> single-season template (never a range).
 *   4. range copy on RAW values (tier_confidence < high AND within_one >= threshold) -> two-tier range.
 *   5. otherwise               -> assigned tier + confidence word.
 */
export function assessmentSentence(a: PlayerAssessment): string {
  if (!a.qualified) {
    if (a.disqualify_reason === 'inactive') {
      return a.last_played_season ? `Inactive, last played ${a.last_played_season}.` : 'Inactive.'
    }
    return `Not enough NHL sample to assess (needs ${a.provenance.pool_floor_desc}).`
  }
  const tier = a.tier_label ?? a.tier ?? 'unrated'
  const grade = a.stability_grade ? `, stability grade ${a.stability_grade}` : ''
  const article = (w: string) => (/^[aeiou]/i.test(w) ? 'an' : 'a')

  const singleSeason = !a.season_window.includes('_')
  if (singleSeason) {
    return `${tier} on a single-season sample${grade}.`
  }

  const conf = a.tier_confidence ?? 0
  const within = a.tier_prob_within_one ?? 0
  const threshold = a.provenance.within_one_range_copy ?? 0.85
  if (conf < HIGH_CONF && within >= threshold) {
    const order = a.tier_probs.map((p) => p.tier)
    const idx = order.indexOf(a.tier ?? '')
    const probOf = (t: string) => a.tier_probs.find((p) => p.tier === t)?.prob ?? 0
    const labelOf = (t: string) => a.tier_probs.find((p) => p.tier === t)?.label ?? t
    const neighbors = [idx - 1, idx + 1]
      .filter((j) => j >= 0 && j < order.length)
      .sort((x, y) => probOf(order[y]) - probOf(order[x]))
    const a1 = tier.toLowerCase()
    const a2 = (neighbors.length ? labelOf(order[neighbors[0]]) : tier).toLowerCase()
    return `Likely ${article(a1)} ${a1} or ${a2} (${Math.round(within * 100)}% combined)${grade}.`
  }

  const word = CONF_WORD[a.confidence_label ?? 'low'] ?? a.confidence_label ?? ''
  return `${tier}, ${word} confidence (${Math.round(conf * 100)}%)${grade}.`
}
