"""Pydantic response models for all API endpoints.

Defines the data models for API responses following the dashboard spec.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from datetime import date as DateType


# ============================================================================
# Game Models
# ============================================================================

class GameDate(BaseModel):
    """Date with game count for date navigation."""
    game_date: DateType = Field(description="Date on which games occurred or are scheduled")
    game_count: int = Field(description="Number of games on this date")


class Game(BaseModel):
    """Basic game information for game list."""
    game_id: int
    game_date: DateType
    season: str
    home_team_id: int
    home_team_abbrev: str
    away_team_id: int
    away_team_abbrev: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    is_preview: bool = Field(description="True if game hasn't been played yet")


class TeamGameStats(BaseModel):
    """Team statistics for a single game."""
    team_id: int
    team_abbrev: str
    score: Optional[int] = None
    cf_pct: Optional[float] = Field(None, description="Corsi For percentage")
    hdcf_per60: Optional[float] = Field(None, description="High-danger chances for per 60")
    hdca_per60: Optional[float] = Field(None, description="High-danger chances against per 60")
    xgf: Optional[float] = Field(None, description="Expected goals for")
    xga: Optional[float] = Field(None, description="Expected goals against")
    zone_entry_proxy_success_rate: Optional[float] = Field(None, description="Controlled zone entry success rate")
    shot_attempts: Optional[int] = Field(None, description="Total shot attempts")
    shots_on_goal: Optional[int] = Field(None, description="Shots on goal")

    # Period-by-period breakdowns
    cf_p1: Optional[int] = Field(None, description="Corsi for in period 1")
    cf_p2: Optional[int] = Field(None, description="Corsi for in period 2")
    cf_p3: Optional[int] = Field(None, description="Corsi for in period 3")
    ca_p1: Optional[int] = Field(None, description="Corsi against in period 1")
    ca_p2: Optional[int] = Field(None, description="Corsi against in period 2")
    ca_p3: Optional[int] = Field(None, description="Corsi against in period 3")
    cf_pct_p1: Optional[float] = Field(None, description="CF% in period 1")
    cf_pct_p2: Optional[float] = Field(None, description="CF% in period 2")
    cf_pct_p3: Optional[float] = Field(None, description="CF% in period 3")
    xgf_p1: Optional[float] = Field(None, description="xGF in period 1")
    xgf_p2: Optional[float] = Field(None, description="xGF in period 2")
    xgf_p3: Optional[float] = Field(None, description="xGF in period 3")
    xga_p1: Optional[float] = Field(None, description="xGA in period 1")
    xga_p2: Optional[float] = Field(None, description="xGA in period 2")
    xga_p3: Optional[float] = Field(None, description="xGA in period 3")
    gf_p1: Optional[int] = Field(None, description="Goals for in period 1")
    gf_p2: Optional[int] = Field(None, description="Goals for in period 2")
    gf_p3: Optional[int] = Field(None, description="Goals for in period 3")
    ga_p1: Optional[int] = Field(None, description="Goals against in period 1")
    ga_p2: Optional[int] = Field(None, description="Goals against in period 2")
    ga_p3: Optional[int] = Field(None, description="Goals against in period 3")

    # 5v5 sequence-mix shares (Phase 2.1): how shot attempts were generated.
    # _for = the team's own offense, _against = the offense it allowed.
    rebound_share_for: Optional[float] = Field(None, description="5v5 share of attempts off rebounds (for)")
    rush_share_for: Optional[float] = Field(None, description="5v5 share of attempts off the rush (for)")
    forecheck_share_for: Optional[float] = Field(None, description="5v5 share of attempts off the forecheck (for)")
    cycle_share_for: Optional[float] = Field(None, description="5v5 share of attempts off the cycle (for)")
    point_shot_share_for: Optional[float] = Field(None, description="5v5 share of point shots (for)")
    other_share_for: Optional[float] = Field(None, description="5v5 share of other-origin attempts (for)")
    cross_ice_share_for: Optional[float] = Field(None, description="5v5 share preceded by a royal-road pass proxy (for)")
    rebound_share_against: Optional[float] = Field(None, description="5v5 share of attempts off rebounds (against)")
    rush_share_against: Optional[float] = Field(None, description="5v5 share of attempts off the rush (against)")
    forecheck_share_against: Optional[float] = Field(None, description="5v5 share of attempts off the forecheck (against)")
    cycle_share_against: Optional[float] = Field(None, description="5v5 share of attempts off the cycle (against)")
    point_shot_share_against: Optional[float] = Field(None, description="5v5 share of point shots (against)")
    other_share_against: Optional[float] = Field(None, description="5v5 share of other-origin attempts (against)")
    cross_ice_share_against: Optional[float] = Field(None, description="5v5 share preceded by a royal-road pass proxy (against)")

    # Scorer-bias adjusted events (Phase 2.3): raw + rink-adjusted
    hits: Optional[int] = Field(None, description="Hits recorded (raw)")
    giveaways: Optional[int] = Field(None, description="Giveaways recorded (raw)")
    takeaways: Optional[int] = Field(None, description="Takeaways recorded (raw)")
    hits_adj: Optional[float] = Field(None, description="Hits adjusted for arena scorer bias")
    giveaways_adj: Optional[float] = Field(None, description="Giveaways adjusted for arena scorer bias")
    takeaways_adj: Optional[float] = Field(None, description="Takeaways adjusted for arena scorer bias")
    # Score-state and opponent adjusted shares (Phase 2.3)
    cf_pct_score_adj: Optional[float] = Field(None, description="Score-state-adjusted Corsi For %")
    xgf_pct_score_adj: Optional[float] = Field(None, description="Score-state-adjusted xGF %")
    cf_pct_opp_adj: Optional[float] = Field(None, description="Opponent-adjusted Corsi For % (interim)")
    xgf_pct_opp_adj: Optional[float] = Field(None, description="Opponent-adjusted xGF % (interim)")


class GameDetail(BaseModel):
    """Detailed game information."""
    game_id: int
    game_date: DateType
    season: str
    home_team: TeamGameStats
    away_team: TeamGameStats
    is_preview: bool
    venue_name: Optional[str] = Field(None, description="Venue/arena name")


class PlayerGameStats(BaseModel):
    """Player statistics for a single game."""
    player_id: int
    player_name: str
    position: str
    team_id: int
    toi: Optional[float] = Field(None, description="Time on ice in minutes")
    goals: Optional[int] = None
    assists: Optional[int] = None
    points: Optional[int] = None
    shots: Optional[int] = None
    cf: Optional[int] = Field(None, description="Corsi For")
    hdcf: Optional[int] = Field(None, description="High-danger chances for")
    ixg: Optional[float] = Field(None, description="Individual expected goals")
    ixg_per60: Optional[float] = Field(None, description="Individual expected goals per 60 minutes")
    hot_cold_flag: Optional[str] = Field(None, description="Hot, cold, or neutral performance indicator")

    # New fields
    first_assists: Optional[int] = Field(None, description="Primary assists")
    second_assists: Optional[int] = Field(None, description="Secondary assists")
    ihdcf: Optional[int] = Field(None, description="Individual high-danger chances for")
    pim: Optional[int] = Field(None, description="Penalty minutes")
    rush_attempts: Optional[int] = Field(None, description="Rush shot attempts")

    # Individual unblocked-attempt counts by sequence type (Phase 2.1)
    seq_rebound_attempts: Optional[int] = Field(None, description="Individual rebound attempts")
    seq_rush_attempts: Optional[int] = Field(None, description="Individual rush attempts")
    seq_forecheck_attempts: Optional[int] = Field(None, description="Individual forecheck attempts")
    seq_cycle_attempts: Optional[int] = Field(None, description="Individual cycle attempts")
    seq_point_shot_attempts: Optional[int] = Field(None, description="Individual point-shot attempts")
    seq_other_attempts: Optional[int] = Field(None, description="Individual other-origin attempts")
    seq_cross_ice_attempts: Optional[int] = Field(None, description="Individual royal-road (cross-ice) attempts")

    # Scorer-bias adjusted events (Phase 2.3): raw + rink-adjusted
    hits: Optional[int] = Field(None, description="Hits (raw)")
    giveaways: Optional[int] = Field(None, description="Giveaways (raw)")
    takeaways: Optional[int] = Field(None, description="Takeaways (raw)")
    hits_adj: Optional[float] = Field(None, description="Hits adjusted for arena scorer bias")
    giveaways_adj: Optional[float] = Field(None, description="Giveaways adjusted for arena scorer bias")
    takeaways_adj: Optional[float] = Field(None, description="Takeaways adjusted for arena scorer bias")


class GamePlayerStats(BaseModel):
    """Player statistics for both teams in a game."""
    game_id: int
    home_players: List[PlayerGameStats]
    away_players: List[PlayerGameStats]


class ShotAttempt(BaseModel):
    """Individual shot attempt with coordinates."""
    x: float = Field(..., description="NHL x-coordinate (-100 to 100)")
    y: float = Field(..., description="NHL y-coordinate (-42.5 to 42.5)")
    outcome: str = Field(..., description="Shot outcome: goal, shot_on_goal, missed_shot, or blocked_shot")
    situation: str = Field(..., description="Situation code (e.g., 5v5, 5v4, etc.)")
    team_id: int = Field(..., description="Team ID that took the shot")
    shot_type: Optional[str] = Field(None, description="Type of shot (snap, slapshot, tip-deflection, backhand, wraparound, other)")

    # Goal-specific details (only present for goals)
    scorer_id: Optional[int] = Field(None, description="Player ID of goal scorer")
    scorer_name: Optional[str] = Field(None, description="Full name of goal scorer")
    period: Optional[int] = Field(None, description="Period number when goal was scored")
    time_in_period: Optional[str] = Field(None, description="Time in period (MM:SS)")
    assist1_id: Optional[int] = Field(None, description="Primary assist player ID")
    assist1_name: Optional[str] = Field(None, description="Primary assist player name")
    assist2_id: Optional[int] = Field(None, description="Secondary assist player ID")
    assist2_name: Optional[str] = Field(None, description="Secondary assist player name")
    goalie_id: Optional[int] = Field(None, description="Goalie who was scored on")
    goalie_name: Optional[str] = Field(None, description="Goalie name")

    # In-house xG + additive decomposition (Phase 2.2). Present for unblocked,
    # non-empty-net shots; contributions + base_rate sum to xg in probability space.
    xg: Optional[float] = Field(None, description="In-house expected goals for this shot")
    base_rate: Optional[float] = Field(None, description="Model base goal rate")
    xg_contrib_location: Optional[float] = Field(None, description="xG contribution from shot location")
    xg_contrib_shot_type: Optional[float] = Field(None, description="xG contribution from shot type")
    xg_contrib_strength: Optional[float] = Field(None, description="xG contribution from strength state")
    xg_contrib_sequence: Optional[float] = Field(None, description="xG contribution from the generating sequence")
    xg_contrib_game_state: Optional[float] = Field(None, description="xG contribution from game state")


class GameShots(BaseModel):
    """Shot attempts for both teams in a game."""
    game_id: int
    home_shots: List[ShotAttempt]
    away_shots: List[ShotAttempt]


# ============================================================================
# Team Models
# ============================================================================

class TeamDetail(BaseModel):
    """Detailed team information."""
    team_id: int
    team_name: str
    team_abbrev: str
    season: str
    games_played: int
    wins: int
    losses: int
    otl: int
    points: int
    cf_pct: float
    hdcf_per60: float
    hdca_per60: float
    xgf_per60: float
    xga_per60: float
    total_goals_for: int
    total_goals_against: int
    zone_entry_proxy_success_rate: Optional[float] = None
    cf_pct_rank: int
    xgf_pct_rank: int
    hdcf_per60_rank: int
    hdca_per60_rank: int
    gf_per_gp_rank: int
    ga_per_gp_rank: int
    zone_entry_proxy_success_rate_rank: Optional[int] = None

    # Zone time percentages
    oz_pct: Optional[float] = Field(None, description="Offensive zone percentage")
    nz_pct: Optional[float] = Field(None, description="Neutral zone percentage")
    dz_pct: Optional[float] = Field(None, description="Defensive zone percentage")

    # Faceoff statistics
    faceoff_win_pct: Optional[float] = Field(None, description="Overall faceoff win %")
    oz_faceoff_win_pct: Optional[float] = Field(None, description="Offensive zone faceoff win %")
    nz_faceoff_win_pct: Optional[float] = Field(None, description="Neutral zone faceoff win %")
    dz_faceoff_win_pct: Optional[float] = Field(None, description="Defensive zone faceoff win %")


class TeamTrendPoint(BaseModel):
    """Single data point in team trends."""
    game_date: DateType
    value: float


class TeamTrends(BaseModel):
    """Rolling trends for a team."""
    team_id: int
    season: str
    cf_pct_5gp: List[TeamTrendPoint]
    cf_pct_10gp: List[TeamTrendPoint]
    xgf_pct_5gp: List[TeamTrendPoint]
    xgf_pct_10gp: List[TeamTrendPoint]
    hdcf_per60_5gp: List[TeamTrendPoint]
    hdcf_per60_10gp: List[TeamTrendPoint]


class RosterPlayer(BaseModel):
    """Player in team roster."""
    player_id: int
    player_name: str
    position: str
    games_played: int
    toi_per_gp: float
    points_per60: float
    cf_pct: float


class TeamRoster(BaseModel):
    """Team roster with player stats."""
    team_id: int
    season: str
    forwards: List[RosterPlayer]
    defensemen: List[RosterPlayer]
    goalies: List[RosterPlayer]


class TeamVsOpponent(BaseModel):
    """Head-to-head stats for team vs opponent."""
    team_id: int
    opponent_id: int
    season: str
    games_played: int
    small_sample: bool = Field(description="True if < 3 games")
    wins: int
    losses: int
    otl: int
    cf_pct: Optional[float] = None
    hdcf_per60: Optional[float] = None
    xgf_per60: Optional[float] = None


# ============================================================================
# Player Models
# ============================================================================

class PlayerDetail(BaseModel):
    """Detailed player information."""
    player_id: int
    player_name: str
    position: str
    team_id: int
    team_abbrev: str
    season: str
    games_played: int
    toi_per_gp: float
    points_per60: float
    goals_per60: float
    assists_per60: float
    cf_pct: float
    hdcf_per60: float

    # New fields
    first_assists: Optional[int] = Field(None, description="Total primary assists")
    second_assists: Optional[int] = Field(None, description="Total secondary assists")
    ihdcf_per60: Optional[float] = Field(None, description="Individual high-danger chances per 60")
    ozs_pct: Optional[float] = Field(None, description="Offensive zone start percentage")
    dzs_pct: Optional[float] = Field(None, description="Defensive zone start percentage")
    nzs_pct: Optional[float] = Field(None, description="Neutral zone start percentage")
    relative_cf_pct: Optional[float] = Field(None, description="CF% relative to team average")
    relative_xgf_pct: Optional[float] = Field(None, description="xGF% relative to team average")
    actual_shooting_pct: Optional[float] = Field(None, description="Actual shooting percentage")
    expected_shooting_pct: Optional[float] = Field(None, description="Expected shooting percentage from xG")
    shooting_luck_delta: Optional[float] = Field(None, description="Difference between actual and expected sh%")


class PlayerTrendPoint(BaseModel):
    """Single data point in player trends."""
    game_date: DateType
    value: float


class PlayerTrends(BaseModel):
    """Rolling trends for a player."""
    player_id: int
    season: str
    points_per60_5gp: List[PlayerTrendPoint]
    points_per60_10gp: List[PlayerTrendPoint]
    cf_pct_5gp: List[PlayerTrendPoint]
    cf_pct_10gp: List[PlayerTrendPoint]


class GamelogEntry(BaseModel):
    """Single game entry in player gamelog."""
    game_id: int
    game_date: DateType
    opponent_id: int
    opponent_abbrev: str
    toi: float
    goals: int
    assists: int
    points: int
    shots: int
    cf: int
    hdcf: int


class PlayerGamelog(BaseModel):
    """Game-by-game log for a player."""
    player_id: int
    season: str
    games: List[GamelogEntry]


class ShotLocation(BaseModel):
    """Shot location data."""
    x: float
    y: float
    is_goal: bool
    danger_level: str = Field(description="low, medium, or high")
    xg: Optional[float] = Field(None, description="In-house expected goals for this shot (Phase 2.2)")


class PlayerShots(BaseModel):
    """Shot data for a player."""
    player_id: int
    season: str
    total_shots: int
    low_danger: int
    medium_danger: int
    high_danger: int
    shot_locations: List[ShotLocation]


class PlayerVsOpponent(BaseModel):
    """Player stats vs specific opponent."""
    player_id: int
    opponent_id: int
    season: str
    games_played: int
    small_sample: bool = Field(description="True if < 3 games")
    toi_per_gp: Optional[float] = None
    points_per60: Optional[float] = None
    cf_pct: Optional[float] = None


# ============================================================================
# New Models for Dashboard Expansion
# ============================================================================

class PlayerZoneDeployment(BaseModel):
    """Player zone deployment statistics."""
    player_id: int
    season: str
    team_id: int
    oz_starts: int = Field(description="Offensive zone starts")
    nz_starts: int = Field(description="Neutral zone starts")
    dz_starts: int = Field(description="Defensive zone starts")
    total_starts: int = Field(description="Total zone starts")
    ozs_pct: float = Field(description="Offensive zone start percentage")
    nzs_pct: float = Field(description="Neutral zone start percentage")
    dzs_pct: float = Field(description="Defensive zone start percentage")


class PlayerSituational(BaseModel):
    """Player statistics broken down by situation."""
    player_id: int
    season: str
    situation: str = Field(description="5v5, pp, pk, or all")
    toi_per_gp: Optional[float] = Field(None, description="TOI per game in this situation")
    points_per60: Optional[float] = Field(None, description="Points per 60 in this situation")
    goals_per60: Optional[float] = Field(None, description="Goals per 60 in this situation")
    ixg_per60: Optional[float] = Field(None, description="ixG per 60 in this situation")
    cf_pct: Optional[float] = Field(None, description="CF% in this situation")
    hdcf_per60: Optional[float] = Field(None, description="HD chances per 60 in this situation")


class TeamSituational(BaseModel):
    """Team statistics broken down by situation for a specific game."""
    team_id: int
    game_id: int
    situation: str = Field(description="5v5, pp, pk, all")
    toi_seconds: Optional[int] = Field(None, description="TOI in seconds for this situation")
    cf_pct: Optional[float] = Field(None, description="CF% in this situation")
    xgf_pct: Optional[float] = Field(None, description="xGF% in this situation")
    hdcf_pct: Optional[float] = Field(None, description="HDCF% in this situation")
    gf: Optional[int] = Field(None, description="Goals for in this situation")
    ga: Optional[int] = Field(None, description="Goals against in this situation")
    shots_for: Optional[int] = Field(None, description="Shot attempts for in this situation")
    shots_against: Optional[int] = Field(None, description="Shot attempts against in this situation")


class ShotData(BaseModel):
    """Shot coordinate data for visualizations."""
    x_coord: float = Field(description="X coordinate on ice")
    y_coord: float = Field(description="Y coordinate on ice")
    shot_type: str = Field(description="Type of shot")
    outcome: str = Field(description="Shot outcome")
    situation: str = Field(description="Situation code")
    period: int = Field(description="Period number")
    game_time_seconds: int = Field(description="Seconds elapsed in game")


class XGWormPoint(BaseModel):
    """Single data point for xG worm chart."""
    game_time_seconds: int = Field(description="Seconds elapsed in game")
    cumulative_xg_diff: float = Field(description="Cumulative xG differential (home - away)")
    home_xg: float = Field(description="Home team cumulative xG")
    away_xg: float = Field(description="Away team cumulative xG")
    event_type: Optional[str] = Field(None, description="'goal' for goal events, null otherwise")
    team_id: Optional[int] = Field(None, description="Team ID for goal events, null otherwise")
    label: Optional[str] = Field(None, description="Goal label like 'CAR 1-0', null for non-events")


class PressurePoint(BaseModel):
    """Smoothed shots/60 rate for each team at one game-time sample (shot pressure chart)."""
    game_time_seconds: int = Field(description="Seconds elapsed in game at this sample")
    home_rate: float = Field(description="Home team smoothed unblocked shots per 60 minutes")
    away_rate: float = Field(description="Away team smoothed unblocked shots per 60 minutes")


class WinProbPoint(BaseModel):
    """Win-probability series point (Phase 2.4)."""
    elapsed_seconds: int = Field(description="Seconds elapsed in game")
    home_wp: float = Field(description="Home team win probability")
    leverage: float = Field(description="Win-probability swing of a goal at this moment")


class WinProbGoalSwing(BaseModel):
    """The win-probability jump caused by a goal."""
    elapsed_seconds: int
    team_id: Optional[int] = None
    scorer_name: Optional[str] = None
    wp_before: float
    wp_after: float
    swing: float = Field(description="home_wp after minus before (signed toward home)")


class WinProbSeries(BaseModel):
    """Server-side win probability + leverage series for a game (Phase 2.4)."""
    game_id: int
    model_version: Optional[str] = None
    series: List[WinProbPoint]
    goal_swings: List[WinProbGoalSwing]


class GoalieSeason(BaseModel):
    """A goalie's season line on the in-house xG layer (Phase 2.5)."""
    goalie_id: int
    goalie_name: Optional[str] = None
    season: str
    team_id: Optional[int] = None
    games_played: int
    shots_faced: int
    saves: int
    goals_against: int
    save_pct: Optional[float] = None
    xga: float
    gsax: float = Field(description="Goals saved above expected (xGA - GA)")
    our_hd_gsax: Optional[float] = Field(None, description="High-danger GSAx (ours)")
    our_hd_save_pct: Optional[float] = None
    ev_gsax: Optional[float] = None
    special_gsax: Optional[float] = None
    last10_gsax: Optional[float] = None
    last10_hd_gsax: Optional[float] = None
    # NHL Edge independent second opinion (overall last-10 save pct; no HD split)
    edge_last10_save_pct: Optional[float] = Field(None, description="NHL Edge last-10 save %")
    edge_games_above_900: Optional[int] = None


