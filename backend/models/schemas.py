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

class TrajectoryCurvePoint(BaseModel):
    age: int
    curve_value: float


class TrajectoryPathPoint(BaseModel):
    age: int
    season: str
    points82: float


class TwinEntry(BaseModel):
    twin_id: int
    twin_name: Optional[str] = None
    similarity: float
    through_age: int
    reduced_features: bool
    next3_points82: Optional[float] = None


class PhysicalPoint(BaseModel):
    season: str
    burst_rate: Optional[float] = None
    max_speed: Optional[float] = None


class PlayerTrajectory(BaseModel):
    """Career trajectory: aging-curve band, player path, twins, physical overlay (Phase 4.4)."""
    player_id: int
    archetype: Optional[str] = None
    curve_label: Optional[str] = Field(None, description="What the curve band represents (archetype or position fallback)")
    curve: List[TrajectoryCurvePoint]
    path: List[TrajectoryPathPoint]
    twins: List[TwinEntry]
    physical: List[PhysicalPoint]
    burst_flag_enabled: bool = Field(
        False, description="Whether the burst-decline early-warning flag passed validation")


class ClutchProfile(BaseModel):
    """Leverage-weighted production with a confidence phrase (Phase 4.3)."""
    n_shots: int
    raw_ixg: float
    clutch_ixg: float
    clutch_delta: float
    p_value: float
    confidence: str = Field(description="Plain-language confidence (no bare p-value at depth 1)")


class GameScorePoint(BaseModel):
    game_date: DateType
    game_score: float


class ConsistencyProfile(BaseModel):
    """Game-score distribution summary + the series for a strip plot (Phase 4.3)."""
    games: int
    mean_gs: float
    sd_gs: float
    iqr_gs: float
    good_game_share: float
    no_show_share: float
    consistency_index: float
    game_scores: List[GameScorePoint]


class CoachTrustProfile(BaseModel):
    """Deployment-trust signals (Phase 4.3)."""
    trust_score: float
    pk_share: float
    protect_lead_rate: float
    road_home_ratio: float


class PlayerReconciliation(BaseModel):
    """Eye-test reconciliation: clutch + consistency + coach trust (Phase 4.3)."""
    player_id: int
    season: str
    clutch: Optional[ClutchProfile] = None
    consistency: Optional[ConsistencyProfile] = None
    coach_trust: Optional[CoachTrustProfile] = None


class DivergenceBoardRow(BaseModel):
    """One divergence-board entry with its generated explanation (Phase 4.3)."""
    player_id: int
    player_name: Optional[str] = None
    position: Optional[str] = None
    team_abbrev: Optional[str] = None
    side: str
    divergence: float
    trust_z: float
    composite_z: float
    composite_total: float
    explanation: str
    archetype: Optional[str] = None   # offensive sub-label (v2 source), for the compact header tag


class DeploymentRow(BaseModel):
    """One deployment-efficiency entry: actual vs justified usage in a situation (the new board)."""
    player_id: int
    player_name: Optional[str] = None
    position: Optional[str] = None
    team_abbrev: Optional[str] = None
    actual_pctile: float
    justified_pctile: float
    gap: float
    gap_sd: float
    value_pctile: float
    value_rank: int
    n_pool: int
    explanation: str


class DeploymentBoard(BaseModel):
    """Both sides of the deployment board for one situation lens, plus an honest caption."""
    situation: str
    value_label: str
    caption: str
    over: List[DeploymentRow] = Field(default_factory=list)
    under: List[DeploymentRow] = Field(default_factory=list)


class PlayerDeploymentEntry(BaseModel):
    """One situation row in a single player's full deployment profile (the row-expansion detail)."""
    situation: str
    value_label: str
    actual_pctile: float
    justified_pctile: float
    gap: float
    value_rank: int
    n_pool: int


class CompositeComponent(BaseModel):
    """One value component on the goals scale (Phase 4.2)."""
    key: str
    label: str
    value: float


class ArchetypeWeight(BaseModel):
    """A player's soft membership in one archetype (Phase 4.2)."""
    archetype: str
    weight: float


