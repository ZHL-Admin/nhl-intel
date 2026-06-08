/**
 * Team API endpoints.
 */
import { apiClient } from './client'
import { TeamDetail, TeamTrends, TeamRoster, TeamVsOpponent, PlayerZoneDeployment, TeamSituational } from './types'

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
export async function getTeamRoster(teamId: number): Promise<TeamRoster> {
  const response = await apiClient.get<TeamRoster>(`/teams/${teamId}/roster`)
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