class GoalieGameLogRow(BaseModel):
    """One game in a goalie's log."""
    game_id: int
    game_date: DateType
    season: str
    team_id: Optional[int] = None
    shots_faced: int
    saves: int
    goals_against: int
    save_pct: Optional[float] = None
    xga: float
    gsax: float
    high_gsax: Optional[float] = None
    high_shots: Optional[int] = None
    high_saves: Optional[int] = None


class GoaltenderStat(BaseModel):
    """A goalie's line for a game, from the goalie who was actually in net per shot."""
    player_id: int
    goalie_name: str
    team_abbrev: str
    shots_against: int
    goals_against: int
    gsax: float = 0.0
    headshot: Optional[str] = None


class TeamComparisonStats(BaseModel):
    """Box-score style team-vs-team counts for the Overview comparison, from play-by-play."""
    home_team_id: int
    away_team_id: int
    home_goals: int
    away_goals: int
    home_sog: int
    away_sog: int
    home_pp_goals: int
    away_pp_goals: int
    home_penalties: int
    away_penalties: int
    home_pim: int
    away_pim: int
    home_hits: int
    away_hits: int
    home_faceoff_wins: int
    away_faceoff_wins: int
    home_blocks: int
    away_blocks: int
    home_giveaways: int
    away_giveaways: int
    home_takeaways: int
    away_takeaways: int


