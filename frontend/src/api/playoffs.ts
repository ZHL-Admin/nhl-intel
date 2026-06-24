/**
 * Playoff bracket predictor API.
 */
import { apiClient } from './client'
import { PlayoffBracket } from './types'

/** Predicted playoff bracket (favorite tree + Monte-Carlo championship odds). */
export async function getPlayoffBracket(season?: string): Promise<PlayoffBracket> {
  const response = await apiClient.get<PlayoffBracket>('/playoffs/bracket', {
    params: season ? { season } : undefined,
  })
  return response.data
}
