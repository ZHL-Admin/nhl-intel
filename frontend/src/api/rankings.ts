import { apiClient } from './client'
import { PowerRatingRow, DeservedStandingRow, ValueRankingRow } from './types'

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
  sort: ValueSort = 'confidence',
): Promise<ValueRankingRow[]> {
  const response = await apiClient.get<ValueRankingRow[]>('/rankings/value', {
    params: { scope, position, limit, sort, ...(season ? { season } : {}) },
  })
  return response.data
}
