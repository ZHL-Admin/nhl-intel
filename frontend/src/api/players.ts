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
} from './types'

/**
 * Fetch detailed information for a specific player.
 */
export async function getPlayerDetail(playerId: number): Promise<PlayerDetail> {
  const response = await apiClient.get<PlayerDetail>(`/players/${playerId}`)
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