class ArchetypeRankRow(BaseModel):
    """A player ranked within an archetype, with composite stack (Phase 4.2)."""
    player_id: int
    player_name: Optional[str] = None
    team_abbrev: Optional[str] = None
    position: Optional[str] = None
    composite_total: float
    composite_total_sd: Optional[float] = None
    components: List[CompositeComponent]
    archetype_weight: float = Field(description="Membership weight in the queried archetype")
    primary_archetype: Optional[str] = None


# Composite component key -> display label (single source for the stack).
COMPOSITE_LABELS = [
    ("ev_offense", "EV Offense"), ("ev_defense", "EV Defense"), ("pp", "Power Play"),
    ("pk", "Penalty Kill"), ("finishing", "Finishing"), ("penalty_diff", "Penalties"),
    ("goalie_gsax", "Goaltending"),
]

# GAR value-component key -> label (single source for the value stack everywhere; matches
# compute_gar.COMPONENTS order).
GAR_LABELS = [
    ("ev_offense", "EV Offense"), ("pp", "Power Play"), ("ev_defense", "EV Defense"),
    ("pk", "Penalty Kill"), ("penalty", "Penalties"), ("faceoff", "Faceoffs"),
]

# Goalie GAR component key -> label (the goalie value stack; a DISTINCT vocabulary from skaters,
# so the mixed leaderboard renders the right bar per row's component_kind). Matches
# models_ml.config.GOALIE_GAR_COMPONENTS order.
GOALIE_GAR_LABELS = [
    ("hd_saves", "High-Danger Saves"), ("md_saves", "Mid-Danger Saves"),
    ("ld_saves", "Low-Danger Saves"), ("pk_goaltending", "Penalty-Kill"),
]


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

    # Composite stack + archetype mix (Phase 4.2). Components are ALWAYS returned (never a
    # total-only shape); archetypes is the soft membership mix, sorted desc.
    composite_total: Optional[float] = None
    composite_total_sd: Optional[float] = None
    composite_components: List[CompositeComponent] = []
    archetypes: List[ArchetypeWeight] = []
    primary_archetype: Optional[str] = None
    # Value (GAR/WAR) block — the goals-reality companion to RAPM impact (Phase 6 GAR).
    value: Optional["PlayerValue"] = None


class ValueGapRead(BaseModel):
    """Deterministic, asymmetric plain-language read of the Impact-vs-Value gap."""
    case: str                  # value_over_impact | impact_over_value | aligned
    headline: str
    body: str


class PlayerValue(BaseModel):
    """GAR/WAR + components, percentiles within position, and the Impact-vs-Value gap read.

    impact_goals is the RAPM-based value (composite EV+ST, finishing excluded) — "what tends to
    repeat"; gar is actual goals above replacement — "what happened". The gap is finishing/luck/
    usage. production_r/rapm_r/finishing_r are the MEASURED year-over-year stabilities, carried so
    the read's "least repeatable" claim traces to a number (consistency rule)."""
    gar: float
    war: float
    gar_sd: float
    war_sd: float
    components: List[CompositeComponent] = []
    value_percentile: Optional[float] = None     # GAR percentile within position (0-1)
    impact_goals: Optional[float] = None
    impact_percentile: Optional[float] = None     # RAPM-value percentile within position (0-1)
    gap_percentile_points: Optional[float] = None  # (value_pct - impact_pct) * 100
    read: Optional[ValueGapRead] = None
    production_r: float
    rapm_r: float
    finishing_r: float
    # Per-player Overall (card-only): a within-position percentile SUMMARY of the two lenses above,
    # always rendered WITH its components. Never a sort key (no /rankings/overall).
    overall: Optional["OverallSummary"] = None


class ValueRankingRow(BaseModel):
    """A row on the value leaderboard — skater OR goalie (Phase 6 GAR + cross-position WAR).

    WAR (= GAR / GOALS_PER_WIN) is the ONLY cross-position-comparable unit, so the mixed (`all`)
    leaderboard sorts by WAR; skater GAR and goalie GAR are different units and are never sorted
    together. `entity_kind` says which table the row came from; `component_kind` tells the frontend
    which component-colour vocabulary to render (skater vs goalie save-tier components).
    """
    player_id: int                       # player_id for skaters, goalie_id for goalies
    player_name: Optional[str] = None
    team_abbrev: Optional[str] = None
    position: Optional[str] = None
    entity_kind: str = "skater"          # skater | goalie
    component_kind: str = "skater"       # skater | goalie  (which bar vocabulary to render)
    gar: float
    war: float
    gar_sd: Optional[float] = None
    war_sd: Optional[float] = None       # goalies render a VISIBLY wider band (principle 6)
    components: List[CompositeComponent] = []


