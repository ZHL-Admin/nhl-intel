import { apiClient } from './client'
import { PowerRatingRow, DeservedStandingRow, ValueRankingRow } from './types'

// RINK THEORY §4.2 — the standing-number payload for the Power Ratings table and
// the Home rail. Backed by the new GET /ratings (merges the existing power +
// deserved queries; data_through = MAX(game_date)).
export interface TeamRating {
  rank: number
  team_id: number
  team_abbrev: string | null
  rating: number
  comp_5v5: number
  comp_finishing: number
  comp_goaltending: number
  comp_special_teams: number
  luck: number | null
}
export interface RatingsPayload {
  season: string
  data_through: string | null
  teams: TeamRating[]
}

/** The Power Ratings payload: per-team rating + four components + luck, DATA THROUGH stamp. */
export async function getRatings(season?: string): Promise<RatingsPayload> {
  const response = await apiClient.get<RatingsPayload>('/ratings', {
    params: season ? { season } : undefined,
  })
  return response.data
}

/** Current power ratings, highest first (Phase 3.1). */
export async function getPowerRankings(season?: string): Promise<PowerRatingRow[]> {
  const response = await apiClient.get<PowerRatingRow[]>('/rankings/power', {
    params: season ? { season } : undefined,
  })
  return response.data
}

/** Actual vs Monte-Carlo deserved points, by deserved points (Phase 3.1). */
export async function getDeservedStandings(season?: string): Promise<DeservedStandingRow[]> {
  const response = await apiClient.get<DeservedStandingRow[]>('/rankings/deserved', {
    params: season ? { season } : undefined,
  })
  return response.data
}

export type ValueScope = 'skaters' | 'goalies' | 'all'
export type ValueSort = 'confidence' | 'point'

/** Value leaderboard — goals/wins above replacement (Phase 6 GAR + cross-position WAR).
 * scope=skaters|goalies sort within position; scope=all is a mixed list ranked by WAR (the only
 * cross-position-comparable unit). sort='confidence' (default) ranks by the lower-confidence bound
 * (war − k·band) so tight-band skaters aren't buried under wide-band goalies; 'point' ranks by the
 * raw (shrunk) point estimate. `position` applies to the skaters scope only. */
export async function getValueRankings(
  scope: ValueScope = 'skaters',
  position: 'ALL' | 'F' | 'D' = 'ALL',
  season?: string,
  limit = 50,
): Promise<ValueRankingRow[]> {
  // M3.5/D14: the endpoint ranks by assessed_war; the deprecated `sort` param is no longer sent.
  const response = await apiClient.get<ValueRankingRow[]>('/rankings/value', {
    params: { scope, position, limit, ...(season ? { season } : {}) },
  })
  return response.data
}
