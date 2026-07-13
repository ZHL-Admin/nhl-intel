/**
 * Trade Builder v2 — the single source for every generated verdict read: the balance tilt,
 * the "Edge {TEAM}" language (shared with the home Ledger, doc 00c §4), team role phrases,
 * receipt lines, fit words, and the combined confidence. Kept pure and framework-free so the
 * page, the scoreboard, and the share card all speak with one voice.
 *
 * TODO(data): the engine does not emit a scalar `tilt`. It is DERIVED here from the per-team
 * talent (WAR) and price-vs-market (dollars) deltas on a shared $/WAR basis; this module is the
 * documented derivation the doc (§2, §7) requires the Ledger's "Edge {TEAM}" to share.
 */
import { TeamTradeResult } from '../../api/types'
import { getTeamAbbrev, getTeamName } from '../../utils/teams'
import { fmtWar, fmtDollarsM } from '../../utils/format'

/** Rough market rate translating a dollar surplus onto the WAR axis so talent + price combine. */
const DOLLARS_PER_WAR = 3_500_000

export interface Domains { talent: [number, number]; surplus: [number, number] }

/** A team's net gain on one combined scale (WAR-equivalent): talent + price-vs-market. */
export function netEdge(t: TeamTradeResult): number {
  const talent = t.talent_delta_war ?? 0
  const price = (t.surplus_delta_dollars ?? 0) / DOLLARS_PER_WAR
  return talent + price
}

/** Net edge expressed back in dollars-equivalent, for the N>=3 signed micro-bars ("+$3.1M eq"). */
export function netEdgeDollars(t: TeamTradeResult): number {
  return netEdge(t) * DOLLARS_PER_WAR
}

export interface TradeTilt {
  /** Signed position in [-1, 1]; negative favors the LEFT team, positive the RIGHT team. */
  value: number
  /** The team the deal favors (highest net edge), or null when essentially even. */
  edgeTeamId: number | null
  /** "Edge Carolina" / "Nearly even" — the shared Ledger phrase. */
  label: string
  /** Worded meter caption, e.g. "Nearly even · slight edge Carolina". */
  meterLabel: string
}

/**
 * Two-team balance tilt. `value` places the meter dot: 0 is dead even, +1 all the way to the
 * right team. Magnitude is squashed so a ~2-WAR-equivalent gap reads as a clear (but not pinned)
 * edge. This is the ONE place "Edge {TEAM}" is decided.
 */
export function twoTeamTilt(left: TeamTradeResult, right: TeamTradeResult): TradeTilt {
  const diff = netEdge(right) - netEdge(left)          // >0 favors right
  const value = Math.max(-1, Math.min(1, diff / 4))    // 4 WAR-eq ≈ pinned
  const mag = Math.abs(diff)
  const edge = mag < 0.3 ? null : diff > 0 ? right : left
  const edgeName = edge ? getTeamName(getTeamAbbrev(edge.team_id)) : null
  const strength = mag < 0.3 ? 'Nearly even'
    : mag < 1.0 ? 'Nearly even · slight edge'
    : mag < 2.2 ? 'Edge'
    : 'Clear edge'
  const label = edgeName ? `Edge ${edgeName}` : 'Nearly even'
  const meterLabel = edgeName
    ? (strength === 'Nearly even · slight edge' ? `Nearly even · slight edge ${edgeName}` : `${strength} ${edgeName}`)
    : 'Nearly even'
  return { value, edgeTeamId: edge?.team_id ?? null, label, meterLabel }
}

/** The edge team across N teams (best net edge) — the Ledger's "Edge {TEAM}" for multi-team deals. */
export function multiTeamEdge(teams: TeamTradeResult[]): TradeTilt {
  if (!teams.length) return { value: 0, edgeTeamId: null, label: 'Nearly even', meterLabel: 'Nearly even' }
  const sorted = [...teams].sort((a, b) => netEdge(b) - netEdge(a))
  const best = sorted[0]
  const mag = netEdge(best)
  const name = getTeamName(getTeamAbbrev(best.team_id))
  const even = mag < 0.3
  return {
    value: 0,
    edgeTeamId: even ? null : best.team_id,
    label: even ? 'Nearly even' : `Edge ${name}`,
    meterLabel: even ? 'Nearly even' : `Edge ${name}`,
  }
}

/** A short serif role phrase generated from the talent/price signs. */
export function rolePhrase(t: TeamTradeResult): string {
  const war = t.talent_delta_war ?? 0
  const price = t.surplus_delta_dollars ?? 0
  const warUp = war >= 0.5, warDn = war <= -0.5
  const priceUp = price >= 2_000_000, priceDn = price <= -2_000_000
  if (warUp && priceDn) return 'Wins now, pays for it'
  if (warUp) return 'Wins now'
  if (warDn && priceUp) return 'Retools for the future'
  if (warDn) return 'Steps back this year'
  if (priceUp) return 'Banks value'
  if (priceDn) return 'Spends to stay level'
  return 'Holds steady'
}