class OverallComponent(BaseModel):
    """One within-position percentile that feeds the per-player Overall (0-1)."""
    key: str
    label: str
    percentile: Optional[float] = None


class OverallSummary(BaseModel):
    """Per-player Overall — a within-position percentile SUMMARY for the player card only.

    `overall_percentile` is itself a within-position percentile (averaged-and-re-percentiled);
    `components` are the within-position percentiles it averaged and MUST always be shown with it
    (the FE enforces this). It is never a leaderboard sort key — there is no /rankings/overall.
    """
    overall_percentile: float            # 0-1, within position group (skaters) or within goalies
    pos_group: Optional[str] = None      # F | D | G
    components: List[OverallComponent] = []
    weights: dict = {}


class GoalieValue(BaseModel):
    """Goalie GAR/WAR + components on the cross-position WAR scale (goals saved above a backup).

    Goalies have no RAPM play-driving lens, so (unlike the skater PlayerValue) there is no
    Impact-vs-Value gap read — the goalie's actual-vs-expected motif is GSAx-vs-Edge on the radar.
    The band is wide by construction; goalie value is presented at tier-level confidence."""
    gar: float                                  # RELIABILITY-SHRUNK goals saved above replacement
    war: float                                  # shrunk WAR (the honest point estimate)
    gar_sd: float
    war_sd: float
    components: List[CompositeComponent] = []   # goalie save-tier components (GOALIE_GAR_LABELS)
    war_percentile: Optional[float] = None      # WAR percentile within goalies (0-1), for context
    raw_war: Optional[float] = None             # pre-regression WAR (transparency; never the headline)


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


class StreakComponent(BaseModel):
    """One Streak Doctor component: goal-scale value + share of total deviation (Phase 3.3)."""
    key: str
    label: str
    value: float
    share: float


class StreakCard(BaseModel):
    """Streak Doctor decomposition of a team's last-N run (Phase 3.3)."""
    team_id: int
    team_abbrev: Optional[str] = None
    season: str
    window_games: int
    games: int
    run_word: str
    verdict: str
    total_deviation: float
    sustainability: int = Field(description="0-100; higher = more likely to persist")
    is_notable: bool
    points_pace: float
    points_pace_z: float
    streak: int = Field(description="Signed current W/L streak (+wins, -losses)")
    components: List[StreakComponent]


class IdentityMetric(BaseModel):
    """One fingerprint metric: raw value + league percentile (Phase 3.2)."""
    key: str
    value: Optional[float] = None
    percentile: Optional[float] = None


class TeamIdentityWindow(BaseModel):
    """A team's fingerprint over one window ('season' or 'last25')."""
    window: str
    games: int
    metrics: List[IdentityMetric]


class TeamIdentity(BaseModel):
    """Team identity fingerprint with per-window metrics + percentiles (Phase 3.2)."""
    team_id: int
    team_abbrev: Optional[str] = None
    season: str
    league_size: int = Field(description="Teams in the season, for percentile->rank")
    windows: List[TeamIdentityWindow]


class StyleMapTeam(BaseModel):
    team_id: int
    team_abbrev: Optional[str] = None
    x: float
    y: float


class StyleMap(BaseModel):
    """League style map: 2D PCA of team fingerprints + axis annotations (Phase 3.2)."""
    season: str
    x_pos_desc: str
    x_neg_desc: str
    y_pos_desc: str
    y_neg_desc: str
    teams: List[StyleMapTeam]