class GoalDetail(BaseModel):
    """Detailed information about a single goal, for the xG worm goal tooltip."""
    game_time_seconds: int = Field(description="Seconds elapsed in game when the goal was scored")
    period: int = Field(description="Period number (4+ = overtime)")
    time_in_period: str = Field(description="Elapsed clock within the period, mm:ss")
    team_id: int = Field(description="Scoring team ID")
    team_abbrev: str = Field(description="Scoring team abbreviation")
    strength: str = Field(description="Goal strength: EV, PP, SH, or EN")
    scorer_id: Optional[int] = Field(None, description="Scorer player ID")
    scorer_name: Optional[str] = Field(None, description="Scorer full name")
    scorer_headshot: Optional[str] = Field(None, description="Scorer headshot image URL")
    assists: List[str] = Field(default_factory=list, description="Assisting player names, in order")


class SpecialTeamsStat(BaseModel):
    """A team's power-play and penalty-kill detail for one game."""
    team_abbrev: str
    is_home: bool
    pp_goals: int
    pp_opp: int
    pp_xg: float
    pp_shots: int
    pk_saves: int
    pk_shots: int


class GoalieDangerStat(BaseModel):
    """A goalie's save record split by shot-danger band, plus total GSAx."""
    player_id: int
    goalie_name: str
    team_abbrev: str
    high_saves: int
    high_shots: int
    med_saves: int
    med_shots: int
    low_saves: int
    low_shots: int
    gsax: float


