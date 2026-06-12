/**
 * Game API endpoints.
 */
import { apiClient } from './client'
import { GameDate, Game, GameDetail, GamePlayerStats, GameShots, XGWormPoint, GoalDetail, PressurePoint, TeamComparisonStats, GoaltenderStat, SpecialTeamsStat, GoalieDangerStat, ShotQualityRow, SkaterImpact } from './types'

/**
 * Fetch list of dates on which games occurred or are scheduled.
 */
export async function getGameDates(fromDate?: string, toDate?: string): Promise<GameDate[]> {
  const params: Record<string, string> = {}
  if (fromDate) params.from_date = fromDate
  if (toDate) params.to_date = toDate

  const response = await apiClient.get<Array<{ game_date: string; game_count: number }>>(`/games/dates`, {
    params,
  })
  // Transform snake_case API response to camelCase
  return response.data.map(d => ({
    date: d.game_date,
    gameCount: d.game_count
  }))
}

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

/**
 * Fetch shot attempt coordinates for a specific game.
 */
export async function getGameShots(gameId: number, situation?: string): Promise<GameShots> {
  const response = await apiClient.get<GameShots>(`/games/${gameId}/shots`, {
    params: {
      situation: situation || 'all'
    },
  })
  return response.data
}

/**
 * Fetch expected goals worm chart data for a specific game.
 */
export async function getGameXGWorm(gameId: number, situation?: string): Promise<XGWormPoint[]> {
  const response = await apiClient.get<XGWormPoint[]>(`/games/${gameId}/xgworm`, {
    params: {
      situation: situation || 'all'
    },
  })
  return response.data
}

/**
 * Fetch detailed goal information (scorer, assists, strength) for a game.
 */
export async function getGameGoals(gameId: number): Promise<GoalDetail[]> {
  const response = await apiClient.get<GoalDetail[]>(`/games/${gameId}/goals`)
  return response.data
}

/**
 * Fetch smoothed shots-per-60 pressure curves for both teams over game time.
 */
export async function getGamePressure(gameId: number): Promise<PressurePoint[]> {
  const response = await apiClient.get<PressurePoint[]>(`/games/${gameId}/pressure`)
  return response.data
}

/** Fetch per-team power-play / penalty-kill detail. */
export async function getGameSpecialTeams(gameId: number): Promise<SpecialTeamsStat[]> {
  const response = await apiClient.get<SpecialTeamsStat[]>(`/games/${gameId}/specialteams`)
  return response.data
}

/** Fetch per-goalie save record split by shot-danger band, with GSAx. */
export async function getGameGoalieDanger(gameId: number): Promise<GoalieDangerStat[]> {
  const response = await apiClient.get<GoalieDangerStat[]>(`/games/${gameId}/goalie-danger`)
  return response.data
}

/** Fetch per-team shot attempts and goals by danger band (shot-quality ladder). */
export async function getGameShotQuality(gameId: number): Promise<ShotQualityRow[]> {
  const response = await apiClient.get<ShotQualityRow[]>(`/games/${gameId}/shot-quality`)
  return response.data
}

/** Fetch per-skater impact lines (real TOI, G/A/P, ixG, iHDCF). */
export async function getGameSkaterImpact(gameId: number): Promise<SkaterImpact[]> {
  const response = await apiClient.get<SkaterImpact[]>(`/games/${gameId}/skater-impact`)
  return response.data
}

/**
 * Fetch box-score team comparison counts (goals, shots, PP, hits, faceoffs, etc.).
 */
export async function getGameTeamStats(gameId: number): Promise<TeamComparisonStats> {
  const response = await apiClient.get<TeamComparisonStats>(`/games/${gameId}/teamstats`)
  return response.data
}

/**
 * Fetch per-goalie lines (shots/goals against) for a game.
 */
export async function getGameGoaltending(gameId: number): Promise<GoaltenderStat[]> {
  const response = await apiClient.get<GoaltenderStat[]>(`/games/${gameId}/goaltending`)
  return response.data
}

/**
 * Fetch games for a specific team in a date range.
 */
export async function getTeamGames(
  teamId: number,
  startDate?: string,
  endDate?: string
): Promise<Game[]> {
  const response = await apiClient.get<Game[]>(`/games/`, {
    params: {
      team_id: teamId,
      start_date: startDate,
      end_date: endDate
    },
  })
  return response.data
}
