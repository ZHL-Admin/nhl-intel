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
    season: int
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


class GameDetail(BaseModel):
    """Detailed game information."""
    game_id: int
    game_date: date
    season: int
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

    # Goal-specific details (only present for goals)
    scorer_id: Optional[int] = Field(None, description="Player ID of goal scorer")
    scorer_name: Optional[str] = Field(None, description="Full name of goal scorer")
    shot_type: Optional[str] = Field(None, description="Type of shot (e.g., Wrist, Slap, Snap)")
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
    season: int
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


class TeamTrendPoint(BaseModel):
    """Single data point in team trends."""
    game_date: date
    value: float


class TeamTrends(BaseModel):
    """Rolling trends for a team."""
    team_id: int
    season: int
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
    season: int
    forwards: List[RosterPlayer]
    defensemen: List[RosterPlayer]
    goalies: List[RosterPlayer]


class TeamVsOpponent(BaseModel):
    """Head-to-head stats for team vs opponent."""
    team_id: int
    opponent_id: int
    season: int
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
    season: int
    games_played: int
    toi_per_gp: float
    points_per60: float
    goals_per60: float
    assists_per60: float
    cf_pct: float
    hdcf_per60: float


class PlayerTrendPoint(BaseModel):
    """Single data point in player trends."""
    game_date: date
    value: float


class PlayerTrends(BaseModel):
    """Rolling trends for a player."""
    player_id: int
    season: int
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
    season: int
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
    season: int
    total_shots: int
    low_danger: int
    medium_danger: int
    high_danger: int
    shot_locations: List[ShotLocation]


class PlayerVsOpponent(BaseModel):
    """Player stats vs specific opponent."""
    player_id: int
    opponent_id: int
    season: int
    games_played: int
    small_sample: bool = Field(description="True if < 3 games")
    toi_per_gp: Optional[float] = None
    points_per60: Optional[float] = None
    cf_pct: Optional[float] = None