class ShotQualityRow(BaseModel):
    """Shot attempts and goals by danger band, per team (the shot-quality ladder)."""
    band: str
    home_abbrev: str
    away_abbrev: str
    home_attempts: int
    home_goals: int
    away_attempts: int
    away_goals: int


class SkaterImpact(BaseModel):
    """A skater's impact line: real TOI + box-score scoring + individual xG / HDC."""
    player_id: int
    player_name: str
    team_abbrev: str
    position: str
    toi: str
    toi_seconds: int
    goals: int
    assists: int
    points: int
    shots: int
    ixg: float
    ihdcf: int


# ============================================================================
# Game Context Models (Phase 1.3: landing + right-rail enrichment)
# ============================================================================

class ContextScratch(BaseModel):
    """A scratched (healthy/injured) player for a game."""
    player_id: int
    player_name: str


class ContextGoalHighlight(BaseModel):
    """A goal's highlight video links, keyed by play-by-play event id."""
    event_id: int
    period: Optional[int] = None
    scorer_player_id: Optional[int] = None
    time_in_period: Optional[str] = None
    highlight_url: Optional[str] = Field(None, description="Shareable nhl.com highlight clip URL")
    ppt_replay_url: Optional[str] = None


class ContextSeriesGame(BaseModel):
    """One prior meeting in the season series."""
    game_id: Optional[int] = None
    game_date: Optional[str] = None
    away_abbrev: Optional[str] = None
    away_score: Optional[int] = None
    home_abbrev: Optional[str] = None
    home_score: Optional[int] = None


