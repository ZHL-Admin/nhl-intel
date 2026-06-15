import { apiClient } from './client'
import { GoalieSeason } from './types'

/** Fetch a goalie's GSAx season line (incl. the NHL Edge second opinion). Phase 2.5. */
export async function getGoalieSeason(goalieId: number, season?: string): Promise<GoalieSeason> {
  const response = await apiClient.get<GoalieSeason>(`/goalies/${goalieId}`, {
    params: season ? { season } : undefined,
  })
  return response.data
}