class PowerRatingRow(BaseModel):
    """A team's current power rating with its four visible components (Phase 3.1).

    All values are on a goals-per-game scale. contrib_* are the weighted component
    contributions and sum to total_rating; the bare component fields are the raw
    (pre-weight) goal values."""
    team_id: int
    team_abbrev: Optional[str] = None
    season: str
    games_played: int
    total_rating: float = Field(description="Sum of the four weighted contributions")
    rating_se: Optional[float] = Field(None, description="Game-resample standard error")
    trajectory_15d: Optional[float] = Field(None, description="Total now minus 15 days ago")
    play_5v5: float
    finishing: float
    goaltending: float
    special_teams: float
    contrib_play_5v5: float
    contrib_finishing: float
    contrib_goaltending: float
    contrib_special_teams: float


class DeservedStandingRow(BaseModel):
    """Actual vs Monte-Carlo deserved points for a team-season (Phase 3.1)."""
    team_id: int
    team_abbrev: Optional[str] = None
    season: str
    games: int
    actual_points: int
    deserved_points: float
    deserved_p10: float
    deserved_p90: float
    luck_delta: float = Field(description="Actual minus deserved points")


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
    # Goalie Value (GAR/WAR on the cross-position scale) + within-goalie Overall (card-only).
    value: Optional["GoalieValue"] = None
    overall: Optional["OverallSummary"] = None


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


# --- Phase 5: signature tools (Lineup Lab, trade fit, matchup previews) ------

class PlayerSearchResult(BaseModel):
    """A current-roster player returned by /players/search (PlayerPicker)."""
    player_id: int
    name: Optional[str] = None
    team_id: Optional[int] = None
    team_abbrev: Optional[str] = None
    position: Optional[str] = None
    headshot_url: Optional[str] = None
    archetype: Optional[str] = None


class LineMemberOut(BaseModel):
    """A member of a scored line, with the profile values the model used."""
    player_id: int
    name: Optional[str] = None
    position: Optional[str] = None
    archetype: Optional[str] = None
    off_impact: Optional[float] = None
    def_impact: Optional[float] = None
    finishing: Optional[float] = None
    toi_5v5: Optional[float] = None


class ObservedBlend(BaseModel):
    """Chemistry-blend details when a line has real shared history."""
    observed_minutes: float
    observed_xgf_pct: float
    model_xgf_pct: float
    w_obs: float


class LineFitProjection(BaseModel):
    """A line-fit projection (Phase 5.1): one forward trio or defense pair."""
    line_type: str
    player_ids: List[int]
    grade: str
    projected_xgf_pct: float
    interval_low: Optional[float] = None
    interval_high: Optional[float] = None
    xgf_per60: Optional[float] = None
    xga_per60: Optional[float] = None
    grade_sentence: Optional[str] = None
    reasons: List[str] = Field(default_factory=list)
    risk: Optional[str] = None
    observed_blend: Optional[ObservedBlend] = None
    deeper_extrapolation: bool = False
    rookie_widened: bool = False
    members: List[LineMemberOut] = Field(default_factory=list)
    limitations: Optional[str] = None
    # populated only for a 5-skater unit
    forward_trio: Optional["LineFitProjection"] = None
    defense_pair: Optional["LineFitProjection"] = None


class LineFitRequest(BaseModel):
    """Body for POST /tools/line-fit."""
    player_ids: List[int] = Field(..., min_length=2, max_length=5)
    season: Optional[str] = None


class BetterFitSwap(BaseModel):
    """A same-caliber candidate who would raise a line's projected xGF% (Phase 5.2)."""
    player_id: int
    name: Optional[str] = None
    team_id: Optional[int] = None
    team_abbrev: Optional[str] = None
    position: Optional[str] = None
    headshot_url: Optional[str] = None
    archetype: Optional[str] = None
    composite_total: Optional[float] = None
    swap_xgf_pct: float
    swap_grade: str
    xgf_gain: float
    reasons: List[str] = Field(default_factory=list)


class SlotSuggestions(BaseModel):
    """Better-fit candidates for one slot (the current member is being compared against)."""
    slot_index: int
    position: Optional[str] = None
    current_player_id: int
    current_player_name: Optional[str] = None
    candidates: List[BetterFitSwap] = Field(default_factory=list)


class LineSuggestionsResponse(BaseModel):
    """Per-slot 'better fits' for a line (POST /tools/line-fit/suggestions)."""
    season: str
    line_type: str
    slots: List[SlotSuggestions] = Field(default_factory=list)