class ContextTeamStat(BaseModel):
    """One team-vs-team game-stat comparison row (category / away / home)."""
    category: str
    away_value: Optional[str] = None
    home_value: Optional[str] = None


class ContextLast10(BaseModel):
    """A team's last-10 record + standing as of the game date (from stg_standings)."""
    team_abbrev: Optional[str] = None
    l10_wins: Optional[int] = None
    l10_losses: Optional[int] = None
    l10_ot_losses: Optional[int] = None
    league_rank: Optional[int] = None
    points: Optional[int] = None


class GameContext(BaseModel):
    """Pregame/postgame context for GameDetail: scratches, series, last-10, goal videos."""
    game_id: int
    away_team_id: Optional[int] = None
    home_team_id: Optional[int] = None
    away_head_coach: Optional[str] = None
    home_head_coach: Optional[str] = None
    away_scratches: List[ContextScratch] = Field(default_factory=list)
    home_scratches: List[ContextScratch] = Field(default_factory=list)
    season_series_away_wins: Optional[int] = None
    season_series_home_wins: Optional[int] = None
    season_series_needed_to_win: Optional[int] = None
    season_series_games: List[ContextSeriesGame] = Field(default_factory=list)
    team_game_stats: List[ContextTeamStat] = Field(default_factory=list)
    goal_highlights: List[ContextGoalHighlight] = Field(default_factory=list)
    away_last10: Optional[ContextLast10] = None
    home_last10: Optional[ContextLast10] = None


