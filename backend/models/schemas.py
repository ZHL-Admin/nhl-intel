"""Pydantic response models for all API endpoints.

Defines the data models for API responses following the dashboard spec.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


# ============================================================================
# Game Models
# ============================================================================

class Game(BaseModel):
    """Basic game information for game list."""
    game_id: int
    game_date: date
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
    zone_entry_success_rate: Optional[float] = Field(None, description="Controlled zone entry success rate")
    shot_attempts: Optional[int] = Field(None, description="Total shot attempts")

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


class GameDetail(BaseModel):
    """Detailed game information."""
    game_id: int
    game_date: date
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
    zone_entry_success_rate: Optional[float] = None
    cf_pct_rank: int
    xgf_pct_rank: int
    hdcf_per60_rank: int
    hdca_per60_rank: int
    gf_per_gp_rank: int
    ga_per_gp_rank: int
    zone_entry_success_rate_rank: Optional[int] = None

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
    game_date: date
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
    game_date: date
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
    game_date: date
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
