/**
 * TypeScript interfaces for all API response shapes.
 * These match the Pydantic models in backend/models/schemas.py
 */

// ============================================================================
// Game Types
// ============================================================================

export interface GameDate {
  date: string
  gameCount: number
}

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
  zone_entry_proxy_success_rate: number | null
  shot_attempts: number | null
  shots_on_goal: number | null
  // Period-by-period breakdowns
  cf_p1?: number | null
  cf_p2?: number | null
  cf_p3?: number | null
  ca_p1?: number | null
  ca_p2?: number | null
  ca_p3?: number | null
  cf_pct_p1?: number | null
  cf_pct_p2?: number | null
  cf_pct_p3?: number | null
  xgf_p1?: number | null
  xgf_p2?: number | null
  xgf_p3?: number | null
  xga_p1?: number | null
  xga_p2?: number | null
  xga_p3?: number | null
  gf_p1?: number | null
  gf_p2?: number | null
  gf_p3?: number | null
  ga_p1?: number | null
  ga_p2?: number | null
  ga_p3?: number | null
  // Scorer-bias adjusted events + score/opponent-adjusted shares (Phase 2.3)
  hits?: number | null
  giveaways?: number | null
  takeaways?: number | null
  hits_adj?: number | null
  giveaways_adj?: number | null
  takeaways_adj?: number | null
  cf_pct_score_adj?: number | null
  xgf_pct_score_adj?: number | null
  cf_pct_opp_adj?: number | null
  xgf_pct_opp_adj?: number | null
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
  first_assists?: number | null
  second_assists?: number | null
  ihdcf?: number | null
  pim?: number | null
  rush_attempts?: number | null
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

  // In-house xG + additive decomposition (Phase 2.2); present for unblocked,
  // non-empty-net shots. Contributions are probability-space deltas that, with
  // base_rate, sum to xg.
  xg?: number | null
  base_rate?: number | null
  xg_contrib_location?: number | null
  xg_contrib_shot_type?: number | null
  xg_contrib_strength?: number | null
  xg_contrib_sequence?: number | null
  xg_contrib_game_state?: number | null
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
  zone_entry_proxy_success_rate: number | null
  cf_pct_rank: number
  xgf_pct_rank: number
  hdcf_per60_rank: number
  hdca_per60_rank: number
  gf_per_gp_rank: number
  ga_per_gp_rank: number
  zone_entry_proxy_success_rate_rank: number | null
  // Zone time percentages
  oz_pct?: number | null
  nz_pct?: number | null
  dz_pct?: number | null
  // Faceoff statistics
  faceoff_win_pct?: number | null
  oz_faceoff_win_pct?: number | null
  nz_faceoff_win_pct?: number | null
  dz_faceoff_win_pct?: number | null
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
  // New fields
  first_assists?: number | null
  second_assists?: number | null
  ihdcf_per60?: number | null
  ozs_pct?: number | null
  dzs_pct?: number | null
  nzs_pct?: number | null
  relative_cf_pct?: number | null
  relative_xgf_pct?: number | null
  actual_shooting_pct?: number | null
  expected_shooting_pct?: number | null
  shooting_luck_delta?: number | null
  // Composite stack + archetype mix (Phase 4.2)
  composite_total?: number | null
  composite_total_sd?: number | null
  composite_components?: CompositeComponent[]
  archetypes?: ArchetypeWeight[]
  primary_archetype?: string | null
  value?: PlayerValue | null
}

export interface ValueGapRead {
  case: string  // value_over_impact | impact_over_value | aligned
  headline: string
  body: string
}
/** One within-position percentile that feeds the Overall summary (0..1). */
export interface OverallComponent {
  key: string
  label: string
  percentile?: number | null
}
/** Per-player Overall — a within-position percentile SUMMARY (card-only, never a sort key).
 * Always rendered WITH its `components` (the percentiles it averaged). */
