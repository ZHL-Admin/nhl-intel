/**
 * Today's Lead selection + headline templates (Blueprint 2.1 / P7). Deterministic: rules are evaluated
 * in order, first match wins. Each headline is filled from the SAME payload the visual renders
 * (consistency rule). Live/upcoming rules (1–2) fire only when today's games are present.
 */
import type { PowerRatingRow, DeservedStandingRow, RosterForecastRow, Game } from '../api/types'
import { TRAJECTORY_MEANINGFUL_MOVE } from './metrics'

export type LeadKind = 'live' | 'upset' | 'mover' | 'luck' | 'offseason'

export interface Lead {
  kind: LeadKind
  kicker: string
  headline: string
  dek: string
  link: { to: string; label: string }
}

interface Inputs {
  slate: Game[]
  lastNight: Game[]
  power: PowerRatingRow[]
  deserved: DeservedStandingRow[]
  offseason: RosterForecastRow[]
}

const abbr = (t?: string | null, id?: number) => t ?? `#${id ?? ''}`

/** First matching rule wins. Returns null only if nothing qualifies (caller falls back). */
export function selectLead({ slate, lastNight, power, deserved, offseason }: Inputs): Lead | null {
  // Rule 1: a live game (the site can't know the swing without the worm; a live game leads regardless).
  const live = slate.find((g) => g.is_live)
  if (live) {
    return {
      kind: 'live', kicker: 'IT’S HAPPENING',
      headline: `${live.away_team_abbrev} at ${live.home_team_abbrev}, live right now`,
      dek: 'Win probability is swinging — watch it move.',
      link: { to: `/games/${live.game_id}`, label: 'Watch the game →' },
    }
  }

  // Rule 2: yesterday's biggest upset by result — the bigger season-possession dog that still won.
  const finals = lastNight.filter((g) => !g.is_preview && !g.is_live)
  const upset = finals
    .map((g) => {
      const homeWon = (g.home_score ?? 0) > (g.away_score ?? 0)
      const winRank = homeWon ? g.home_cf_rank : g.away_cf_rank
      const loseRank = homeWon ? g.away_cf_rank : g.home_cf_rank
      const edge = winRank != null && loseRank != null ? winRank - loseRank : 0 // winner much worse rank = bigger upset
      return { g, homeWon, edge }
    })
    .filter((x) => x.edge >= 8)
    .sort((a, b) => b.edge - a.edge)[0]
  if (upset) {
    const w = upset.homeWon ? upset.g.home_team_abbrev : upset.g.away_team_abbrev
    const l = upset.homeWon ? upset.g.away_team_abbrev : upset.g.home_team_abbrev
    return {
      kind: 'upset', kicker: 'LAST NIGHT’S SHOCKER',
      headline: `${w} stunned ${l}`,
      dek: 'The underdog by the season’s possession numbers took it anyway.',
      link: { to: `/games/${upset.g.game_id}`, label: 'See how →' },
    }
  }

  // Rule 3: the largest 15-day power mover past the meaningful threshold.
  const mover = [...power]
    .filter((r) => r.trajectory_15d != null && Math.abs(r.trajectory_15d) > TRAJECTORY_MEANINGFUL_MOVE)
    .sort((a, b) => Math.abs(b.trajectory_15d ?? 0) - Math.abs(a.trajectory_15d ?? 0))[0]
  if (mover) {
    const up = (mover.trajectory_15d ?? 0) > 0
    return {
      kind: 'mover', kicker: 'ON THE MOVE',
      headline: `${abbr(mover.team_abbrev, mover.team_id)} is ${up ? 'surging' : 'sliding'}`,
      dek: `Their power rating has moved ${up ? '+' : '−'}${Math.abs(mover.trajectory_15d ?? 0).toFixed(2)} over 15 days.`,
      link: { to: '/teams?view=power', label: 'Power ratings →' },
    }
  }

  // Rule 4: the largest luck gap (actual vs deserved points).
  const luck = [...deserved].sort((a, b) => Math.abs(b.luck_delta) - Math.abs(a.luck_delta))[0]
  if (luck && Math.abs(luck.luck_delta) >= 3) {
    const lucky = luck.luck_delta > 0
    return {
      kind: 'luck', kicker: 'LUCK WATCH',
      headline: `${abbr(luck.team_abbrev, luck.team_id)} has been ${lucky ? 'riding its luck' : 'snakebitten'}`,
      dek: `${Math.round(luck.actual_points)} actual points vs ${Math.round(luck.deserved_points)} deserved.`,
      link: { to: '/teams?view=deserved', label: 'Deserved standings →' },
    }
  }

  // Rule 5 (offseason fallback): the biggest projected offseason WAR change.
  const gainer = [...offseason].sort((a, b) => b.net_delta_war - a.net_delta_war)[0]
  if (gainer) {
    return {
      kind: 'offseason', kicker: 'OFFSEASON BOARD',
      headline: `${abbr(gainer.team_abbrev, gainer.team_id)} got the most better this summer`,
      dek: `Projected ${gainer.net_delta_war >= 0 ? '+' : '−'}${Math.abs(gainer.net_delta_war).toFixed(1)} WAR from the moves they made.`,
      link: { to: '/studio/offseason', label: 'Offseason forecast →' },
    }
  }

  return null
}
