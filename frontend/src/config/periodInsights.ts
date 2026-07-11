/**
 * Period-insight template set (Blueprint F6). The old headline credited whichever team won the
 * possession battle with "taking control" — but when the TRAILING team wins possession late, that's
 * score effects (chasing the game), not control. These templates are score-aware: they use the
 * period's own CF% (a fraction in the payload) and the score entering the period to pick the read.
 *
 * Wire into the period panel by computing PeriodInsightInput from mart_team_game_stats period fields
 * (cf_pct_p{n}) + the running score, and rendering `composePeriodInsight(...)`.
 */
export interface PeriodInsightInput {
  period: 1 | 2 | 3 | 4
  homeAbbrev: string
  awayAbbrev: string
  /** Period CF% as fractions (0..1). */
  homeCfPct: number
  awayCfPct: number
  /** Score ENTERING the period. */
  homeGoalsBefore: number
  awayGoalsBefore: number
}

const ord = (p: number) => (p >= 4 ? 'OT' : p === 1 ? '1st' : p === 2 ? '2nd' : '3rd')

export function composePeriodInsight(i: PeriodInsightInput): string {
  const possHome = i.homeCfPct >= i.awayCfPct
  const possTeam = possHome ? i.homeAbbrev : i.awayAbbrev
  const cf = Math.round((possHome ? i.homeCfPct : i.awayCfPct) * 100)
  const tied = i.homeGoalsBefore === i.awayGoalsBefore
  const homeLed = i.homeGoalsBefore > i.awayGoalsBefore

  // Branch 1: trailing team won possession → score effects, not control.
  if (!tied && homeLed !== possHome) {
    return `${possTeam} pushed the ${ord(i.period)} (${cf}% CF) but was chasing the game.`
  }
  // Branch 2: leading team also controlled play → genuine control.
  if (!tied && homeLed === possHome) {
    return `${possTeam} controlled the ${ord(i.period)} (${cf}% CF) with the lead.`
  }
  // Branch 3: tied entering the period → a straight possession read.
  return `${possTeam} carried the ${ord(i.period)} (${cf}% CF).`
}