class TeamLine(BaseModel):
    """A team's current line (trio/pair) with observed results + projected grade."""
    line_type: str
    player_ids: List[int]
    member_names: List[str] = Field(default_factory=list)
    minutes: float
    observed_xgf_pct: Optional[float] = None
    projection: Optional[LineFitProjection] = None


class TeamLines(BaseModel):
    """A team's rolling current lines for the line-swap widget."""
    team_id: int
    season: str
    forward_lines: List[TeamLine] = Field(default_factory=list)
    defense_pairs: List[TeamLine] = Field(default_factory=list)


class NeedComponent(BaseModel):
    """One gap in a team's need profile (archetype or composite component)."""
    key: str
    label: str
    gap: float          # how far below the top-8 average (positive = a need)
    team_value: float
    reference_value: float


class TeamNeedProfile(BaseModel):
    """A team's need profile vs the top-8 by power rating (Phase 5.3)."""
    team_id: int
    season: str
    archetype_needs: List[NeedComponent] = Field(default_factory=list)
    component_needs: List[NeedComponent] = Field(default_factory=list)


class TradeFitRequest(BaseModel):
    """Body for POST /tools/trade-fit."""
    player_id: int
    team_id: int
    season: Optional[str] = None


class FitDimension(BaseModel):
    """One separately-measured Trade Fit dimension (positional / need / style / line / quality).

    `level` is 0-1 for the bar (None = not measurable). `tone` drives colour discipline —
    'neutral' for a LOW need (not a gap, never red); 'positive' for strength; 'warn' for a genuine
    stylistic mismatch. `uncertain`/`sd` flag model estimates (line, quality)."""
    key: str
    label: str
    level: Optional[float] = None
    value: str = ""
    note: str = ""
    tone: str = "neutral"          # positive | neutral | warn
    uncertain: bool = False
    sd: Optional[float] = None


class TradeFitResult(BaseModel):
    """Multi-dimension Trade Fit (Phase 5.3 rebuild): a positional gate * weighted need/style/line/
    quality blend -> a combined letter grade, ALWAYS decomposed into its dimensions. No zero-floor;
    need is one dimension, not the master score. The verdict notes context the model can't see."""
    player_id: int
    player_name: Optional[str] = None
    team_id: int
    season: str
    overall_grade: str             # A-F
    overall_score: float           # 0-100 (decomposable into `dimensions`)
    verdict_sentence: str = ""
    dimensions: List[FitDimension] = Field(default_factory=list)
    player_archetypes: List["ArchetypeWeight"] = Field(default_factory=list)
    need_profile: Optional[TeamNeedProfile] = None


class BestTeamFit(BaseModel):
    """A team whose gaps a player fills well (Phase 5.3 — Trade Fit 'best teams')."""
    team_id: int
    fit_score: float
    grade: Optional[str] = None
    reason: Optional[str] = None
    top_need_label: Optional[str] = None
    top_need_gap: Optional[float] = None


class MatchupPreviewTeam(BaseModel):
    """One team's side of a matchup preview."""
    team_id: int
    team_abbrev: Optional[str] = None
    power_rating: Optional[float] = None
    goalie_name: Optional[str] = None
    goalie_last10_gsax: Optional[float] = None
    fingerprint_top: List[str] = Field(default_factory=list)


class MatchupPreview(BaseModel):
    """Pregame matchup preview for an unplayed game (Phase 5.3)."""
    game_id: int
    game_state: str
    home: MatchupPreviewTeam
    away: MatchupPreviewTeam
    home_pregame_wp: Optional[float] = None
    style_clash: List[str] = Field(default_factory=list)
    season_series: Optional[str] = None
    notable_streaks: List[str] = Field(default_factory=list)


# resolve self/forward references for the Phase 5 models
LineFitProjection.model_rebuild()
TradeFitResult.model_rebuild()
PlayerValue.model_rebuild()    # resolves the forward ref to OverallSummary
GoalieSeason.model_rebuild()   # resolves forward refs to GoalieValue + OverallSummary


# --- Skills radar (Part B) ---------------------------------------------------

