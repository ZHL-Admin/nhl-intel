/**
 * Team API endpoints.
 */
import { apiClient } from './client'
import { TeamDetail, TeamTrends, TeamRoster, TeamVsOpponent, PlayerZoneDeployment, TeamSituational, TeamIdentity, StyleMap, StreakCard, StandingsRow, TeamInsight } from './types'

/**
 * Fetch detailed information for a specific team.
 */
export async function getTeamDetail(teamId: number): Promise<TeamDetail> {
  const response = await apiClient.get<TeamDetail>(`/teams/${teamId}`)
  return response.data
}

/**
 * Fetch rolling trends for a specific team.
 */
export async function getTeamTrends(teamId: number): Promise<TeamTrends> {
  const response = await apiClient.get<TeamTrends>(`/teams/${teamId}/trends`)
  return response.data
}

/**
 * Fetch roster for a specific team.
 */
export async function getTeamRoster(teamId: number, season?: string): Promise<TeamRoster> {
  const response = await apiClient.get<TeamRoster>(`/teams/${teamId}/roster`, {
    params: season ? { season } : undefined,
  })
  return response.data
}

/**
 * Fetch head-to-head stats for a team vs specific opponent.
 */
export async function getTeamVsOpponent(
  teamId: number,
  opponentId: number
): Promise<TeamVsOpponent> {
  const response = await apiClient.get<TeamVsOpponent>(
    `/teams/${teamId}/vs/${opponentId}`
  )
  return response.data
}

/**
 * Fetch zone deployment statistics for all players on a team.
 */
export async function getTeamDeployment(
  teamId: number,
  season?: string
): Promise<PlayerZoneDeployment[]> {
  const response = await apiClient.get<PlayerZoneDeployment[]>(
    `/teams/${teamId}/deployment`,
    {
      params: {
        season: season || 'current'
      },
    }
  )
  return response.data
}

/**
 * Fetch situational statistics for a team in a specific game.
 */
export async function getTeamSituational(
  teamId: number,
  gameId: number
): Promise<TeamSituational[]> {
  const response = await apiClient.get<TeamSituational[]>(
    `/teams/${teamId}/situational`,
    {
      params: {
        game_id: gameId
      },
    }
  )
  return response.data
}

/** Team identity fingerprint with per-window metric percentiles (Phase 3.2). */
export async function getTeamIdentity(teamId: number, season?: string): Promise<TeamIdentity> {
  const response = await apiClient.get<TeamIdentity>(`/teams/${teamId}/identity`, {
    params: season ? { season } : undefined,
  })
  return response.data
}

/** League style map: 2D PCA of team fingerprints + axis annotations (Phase 3.2). */
export async function getStyleMap(season?: string): Promise<StyleMap> {
  const response = await apiClient.get<StyleMap>('/teams/style-map', {
    params: season ? { season } : undefined,
  })
  return response.data
}

/** Streak Doctor card for a team (last-N run decomposition). Phase 3.3. */
export async function getTeamStreak(teamId: number, window = 10, season?: string): Promise<StreakCard> {
  const response = await apiClient.get<StreakCard>(`/teams/${teamId}/streak`, {
    params: { window, ...(season ? { season } : {}) },
  })
  return response.data
}

/** Current league standings (latest row per team). Sliced to a division for the StandingsLadder. */
export async function getStandings(season?: string): Promise<StandingsRow[]> {
  const response = await apiClient.get<StandingsRow[]>('/teams/standings', {
    params: season ? { season } : undefined,
  })
  return response.data
}

/** Generated Overview quick-insight cards for a team (engine copy). Most-salient first. */
export async function getTeamInsights(teamId: number, season?: string): Promise<TeamInsight[]> {
  const response = await apiClient.get<TeamInsight[]>(`/teams/${teamId}/insights`, {
    params: season ? { season } : undefined,
  })
  return response.data
}