export interface OverallSummary {
  overall_percentile: number          // 0..1, within position group (F/D) or within goalies
  pos_group?: string | null           // F | D | G
  components: OverallComponent[]
  weights?: Record<string, number>
}
export interface PlayerValue {
  gar: number
  war: number
  gar_sd: number
  war_sd: number
  components: CompositeComponent[]
  value_percentile?: number | null   // 0..1, within position
  impact_goals?: number | null
  impact_percentile?: number | null  // 0..1, within position
  gap_percentile_points?: number | null
  read?: ValueGapRead | null
  production_r: number
  rapm_r: number
  finishing_r: number
  overall?: OverallSummary | null
}
/** A goalie's GAR/WAR block (reliability-shrunk goals saved above a backup) on the cross-position
 * WAR scale. `raw_war` is the pre-regression value, shown only as a small transparency readout. */
export interface GoalieValue {
  gar: number
  war: number
  gar_sd: number
  war_sd: number
  components: CompositeComponent[]    // goalie save-tier components
  war_percentile?: number | null      // 0..1, within goalies
  raw_war?: number | null             // pre-regression WAR (transparency)
}
/** A row on the value leaderboard — skater OR goalie. The mixed (`all`) list sorts by WAR, the
 * only cross-position-comparable unit. `component_kind` selects the bar colour vocabulary. */
export interface ValueRankingRow {
  player_id: number
  player_name?: string | null
  team_abbrev?: string | null
  position?: string | null
  entity_kind?: 'skater' | 'goalie'
  component_kind?: 'skater' | 'goalie'
  gar: number
  war: number
  gar_sd?: number | null
  war_sd?: number | null
  components: CompositeComponent[]
}

