/**
 * Lightweight in-game win-probability model.
 *
 * Both teams are modelled as scoring the rest of the game at a league-average
 * Poisson rate. The final goal differential is therefore the difference of two
 * Poissons (a Skellam distribution); win probability is the mass of that
 * distribution that leaves the home team ahead, with ties split 50/50 for OT.
 *
 * This uses only the score and time remaining — no shift data required.
 */

const RATE_PER_60 = 3.0 // league-average goals per team per 60 minutes
const REGULATION_SECONDS = 3600

function poissonPmf(lambda: number, kMax: number): number[] {
  const out: number[] = []
  let p = Math.exp(-lambda) // P(X = 0)
  out.push(p)
  for (let k = 1; k <= kMax; k++) {
    p = (p * lambda) / k
    out.push(p)
  }
  return out
}

/** Probability the home team wins given its current lead and seconds remaining. */
export function homeWinProbability(homeLead: number, remainingSeconds: number): number {
  const lambda = RATE_PER_60 * (Math.max(0, remainingSeconds) / 3600) + 1e-6
  const kMax = 12
  const pmf = poissonPmf(lambda, kMax)
  let win = 0
  let tie = 0
  for (let h = 0; h <= kMax; h++) {
    for (let a = 0; a <= kMax; a++) {
      const finalDiff = homeLead + h - a
      const p = pmf[h] * pmf[a]
      if (finalDiff > 0) win += p
      else if (finalDiff === 0) tie += p
    }
  }
  return win + 0.5 * tie
}

export interface WinProbPoint {
  t: number
  homeWp: number
}

interface GoalLike {
  game_time_seconds: number
  team_id: number
}

/** Sample the home win-probability curve across the game from the goal timeline. */
export function winProbabilitySeries(
  goals: GoalLike[],
  homeTeamId: number,
  end: number,
  step = 30
): WinProbPoint[] {
  const sorted = [...goals].sort((a, b) => a.game_time_seconds - b.game_time_seconds)
  const series: WinProbPoint[] = []
  for (let t = 0; t <= end; t += step) {
    let lead = 0
    for (const g of sorted) {
      if (g.game_time_seconds <= t) lead += g.team_id === homeTeamId ? 1 : -1
      else break
    }
    const remaining = Math.max(0, REGULATION_SECONDS - t)
    series.push({ t, homeWp: homeWinProbability(lead, remaining) })
  }
  return series
}