# ============================================================================
# NHL Edge Profiles (Phase 1.2: season-aggregate tracking data)
# ============================================================================

class EdgePlayerProfile(BaseModel):
    """Per player-season NHL Edge profile (season-aggregate tracking data)."""
    player_id: int
    season_id: int
    game_type: int
    max_skating_speed_mph: Optional[float] = None
    max_skating_speed_pctile: Optional[float] = None
    bursts_22_plus: Optional[int] = None
    bursts_22_plus_pctile: Optional[float] = None
    bursts_20_to_22: Optional[int] = None
    bursts_18_to_20: Optional[int] = None
    bursts_22_plus_per60: Optional[float] = None
    bursts_20_plus_per60: Optional[float] = None
    avg_shot_speed_mph: Optional[float] = None
    max_shot_speed_mph: Optional[float] = None
    distance_per60_mi: Optional[float] = None
    distance_total_mi: Optional[float] = None
    oz_time_pct: Optional[float] = None
    nz_time_pct: Optional[float] = None
    dz_time_pct: Optional[float] = None
    oz_time_pct_es: Optional[float] = None
    dz_time_pct_es: Optional[float] = None
    oz_start_pct: Optional[float] = None
    dz_start_pct: Optional[float] = None
    total_sog: Optional[int] = None
    high_danger_sog: Optional[int] = None
    high_danger_goals: Optional[int] = None
    high_danger_sog_share: Optional[float] = None
    toi_minutes: Optional[float] = None


class EdgeTeamProfile(BaseModel):
    """Per team-season NHL Edge profile (danger-bucket shot shares)."""
    team_id: int
    season_id: int
    game_type: int
    total_sog: Optional[int] = None
    high_danger_sog: Optional[int] = None
    mid_danger_sog: Optional[int] = None
    long_danger_sog: Optional[int] = None
    high_danger_goals: Optional[int] = None
    high_danger_sog_share: Optional[float] = None
    mid_danger_sog_share: Optional[float] = None
    long_danger_sog_share: Optional[float] = None
    high_danger_shooting_pct: Optional[float] = None
