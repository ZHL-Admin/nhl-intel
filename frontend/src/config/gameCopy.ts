/**
 * Deterministic copy generators for the Game Detail v2 page (doc 02, §12). Every generated string on
 * the page is composed here from stored payloads — never free text. Each generator has an honest
 * fallback when a datum is missing. Pole convention (§0): HOME → blue, AWAY → red; a "pole" field is
 * 'home' | 'away' | 'neutral', consumed by the page for dot / bar / value coloring.
 */
import { getTeamName } from '../utils/teams'

/** City label for a serif leader line. Handles the two-word nicknames explicitly. */
const TWO_WORD_NICKNAMES = ['Golden Knights', 'Maple Leafs', 'Blue Jackets', 'Red Wings']
export function cityOf(abbrev: string): string {
  const name = getTeamName(abbrev)
  if (name === abbrev) return abbrev
  for (const nick of TWO_WORD_NICKNAMES) {
    if (name.endsWith(nick)) return name.slice(0, name.length - nick.length).trim()
  }
  return name.split(' ').slice(0, -1).join(' ') || name
}

const one = (v: number) => v.toFixed(1)
const two = (v: number) => v.toFixed(2)

// ── The deserved-score context line (header §1) ────────────────────────────
export function composeDeservedContext(i: {
  homeXg: number; awayXg: number; homeWon: boolean; leaderAbbrev: string
}): string {
  const xgTie = Math.abs(i.homeXg - i.awayXg) < 0.15
  if (xgTie) return 'the chances split almost evenly'
  const xgLeaderIsHome = i.homeXg > i.awayXg
  const deservedMatchesActual = xgLeaderIsHome === i.homeWon
  if (deservedMatchesActual) return 'the team that won also out-chanced the team that lost'
  return 'the team that lost out-chanced the team that won'
}

// ── Series state (header §1 meta) ──────────────────────────────────────────
export function composeSeriesState(i: {
  homeAbbrev: string; awayAbbrev: string
  homeWins?: number | null; awayWins?: number | null; neededToWin?: number | null
}): string | null {
  const hw = i.homeWins, aw = i.awayWins, need = i.neededToWin
  if (hw == null || aw == null) return null
  if (need != null && (hw >= need || aw >= need)) {
    const winner = hw >= need ? i.homeAbbrev : i.awayAbbrev
    const hi = Math.max(hw, aw), lo = Math.min(hw, aw)
    return `${cityOf(winner)} wins the series ${hi}–${lo}`
  }
  if (hw === aw) return `Series tied ${hw}–${aw}`
  const leader = hw > aw ? i.homeAbbrev : i.awayAbbrev
  return `${leader} leads ${Math.max(hw, aw)}–${Math.min(hw, aw)}`
}

// ── The four verdict receipts (§2) ─────────────────────────────────────────
export type Pole = 'home' | 'away' | 'neutral'
export interface Receipt { text: string; pole: Pole }

