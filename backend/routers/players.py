"""Player-related API endpoints.

Provides endpoints for player details, trends, gamelog, shots, and vs-opponent stats.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from typing import Optional, List

import json

from google.cloud import bigquery

from models.schemas import (
    PlayerDetail, PlayerTrends, PlayerTrendPoint, PlayerGamelog, GamelogEntry,
    PlayerShots, ShotLocation, PlayerVsOpponent, PlayerSituational, EdgePlayerProfile,
    CompositeComponent, ArchetypeWeight, ArchetypeRankRow, COMPOSITE_LABELS,
    PlayerReconciliation, ClutchProfile, ConsistencyProfile, CoachTrustProfile,
    GameScorePoint, DivergenceBoardRow,
    PlayerTrajectory, TrajectoryCurvePoint, TrajectoryPathPoint, TwinEntry, PhysicalPoint,
    PlayerSearchResult, PlayerRadar,
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()


def _confidence_phrase(p: float) -> str:
    if p < 0.05:
        return "strong evidence"
    if p < 0.10:
        return "some evidence"
    if p < 0.20:
        return "weak, suggestive evidence"
    return "no clear evidence (within noise)"


def _components_from_row(r: dict) -> List[CompositeComponent]:
    """Build the composite stack from a player_composite row (components always present)."""
    return [CompositeComponent(key=k, label=lbl, value=float(r.get(k) or 0.0))
            for k, lbl in COMPOSITE_LABELS]


def _archetype_mix(player_id: int, season: str) -> tuple[List[ArchetypeWeight], Optional[str]]:
    rows = bq_service.query(f"""
        SELECT archetypes, primary_archetype
        FROM {bq_service.get_models_table_id('player_archetypes')}
        WHERE player_id = {player_id} AND season = '{season}'
        LIMIT 1
    """)
    if not rows:
        return [], None
    mix = [ArchetypeWeight(archetype=a["archetype"], weight=a["weight"])
           for a in json.loads(rows[0]["archetypes"])]
    return mix, rows[0]["primary_archetype"]


def _composite(player_id: int, season: str) -> Optional[dict]:
    rows = bq_service.query(f"""
        SELECT * FROM {bq_service.get_models_table_id('player_composite')}
        WHERE player_id = {player_id} AND season_window = '{season}'
        LIMIT 1
    """)
    return rows[0] if rows else None


def _season_str_to_id(season: Optional[str]) -> Optional[int]:
    """Convert a 'YYYY-YY' season string to the Edge YYYYYYYY id (e.g. 2024-25 -> 20242025)."""
    if not season:
        return None
    try:
        start = int(season[:4])
        return start * 10000 + (start + 1)
    except (ValueError, IndexError):
        return None


# Registered before /{player_id} so "divergence-board" is not coerced to an int player id.
@router.get("/divergence-board", response_model=List[DivergenceBoardRow])
@cache(ttl=1800)
async def get_divergence_board(
    season: Optional[str] = Query(None, description="season_window (default: latest)"),
) -> List[DivergenceBoardRow]:
    """Players whose coach-trust deployment most diverges from isolated value (Phase 4.3)."""
    board = bq_service.get_models_table_id('divergence_board')
    rosters = bq_service.get_full_table_id('stg_rosters')
    if not season:
        season = bq_service.query(f"SELECT MAX(season_window) AS s FROM {board}")[0]['s']
    rows = bq_service.query(f"""
        WITH nm AS (
            SELECT player_id, ANY_VALUE(first_name || ' ' || last_name) AS name,
                   ARRAY_AGG(team_id ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS team_id
            FROM {rosters}
            WHERE SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
            GROUP BY player_id
        ),
        tm AS (
            SELECT team_id, ANY_VALUE(team_abbrev) AS abbrev
            FROM {bq_service.get_full_table_id('mart_team_game_stats')} GROUP BY team_id
        )
        SELECT b.player_id, nm.name, tm.abbrev AS team_abbrev, b.pos_group AS position,
               b.side, b.divergence, b.trust_z, b.composite_z, b.composite_total, b.explanation
        FROM {board} b
        LEFT JOIN nm ON b.player_id = nm.player_id
        LEFT JOIN tm ON nm.team_id = tm.team_id
        WHERE b.season_window = '{season}'
        ORDER BY b.divergence DESC
    """)
    return [DivergenceBoardRow(
        player_id=r['player_id'], player_name=r.get('name'), position=r.get('position'),
        team_abbrev=r.get('team_abbrev'),
        side=r['side'], divergence=r['divergence'], trust_z=r['trust_z'],
        composite_z=r['composite_z'], composite_total=r['composite_total'],
        explanation=r['explanation']) for r in rows]


@router.get("/search", response_model=List[PlayerSearchResult])
@cache(ttl=3600)
async def search_players(
    q: str = Query(..., min_length=1, description="Name prefix/substring"),
    limit: int = Query(20, ge=1, le=50),
    season: Optional[str] = Query(None, description="Roster season (default: latest)"),
) -> List[PlayerSearchResult]:
    """Current-roster players matching `q` for the Lineup Lab PlayerPicker (Phase 5.2).

    Registered BEFORE /{player_id} so the single-segment path is not coerced to the int param.
    """
    from services import tools as tool_svc
    rows = await run_in_threadpool(tool_svc.search_players, q, limit, season)
    return [PlayerSearchResult(**r) for r in rows]


@router.get("/{player_id}/radar", response_model=PlayerRadar)
@cache(ttl=1800)
async def get_player_radar(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> PlayerRadar:
    """Skater skills radar: ordered spokes (percentile-within-position) + derived labels (Part B)."""
    from services.radar import player_radar as _radar
    payload = await run_in_threadpool(_radar, player_id, season)
    if payload is None:
        raise HTTPException(status_code=404, detail="No radar for this player")
    return PlayerRadar(**payload)


@router.get("/{player_id}/trajectory", response_model=PlayerTrajectory)
@cache(ttl=1800)
async def get_player_trajectory(player_id: int) -> PlayerTrajectory:
    """Career trajectory: aging-curve band for the player's archetype, his points/82 path by
    age, career twins + outcomes, and the physical-aging overlay (Phase 4.4)."""
    p = bq_service
    arch_rows = p.query(f"""
        SELECT primary_archetype, pos_group FROM {p.get_models_table_id('player_archetypes')}
        WHERE player_id = {player_id} ORDER BY season DESC LIMIT 1""")
    archetype = arch_rows[0]['primary_archetype'] if arch_rows else None
    pos_group = arch_rows[0]['pos_group'] if arch_rows else None

    def _curve(name):
        cr = p.query(f"""SELECT age, curve_value FROM {p.get_models_table_id('aging_curves')}
            WHERE archetype = @a ORDER BY age""",
            params=[bigquery.ScalarQueryParameter("a", "STRING", name)])
        return [TrajectoryCurvePoint(age=r['age'], curve_value=r['curve_value']) for r in cr]

    curve = _curve(archetype) if archetype else []
    curve_label = archetype
    if not curve:  # burst-defined / sparse archetype -> position-group fallback band
        fallback = "All Defensemen" if pos_group == "D" else "All Forwards"
        curve = _curve(fallback)
        curve_label = fallback

    # player's points/82 path by age
    pr = p.query(f"""
        WITH pg AS (
          SELECT season,
            SUM(individual_goals + first_assists + second_assists) / COUNT(*) * 82 AS points82
          FROM {p.get_full_table_id('mart_player_game_stats')}
          WHERE player_id = {player_id}
            AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
          GROUP BY season HAVING COUNT(*) >= 20
        ),
        b AS (SELECT birth_date FROM {p.get_full_table_id('stg_player_bio')} WHERE player_id = {player_id})
        SELECT pg.season, pg.points82,
          CAST(FLOOR(DATE_DIFF(DATE(CAST(SUBSTR(pg.season,1,4) AS INT64),10,1),
               (SELECT birth_date FROM b), DAY)/365.25) AS INT64) AS age
        FROM pg ORDER BY season""")
    path = [TrajectoryPathPoint(age=r['age'], season=r['season'], points82=r['points82'])
            for r in pr if r['age'] is not None]

    tw = p.query(f"""
        WITH nm AS (SELECT player_id, ANY_VALUE(first_name||' '||last_name) AS name
                    FROM {p.get_full_table_id('stg_rosters')} GROUP BY player_id)
        SELECT t.twin_id, nm.name, t.similarity, t.through_age, t.reduced_features,
               t.twin_next3_points82
        FROM {p.get_models_table_id('player_twins')} t LEFT JOIN nm ON t.twin_id = nm.player_id
        WHERE t.player_id = {player_id} ORDER BY t.similarity DESC""")
    twins = [TwinEntry(twin_id=r['twin_id'], twin_name=r.get('name'), similarity=r['similarity'],
                       through_age=r['through_age'], reduced_features=r['reduced_features'],
                       next3_points82=r.get('twin_next3_points82')) for r in tw]

    ph = p.query(f"""SELECT season, burst_rate, max_speed, early_warning
        FROM {p.get_models_table_id('player_physical')}
        WHERE player_id = {player_id} ORDER BY season""")
    physical = [PhysicalPoint(season=r['season'], burst_rate=r.get('burst_rate'),
                              max_speed=r.get('max_speed')) for r in ph]
    flag_enabled = any(r.get('early_warning') for r in ph)

    return PlayerTrajectory(player_id=player_id, archetype=archetype, curve_label=curve_label,
                            curve=curve, path=path, twins=twins, physical=physical,
                            burst_flag_enabled=flag_enabled)


@router.get("/{player_id}/reconciliation", response_model=PlayerReconciliation)
@cache(ttl=1800)
async def get_player_reconciliation(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> PlayerReconciliation:
    """Eye-test reconciliation: clutch + consistency + coach trust (Phase 4.3)."""
    if not season:
        season = bq_service.query(
            f"SELECT MAX(season) AS s FROM {bq_service.get_full_table_id('mart_player_game_score')}"
        )[0]['s']

    clutch = None
    cl = bq_service.query(f"""SELECT * FROM {bq_service.get_models_table_id('player_clutch')}
        WHERE player_id = {player_id} AND season_window = '{season}' LIMIT 1""")
    if cl:
        r = cl[0]
        clutch = ClutchProfile(
            n_shots=r['n_shots'], raw_ixg=r['raw_ixg'], clutch_ixg=r['clutch_ixg'],
            clutch_delta=r['clutch_delta'], p_value=r['p_value'],
            confidence=_confidence_phrase(r['p_value']))

    consistency = None
    co = bq_service.query(f"""SELECT * FROM {bq_service.get_models_table_id('player_consistency')}
        WHERE player_id = {player_id} AND season_window = '{season}' LIMIT 1""")
    if co:
        r = co[0]
        series = bq_service.query(f"""
            SELECT game_date, game_score
            FROM {bq_service.get_full_table_id('mart_player_game_score')}
            WHERE player_id = {player_id} AND season = '{season}'
              AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
            ORDER BY game_date""")
        consistency = ConsistencyProfile(
            games=r['games'], mean_gs=r['mean_gs'], sd_gs=r['sd_gs'], iqr_gs=r['iqr_gs'],
            good_game_share=r['good_game_share'], no_show_share=r['no_show_share'],
            consistency_index=r['consistency_index'],
            game_scores=[GameScorePoint(game_date=s['game_date'], game_score=s['game_score'])
                         for s in series])

    coach_trust = None
    ct = bq_service.query(f"""SELECT * FROM {bq_service.get_models_table_id('player_coach_trust')}
        WHERE player_id = {player_id} AND season_window = '{season}' LIMIT 1""")
    if ct:
        r = ct[0]
        coach_trust = CoachTrustProfile(
            trust_score=r['trust_score'], pk_share=r['pk_share'],
            protect_lead_rate=r['protect_lead_rate'], road_home_ratio=r['road_home_ratio'])

    return PlayerReconciliation(player_id=player_id, season=season, clutch=clutch,
                                consistency=consistency, coach_trust=coach_trust)


# NOTE: literal path — must be defined before the /{player_id} route so it isn't shadowed.
@router.get("/leaders", response_model=List[ArchetypeRankRow])
@cache(ttl=1800)
async def get_overall_leaders(
    position: str = Query("ALL", description="ALL | F | D"),
    season: Optional[str] = Query(None, description="Season (default: latest)"),
    limit: int = Query(50, ge=1, le=200),
) -> List[ArchetypeRankRow]:
    """The highest-value skaters overall, by composite total (Phase 4.2)."""
    arch = bq_service.get_models_table_id('player_archetypes')
    comp = bq_service.get_models_table_id('player_composite')
    rosters = bq_service.get_full_table_id('stg_rosters')
    if not season:
        season = bq_service.query(f"SELECT MAX(season_window) AS s FROM {comp}")[0]['s']
    groups = {"F": "('C','L','R')", "D": "('D')"}.get(position.upper(), "('C','L','R','D')")
    rows = bq_service.query(f"""
        WITH nm AS (
            SELECT player_id, ANY_VALUE(first_name || ' ' || last_name) AS name,
                   ANY_VALUE(position_code) AS position,
                   ARRAY_AGG(team_id ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS team_id
            FROM {rosters}
            WHERE SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
            GROUP BY player_id
        ),
        tm AS (
            SELECT team_id, ANY_VALUE(team_abbrev) AS abbrev
            FROM {bq_service.get_full_table_id('mart_team_game_stats')} GROUP BY team_id
        ),
        ar AS (
            SELECT player_id, archetypes, primary_archetype FROM {arch} WHERE season = '{season}'
        )
        SELECT c.*, nm.name, nm.position AS roster_pos, tm.abbrev AS team_abbrev,
               ar.archetypes, ar.primary_archetype AS primary_arch
        FROM {comp} c
        JOIN nm ON c.player_id = nm.player_id
        LEFT JOIN tm ON nm.team_id = tm.team_id
        LEFT JOIN ar ON c.player_id = ar.player_id
        WHERE c.season_window = '{season}' AND nm.position IN {groups}
        ORDER BY c.total DESC
        LIMIT {limit}
    """)
    out = []
    for r in rows:
        primary = r.get("primary_arch")
        weight = 0.0
        if r.get("archetypes"):
            weight = next((a["weight"] for a in json.loads(r["archetypes"])
                           if a["archetype"] == primary), 0.0)
        out.append(ArchetypeRankRow(
            player_id=r["player_id"], player_name=r.get("name"),
            team_abbrev=r.get("team_abbrev"), position=r.get("roster_pos"),
            composite_total=float(r["total"]),
            composite_total_sd=float(r["total_sd"]) if r.get("total_sd") is not None else None,
            components=_components_from_row(r), archetype_weight=weight,
            primary_archetype=primary))
    return out


@router.get("/{player_id}", response_model=PlayerDetail)
@cache(ttl=600)
async def get_player_detail(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2023-24)"),
) -> PlayerDetail:
    """Get detailed information for a specific player.

    Args:
        player_id: NHL player ID.
        season: Optional season filter.

    Returns:
        Player details including current season stats.

    Raises:
        HTTPException: If player not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Get aggregated player stats
    sql = f"""
    SELECT
        player_id,
        CONCAT(first_name, ' ', last_name) as player_name,
        position_code as position,
        team_id,
        COUNT(DISTINCT game_id) as games_played,
        AVG(toi_5v5) as toi_per_gp,
        AVG(primary_points_per60) as points_per60,
        AVG((individual_goals / toi_5v5) * 60.0) as goals_per60,
        AVG((first_assists / toi_5v5) * 60.0) as assists_per60,
        AVG(on_ice_xgf_pct) as cf_pct,
        AVG(ixg_per60) as hdcf_per60
    FROM {bq_service.get_full_table_id('mart_player_game_stats')}
    WHERE player_id = {player_id}
    GROUP BY player_id, first_name, last_name, position_code, team_id
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Player not found")

    row = results[0]

    # Get team abbrev
    team_sql = f"""
    SELECT DISTINCT team_abbrev
    FROM {bq_service.get_full_table_id('mart_team_game_stats')}
    WHERE team_id = {row['team_id']}
    LIMIT 1
    """
    team_result = bq_service.query(team_sql)
    team_abbrev = team_result[0]['team_abbrev'] if team_result else "UNK"

    # Get additional stats from new mart tables
    # Zone deployment
    zone_deployment = bq_service.get_player_zone_deployment(row['player_id'], season)
    ozs_pct = zone_deployment[0]['ozs_pct'] if zone_deployment else None
    dzs_pct = zone_deployment[0]['dzs_pct'] if zone_deployment else None
    nzs_pct = zone_deployment[0]['nzs_pct'] if zone_deployment else None

    # Shooting luck
    shooting_luck = bq_service.get_player_shooting_luck(row['player_id'], season)
    actual_shooting_pct = shooting_luck[0]['actual_shooting_pct'] if shooting_luck else None
    expected_shooting_pct = shooting_luck[0]['expected_shooting_pct'] if shooting_luck else None
    shooting_luck_delta = shooting_luck[0]['shooting_luck_delta'] if shooting_luck else None

    # Relative performance
    relative_stats = bq_service.get_player_relative(row['player_id'], season)
    relative_cf_pct = relative_stats[0]['relative_cf_pct'] if relative_stats else None
    relative_xgf_pct = relative_stats[0]['relative_xgf_pct'] if relative_stats else None

    # Get assists breakdown (first_assists and second_assists) from mart_player_game_stats
    assists_sql = f"""
    SELECT
        SUM(first_assists) as total_first_assists,
        SUM(second_assists) as total_second_assists,
        SAFE_DIVIDE(SUM(ihdcf), SUM(toi_5v5)) * 60 as avg_ihdcf_per60
    FROM {bq_service.get_full_table_id('mart_player_game_stats')}
    WHERE player_id = {row['player_id']}
    """
    assists_result = bq_service.query(assists_sql)
    first_assists = assists_result[0]['total_first_assists'] if assists_result else None
    second_assists = assists_result[0]['total_second_assists'] if assists_result else None
    ihdcf_per60 = assists_result[0]['avg_ihdcf_per60'] if assists_result else None

    comp = _composite(row['player_id'], season)
    components = _components_from_row(comp) if comp else []
    archetypes, primary_archetype = _archetype_mix(row['player_id'], season)

    return PlayerDetail(
        player_id=row['player_id'],
        player_name=row['player_name'],
        position=row['position'],
        team_id=row['team_id'],
        team_abbrev=team_abbrev,
        season=season,
        games_played=row['games_played'],
        toi_per_gp=row['toi_per_gp'],
        points_per60=row['points_per60'],
        goals_per60=row['goals_per60'],
        assists_per60=row['assists_per60'],
        cf_pct=row['cf_pct'],
        hdcf_per60=row['hdcf_per60'],
        first_assists=first_assists,
        second_assists=second_assists,
        ihdcf_per60=ihdcf_per60,
        ozs_pct=ozs_pct,
        dzs_pct=dzs_pct,
        nzs_pct=nzs_pct,
        relative_cf_pct=relative_cf_pct,
        relative_xgf_pct=relative_xgf_pct,
        actual_shooting_pct=actual_shooting_pct,
        expected_shooting_pct=expected_shooting_pct,
        shooting_luck_delta=shooting_luck_delta,
        composite_total=float(comp['total']) if comp else None,
        composite_total_sd=float(comp['total_sd']) if comp and comp.get('total_sd') is not None else None,
        composite_components=components,
        archetypes=archetypes,
        primary_archetype=primary_archetype,
    )


@router.get("/archetypes/{archetype}", response_model=List[ArchetypeRankRow])
@cache(ttl=1800)
async def get_archetype_ranking(
    archetype: str,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
    limit: int = Query(50, ge=1, le=200),
) -> List[ArchetypeRankRow]:
    """Players whose primary archetype is `archetype`, ranked by composite total (Phase 4.2)."""
    arch = bq_service.get_models_table_id('player_archetypes')
    comp = bq_service.get_models_table_id('player_composite')
    rosters = bq_service.get_full_table_id('stg_rosters')
    if not season:
        season = bq_service.query(f"SELECT MAX(season) AS s FROM {arch}")[0]['s']
    rows = bq_service.query(f"""
        WITH a AS (
            SELECT player_id, archetypes, primary_archetype AS primary_arch
            FROM {arch} WHERE season = '{season}' AND primary_archetype = @archetype
        ),
        nm AS (
            SELECT player_id, ANY_VALUE(first_name || ' ' || last_name) AS name,
                   ANY_VALUE(position_code) AS position,
                   ARRAY_AGG(team_id ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS team_id
            FROM {rosters}
            WHERE SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
            GROUP BY player_id
        ),
        tm AS (
            SELECT team_id, ANY_VALUE(team_abbrev) AS abbrev
            FROM {bq_service.get_full_table_id('mart_team_game_stats')} GROUP BY team_id
        )
        SELECT a.player_id, a.archetypes, a.primary_arch, nm.name, nm.position,
               tm.abbrev AS team_abbrev, c.*
        FROM a
        JOIN {comp} c ON a.player_id = c.player_id AND c.season_window = '{season}'
        LEFT JOIN nm ON a.player_id = nm.player_id
        LEFT JOIN tm ON nm.team_id = tm.team_id
        ORDER BY c.total DESC
        LIMIT {limit}
    """, params=[bigquery.ScalarQueryParameter("archetype", "STRING", archetype)])
    out = []
    for r in rows:
        weight = next((a["weight"] for a in json.loads(r["archetypes"])
                       if a["archetype"] == archetype), 0.0)
        out.append(ArchetypeRankRow(
            player_id=r["player_id"], player_name=r.get("name"),
            team_abbrev=r.get("team_abbrev"), position=r.get("position"),
            composite_total=float(r["total"]),
            composite_total_sd=float(r["total_sd"]) if r.get("total_sd") is not None else None,
            components=_components_from_row(r), archetype_weight=weight,
            primary_archetype=r.get("primary_arch")))
    return out


@router.get("/{player_id}/edge", response_model=EdgePlayerProfile)
@cache(ttl=86400)
async def get_player_edge(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2024-25); latest if omitted"),
    game_type: int = Query(2, description="2=regular season, 3=playoffs"),
) -> EdgePlayerProfile:
    """NHL Edge skater profile: skating speed/bursts, distance, shot speed, zone time,
    and danger-bucket shot share (season-aggregate tracking data)."""
    row = bq_service.get_player_edge(player_id, _season_str_to_id(season), game_type)
    if not row:
        raise HTTPException(status_code=404, detail="No NHL Edge data for this player/season")
    return EdgePlayerProfile(**row)


@router.get("/{player_id}/trends", response_model=PlayerTrends)
@cache(ttl=600)
async def get_player_trends(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2023-24)"),
) -> PlayerTrends:
    """Get rolling trends for a specific player.

    Args:
        player_id: NHL player ID.
        season: Optional season filter.

    Returns:
        Player trends including 5-game and 10-game rolling averages.

    Raises:
        HTTPException: If player not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Calculate rolling averages
    sql = f"""
    WITH ordered_games AS (
        SELECT
            game_date,
            primary_points_per60,
            on_ice_xgf_pct as cf_pct,
            ROW_NUMBER() OVER (ORDER BY game_date) as game_num
        FROM {bq_service.get_full_table_id('mart_player_game_stats')}
        WHERE player_id = {player_id}
    )
    SELECT
        game_date,
        AVG(primary_points_per60) OVER (
            ORDER BY game_date
            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ) as points_per60_5gp,
        AVG(cf_pct) OVER (
            ORDER BY game_date
            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ) as cf_pct_5gp,
        game_num
    FROM ordered_games
    WHERE game_num >= 5
    ORDER BY game_date
    LIMIT 50
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Player not found or insufficient data")

    points_per60_5gp = []
    points_per60_10gp = []  # TODO: Add 10-game rolling
    cf_pct_5gp = []
    cf_pct_10gp = []  # TODO: Add 10-game rolling

    for row in results:
        points_per60_5gp.append(PlayerTrendPoint(
            game_date=row['game_date'],
            value=row['points_per60_5gp']
        ))
        cf_pct_5gp.append(PlayerTrendPoint(
            game_date=row['game_date'],
            value=row['cf_pct_5gp']
        ))

    return PlayerTrends(
        player_id=player_id,
        season=season,
        points_per60_5gp=points_per60_5gp,
        points_per60_10gp=points_per60_10gp,
        cf_pct_5gp=cf_pct_5gp,
        cf_pct_10gp=cf_pct_10gp
    )


@router.get("/{player_id}/gamelog", response_model=PlayerGamelog)
@cache(ttl=600)
async def get_player_gamelog(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2023-24)"),
    limit: int = Query(20, description="Number of games to return", ge=1, le=100),
) -> PlayerGamelog:
    """Get game-by-game log for a specific player.

    Args:
        player_id: NHL player ID.
        season: Optional season filter.
        limit: Number of games to return (default 20, max 100).

    Returns:
        Player gamelog with per-game stats.

    Raises:
        HTTPException: If player not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Get game-by-game stats with opponent info
    sql = f"""
    WITH player_games AS (
        SELECT
            p.game_id,
            p.game_date,
            p.team_id,
            p.toi_5v5 as toi,
            CAST(p.primary_points_per60 * p.toi_5v5 / 60.0 AS INT64) as points,
            0 as goals,
            0 as assists,
            0 as shots,
            0 as cf,
            CAST(p.ixg_per60 * p.toi_5v5 / 60.0 AS INT64) as hdcf
        FROM {bq_service.get_full_table_id('mart_player_game_stats')} p
        WHERE p.player_id = {player_id}
    ),
    game_info AS (
        SELECT
            g.game_id,
            CASE
                WHEN g.home_team_id = pg.team_id THEN g.away_team_id
                ELSE g.home_team_id
            END as opponent_id,
            CASE
                WHEN g.home_team_id = pg.team_id THEN g.away_team_abbrev
                ELSE g.home_team_abbrev
            END as opponent_abbrev
        FROM {bq_service.get_full_table_id('stg_boxscores')} g
        INNER JOIN player_games pg ON g.game_id = pg.game_id
    )
    SELECT
        pg.*,
        gi.opponent_id,
        gi.opponent_abbrev
    FROM player_games pg
    LEFT JOIN game_info gi ON pg.game_id = gi.game_id
    ORDER BY pg.game_date DESC
    LIMIT {limit}
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Player not found")

    games: List[GamelogEntry] = []
    for row in results:
        games.append(GamelogEntry(
            game_id=row['game_id'],
            game_date=row['game_date'],
            opponent_id=row['opponent_id'],
            opponent_abbrev=row['opponent_abbrev'],
            toi=row['toi'],
            goals=row['goals'],
            assists=row['assists'],
            points=row['points'],
            shots=row['shots'],
            cf=row['cf'],
            hdcf=row['hdcf']
        ))

    return PlayerGamelog(
        player_id=player_id,
        season=season,
        games=games
    )


@router.get("/{player_id}/shots", response_model=PlayerShots)
@cache(ttl=600)
async def get_player_shots(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2023-24)"),
) -> PlayerShots:
    """Get shot data for a specific player.

    Args:
        player_id: NHL player ID.
        season: Optional season filter.

    Returns:
        Player shot data including location and danger level breakdowns.

    Raises:
        HTTPException: If player not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Get shot location data from int_shot_types, joined to the in-house xG model.
    sql = f"""
    SELECT
        s.x_coord,
        s.y_coord,
        s.is_goal,
        s.is_high_danger,
        CASE
            WHEN s.is_high_danger THEN 'high'
            WHEN ABS(s.x_coord) > 50 OR ABS(s.y_coord) > 20 THEN 'low'
            ELSE 'medium'
        END as danger_level,
        mx.xg
    FROM {bq_service.get_full_table_id('int_shot_types')} s
    LEFT JOIN {bq_service.get_models_table_id('shot_xg')} mx
        ON s.game_id = mx.game_id AND s.event_id = mx.event_id
    WHERE s.shooter_player_id = {player_id}
    LIMIT 500
    """

    results = bq_service.query(sql)

    # Calculate summary stats
    total_shots = len(results)
    low_danger = 0
    medium_danger = 0
    high_danger = 0

    shot_locations: List[ShotLocation] = []
    for row in results:
        danger = row['danger_level']
        if danger == 'high':
            high_danger += 1
        elif danger == 'medium':
            medium_danger += 1
        else:
            low_danger += 1

        shot_locations.append(ShotLocation(
            x=row['x_coord'] or 0.0,
            y=row['y_coord'] or 0.0,
            is_goal=row['is_goal'],
            danger_level=danger,
            xg=row.get('xg')
        ))

    return PlayerShots(
        player_id=player_id,
        season=season,
        total_shots=total_shots,
        low_danger=low_danger,
        medium_danger=medium_danger,
        high_danger=high_danger,
        shot_locations=shot_locations
    )


@router.get("/{player_id}/vs/{opponent_id}", response_model=PlayerVsOpponent)
@cache(ttl=600)
async def get_player_vs_opponent(
    player_id: int,
    opponent_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2023-24)"),
) -> PlayerVsOpponent:
    """Get player stats vs specific opponent.

    Args:
        player_id: NHL player ID.
        opponent_id: Opponent team ID.
        season: Optional season filter.

    Returns:
        Player stats vs opponent with small_sample flag if < 3 games.

    Raises:
        HTTPException: If player or opponent not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Find games where player faced this opponent
    sql = f"""
    WITH player_games AS (
        SELECT
            p.game_id,
            p.team_id,
            p.toi_5v5,
            p.primary_points_per60,
            0.5 as cf_pct  -- TODO: Calculate from on-ice data
        FROM {bq_service.get_full_table_id('mart_player_game_stats')} p
        WHERE p.player_id = {player_id}
    ),
    opponent_games AS (
        SELECT DISTINCT g.game_id
        FROM {bq_service.get_full_table_id('stg_boxscores')} g
        WHERE (g.home_team_id = {opponent_id} OR g.away_team_id = {opponent_id})
          AND g.season = '{season}'
    )
    SELECT
        COUNT(*) as games_played,
        AVG(pg.toi_5v5) as toi_per_gp,
        AVG(pg.primary_points_per60) as points_per60,
        AVG(pg.cf_pct) as cf_pct
    FROM player_games pg
    INNER JOIN opponent_games og ON pg.game_id = og.game_id
    """

    results = bq_service.query(sql)
    if not results or results[0]['games_played'] == 0:
        raise HTTPException(status_code=404, detail="No games found against this opponent")

    row = results[0]
    small_sample = row['games_played'] < 3

    return PlayerVsOpponent(
        player_id=player_id,
        opponent_id=opponent_id,
        season=season,
        games_played=row['games_played'],
        small_sample=small_sample,
        toi_per_gp=row['toi_per_gp'] if not small_sample else None,
        points_per60=row['points_per60'] if not small_sample else None,
        cf_pct=row['cf_pct'] if not small_sample else None
    )


@router.get("/{player_id}/situational", response_model=List[PlayerSituational])
@cache(ttl=21600)  # 6 hours
async def get_player_situational(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., '2024-25')"),
) -> List[PlayerSituational]:
    """Get situational stats for a player.

    Args:
        player_id: NHL player ID.
        season: Optional season filter in format "YYYY-YY".

    Returns:
        List of situational stat records (usually 4: all, 5v5, pp, pk).

    Raises:
        HTTPException: If player not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('mart_player_situational')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else "2024-25"

    # Get situational data using the service layer
    results = bq_service.get_player_situational(player_id, season)

    if not results:
        raise HTTPException(status_code=404, detail="Player not found")

    situational_stats = []
    for row in results:
        stat = PlayerSituational(
            player_id=row['player_id'],
            season=row['season'],
            situation=row['situation'],
            toi_per_gp=row.get('toi_per_gp'),
            points_per60=row.get('points_per60'),
            goals_per60=row.get('goals_per60'),
            ixg_per60=row.get('ixg_per60'),
            cf_pct=row.get('cf_pct'),
            hdcf_per60=row.get('hdcf_per60')
        )
        situational_stats.append(stat)

    return situational_stats
