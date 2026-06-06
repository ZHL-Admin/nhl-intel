/**
 * TypeScript interfaces for all API response shapes.
 * These match the Pydantic models in backend/models/schemas.py
 */

// ============================================================================
// Game Types
// ============================================================================

export interface Game {
  game_id: number
  game_date: string
  season: number
  home_team_id: number
  home_team_abbrev: string
  home_team_name?: string
  away_team_id: number
  away_team_abbrev: string
  away_team_name?: string
  home_score: number | null
  away_score: number | null
  is_preview: boolean
  is_live?: boolean
  period?: string
  time_remaining?: string
  game_time?: string
  home_cf_pct?: number
  away_cf_pct?: number
  home_cf_rank?: number
  away_cf_rank?: number
  ai_note?: string
}

export interface TeamGameStats {
  team_id: number
  team_abbrev: string
  score: number | null
  cf_pct: number | null
  hdcf_per60: number | null
  hdca_per60: number | null
  xgf: number | null
  xga: number | null
  zone_entry_success_rate: number | null
  shot_attempts: number | null
}

export interface GameDetail {
  game_id: number
  game_date: string
  season: number
  home_team: TeamGameStats
  away_team: TeamGameStats
  is_preview: boolean
  venue_name: string | null
}

export interface PlayerGameStats {
  player_id: number
  player_name: string
  position: string
  team_id: number
  toi: number | null
  goals: number | null
  assists: number | null
  points: number | null
  shots: number | null
  cf: number | null
  hdcf: number | null
  ixg: number | null
  ixg_per60: number | null
  hot_cold_flag: string | null
}

export interface GamePlayerStats {
  game_id: number
  home_players: PlayerGameStats[]
  away_players: PlayerGameStats[]
}

export interface ShotAttempt {
  x: number
  y: number
  outcome: 'goal' | 'shot_on_goal' | 'missed_shot' | 'blocked_shot'
  situation: string
  team_id: number

  // Goal-specific details (only present for goals)
  scorer_id?: number
  scorer_name?: string
  shot_type?: string
  period?: number
  time_in_period?: string
  assist1_id?: number
  assist1_name?: string
  assist2_id?: number
  assist2_name?: string
  goalie_id?: number
  goalie_name?: string
}

export interface GameShots {
  game_id: number
  home_shots: ShotAttempt[]
  away_shots: ShotAttempt[]
}

// ============================================================================
// Team Types
// ============================================================================

export interface TeamDetail {
  team_id: number
  team_name: string
  team_abbrev: string
  season: number
  games_played: number
  wins: number
  losses: number
  otl: number
  points: number
  cf_pct: number
  hdcf_per60: number
  hdca_per60: number
  xgf_per60: number
  xga_per60: number
  total_goals_for: number
  total_goals_against: number
  zone_entry_success_rate: number | null
}

export interface TeamTrendPoint {
  game_date: string
  value: number
}

export interface TeamTrends {
  team_id: number
  season: number
  cf_pct_5gp: TeamTrendPoint[]
  cf_pct_10gp: TeamTrendPoint[]
  xgf_pct_5gp: TeamTrendPoint[]
  xgf_pct_10gp: TeamTrendPoint[]
  hdcf_per60_5gp: TeamTrendPoint[]
  hdcf_per60_10gp: TeamTrendPoint[]
}

export interface RosterPlayer {
  player_id: number
  player_name: string
  position: string
  games_played: number
  toi_per_gp: number
  points_per60: number
  cf_pct: number
}

export interface TeamRoster {
  team_id: number
  season: number
  forwards: RosterPlayer[]
  defensemen: RosterPlayer[]
  goalies: RosterPlayer[]
}

export interface TeamVsOpponent {
  team_id: number
  opponent_id: number
  season: number
  games_played: number
  small_sample: boolean
  wins: number
  losses: number
  otl: number
  cf_pct: number | null
  hdcf_per60: number | null
  xgf_per60: number | null
}

// ============================================================================
// Player Types
// ============================================================================

export interface PlayerDetail {
  player_id: number
  player_name: string
  position: string
  team_id: number
  team_abbrev: string
  season: number
  games_played: number
  toi_per_gp: number
  points_per60: number
  goals_per60: number
  assists_per60: number
  cf_pct: number
  hdcf_per60: number
}

export interface PlayerTrendPoint {
  game_date: string
  value: number
}

export interface PlayerTrends {
  player_id: number
  season: number
  points_per60_5gp: PlayerTrendPoint[]
  points_per60_10gp: PlayerTrendPoint[]
  cf_pct_5gp: PlayerTrendPoint[]
  cf_pct_10gp: PlayerTrendPoint[]
}

export interface GamelogEntry {
  game_id: number
  game_date: string
  opponent_id: number
  opponent_abbrev: string
  toi: number
  goals: number
  assists: number
  points: number
  shots: number
  cf: number
  hdcf: number
}

export interface PlayerGamelog {
  player_id: number
  season: number
  games: GamelogEntry[]
}

export interface ShotLocation {
  x: number
  y: number
  is_goal: boolean
  danger_level: string
}

export interface PlayerShots {
  player_id: number
  season: number
  total_shots: number
  low_danger: number
  medium_danger: number
  high_danger: number
  shot_locations: ShotLocation[]
}

export interface PlayerVsOpponent {
  player_id: number
  opponent_id: number
  season: number
  games_played: number
  small_sample: boolean
  toi_per_gp: number | null
  points_per60: number | null
  cf_pct: number | null
}