export function composeReceipts(i: {
  homeAbbrev: string; awayAbbrev: string; homeWon: boolean
  homeXg: number; awayXg: number
  winGoalie?: { last: string; saves: number; shots: number; gsax: number; isHome: boolean } | null
  topDriver?: { last: string; gameScore: number; isHome: boolean } | null
  hdFinish?: { winnerAbbrev: string; goals: number; attempts: number; winnerIsHome: boolean } | null
  ppToWinnerNet?: number
}): Receipt[] {
  const receipts: Receipt[] = []
  const xgLeaderIsHome = i.homeXg > i.awayXg
  const leaderAbbrev = xgLeaderIsHome ? i.homeAbbrev : i.awayAbbrev
  const hi = Math.max(i.homeXg, i.awayXg), lo = Math.min(i.homeXg, i.awayXg)
  const deservedDiffers = xgLeaderIsHome !== i.homeWon

  // 1. deserved-score receipt (pole = xG leader)
  if (Math.abs(i.homeXg - i.awayXg) < 0.15) {
    receipts.push({ text: `Expected goals split evenly, ${two(i.homeXg)} to ${two(i.awayXg)}.`, pole: 'neutral' })
  } else {
    receipts.push({ text: `${leaderAbbrev} out-chanced the room, ${two(hi)} to ${two(lo)} in expected goals.`, pole: xgLeaderIsHome ? 'home' : 'away' })
  }

  // 2. goalie receipt (pole = goalie's team). When the deserved and actual winners differ, this credits
  //    the side that lost the chance battle but won the game (§2 requirement).
  if (i.winGoalie) {
    const g = i.winGoalie
    const savePct = g.shots > 0 ? (g.saves / g.shots).toFixed(3).replace(/^0/, '') : '—'
    receipts.push({
      text: `${g.last} stopped ${g.saves} of ${g.shots} (${savePct}), ${g.gsax >= 0 ? '+' : ''}${two(g.gsax)} goals saved above expected.`,
      pole: g.isHome ? 'home' : 'away',
    })
  }

  // 3. top driver (pole = driver's team)
  if (i.topDriver) {
    receipts.push({ text: `${i.topDriver.last} led all skaters with a ${two(i.topDriver.gameScore)} game score.`, pole: i.topDriver.isHome ? 'home' : 'away' })
  }

  // 4. finishing / special teams
  if (i.ppToWinnerNet && i.ppToWinnerNet > 0) {
    receipts.push({ text: `Special teams tilted it: the winner netted ${i.ppToWinnerNet} more power-play ${i.ppToWinnerNet === 1 ? 'goal' : 'goals'}.`, pole: 'neutral' })
  } else if (i.hdFinish && i.hdFinish.attempts > 0) {
    const pct = Math.round((i.hdFinish.goals / i.hdFinish.attempts) * 100)
    receipts.push({ text: `${i.hdFinish.winnerAbbrev} finished ${pct}% of its high-danger looks (${i.hdFinish.goals} of ${i.hdFinish.attempts}).`, pole: i.hdFinish.winnerIsHome ? 'home' : 'away' })
  } else {
    receipts.push({ text: 'The margin held from even strength.', pole: 'neutral' })
  }

  // Guarantee a receipt credits the losing side of the deserved score (the actual winner) when they differ.
  if (deservedDiffers) {
    const winnerAbbrev = i.homeWon ? i.homeAbbrev : i.awayAbbrev
    const winnerPole: Pole = i.homeWon ? 'home' : 'away'
    const credits = receipts.some((r) => r.pole === winnerPole)
    if (!credits) receipts.push({ text: `${winnerAbbrev} won the scoreboard despite the chance deficit.`, pole: winnerPole })
  }

  return receipts.slice(0, 4)
}

// ── Hinge one-line description (§4) ─────────────────────────────────────────
export function composeHinge(i: {
  scoringAbbrev: string; homeBefore: number; awayBefore: number; isHome: boolean; strength?: string
}): string {
  const own = i.isHome ? i.homeBefore : i.awayBefore
  const opp = i.isHome ? i.awayBefore : i.homeBefore
  const strengthTag = i.strength && i.strength !== 'EV' ? ` on the ${i.strength === 'PP' ? 'power play' : i.strength === 'SH' ? 'penalty kill' : i.strength.toLowerCase()}` : ''
  if (own === opp) return `broke a ${own}–${own} tie${strengthTag}`
  if (own < opp) {
    if (opp - own === 1) return `pulled within one${strengthTag}`
    return `answered back${strengthTag}`
  }
  // own > opp
  if (own - opp === 1) return `extended the lead${strengthTag}`
  return `stretched it further${strengthTag}`
}

// ── Section captions (§3, §4, §5, §6) ──────────────────────────────────────
export function composeWormCaption(homeAbbrev: string, awayAbbrev: string): string {
  return `Above the line, ${homeAbbrev} is out-chancing; below it, ${awayAbbrev}.`
}

export function composeCreaseCaption(i: { gsaxSwing: number; margin: number }): string {
  const swing = one(Math.abs(i.gsaxSwing))
  if (i.margin === 0) return `A ${swing}-goal swing between the two creases.`
  return `A ${swing}-goal swing between the creases against a ${i.margin}-goal final margin.`
}

export function composeChanceCaption(i: {
  homeAbbrev: string; awayAbbrev: string; homeAttempts: number; awayAttempts: number
}): string {
  const leader = i.homeAttempts >= i.awayAttempts ? i.homeAbbrev : i.awayAbbrev
  const hi = Math.max(i.homeAttempts, i.awayAttempts), lo = Math.min(i.homeAttempts, i.awayAttempts)
  return `${leader} drove more volume, ${hi} attempts to ${lo}, folded to each attacking end.`
}

export function composeH2HInvertedNote(): string {
  return 'On giveaways, fewer is better — the bar leans toward the tidier side.'
}
