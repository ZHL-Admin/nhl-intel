/**
 * Deterministic game-verdict composer (Blueprint 2.3). The one-sentence verdict on a game is generated
 * from stored fields ONLY (consistency rule) — never free text. Templates are keyed on four booleans
 * derived from the team-stats + goaltending payloads; the first matching case wins. Wire into GameDetail
 * by computing GameVerdictInputs from its loaded payloads and rendering `composeGameVerdict(...)` as the
 * verdict line (serif) beneath the header.
 */
export interface GameVerdictInputs {
  winnerAbbrev: string
  loserAbbrev: string
  /** Winner closed below ~35% pregame win prob (upset). */
  upset: boolean
  /** The team that generated more xG is the team that won. */
  xgWinnerIsWinner: boolean
  /** Winning goalie's goals-saved-above-expected ≥ 1.5 (a theft). */
  goalieTheft: boolean
  /** Special teams net was the game's margin. */
  specialTeamsDecided: boolean
  goalieName?: string | null
  gsax?: number | null
}

const one = (v?: number | null) => (v == null ? '' : v.toFixed(1))

/** Compose the verdict sentence. Cases are evaluated in priority order; first match wins. */
export function composeGameVerdict(i: GameVerdictInputs): string {
  const W = i.winnerAbbrev
  const L = i.loserAbbrev

  if (i.goalieTheft) {
    const who = i.goalieName ? i.goalieName : `${W}'s goalie`
    const n = i.gsax != null ? `${one(i.gsax)} goals above expected` : 'a wall in net'
    return `${W} stole one: outchanced, but ${who} was worth ${n}.`
  }
  if (i.upset && !i.xgWinnerIsWinner) {
    return `${W} pulled the upset over ${L} without the run of play.`
  }
  if (i.upset) {
    return `${W} pulled the upset over ${L} — and earned it on the chances.`
  }
  if (i.specialTeamsDecided) {
    return `Special teams decided it: ${W} over ${L}.`
  }
  if (i.xgWinnerIsWinner) {
    return `${W} earned it: more chances, and they cashed them against ${L}.`
  }
  return `${W} edged ${L} in a game that could have gone either way.`
}

/** Pregame lean sentence (deterministic). */
export function composePregameLean(favAbbrev: string, favWinProb: number, home: boolean): string {
  const pct = Math.round(favWinProb * 100)
  const where = home ? 'at home' : 'on the road'
  if (pct <= 55) return `${favAbbrev} by a coin flip: ${pct}% ${where}.`
  if (pct >= 70) return `${favAbbrev} are heavy favourites at ${pct}% ${where}.`
  return `${favAbbrev} lean, ${pct}% ${where}.`
}
