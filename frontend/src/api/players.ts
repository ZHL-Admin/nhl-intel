/**
 * Player API endpoints.
 */
import { apiClient } from './client'
import {
  PlayerDetail,
  PlayerTrends,
  PlayerGamelog,
  PlayerShots,
  PlayerVsOpponent,
  PlayerSituational,
  ArchetypeRankRow,
  PlayerReconciliation,
  DivergenceBoardRow,
  PlayerTrajectory,
} from './types'

/**
 * Fetch detailed information for a specific player.
 */
export async function getPlayerDetail(playerId: number, season?: string): Promise<PlayerDetail> {
  const response = await apiClient.get<PlayerDetail>(`/players/${playerId}`, {
    params: season ? { season } : undefined,
  })
  return response.data
}

/**
 * Fetch rolling trends for a specific player.
 */
export async function getPlayerTrends(playerId: number): Promise<PlayerTrends> {
  const response = await apiClient.get<PlayerTrends>(`/players/${playerId}/trends`)
  return response.data
}

/**
 * Fetch game-by-game log for a specific player.
 */
export async function getPlayerGamelog(playerId: number): Promise<PlayerGamelog> {
  const response = await apiClient.get<PlayerGamelog>(`/players/${playerId}/gamelog`)
  return response.data
}

/**
 * Fetch shot location data for a specific player.
 */
export async function getPlayerShots(playerId: number): Promise<PlayerShots> {
  const response = await apiClient.get<PlayerShots>(`/players/${playerId}/shots`)
  return response.data
}

/**
 * Fetch player stats vs specific opponent.
 */
export async function getPlayerVsOpponent(
  playerId: number,
  opponentId: number
): Promise<PlayerVsOpponent> {
  const response = await apiClient.get<PlayerVsOpponent>(
    `/players/${playerId}/vs/${opponentId}`
  )
  return response.data
}

/**
 * Fetch situational statistics for a player.
 */
export async function getPlayerSituational(
  playerId: number,
  season?: string
): Promise<PlayerSituational[]> {
  const response = await apiClient.get<PlayerSituational[]>(
    `/players/${playerId}/situational`,
    {
      params: {
        season: season || 'current'
      },
    }
  )
  return response.data
}

/** The highest-value skaters overall by composite total, optionally by position (Phase 4.2). */
export async function getOverallLeaders(
  position: 'ALL' | 'F' | 'D' = 'ALL', season?: string, limit = 50,
): Promise<ArchetypeRankRow[]> {
  const response = await apiClient.get<ArchetypeRankRow[]>('/players/leaders', {
    params: { position, limit, ...(season ? { season } : {}) },
  })
  return response.data
}

/** Players whose primary archetype is `archetype`, ranked by composite total (Phase 4.2). */
export async function getArchetypeRanking(
  archetype: string, season?: string, limit = 50,
): Promise<ArchetypeRankRow[]> {
  const response = await apiClient.get<ArchetypeRankRow[]>(
    `/players/archetypes/${encodeURIComponent(archetype)}`,
    { params: { limit, ...(season ? { season } : {}) } },
  )
  return response.data
}

/** Eye-test reconciliation: clutch + consistency + coach trust (Phase 4.3). */
export async function getPlayerReconciliation(playerId: number, season?: string): Promise<PlayerReconciliation> {
  const response = await apiClient.get<PlayerReconciliation>(`/players/${playerId}/reconciliation`, {
    params: season ? { season } : undefined,
  })
  return response.data
}

/** Divergence board: coach-trust vs isolated value, with explanations (Phase 4.3). */
export async function getDivergenceBoard(season?: string): Promise<DivergenceBoardRow[]> {
  const response = await apiClient.get<DivergenceBoardRow[]>('/players/divergence-board', {
    params: season ? { season } : undefined,
  })
  return response.data
}

/** Career trajectory: aging-curve band, player path, twins, physical overlay (Phase 4.4). */
export async function getPlayerTrajectory(playerId: number): Promise<PlayerTrajectory> {
  const response = await apiClient.get<PlayerTrajectory>(`/players/${playerId}/trajectory`)
  return response.data
}

/** Skater skills radar: spokes + derived labels (Part B). */
export async function getPlayerRadar(playerId: number | string, season?: string): Promise<import('./types').PlayerRadar> {
  const r = await apiClient.get(`/players/${playerId}/radar`, { params: season ? { season } : undefined })
  return r.data
}

/** Fast single-query season stat line for the Players-card expansion. */
export async function getPlayerSummary(playerId: number | string, season?: string): Promise<import('./types').PlayerSummary> {
  const r = await apiClient.get(`/players/${playerId}/summary`, { params: season ? { season } : undefined })
  return r.data
}

/** Base stats + within-position ranks + light bio for the inline row expansion. */
export async function getPlayerPreview(playerId: number | string, season?: string): Promise<import('./types').PlayerPreview> {
  const r = await apiClient.get(`/players/${playerId}/preview`, { params: season ? { season } : undefined })
  return r.data
}

/** Position-scoped total-value (WAR) slice centered on this player, for the player-page header
 * ranking module. Same lens/ordering/value as the Players index default sort. 404 if unqualified. */
export async function getPlayerValueNeighbors(
  playerId: number | string, season?: string,
): Promise<import('./types').ValueNeighborhood> {
  const r = await apiClient.get(`/players/${playerId}/value-neighbors`, { params: season ? { season } : undefined })
  return r.data
}

/** Deployment-efficiency board (actual vs justified usage) for a situation lens. */
export async function getDeploymentBoard(situation: string, limit = 15): Promise<import('./types').DeploymentBoard> {
  const r = await apiClient.get('/players/deployment-board', { params: { situation, limit } })
  return r.data
}

/** A player's full deployment profile across situations (the board-row expansion). */
export async function getPlayerDeployment(playerId: number | string): Promise<import('./types').PlayerDeploymentEntry[]> {
  const r = await apiClient.get(`/players/${playerId}/deployment`)
  return r.data
}