class RadarSpoke(BaseModel):
    """One radar axis: a percentile-within-position value with an honesty tag."""
    key: str
    label: str
    tag: str                      # skill | usage | style | proxy
    value: Optional[float] = None  # raw stat value (None for an archetype centroid radar)
    percentile: Optional[float] = None
    sd: Optional[float] = None
    present: bool = True


class PlayerRadar(BaseModel):
    """Skater skills radar (Part B): ordered, variable-length spokes + derived labels."""
    player_id: int
    season: str
    pos_group: Optional[str] = None
    spokes: List[RadarSpoke] = Field(default_factory=list)
    overall_label: Optional[str] = None
    offensive_label: Optional[str] = None
    defensive_label: Optional[str] = None
    descriptor: Optional[str] = None
    baseline: Optional[str] = None


class GoalieRadar(BaseModel):
    """Goalie skills radar (Part B): spokes percentiled within goalies."""
    goalie_id: int
    season: str
    games_played: Optional[int] = None
    spokes: List[RadarSpoke] = Field(default_factory=list)
    baseline: Optional[str] = None


# --- Archetype explainer (gallery + style-map) — placed after RadarSpoke (reused below) ---
class ArchetypeTrait(BaseModel):
    label: str
    dir: Optional[str] = None      # '+' | '-' (universal traits)
    z: float
    share: Optional[float] = None  # universal-trait one-sided share (0..1)


class ArchetypeExemplar(BaseModel):
    player_id: int
    name: Optional[str] = None
    season: str
    team_abbrev: Optional[str] = None
    weight: float


class ArchetypeCard(BaseModel):
    """One discovered archetype: characteristic centroid radar + measured traits + real exemplars."""
    key: str
    name: str
    pos_group: str
    family: Optional[str] = None
    descriptor: Optional[str] = None
    member_count: int
    universal_traits: List[ArchetypeTrait] = Field(default_factory=list)
    distinctive_traits: List[ArchetypeTrait] = Field(default_factory=list)
    centroid_radar: List[RadarSpoke] = Field(default_factory=list)
    exemplars: List[ArchetypeExemplar] = Field(default_factory=list)


class StyleMapPoint(BaseModel):
    player_id: int
    name: Optional[str] = None
    team_abbrev: Optional[str] = None
    season: str
    x: float
    y: float
    archetype: str
    membership: float
    is_boundary: bool


class StyleMapRegion(BaseModel):
    archetype: str
    x: float
    y: float
    member_count: int


class PlayerStyleMap(BaseModel):
    """A position's player style-map: real player points + discovered cluster regions.

    Distinct from the team-level `StyleMap` (Phase 3.2) above; named differently so it no
    longer shadows it (the duplicate class name broke GET /teams/style-map)."""
    pos_group: str
    points: List[StyleMapPoint] = Field(default_factory=list)
    regions: List[StyleMapRegion] = Field(default_factory=list)


class PlayerSummary(BaseModel):
    """Lightweight season stat line for the Players-card expansion (one query)."""
    player_id: int
    season: str
    games_played: int
    toi_per_gp: Optional[float] = None
    goals_per60: Optional[float] = None
    assists_per60: Optional[float] = None
    points_per60: Optional[float] = None
    xgf_pct: Optional[float] = None


class PreviewStat(BaseModel):
    """One base stat with its WITHIN-POSITION rank, for the inline row-expansion table."""
    key: str
    label: str
    value: Optional[float] = None
    fmt: str                       # int | rate | min | pct3 | plus
    rank: Optional[int] = None     # 1 = best among qualified peers (None for context-only rows like GP)
    n: Optional[int] = None        # size of the qualified peer pool


class PlayerPreview(BaseModel):
    """Skater base stats + within-position ranks + light bio for the inline expansion."""
    player_id: int
    season: str
    pos_group: Optional[str] = None
    age: Optional[int] = None
    shoots: Optional[str] = None
    stats: List[PreviewStat] = Field(default_factory=list)


class GoaliePreview(BaseModel):
    """Goalie base stats + within-goalie ranks for the inline expansion."""
    goalie_id: int
    season: str
    age: Optional[int] = None
    catches: Optional[str] = None
    stats: List[PreviewStat] = Field(default_factory=list)
