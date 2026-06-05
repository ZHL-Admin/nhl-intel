/**
 * Game API endpoints.
 */
import { apiClient } from './client'
import { Game, GameDetail, GamePlayerStats } from './types'

/**
 * Fetch all games for a specific date.
 */
export async function getGamesByDate(date: string): Promise<Game[]> {
  const response = await apiClient.get<Game[]>(`/games/`, {
    params: {
      start_date: date,
      end_date: date
    },
  })
  return response.data
}

/**
 * Fetch detailed information for a specific game.
 */
export async function getGameDetail(gameId: number): Promise<GameDetail> {
  const response = await apiClient.get<GameDetail>(`/games/${gameId}`)
  return response.data
}

/**
 * Fetch player statistics for a specific game.
 */
export async function getGamePlayerStats(gameId: number): Promise<GamePlayerStats> {
  const response = await apiClient.get<GamePlayerStats>(`/games/${gameId}/players`)
  return response.data
}
