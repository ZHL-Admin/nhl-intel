import { apiClient } from './client'
import {
  PlayerSearchResult, LineFitProjection, TeamLines, TradeFitResult, LineSuggestions, BestTeamFit,
  RosterSlotInput, RosterEvaluateResponse, RosterSuggestResponse,
} from './types'

/** Line-aware 'great fit' candidates for one depth-chart slot (caliber-tiered to the line). */
export async function rosterSuggest(
  team_id: number, slot: string, roster?: RosterSlotInput[], season?: string,
): Promise<RosterSuggestResponse> {
  const response = await apiClient.post<RosterSuggestResponse>('/tools/roster-suggest', {
    team_id, slot, roster, ...(season ? { season } : {}),
  })
  return response.data
}

/** Evaluate a user-built roster (Roster Builder). roster omitted => auto-build the optimal lineup
 * from the team's current roster; optimize=true => re-sort the placed pool optimally. */
export async function rosterEvaluate(
  team_id: number, roster?: RosterSlotInput[], optimize = false, season?: string,
): Promise<RosterEvaluateResponse> {
  const response = await apiClient.post<RosterEvaluateResponse>('/tools/roster-evaluate', {
    team_id, roster, optimize, ...(season ? { season } : {}),
  })
  return response.data
}

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

/** The teams whose gaps a player fills best, ranked (Phase 5.3). */
export async function bestTeamFits(player_id: number, excludeTeam?: number, season?: string): Promise<BestTeamFit[]> {
  const response = await apiClient.get<BestTeamFit[]>('/tools/trade-fit/best-teams', {
    params: { player_id, ...(excludeTeam ? { exclude_team: excludeTeam } : {}), ...(season ? { season } : {}) },
  })
  return response.data
}
