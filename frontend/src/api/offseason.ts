import { apiClient } from './client'
import { RosterForecastRow, OffseasonTeamDetail } from './types'

/** League board: every team's projected next-season rating, delta, rank and band (Phase 6 tool). */
export async function getOffseasonBoard(season?: string): Promise<RosterForecastRow[]> {
  const response = await apiClient.get<RosterForecastRow[]>('/tools/offseason', {
    params: { ...(season ? { season } : {}) },
  })
  return response.data
}

/** One team's full offseason decomposition: move ledger, components, projected lineup, verdict. */
export async function getTeamOffseason(teamId: number, season?: string): Promise<OffseasonTeamDetail> {
  const response = await apiClient.get<OffseasonTeamDetail>(`/teams/${teamId}/offseason`, {
    params: { ...(season ? { season } : {}) },
  })
  return response.data
}
