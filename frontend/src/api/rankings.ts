import { apiClient } from './client'
import { PowerRatingRow, DeservedStandingRow } from './types'

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
