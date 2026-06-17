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

/** Value leaderboard — goals/wins above replacement (Phase 6 GAR + cross-position WAR).
 * scope=skaters|goalies sort by their native GAR; scope=all is a mixed skater+goalie list sorted
 * by WAR (the only cross-position-comparable unit). `position` applies to the skaters scope only. */
export async function getValueRankings(
  scope: ValueScope = 'skaters',
  position: 'ALL' | 'F' | 'D' = 'ALL',
  season?: string,
  limit = 50,
): Promise<ValueRankingRow[]> {
  const response = await apiClient.get<ValueRankingRow[]>('/rankings/value', {
    params: { scope, position, limit, ...(season ? { season } : {}) },
  })
  return response.data
}
