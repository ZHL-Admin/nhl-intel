import { apiClient } from './client'
import { PlayerSearchResult, LineFitProjection, TeamLines, TradeFitResult, LineSuggestions } from './types'

/** Current-roster players matching `q` for the PlayerPicker (Phase 5.2). */
export async function searchPlayers(q: string, limit = 12, season?: string): Promise<PlayerSearchResult[]> {
  const response = await apiClient.get<PlayerSearchResult[]>('/players/search', {
    params: { q, limit, ...(season ? { season } : {}) },
  })
  return response.data
}

/** Project a hypothetical line (2 D, 3 F, or a 5-skater unit) — Phase 5.1 engine. */
export async function lineFit(player_ids: number[], season?: string): Promise<LineFitProjection> {
  const response = await apiClient.post<LineFitProjection>('/tools/line-fit', { player_ids, season })
  return response.data
}

/** Per-slot "better fit" suggestions for a line — same-caliber swaps ranked by xGF gain. */
export async function lineFitSuggestions(player_ids: number[], season?: string): Promise<LineSuggestions> {
  const response = await apiClient.post<LineSuggestions>('/tools/line-fit/suggestions', { player_ids, season })
  return response.data
}

/** A team's current lines (last 10 games) with observed results + projected grades. */
export async function getTeamLines(teamId: number, season?: string): Promise<TeamLines> {
  const response = await apiClient.get<TeamLines>(`/teams/${teamId}/lines`, {
    params: season ? { season } : undefined,
  })
  return response.data
}

/** Score how well a player addresses a team's needs (Phase 5.3). */
export async function tradeFit(player_id: number, team_id: number, season?: string): Promise<TradeFitResult> {
  const response = await apiClient.post<TradeFitResult>('/tools/trade-fit', { player_id, team_id, season })
  return response.data
}