export interface CompositeComponent {
  key: string
  label: string
  value: number
}
export interface ArchetypeWeight {
  archetype: string
  weight: number
}
export interface ArchetypeRankRow {
  player_id: number
  player_name?: string | null
  team_abbrev?: string | null
  position?: string | null
  composite_total: number
  composite_total_sd?: number | null
  components: CompositeComponent[]
  archetype_weight: number
  primary_archetype?: string | null
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

// Win probability + leverage (Phase 2.4)
export interface WinProbPoint {
  elapsed_seconds: number
  home_wp: number
  leverage: number
}

export interface WinProbGoalSwing {
  elapsed_seconds: number
  team_id: number | null
  scorer_name: string | null
  wp_before: number
  wp_after: number
  swing: number
}

export interface WinProbSeries {
  game_id: number
  model_version: string | null
  series: WinProbPoint[]
  goal_swings: WinProbGoalSwing[]
}

// Goalie GSAx season line (Phase 2.5)
export interface GoalieSeason {
  goalie_id: number
  goalie_name: string | null
  season: string
  team_id: number | null
  games_played: number
  shots_faced: number
  saves: number
  goals_against: number
  save_pct: number | null
  xga: number
  gsax: number
  our_hd_gsax: number | null
  our_hd_save_pct: number | null
  last10_gsax: number | null
  edge_last10_save_pct: number | null
  edge_games_above_900: number | null
  value?: GoalieValue | null
  overall?: OverallSummary | null
}

// ============================================================================
// Advanced Analytics Types
// ============================================================================

export interface XGWormPoint {
  game_time_seconds: number
  cumulative_xg_diff: number
  home_xg: number
  away_xg: number
  event_type?: string | null
  team_id?: number | null
  label?: string | null
}

export interface PressurePoint {
  game_time_seconds: number
  home_rate: number
  away_rate: number
}

export interface GoaltenderStat {
  player_id: number
  goalie_name: string
  team_abbrev: string
  shots_against: number
  goals_against: number
  gsax: number
  headshot?: string | null
}

export interface TeamComparisonStats {
  home_team_id: number
  away_team_id: number
  home_goals: number
  away_goals: number
  home_sog: number
  away_sog: number
  home_pp_goals: number
  away_pp_goals: number
  home_penalties: number
  away_penalties: number
  home_pim: number
  away_pim: number
  home_hits: number
  away_hits: number
  home_faceoff_wins: number
  away_faceoff_wins: number
  home_blocks: number
  away_blocks: number
  home_giveaways: number
  away_giveaways: number
  home_takeaways: number
  away_takeaways: number
}

export interface GoalDetail {
  game_time_seconds: number
  period: number
  time_in_period: string
  team_id: number
  team_abbrev: string
  strength: string
  scorer_id?: number | null
  scorer_name?: string | null
  scorer_headshot?: string | null
  assists: string[]
}

export interface SpecialTeamsStat {
  team_abbrev: string
  is_home: boolean
  pp_goals: number
  pp_opp: number
  pp_xg: number
  pp_shots: number
  pk_saves: number
  pk_shots: number
}

export interface GoalieDangerStat {
  player_id: number
  goalie_name: string
  team_abbrev: string
  high_saves: number
  high_shots: number
  med_saves: number
  med_shots: number
  low_saves: number
  low_shots: number
  gsax: number
}

export interface ShotQualityRow {
  band: string
  home_abbrev: string
  away_abbrev: string
  home_attempts: number
  home_goals: number
  away_attempts: number
  away_goals: number
}

export interface SkaterImpact {
  player_id: number
  player_name: string
  team_abbrev: string
  position: string
  toi: string
  toi_seconds: number
  goals: number
  assists: number
  points: number
  shots: number
  ixg: number
  ihdcf: number
}

export interface PlayerZoneDeployment {
  player_id: number
  season: string
  team_id: number
  oz_starts: number
  nz_starts: number
  dz_starts: number
  total_starts: number
  ozs_pct: number
  nzs_pct: number
  dzs_pct: number
}

export interface PlayerSituational {
  player_id: number
  season: string
  situation: string
  toi_per_gp?: number | null
  points_per60?: number | null
  goals_per60?: number | null
  ixg_per60?: number | null
  cf_pct?: number | null
  hdcf_per60?: number | null
}

export interface TeamSituational {
  team_id: number
  game_id: number
  situation: string
  toi_seconds?: number | null
  cf_pct?: number | null
  xgf_pct?: number | null
  hdcf_pct?: number | null
  gf?: number | null
  ga?: number | null
  shots_for?: number | null
  shots_against?: number | null
  xgf?: number | null
  xga?: number | null
  hdcf_per60?: number | null
  hdca_per60?: number | null
  zone_entry_proxy_success_rate?: number | null
  shot_attempts?: number | null
}

// ============================================================================
// Game Context (Phase 1.3: landing + right-rail enrichment)
// ============================================================================

export interface ContextScratch {
  player_id: number
  player_name: string
}

export interface ContextGoalHighlight {
  event_id: number
  period?: number | null
  scorer_player_id?: number | null
  time_in_period?: string | null
  highlight_url?: string | null
  ppt_replay_url?: string | null
}

export interface ContextSeriesGame {
  game_id?: number | null
  game_date?: string | null
  away_abbrev?: string | null
  away_score?: number | null
  home_abbrev?: string | null
  home_score?: number | null
}

export interface ContextTeamStat {
  category: string
  away_value?: string | null
  home_value?: string | null
}

export interface ContextLast10 {
  team_abbrev?: string | null
  l10_wins?: number | null
  l10_losses?: number | null
  l10_ot_losses?: number | null
  league_rank?: number | null
  points?: number | null
}

export interface GameContext {
  game_id: number
  away_team_id?: number | null
  home_team_id?: number | null
  away_head_coach?: string | null
  home_head_coach?: string | null
  away_scratches: ContextScratch[]
  home_scratches: ContextScratch[]
  season_series_away_wins?: number | null
  season_series_home_wins?: number | null
  season_series_needed_to_win?: number | null
  season_series_games: ContextSeriesGame[]
  team_game_stats: ContextTeamStat[]
  goal_highlights: ContextGoalHighlight[]
  away_last10?: ContextLast10 | null
  home_last10?: ContextLast10 | null
}

// --- Rankings (Phase 3.1) ---
export interface PowerRatingRow {
  team_id: number
  team_abbrev?: string | null
  season: string
  games_played: number
  total_rating: number
  rating_se?: number | null
  trajectory_15d?: number | null
  play_5v5: number
  finishing: number
  goaltending: number
  special_teams: number
  contrib_play_5v5: number
  contrib_finishing: number
  contrib_goaltending: number
  contrib_special_teams: number
}

export interface DeservedStandingRow {
  team_id: number
  team_abbrev?: string | null
  season: string
  games: number
  actual_points: number
  deserved_points: number
  deserved_p10: number
  deserved_p90: number
  luck_delta: number
}

// --- Team identity + style map (Phase 3.2) ---
export interface IdentityMetric {
  key: string
  value?: number | null
  percentile?: number | null
}
export interface TeamIdentityWindow {
  window: string
  games: number
  metrics: IdentityMetric[]
}
export interface TeamIdentity {
  team_id: number
  team_abbrev?: string | null
  season: string
  league_size: number
  windows: TeamIdentityWindow[]
}
export interface StyleMapTeam {
  team_id: number
  team_abbrev?: string | null
  x: number
  y: number
}
export interface StyleMap {
  season: string
  x_pos_desc: string
  x_neg_desc: string
  y_pos_desc: string
  y_neg_desc: string
  teams: StyleMapTeam[]
}

// --- Streak Doctor (Phase 3.3) ---
export interface StreakComponent {
  key: string
  label: string
  value: number
  share: number
}
export interface StreakCard {
  team_id: number
  team_abbrev?: string | null
  season: string
  window_games: number
  games: number
  run_word: string
  verdict: string
  total_deviation: number
  sustainability: number
  is_notable: boolean
  points_pace: number
  points_pace_z: number
  streak: number
  components: StreakComponent[]
}

// --- Reconciliation + divergence (Phase 4.3) ---
export interface ClutchProfile {
  n_shots: number
  raw_ixg: number
  clutch_ixg: number
  clutch_delta: number
  p_value: number
  confidence: string
}
export interface GameScorePoint { game_date: string; game_score: number }
export interface ConsistencyProfile {
  games: number
  mean_gs: number
  sd_gs: number
  iqr_gs: number
  good_game_share: number
  no_show_share: number
  consistency_index: number
  game_scores: GameScorePoint[]
}
export interface CoachTrustProfile {
  trust_score: number
  pk_share: number
  protect_lead_rate: number
  road_home_ratio: number
}
export interface PlayerReconciliation {
  player_id: number
  season: string
  clutch?: ClutchProfile | null
  consistency?: ConsistencyProfile | null
  coach_trust?: CoachTrustProfile | null
}
export interface DivergenceBoardRow {
  player_id: number
  player_name?: string | null
  position?: string | null
  team_abbrev?: string | null
  side: string
  divergence: number
  trust_z: number
  composite_z: number
  composite_total: number
  explanation: string
  archetype?: string | null
}

// --- Trajectory (Phase 4.4) ---
export interface TrajectoryCurvePoint { age: number; curve_value: number }
export interface TrajectoryPathPoint { age: number; season: string; points82: number }
export interface TwinEntry {
  twin_id: number
  twin_name?: string | null
  similarity: number
  through_age: number
  reduced_features: boolean
  next3_points82?: number | null
}
export interface PhysicalPoint { season: string; burst_rate?: number | null; max_speed?: number | null }
export interface PlayerTrajectory {
  player_id: number
  archetype?: string | null
  curve_label?: string | null
  curve: TrajectoryCurvePoint[]
  path: TrajectoryPathPoint[]
  twins: TwinEntry[]
  physical: PhysicalPoint[]
  burst_flag_enabled: boolean
}

// --- Phase 5: signature tools (Lineup Lab) ---
export interface PlayerSearchResult {
  player_id: number
  name?: string | null
  team_id?: number | null
  team_abbrev?: string | null
  position?: string | null
  headshot_url?: string | null
  archetype?: string | null
}
export interface LineMemberOut {
  player_id: number
  name?: string | null
  position?: string | null
  archetype?: string | null
  off_impact?: number | null
  def_impact?: number | null
  finishing?: number | null
  toi_5v5?: number | null
}
export interface ObservedBlend {
  observed_minutes: number
  observed_xgf_pct: number
  model_xgf_pct: number
  w_obs: number
}
export interface LineFitProjection {
  line_type: string
  player_ids: number[]
  grade: string
  projected_xgf_pct: number
  interval_low?: number | null
  interval_high?: number | null
  xgf_per60?: number | null
  xga_per60?: number | null
  grade_sentence?: string | null
  reasons: string[]
  risk?: string | null
  observed_blend?: ObservedBlend | null
  deeper_extrapolation: boolean
  rookie_widened: boolean
  members: LineMemberOut[]
  limitations?: string | null
  forward_trio?: LineFitProjection | null
  defense_pair?: LineFitProjection | null
}
export interface BetterFitSwap {
  player_id: number
  name?: string | null
  team_id?: number | null
  team_abbrev?: string | null
  position?: string | null
  headshot_url?: string | null
  archetype?: string | null
  composite_total?: number | null
  swap_xgf_pct: number
  swap_grade: string
  xgf_gain: number
  reasons: string[]
}
export interface SlotSuggestions {
  slot_index: number
  position?: string | null
  current_player_id: number
  current_player_name?: string | null
  candidates: BetterFitSwap[]
}
export interface LineSuggestions {
  season: string
  line_type: string
  slots: SlotSuggestions[]
}

export interface TeamLine {
  line_type: string
  player_ids: number[]
  member_names: string[]
  minutes: number
  observed_xgf_pct?: number | null
  projection?: LineFitProjection | null
}
export interface TeamLines {
  team_id: number
  season: string
  forward_lines: TeamLine[]
  defense_pairs: TeamLine[]
}

// --- Phase 5.3: trade fit + matchup previews ---
export interface NeedComponent {
  key: string
  label: string
  gap: number
  team_value: number
  reference_value: number
}
export interface TeamNeedProfile {
  team_id: number
  season: string
  archetype_needs: NeedComponent[]
  component_needs: NeedComponent[]
}
export interface ArchetypeWeightLite { archetype: string; weight: number }
export interface BestTeamFit {
  team_id: number
  fit_score: number
  reason?: string | null
  top_need_label?: string | null
  top_need_gap?: number | null
}
export interface TradeFitResult {
  player_id: number
  player_name?: string | null
  team_id: number
  season: string
  fit_score: number
  reasons: string[]
  player_archetypes: ArchetypeWeightLite[]
  need_profile?: TeamNeedProfile | null
}
export interface MatchupPreviewTeam {
  team_id: number
  team_abbrev?: string | null
  power_rating?: number | null
  goalie_name?: string | null
  goalie_last10_gsax?: number | null
  fingerprint_top: string[]
}
export interface MatchupPreview {
  game_id: number
  game_state: string
  home: MatchupPreviewTeam
  away: MatchupPreviewTeam
  home_pregame_wp?: number | null
  style_clash: string[]
  season_series?: string | null
  notable_streaks: string[]
}

// --- Skills radar (Part B) ---
export interface RadarSpoke {
  key: string
  label: string
  tag: string            // skill | usage | style | proxy
  value: number
  percentile?: number | null
  sd?: number | null
  present: boolean
}
export interface PlayerRadar {
  player_id: number
  season: string
  pos_group?: string | null
  spokes: RadarSpoke[]
  overall_label?: string | null
  offensive_label?: string | null
  defensive_label?: string | null
  descriptor?: string | null
  baseline?: string | null
}
export interface GoalieRadar {
  goalie_id: number
  season: string
  games_played?: number | null
  spokes: RadarSpoke[]
  baseline?: string | null
}

export interface PlayerSummary {
  player_id: number
  season: string
  games_played: number
  toi_per_gp?: number | null
  goals_per60?: number | null
  assists_per60?: number | null
  points_per60?: number | null
  xgf_pct?: number | null
}

/** One base stat with its within-position rank, for the inline row-expansion table. */
export interface PreviewStat {
  key: string
  label: string
  value?: number | null
  fmt: string                 // int | rate | min | pct1 | pct3 | plus
  rank?: number | null        // 1 = best among qualified peers
  n?: number | null
}
export interface PlayerPreview {
  player_id: number
  season: string
  pos_group?: string | null
  age?: number | null
  shoots?: string | null
  stats: PreviewStat[]
}
export interface GoaliePreview {
  goalie_id: number
  season: string
  age?: number | null
  catches?: string | null
  stats: PreviewStat[]
}