/** The N>=3 per-row worded label, placed in the bar cell. */
export function rowEdgeLabel(t: TeamTradeResult, rank: number, count: number): string {
  if (rank === 0 && netEdge(t) >= 0.3) return 'Comes out ahead'
  if (rank === count - 1 && netEdge(t) <= -0.3) return 'Gives up the most'
  return 'About even'
}

// ── Fit words (configurable thresholds; doc §4) ──────────────────────────────
export const FIT_THRESHOLDS = { strong: 0.66, good: 0.5, fair: 0.33 }
export function fitWord(score: number | null | undefined): string {
  if (score == null) return '—'
  if (score >= FIT_THRESHOLDS.strong) return 'Strong'
  if (score >= FIT_THRESHOLDS.good) return 'Good'
  if (score >= FIT_THRESHOLDS.fair) return 'Fair'
  return 'Poor'
}
/** A team's incoming-fit score: the mean of its incoming players' fit scores (0..1). */
export function teamFitScore(t: TeamTradeResult): number | null {
  const scores = t.fit_details.map((f) => f.fit_score).filter((s): s is number => s != null)
  if (!scores.length) return null
  return scores.reduce((a, b) => a + b, 0) / scores.length
}

// ── Confidence (combined across teams; doc §2) ───────────────────────────────
export type ConfTone = 'high' | 'medium' | 'low'
export function combinedConfidence(teams: TeamTradeResult[]): ConfTone {
  const words = teams.map((t) => (t.confidence ?? 'medium').toLowerCase())
  if (words.some((w) => w === 'low' || w === 'proxy')) return 'low'
  if (words.length > 0 && words.every((w) => w === 'high')) return 'high'
  return 'medium'
}

// ── Receipt lines (three per side; a cap violation is always one) ─────────────
export type Valence = 'pos' | 'neg' | 'neutral'
export interface Receipt { valence: Valence; lead: string; body: string }

const valOf = (v: number | null | undefined): Valence =>
  v == null || Math.abs(v) < 1e-9 ? 'neutral' : v > 0 ? 'pos' : 'neg'

/** Generate receipt lines for one team, from the four work metrics, with template fallbacks. */
export function teamReceipts(t: TeamTradeResult, max: number): Receipt[] {
  const out: Receipt[] = []
  // Talent
  const war = t.talent_delta_war
  if (war != null) {
    out.push({
      valence: valOf(war),
      lead: war >= 0 ? 'Gains talent' : 'Sheds talent',
      body: `${fmtWar(war)} WAR next season`,
    })
  }
  // Price vs market
  const price = t.surplus_delta_dollars
  if (price != null) {
    out.push({
      valence: valOf(price),
      lead: price >= 0 ? 'Buys value' : 'Overpays',
      body: `${fmtDollarsM(price, true)} vs market`,
    })
  }
  // Fit
  const fit = teamFitScore(t)
  if (fit != null && out.length < max) {
    const word = fitWord(fit)
    out.push({
      valence: word === 'Strong' || word === 'Good' ? 'pos' : word === 'Poor' ? 'neg' : 'neutral',
      lead: `${word} fit`,
      body: t.fit_details[0]?.player_name ? `for ${t.fit_details[0].player_name}` : 'into the lineup',
    })
  }
  // Cap — a violation is always surfaced.
  const cap = t.cap
  if (cap) {
    const over = cap.over_cap === true
    const marginTxt = cap.margin != null ? fmtDollarsM(Math.abs(cap.margin)) : ''
    const capReceipt: Receipt = {
      valence: over ? 'neg' : 'neutral',
      lead: over ? 'Over the cap' : 'Cap fits',
      body: over ? `${marginTxt} above the ceiling` : marginTxt ? `${marginTxt} of room` : 'within the ceiling',
    }
    if (over) {
      // Force the violation into view: drop the last non-cap line if we are at capacity.
      const trimmed = out.slice(0, Math.max(0, max - 1))
      return [...trimmed, capReceipt]
    }
    if (out.length < max) out.push(capReceipt)
  }
  return out.slice(0, max)
}

/** One deterministic prose sentence for the share card + placeholder verdict. */
export function verdictSentence(teams: TeamTradeResult[]): string {
  if (teams.length < 2) return ''
  const edge = teams.length >= 3 ? multiTeamEdge(teams) : twoTeamTilt(teams[0], teams[1])
  const phrases = teams.map((t) => `${getTeamName(getTeamAbbrev(t.team_id))} ${rolePhrase(t).toLowerCase()}`)
  return `${edge.label}. ${phrases.join('; ')}.`
}

export { valOf }
