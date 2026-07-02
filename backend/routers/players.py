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
    PlayerShotQuality, ShotQualityBand, SeasonTotalRank,
    CompositeComponent, ArchetypeWeight, ArchetypeRankRow, COMPOSITE_LABELS,
    PlayerReconciliation, ClutchProfile, ConsistencyProfile, CoachTrustProfile,
    GameScorePoint, DivergenceBoardRow,
    PlayerTrajectory, TrajectoryCurvePoint, TrajectoryPathPoint, TwinEntry, PhysicalPoint,
    PlayerSearchResult, PlayerRadar, PlayerSummary, PlayerValue, ValueGapRead, GAR_LABELS,
    ImpactContext, WowyPartner, PlayerWowy,
    OverallSummary, OverallComponent, PreviewStat, PlayerPreview,
    DeploymentRow, DeploymentBoard, PlayerDeploymentEntry,
    PlayerContract, CapShareYear,
    ValueNeighbor, ValueNeighborhood,
    PlayerVerdict,
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


_DURABLE_SEASONS = ['2021-22', '2022-23', '2023-24', '2024-25', '2025-26']


def _durable_archetype(player_id: int) -> Optional[str]:
    """The DURABLE archetype label: the modal primary_archetype across the last three seasons (ties
    break toward the more recent). Same rule the verdict builder uses, so the header chip and the
    composed verdict read one identity, not the current-season flip."""
    rows = bq_service.query(f"""
        SELECT season, primary_archetype
        FROM {bq_service.get_models_table_id('player_archetypes')}
        WHERE player_id = {player_id}
          AND season IN ({", ".join(f"'{s}'" for s in _DURABLE_SEASONS)})
        ORDER BY season DESC
    """)
    last3 = [r['primary_archetype'] for r in (rows or [])[:3] if r.get('primary_archetype')]
    if not last3:
        return None
    counts: dict = {}
    for a in last3:
        counts[a] = counts.get(a, 0) + 1
    top = max(counts.values())
    for a in last3:  # most-recent among the labels tied for the top count (last3 is newest-first)
        if counts[a] == top:
            return a
    return last3[0]


def _season_totals(player_id: int, season: str, is_goalie: bool) -> List[SeasonTotalRank]:
    """Season totals with LEAGUE-WIDE rank (scoring-race position for skaters; among goalies for
    goalies). Computed from full-league season aggregates, NOT the per-position rate ranks elsewhere.
    Skaters rank on goals/assists/points/points-per-GP/shots; goalies on GAA/SV%/GSAx/wins/shutouts.
    Shots-on-goal are derived from int_shot_attempts_all (is_on_net), since the skater mart has shot
    ATTEMPTS, not SOG."""
    pgs = bq_service.get_full_table_id('mart_player_game_stats')
    nhl = "SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')"
    out: List[SeasonTotalRank] = []
    if not is_goalie:
        sa = bq_service.get_full_table_id('int_shot_attempts_all')
        rows = bq_service.query(f"""
            WITH agg AS (
                SELECT player_id,
                       COUNT(DISTINCT game_id) AS gp,
                       SUM(individual_goals) AS g,
                       SUM(first_assists) + SUM(second_assists) AS a,
                       SUM(individual_goals) + SUM(first_assists) + SUM(second_assists) AS p
                FROM {pgs}
                WHERE season = '{season}' AND {nhl} AND position_code IN ('C', 'L', 'R', 'D')
                GROUP BY player_id
            ),
            sog AS (
                SELECT COALESCE(shooting_player_id, scoring_player_id) AS pid, COUNT(*) AS s
                FROM {sa}
                WHERE season = '{season}' AND {nhl} AND is_on_net
                GROUP BY COALESCE(shooting_player_id, scoring_player_id)
            ),
            j AS (
                SELECT a.player_id, a.gp, a.g, a.a, a.p,
                       CASE WHEN a.gp > 0 THEN a.p * 1.0 / a.gp ELSE NULL END AS p_gp,
                       COALESCE(sog.s, 0) AS s
                FROM agg a LEFT JOIN sog ON sog.pid = a.player_id
                WHERE a.gp >= 1
            ),
            ranked AS (
                SELECT player_id, g, a, p, p_gp, s,
                       COUNT(*) OVER () AS pool,
                       RANK() OVER (ORDER BY g DESC) AS g_rank,
                       RANK() OVER (ORDER BY a DESC) AS a_rank,
                       RANK() OVER (ORDER BY p DESC) AS p_rank,
                       RANK() OVER (ORDER BY p_gp DESC NULLS LAST) AS pgp_rank,
                       RANK() OVER (ORDER BY s DESC) AS s_rank
                FROM j
            )
            SELECT * FROM ranked WHERE player_id = {int(player_id)}
        """)
        if not rows:
            return out
        r = rows[0]
        pool = r.get('pool')
        out.append(SeasonTotalRank(key='goals', label='Goals', display=str(int(r.get('g') or 0)), rank=r.get('g_rank'), pool=pool))
        out.append(SeasonTotalRank(key='assists', label='Assists', display=str(int(r.get('a') or 0)), rank=r.get('a_rank'), pool=pool))
        out.append(SeasonTotalRank(key='points', label='Points', display=str(int(r.get('p') or 0)), rank=r.get('p_rank'), pool=pool))
        out.append(SeasonTotalRank(key='points_per_gp', label='Points/GP',
                                   display=f"{float(r['p_gp']):.2f}" if r.get('p_gp') is not None else '—',
                                   rank=r.get('pgp_rank'), pool=pool))
        out.append(SeasonTotalRank(key='shots', label='Shots', display=str(int(r.get('s') or 0)), rank=r.get('s_rank'), pool=pool))
        return out

    # goalie variant
    gs = bq_service.get_full_table_id('mart_goalie_season')
    rows = bq_service.query(f"""
        WITH qual AS (
            SELECT goalie_id, gaa, save_pct, gsax, wins, shutouts
            FROM {gs} WHERE season = '{season}' AND games_played >= 1
        ),
        ranked AS (
            SELECT goalie_id, gaa, save_pct, gsax, wins, shutouts,
                   COUNT(*) OVER () AS pool,
                   RANK() OVER (ORDER BY gaa ASC NULLS LAST) AS gaa_rank,
                   RANK() OVER (ORDER BY save_pct DESC NULLS LAST) AS svp_rank,
                   RANK() OVER (ORDER BY gsax DESC NULLS LAST) AS gsax_rank,
                   RANK() OVER (ORDER BY wins DESC NULLS LAST) AS wins_rank,
                   RANK() OVER (ORDER BY shutouts DESC NULLS LAST) AS so_rank
            FROM qual
        )
        SELECT * FROM ranked WHERE goalie_id = {int(player_id)}
    """)
    if not rows:
        return out
    r = rows[0]
    pool = r.get('pool')
    out.append(SeasonTotalRank(key='gaa', label='GAA', display=f"{float(r['gaa']):.2f}" if r.get('gaa') is not None else '—', rank=r.get('gaa_rank'), pool=pool))
    out.append(SeasonTotalRank(key='save_pct', label='SV%',
                               display=(f"{float(r['save_pct']):.3f}".lstrip('0') if r.get('save_pct') is not None else '—'),
                               rank=r.get('svp_rank'), pool=pool))
    out.append(SeasonTotalRank(key='gsax', label='GSAx', display=(f"{float(r['gsax']):+.1f}" if r.get('gsax') is not None else '—'), rank=r.get('gsax_rank'), pool=pool))
    out.append(SeasonTotalRank(key='wins', label='Wins', display=str(int(r.get('wins') or 0)), rank=r.get('wins_rank'), pool=pool))
    out.append(SeasonTotalRank(key='shutouts', label='Shutouts', display=str(int(r.get('shutouts') or 0)), rank=r.get('so_rank'), pool=pool))
    return out


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


def _value_block(player_id: int, season: str):
    """Build the Value (GAR/WAR) block + Impact-vs-Value percentile gap read.

    GAR (actual goals above replacement, 'what happened') vs impact_goals (the RAPM-based value
    from composite, 'what tends to repeat'). Percentiles are within position group; the read is
    deterministic + asymmetric and cites the MEASURED stability r-values (consistency rule)."""
    from models_ml import config as mlcfg
    from insight_engine.templates import value_gap
    floor = mlcfg.GAR_CONFIG["MIN_TOI_5V5_FOR_RANKING"]
    stab = mlcfg.GAR_STABILITY_YOY
    gar_t = bq_service.get_models_table_id("player_gar")
    comp_t = bq_service.get_models_table_id("player_composite")

    rows = bq_service.query(f"""
        WITH base AS (
            SELECT g.player_id, g.position, g.gar, g.war, g.gar_sd, g.war_sd,
                   g.ev_offense, g.pp, g.ev_defense, g.pk, g.penalty, g.faceoff,
                   (coalesce(c.ev_offense, 0) + coalesce(c.ev_defense, 0)
                    + coalesce(c.pp, 0) + coalesce(c.pk, 0)) AS impact_goals,
                   case when g.position = 'D' then 'D' else 'F' end AS pg
            FROM {gar_t} g
            LEFT JOIN {comp_t} c
              ON g.player_id = c.player_id AND g.season_window = c.season_window
            WHERE g.season_window = '{season}' AND g.toi_5v5 >= {floor}
        ),
        ranked AS (
            SELECT *, percent_rank() OVER (PARTITION BY pg ORDER BY gar) AS value_pct,
                      percent_rank() OVER (PARTITION BY pg ORDER BY impact_goals) AS impact_pct
            FROM base
        )
        SELECT * FROM ranked WHERE player_id = {player_id} LIMIT 1
    """)
    qualified = bool(rows)
    if not rows:  # below the ranking floor — still surface GAR, without percentile/read
        raw = bq_service.query(f"""SELECT player_id, position, gar, war, gar_sd, war_sd,
            ev_offense, pp, ev_defense, pk, penalty, faceoff
            FROM {gar_t} WHERE player_id = {player_id} AND season_window = '{season}' LIMIT 1""")
        if not raw:
            return None
        rows = raw

    r = rows[0]
    comps = [CompositeComponent(key=k, label=lbl, value=float(r.get(k) or 0.0))
             for k, lbl in GAR_LABELS]
    out = dict(gar=float(r["gar"]), war=float(r["war"]),
               gar_sd=float(r.get("gar_sd") or 0.0), war_sd=float(r.get("war_sd") or 0.0),
               components=comps,
               production_r=stab["production_r"], rapm_r=stab["rapm_r"],
               finishing_r=stab["finishing_r"])
    if qualified and r.get("value_pct") is not None:
        vp, ip = float(r["value_pct"]), float(r["impact_pct"])
        read = value_gap.read(
            name=_player_short_name(player_id), value_pct=vp, impact_pct=ip,
            production_r=stab["production_r"], rapm_r=stab["rapm_r"], finishing_r=stab["finishing_r"])
        out.update(value_percentile=vp, impact_percentile=ip,
                   impact_goals=float(r.get("impact_goals") or 0.0),
                   gap_percentile_points=round((vp - ip) * 100, 1),
                   read=ValueGapRead(case=read["case"], headline=read["headline"], body=read["body"]))
    out["overall"] = _skater_overall(player_id, season)
    return PlayerValue(**out)


def _skater_overall(player_id: int, season: str) -> Optional[OverallSummary]:
    """The within-position Overall summary for the player card (Phase 6 Overall). Card-only —
    never a sort key. Its component percentiles are the SAME within-position percent_ranks the
    value block surfaces (production = GAR, play-driving = RAPM-based composite), so the number
    matches the lenses shown beside it (consistency rule)."""
    rows = bq_service.query(f"""
        SELECT overall_percentile, production_percentile, play_driving_percentile,
               pos_group, w_production, w_play_driving
        FROM {bq_service.get_models_table_id('player_overall')}
        WHERE player_id = {player_id} AND season_window = '{season}' LIMIT 1""")
    if not rows:
        return None
    r = rows[0]
    return OverallSummary(
        overall_percentile=float(r["overall_percentile"]), pos_group=r.get("pos_group"),
        components=[
            OverallComponent(key="production", label="Production (GAR)",
                             percentile=_f(r.get("production_percentile"))),
            OverallComponent(key="play_driving", label="Play-Driving (RAPM)",
                             percentile=_f(r.get("play_driving_percentile"))),
        ],
        weights={"production": _f(r.get("w_production")), "play_driving": _f(r.get("w_play_driving"))})


def _f(v):
    return float(v) if v is not None else None


def _player_short_name(player_id: int) -> str:
    rows = bq_service.query(
        f"SELECT ANY_VALUE(last_name) AS n FROM {bq_service.get_full_table_id('stg_rosters')} "
        f"WHERE player_id = {player_id}")
    return (rows[0]["n"] if rows and rows[0].get("n") else "This player")


# ── Deployment-efficiency board (the Divergence Board rework) ───────────────────────────────
# Mirrors models_ml.config.DEPLOYMENT board-selection rules (under-used usage floor + PK gate).
_DEP_SITUATIONS = ("all", "5v5", "pp", "pk", "key_moments")
_DEP_FLOORED = {"all", "5v5", "key_moments"}           # usage types where 0 = healthy scratch
_DEP_UNDER_USAGE_FLOOR = 0.12
_DEP_PK_SD_GATE = 0.5
_DEP_CAPTION = {
    "all": "Comparing total ice time against overall value.",
    "5v5": "Comparing 5v5 ice time against even-strength (RAPM) impact.",
    "pp": "Comparing power-play time against power-play impact.",
    "pk": "Comparing penalty-kill time against penalty-kill + defensive impact.",
    "key_moments": "Comparing high-leverage ice time against overall value — “key moments” = the "
                   "most pivotal 25% of game time by win-probability leverage.",
}


def _deployment_board_sync(situation: str, limit: int) -> DeploymentBoard:
    from insight_engine.templates.divergence import deployment_explain
    dep = bq_service.get_models_table_id("deployment_efficiency")
    rosters = bq_service.get_full_table_id("stg_rosters")
    teams = bq_service.get_full_table_id("mart_team_game_stats")
    rows = bq_service.query(f"""
        WITH nm AS (
            SELECT player_id, ANY_VALUE(first_name || ' ' || last_name) AS name,
                   ARRAY_AGG(team_id ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS team_id
            FROM {rosters}
            WHERE SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
            GROUP BY player_id
        ),
        tm AS (SELECT team_id, ANY_VALUE(team_abbrev) AS abbrev FROM {teams} GROUP BY team_id)
        SELECT d.*, nm.name, tm.abbrev AS team_abbrev
        FROM {dep} d
        LEFT JOIN nm ON d.player_id = nm.player_id
        LEFT JOIN tm ON nm.team_id = tm.team_id
        WHERE d.situation = '{situation}'
    """)
    value_label = rows[0]["value_label"] if rows else ""
    floored = situation in _DEP_FLOORED

    def mk(side, r):
        return DeploymentRow(
            player_id=r["player_id"], player_name=r.get("name"), position=r.get("position"),
            team_abbrev=r.get("team_abbrev"),
            actual_pctile=r["actual_pctile"], justified_pctile=r["justified_pctile"],
            gap=r["gap"], gap_sd=r["gap_sd"], value_pctile=r["value_pctile"],
            value_rank=int(r["value_rank"]), n_pool=int(r["n_pool"]),
            explanation=deployment_explain(side=side, situation=situation, value_label=value_label,
                                           value_rank=int(r["value_rank"]), n_pool=int(r["n_pool"]),
                                           actual_pctile=r["actual_pctile"], position=r.get("position") or "F"))

    over = sorted((r for r in rows if r["conf_gap"] > 0), key=lambda r: -r["conf_gap"])
    under = [r for r in rows if r["conf_gap"] < 0]
    if floored:
        under = [r for r in under if r["actual_pctile"] >= _DEP_UNDER_USAGE_FLOOR]
    if situation == "pk":
        under = [r for r in under if r["value_sd_pctile"] <= _DEP_PK_SD_GATE]
    under = sorted(under, key=lambda r: r["conf_gap"])
    return DeploymentBoard(
        situation=situation, value_label=value_label, caption=_DEP_CAPTION.get(situation, ""),
        over=[mk("over", r) for r in over[:limit]],
        under=[mk("under", r) for r in under[:limit]])


@router.get("/deployment-board", response_model=DeploymentBoard)
@cache(ttl=1800)
async def get_deployment_board(
    situation: str = Query("all", description="all | 5v5 | pp | pk | key_moments"),
    limit: int = Query(15, ge=1, le=40),
) -> DeploymentBoard:
    """Deployment efficiency: actual vs justified usage, by situation (the Divergence Board rework)."""
    if situation not in _DEP_SITUATIONS:
        raise HTTPException(status_code=400, detail=f"situation must be one of {_DEP_SITUATIONS}")
    return await run_in_threadpool(_deployment_board_sync, situation, limit)


def _player_deployment_sync(player_id: int):
    dep = bq_service.get_models_table_id("deployment_efficiency")
    rows = bq_service.query(
        f"SELECT situation, value_label, actual_pctile, justified_pctile, gap, value_rank, n_pool "
        f"FROM {dep} WHERE player_id = {int(player_id)}")
    order = {s: i for i, s in enumerate(_DEP_SITUATIONS)}
    rows.sort(key=lambda r: order.get(r["situation"], 99))
    return [PlayerDeploymentEntry(
        situation=r["situation"], value_label=r["value_label"],
        actual_pctile=r["actual_pctile"], justified_pctile=r["justified_pctile"],
        gap=r["gap"], value_rank=int(r["value_rank"]), n_pool=int(r["n_pool"])) for r in rows]


@router.get("/{player_id}/deployment", response_model=List[PlayerDeploymentEntry])
@cache(ttl=1800)
async def get_player_deployment(player_id: int) -> List[PlayerDeploymentEntry]:
    """A single player's full deployment profile across situations (the board-row expansion)."""
    return await run_in_threadpool(_player_deployment_sync, player_id)


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
    # the trust window is labelled "{start}_{end}" (e.g. 2023-24_2025-26); the archetype tag
    # comes from the radar of its END season.
    radar_season = season.split('_')[-1] if season and '_' in season else season
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
        ),
        ar AS (
            SELECT player_id, offensive_label, overall_label
            FROM {bq_service.get_models_table_id('player_radar')}
            WHERE season = '{radar_season}'
        )
        SELECT b.player_id, nm.name, tm.abbrev AS team_abbrev, b.pos_group AS position,
               b.side, b.divergence, b.trust_z, b.composite_z, b.composite_total, b.explanation,
               ar.offensive_label, ar.overall_label
        FROM {board} b
        LEFT JOIN nm ON b.player_id = nm.player_id
        LEFT JOIN tm ON nm.team_id = tm.team_id
        LEFT JOIN ar ON b.player_id = ar.player_id
        WHERE b.season_window = '{season}'
        ORDER BY b.divergence DESC
    """)
    return [DivergenceBoardRow(
        player_id=r['player_id'], player_name=r.get('name'), position=r.get('position'),
        team_abbrev=r.get('team_abbrev'),
        side=r['side'], divergence=r['divergence'], trust_z=r['trust_z'],
        composite_z=r['composite_z'], composite_total=r['composite_total'],
        explanation=r['explanation'],
        archetype=(r.get('offensive_label') or r.get('overall_label'))) for r in rows]


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


@router.get("/{player_id}/summary", response_model=PlayerSummary)
@cache(ttl=1800)
async def get_player_summary(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> PlayerSummary:
    """Fast single-query season stat line for the Players-card expansion (Part B usability)."""
    if not season:
        r = bq_service.query(
            f"SELECT MAX(season) AS s FROM {bq_service.get_full_table_id('mart_player_game_stats')} "
            f"WHERE player_id = {player_id}")
        season = r[0]['s'] if r and r[0]['s'] else None
    rows = bq_service.query(f"""
        SELECT COUNT(DISTINCT game_id) AS games_played,
               AVG(toi_5v5) AS toi_per_gp,
               AVG((individual_goals / toi_5v5) * 60.0) AS goals_per60,
               AVG((first_assists / toi_5v5) * 60.0) AS assists_per60,
               AVG(primary_points_per60) AS points_per60,
               AVG(on_ice_xgf_pct) AS xgf_pct
        FROM {bq_service.get_full_table_id('mart_player_game_stats')}
        WHERE player_id = {player_id} AND season = '{season}'
          AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
    """)
    if not rows or rows[0]['games_played'] == 0:
        raise HTTPException(status_code=404, detail="No season stats for this player")
    r = rows[0]
    return PlayerSummary(player_id=player_id, season=season,
        games_played=int(r['games_played']),
        toi_per_gp=r.get('toi_per_gp'), goals_per60=r.get('goals_per60'),
        assists_per60=r.get('assists_per60'), points_per60=r.get('points_per60'),
        xgf_pct=r.get('xgf_pct'),
        impact_context=_impact_context_for(player_id, season))


def _impact_context_for(player_id: int, season: str) -> Optional[ImpactContext]:
    """Transparent impact context (isolated-impact + entanglement + carry + single-vs-multi-year
    divergence) from mart_player_impact_context. None when the player has no row that season
    (e.g. under the 200-5v5-minute floor, or a goalie). Additive; never breaks the summary."""
    rows = bq_service.query(f"""
        SELECT off_impact, def_impact, total_impact, off_sd, def_sd,
               multi_total_impact, single_vs_multi_delta,
               entangled, max_partner_toi_share, partner_entropy,
               carry_score, rel_xgf_pct, impact_toi_min
        FROM {bq_service.get_full_table_id('mart_player_impact_context')}
        WHERE player_id = {int(player_id)} AND season = '{season}'
    """)
    if not rows:
        return None
    c = rows[0]
    return ImpactContext(
        off_impact=c.get('off_impact'), def_impact=c.get('def_impact'),
        total_impact=c.get('total_impact'), off_sd=c.get('off_sd'), def_sd=c.get('def_sd'),
        multi_total_impact=c.get('multi_total_impact'),
        single_vs_multi_delta=c.get('single_vs_multi_delta'),
        entangled=(None if c.get('entangled') is None else bool(c.get('entangled'))),
        max_partner_toi_share=c.get('max_partner_toi_share'),
        partner_entropy=c.get('partner_entropy'),
        carry_score=c.get('carry_score'), rel_xgf_pct=c.get('rel_xgf_pct'),
        impact_toi_min=c.get('impact_toi_min'))


@router.get("/{player_id}/wowy", response_model=PlayerWowy)
@cache(ttl=1800)
async def get_player_wowy(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest with WOWY data)"),
) -> PlayerWowy:
    """With-or-without-you partner splits (5v5) for a player-season, sorted by shared TOI.
    Reads mart_player_wowy; small_sample (< 50 shared minutes) is carried per partner."""
    wowy_t = bq_service.get_full_table_id('mart_player_wowy')
    if not season:
        r = bq_service.query(f"SELECT MAX(season) AS s FROM {wowy_t} WHERE player_id = {int(player_id)}")
        season = r[0]['s'] if r and r[0]['s'] else None
    if not season:
        raise HTTPException(status_code=404, detail="No WOWY data for this player")
    rows = bq_service.query(f"""
        WITH names AS (
            SELECT player_id, ANY_VALUE(first_name || ' ' || last_name) AS name
            FROM {bq_service.get_full_table_id('stg_rosters')}
            GROUP BY player_id
        )
        SELECT w.partner_id, n.name AS partner_name,
               w.toi_together_sec, w.xgf_pct_together, w.xgf_per60_together, w.xga_per60_together,
               w.xgf_pct_focal_without_partner, w.xgf_pct_partner_without_focal,
               w.together_minus_focal_alone, w.partner_with_focal_minus_partner_without,
               w.small_sample
        FROM {wowy_t} w
        LEFT JOIN names n ON n.player_id = w.partner_id
        WHERE w.player_id = {int(player_id)} AND w.season = '{season}'
        ORDER BY w.toi_together_sec DESC
    """)
    partners = [WowyPartner(
        partner_id=int(x['partner_id']), partner_name=x.get('partner_name'),
        toi_together_sec=float(x['toi_together_sec']),
        xgf_pct_together=x.get('xgf_pct_together'),
        xgf_per60_together=x.get('xgf_per60_together'),
        xga_per60_together=x.get('xga_per60_together'),
        xgf_pct_focal_without_partner=x.get('xgf_pct_focal_without_partner'),
        xgf_pct_partner_without_focal=x.get('xgf_pct_partner_without_focal'),
        together_minus_focal_alone=x.get('together_minus_focal_alone'),
        partner_with_focal_minus_partner_without=x.get('partner_with_focal_minus_partner_without'),
        small_sample=bool(x['small_sample']),
    ) for x in rows]
    return PlayerWowy(player_id=player_id, season=season, partners=partners)


def _age_at_season(birth_date, season: str) -> Optional[int]:
    """Age on Oct 1 of the season's first year (matches the aging-curve convention)."""
    if not birth_date or not season or '-' not in season:
        return None
    try:
        start_year = int(season.split('-')[0])
        bd = birth_date  # a datetime.date from BigQuery
        age = start_year - bd.year - (1 if (10, 1) < (bd.month, bd.day) else 0)
        return age if 15 <= age <= 50 else None
    except Exception:
        return None


def _player_preview_sync(player_id: int, season: Optional[str]) -> PlayerPreview:
    mart = bq_service.get_full_table_id('mart_player_game_stats')
    radar_t = bq_service.get_models_table_id('player_radar')
    if not season:
        r = bq_service.query(f"SELECT MAX(season) AS s FROM {mart} WHERE player_id = {int(player_id)}")
        season = r[0]['s'] if r and r[0]['s'] else None
    if not season:
        raise HTTPException(status_code=404, detail="No season stats for this player")

    rows = bq_service.query(f"""
        WITH agg AS (
            SELECT player_id,
                   COUNT(DISTINCT game_id) AS gp,
                   SUM(individual_goals) AS g,
                   SUM(first_assists) AS a1,
                   SUM(second_assists) AS a2,
                   SUM(toi_5v5) AS toi_sum,
                   AVG(on_ice_xgf_pct) AS xgf
            FROM {mart}
            WHERE season = '{season}'
              AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
            GROUP BY player_id
        ),
        joined AS (
            SELECT a.player_id, a.gp, a.g, a.a1 + a.a2 AS a, a.xgf,
                   a.g + a.a1 + a.a2 AS p,
                   SAFE_DIVIDE((a.g + a.a1 + a.a2) * 60.0, a.toi_sum) AS p60,
                   pr.pos_group
            FROM agg a
            LEFT JOIN {radar_t} pr ON pr.player_id = a.player_id AND pr.season = '{season}'
        ),
        qual AS (SELECT * FROM joined WHERE gp >= 10 AND pos_group IN ('F', 'D')),
        ranked AS (
            SELECT player_id,
                   COUNT(*) OVER (PARTITION BY pos_group) AS n,
                   RANK() OVER (PARTITION BY pos_group ORDER BY g DESC) AS g_rank,
                   RANK() OVER (PARTITION BY pos_group ORDER BY a DESC) AS a_rank,
                   RANK() OVER (PARTITION BY pos_group ORDER BY p DESC) AS p_rank,
                   RANK() OVER (PARTITION BY pos_group ORDER BY p60 DESC) AS p60_rank,
                   RANK() OVER (PARTITION BY pos_group ORDER BY xgf DESC) AS xgf_rank
            FROM qual
        )
        SELECT j.player_id, j.pos_group, j.gp, j.g, j.a, j.p, j.p60, j.xgf,
               r.n, r.g_rank, r.a_rank, r.p_rank, r.p60_rank, r.xgf_rank
        FROM joined j LEFT JOIN ranked r USING (player_id)
        WHERE j.player_id = {int(player_id)}
    """)
    if not rows:
        raise HTTPException(status_code=404, detail="No season stats for this player")
    r = rows[0]
    n = r.get('n')
    bio = bq_service.query(
        f"SELECT birth_date, shoots FROM {bq_service.get_full_table_id('stg_player_bio')} "
        f"WHERE player_id = {int(player_id)} LIMIT 1")
    b = bio[0] if bio else {}

    def stat(key, label, value, fmt, rank):
        return PreviewStat(key=key, label=label,
                           value=None if value is None else float(value),
                           fmt=fmt, rank=rank, n=(n if rank is not None else None))

    stats = [
        stat('gp', 'GP', r.get('gp'), 'int', None),
        stat('g', 'G', r.get('g'), 'int', r.get('g_rank')),
        stat('a', 'A', r.get('a'), 'int', r.get('a_rank')),
        stat('p', 'P', r.get('p'), 'int', r.get('p_rank')),
        stat('p60', 'P/60', r.get('p60'), 'rate', r.get('p60_rank')),
        stat('xgf', 'xGF%', r.get('xgf'), 'pct1', r.get('xgf_rank')),
    ]
    return PlayerPreview(
        player_id=player_id, season=season, pos_group=r.get('pos_group'),
        age=_age_at_season(b.get('birth_date'), season), shoots=b.get('shoots'),
        stats=stats)


@router.get("/{player_id}/preview", response_model=PlayerPreview)
@cache(ttl=1800)
async def get_player_preview(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> PlayerPreview:
    """Base stats with WITHIN-POSITION ranks + light bio for the inline row expansion."""
    return await run_in_threadpool(_player_preview_sync, player_id, season)


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


def _value_neighbors_sync(player_id: int, season: Optional[str], half: int = 3) -> Optional[ValueNeighborhood]:
    """Position-scoped total-value (WAR) window around a player. Reuses the EXACT ordering and value
    the Players index uses (rankings._skater_value_rows / _goalie_value_rows, sort='confidence'), so
    the player-page header module can never disagree with the Players page."""
    from routers.rankings import _skater_value_rows, _goalie_value_rows
    gar = bq_service.get_models_table_id('player_gar')
    gg = bq_service.get_models_table_id('goalie_gar')
    if not season:
        season = bq_service.query(
            f"SELECT MAX(season_window) AS s FROM {gar} WHERE season_window LIKE '____-__'")[0]['s']

    # Which position pool does this player belong to? (forwards / defensemen / goalies)
    posrow = bq_service.query(
        f"SELECT position FROM {gar} WHERE player_id = {int(player_id)} AND season_window = '{season}'")
    if posrow:
        group = 'D' if (posrow[0].get('position') == 'D') else 'F'
        rows = _skater_value_rows(group, season, 1000, 'confidence')
        scope = 'defensemen' if group == 'D' else 'forwards'
    else:
        grow = bq_service.query(
            f"SELECT 1 FROM {gg} WHERE goalie_id = {int(player_id)} AND season_window = '{season}'")
        if not grow:
            return None    # not in any qualifying value pool this season -> header omits the module
        rows = _goalie_value_rows(season, 1000, 'confidence')
        scope = 'goalies'

    idx = next((i for i, r in enumerate(rows) if r.player_id == player_id), None)
    if idx is None:
        return None

    # ~7 rows centered on the player; shift the window inward at the ends so it stays full
    n = len(rows)
    lo, hi = idx - half, idx + half
    if lo < 0:
        hi -= lo; lo = 0
    if hi > n - 1:
        lo -= (hi - (n - 1)); hi = n - 1
    lo = max(0, lo)
    neighbors = [
        ValueNeighbor(rank=i + 1, player_id=rows[i].player_id, player_name=rows[i].player_name,
                      team_abbrev=rows[i].team_abbrev, war=rows[i].war, is_current=(i == idx))
        for i in range(lo, hi + 1)
    ]
    return ValueNeighborhood(
        player_id=player_id, season=season, scope=scope,
        scope_label=f"Among {scope}, by total value", unit="WAR",
        rank=idx + 1, n=n, neighbors=neighbors)


@router.get("/{player_id}/verdict", response_model=PlayerVerdict)
@cache(ttl=1800)
async def get_player_verdict(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> PlayerVerdict:
    """The composed scouting read (Workstream B). 404 if no verdict has been generated yet, so the
    profile falls back to the archetype descriptor. Read-only; the prose is written by the weekly
    models_ml.generate_verdicts job after the consistency check."""
    def _q() -> Optional[dict]:
        try:
            tbl = bq_service.get_models_table_id('player_verdict')
            s = season
            if not s:
                r = bq_service.query(f"SELECT MAX(season) AS s FROM {tbl} WHERE player_id = {int(player_id)}")
                s = r[0]['s'] if r and r[0].get('s') else None
            if not s:
                return None
            rows = bq_service.query(
                f"SELECT player_id, season, long, short, identity_confidence, model_version, "
                f"CAST(generated_at AS STRING) AS generated_at "
                f"FROM {tbl} WHERE player_id = {int(player_id)} AND season = '{s}' LIMIT 1")
            return rows[0] if rows else None
        except Exception:
            return None  # table not created yet -> fall back
    row = await run_in_threadpool(_q)
    if not row:
        raise HTTPException(status_code=404, detail="No composed verdict yet")
    return PlayerVerdict(**{k: row.get(k) for k in PlayerVerdict.model_fields})


@router.get("/{player_id}/value-neighbors", response_model=ValueNeighborhood)
@cache(ttl=1800)
async def get_player_value_neighbors(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest single season)"),
) -> ValueNeighborhood:
    """A position-scoped slice of the total-value (WAR) leaderboard centered on this player (~3 above,
    ~3 below), for the player-page header ranking module. Same lens, ordering, and value as the
    Players index default sort. 404 if the player isn't in a qualifying value pool this season."""
    payload = await run_in_threadpool(_value_neighbors_sync, player_id, season)
    if payload is None:
        raise HTTPException(status_code=404, detail="Player not in a qualifying value pool")
    return payload


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
    limit: int = Query(50, ge=1, le=1000),
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


def _rate_stat_ranks(player_id: int, season: str) -> dict:
    """Within-position DISPLAY ranks for the six snapshot rate stats (1 = best). Ranks the SAME
    per-game-averaged expressions get_player_detail returns, partitioned by F/D, over players with
    >= 10 GP, so the rank agrees with the value shown. Display-only; changes no metric formula."""
    mart = bq_service.get_full_table_id('mart_player_game_stats')
    try:
        rows = bq_service.query(f"""
            WITH per_player AS (
                SELECT player_id,
                       CASE WHEN ANY_VALUE(position_code) = 'D' THEN 'D' ELSE 'F' END AS pos_group,
                       COUNT(DISTINCT game_id) AS gp,
                       AVG(toi_5v5) AS toi,
                       AVG(primary_points_per60) AS p60,
                       AVG(SAFE_DIVIDE(individual_goals, toi_5v5) * 60.0) AS g60,
                       AVG(SAFE_DIVIDE(first_assists, toi_5v5) * 60.0) AS a60,
                       AVG(on_ice_xgf_pct) AS cf,
                       AVG(ixg_per60) AS hdcf
                FROM {mart}
                WHERE season = '{season}'
                  AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
                  AND position_code IN ('C', 'L', 'R', 'D')
                GROUP BY player_id
            ),
            qual AS (SELECT * FROM per_player WHERE gp >= 10),
            ranked AS (
                SELECT player_id,
                       COUNT(*) OVER (PARTITION BY pos_group) AS n,
                       RANK() OVER (PARTITION BY pos_group ORDER BY toi DESC) AS toi_rank,
                       RANK() OVER (PARTITION BY pos_group ORDER BY p60 DESC) AS points_per60_rank,
                       RANK() OVER (PARTITION BY pos_group ORDER BY g60 DESC) AS goals_per60_rank,
                       RANK() OVER (PARTITION BY pos_group ORDER BY a60 DESC) AS assists_per60_rank,
                       RANK() OVER (PARTITION BY pos_group ORDER BY cf DESC) AS cf_pct_rank,
                       RANK() OVER (PARTITION BY pos_group ORDER BY hdcf DESC) AS hdcf_per60_rank
                FROM qual
            )
            SELECT * FROM ranked WHERE player_id = {int(player_id)}
        """)
        if not rows:
            return {}
        r = rows[0]
        keys = ['toi_rank', 'points_per60_rank', 'goals_per60_rank', 'assists_per60_rank',
                'cf_pct_rank', 'hdcf_per60_rank']
        out = {k: (int(r[k]) if r.get(k) is not None else None) for k in keys}
        out['rank_pool'] = int(r['n']) if r.get('n') is not None else None
        return out
    except Exception:
        return {}   # ranks are a display nicety; never fail the detail load over them


def _edge_zone_starts(player_id: int, season: str) -> dict:
    """Per-player NHL Edge zone starts (official, all situations, season, regular season) for the
    Role & deployment line and verdict. Neutral is included in Edge's denominator. Returns {} if
    the player has no Edge zone-time row (e.g. pre-2021-22), so the UI falls back to the team proxy."""
    sid = _season_str_to_id(season)
    if not sid:
        return {}
    try:
        rows = bq_service.query(f"""
            SELECT oz_start_pct AS edge_oz_start_pct, nz_start_pct AS edge_nz_start_pct,
                   dz_start_pct AS edge_dz_start_pct, oz_start_pctile AS edge_oz_start_pctile
            FROM {bq_service.get_full_table_id('mart_edge_player_profile')}
            WHERE player_id = {int(player_id)} AND season_id = {int(sid)} AND game_type = 2
            LIMIT 1""")
        if not rows:
            return {}
        r = rows[0]
        keys = ('edge_oz_start_pct', 'edge_nz_start_pct', 'edge_dz_start_pct', 'edge_oz_start_pctile')
        return {k: (float(r[k]) if r.get(k) is not None else None) for k in keys}
    except Exception:
        return {}


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
    # Headline stats are for the resolved SEASON (NHL games only) — not career aggregates.
    # ARRAY_AGG picks the player's latest team that season so a mid-season trade yields one row.
    sql = f"""
    SELECT
        player_id,
        ANY_VALUE(CONCAT(first_name, ' ', last_name)) as player_name,
        ANY_VALUE(position_code) as position,
        ARRAY_AGG(team_id ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] as team_id,
        COUNT(DISTINCT game_id) as games_played,
        AVG(toi_5v5) as toi_per_gp,
        AVG(primary_points_per60) as points_per60,
        AVG((individual_goals / toi_5v5) * 60.0) as goals_per60,
        AVG((first_assists / toi_5v5) * 60.0) as assists_per60,
        AVG(on_ice_xgf_pct) as cf_pct,
        AVG(ixg_per60) as hdcf_per60
    FROM {bq_service.get_full_table_id('mart_player_game_stats')}
    WHERE player_id = {player_id}
        AND season = '{season}'
        AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
    GROUP BY player_id
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Player not found")

    row = results[0]

    # Current team LABEL comes from dim_current_roster, whose team_id is the LIVE-first resolved
    # current team (built from int_player_current_team in precompute). dim is a serving table, so
    # this works under DuckDB. An offseason trade shows the NEW club here even though the stats
    # above are still his old-team games (membership != performance — value/archetype lag until he
    # plays for the new team). Falls back to the latest-game team_id when the player isn't in the
    # current-roster dim (retired / not on a current roster).
    try:
        cur = bq_service.query(
            f"SELECT team_id FROM {bq_service.get_models_table_id('dim_current_roster')} "
            f"WHERE player_id = {player_id} LIMIT 1")
        if cur and cur[0].get('team_id') is not None:
            row['team_id'] = cur[0]['team_id']
    except Exception:
        pass  # current-roster dim unavailable: fall back to the latest-game team_id

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
    durable_archetype = _durable_archetype(row['player_id'])
    try:
        season_totals = _season_totals(row['player_id'], season, row['position'] == 'G')
    except Exception:
        season_totals = []

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
        durable_archetype=durable_archetype,
        season_totals=season_totals,
        value=_value_block(row['player_id'], season),
        **_rate_stat_ranks(row['player_id'], season),
        **_edge_zone_starts(row['player_id'], season),
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
    # Default to the player's latest season (mart season is a string like '2025-26').
    if not season:
        season_result = bq_service.query(
            f"SELECT MAX(season) AS s FROM {bq_service.get_full_table_id('mart_player_game_stats')} "
            f"WHERE player_id = {player_id}")
        season = season_result[0]['s'] if season_result and season_result[0].get('s') else None
    if not season:
        raise HTTPException(status_code=404, detail="Player not found or insufficient data")

    # Season-scoped, NHL games only (reg + playoffs). 5-game rolling. Goals/60 and ixG/60 are
    # volume-weighted over the window (sum/sum), the correct per-60 basis for a sustainability read;
    # individual_goals and ixg share one shot source, so the two lines are apples-to-apples.
    sql = f"""
    WITH ordered_games AS (
        SELECT
            game_date,
            primary_points_per60,
            on_ice_xgf_pct AS cf_pct,
            individual_goals,
            ixg,
            toi_5v5,
            ROW_NUMBER() OVER (ORDER BY game_date) AS game_num
        FROM {bq_service.get_full_table_id('mart_player_game_stats')}
        WHERE player_id = {player_id} AND season = '{season}'
          AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
    )
    SELECT
        game_date,
        AVG(primary_points_per60) OVER w AS points_per60_5gp,
        AVG(cf_pct) OVER w AS cf_pct_5gp,
        SAFE_DIVIDE(SUM(individual_goals) OVER w, SUM(toi_5v5) OVER w) * 60 AS goals_per60_5gp,
        SAFE_DIVIDE(SUM(ixg) OVER w, SUM(toi_5v5) OVER w) * 60 AS ixg_per60_5gp,
        game_num
    FROM ordered_games
    WINDOW w AS (ORDER BY game_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)
    ORDER BY game_date
    LIMIT 200
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Player not found or insufficient data")

    points_per60_5gp = []
    points_per60_10gp = []  # TODO: Add 10-game rolling
    cf_pct_5gp = []
    cf_pct_10gp = []  # TODO: Add 10-game rolling
    goals_per60_5gp = []
    ixg_per60_5gp = []

    for row in results:
        points_per60_5gp.append(PlayerTrendPoint(game_date=row['game_date'], value=row['points_per60_5gp']))
        cf_pct_5gp.append(PlayerTrendPoint(game_date=row['game_date'], value=row['cf_pct_5gp']))
        if row.get('goals_per60_5gp') is not None:
            goals_per60_5gp.append(PlayerTrendPoint(game_date=row['game_date'], value=row['goals_per60_5gp']))
        if row.get('ixg_per60_5gp') is not None:
            ixg_per60_5gp.append(PlayerTrendPoint(game_date=row['game_date'], value=row['ixg_per60_5gp']))

    return PlayerTrends(
        player_id=player_id,
        season=season,
        points_per60_5gp=points_per60_5gp,
        points_per60_10gp=points_per60_10gp,
        cf_pct_5gp=cf_pct_5gp,
        cf_pct_10gp=cf_pct_10gp,
        goals_per60_5gp=goals_per60_5gp,
        ixg_per60_5gp=ixg_per60_5gp,
    )


@router.get("/{player_id}/shot-quality", response_model=PlayerShotQuality)
@cache(ttl=1800)
async def get_player_shot_quality(
    player_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2025-26)"),
) -> PlayerShotQuality:
    """Shot-zone quality (Shot Map tab): the player's unblocked-shot diet bucketed by per-shot xG
    into low/medium/high danger, with each band's share alongside the positional league pool (F vs D)
    so the bars read as 'how this player's shot quality compares to his position'."""
    if not season:
        sr = bq_service.query(
            f"SELECT MAX(season) AS s FROM {bq_service.get_full_table_id('mart_player_game_stats')} "
            f"WHERE player_id = {player_id}")
        season = sr[0]['s'] if sr and sr[0].get('s') else None
    if not season:
        raise HTTPException(status_code=404, detail="No shot data for this player")

    # Danger bands by per-shot xG (config.DANGER_TIERS): low [0,0.05), medium [0.05,0.15), high [0.15,1].
    sql = f"""
    WITH pos AS (
        SELECT player_id, CASE WHEN MAX(position_code) = 'D' THEN 'D' ELSE 'F' END AS pos_group
        FROM {bq_service.get_full_table_id('mart_player_game_stats')}
        GROUP BY player_id
    ),
    banded AS (
        -- credit goals to the scorer: goals carry scoring_player_id with a null shooter (see mart).
        SELECT COALESCE(s.shooting_player_id, s.scoring_player_id) AS pid, p.pos_group, s.is_goal,
            CASE WHEN s.xg_value < 0.05 THEN 'low'
                 WHEN s.xg_value < 0.15 THEN 'medium' ELSE 'high' END AS band
        FROM {bq_service.get_full_table_id('int_shot_attempts_all')} s
        JOIN pos p ON COALESCE(s.shooting_player_id, s.scoring_player_id) = p.player_id
        WHERE s.season = '{season}'
          AND SUBSTR(CAST(s.game_id AS STRING), 5, 2) IN ('02', '03')
          AND s.xg_value IS NOT NULL
    )
    SELECT band,
        SUM(CASE WHEN pid = {player_id} THEN 1 ELSE 0 END) AS p_attempts,
        SUM(CASE WHEN pid = {player_id} AND is_goal THEN 1 ELSE 0 END) AS p_goals,
        SUM(CASE WHEN pos_group = (SELECT pos_group FROM pos WHERE player_id = {player_id}) THEN 1 ELSE 0 END) AS pool_attempts
    FROM banded
    GROUP BY band
    """
    rows = bq_service.query(sql)
    by_band = {r['band']: r for r in rows}
    total = sum(int(by_band.get(b, {}).get('p_attempts') or 0) for b in ('low', 'medium', 'high'))
    pool_total = sum(int(by_band.get(b, {}).get('pool_attempts') or 0) for b in ('low', 'medium', 'high'))
    if total == 0:
        raise HTTPException(status_code=404, detail="No shot data for this player")

    pos_group = None
    pg = bq_service.query(
        f"SELECT CASE WHEN MAX(position_code) = 'D' THEN 'D' ELSE 'F' END AS g "
        f"FROM {bq_service.get_full_table_id('mart_player_game_stats')} WHERE player_id = {player_id}")
    if pg and pg[0].get('g'):
        pos_group = pg[0]['g']

    bands = []
    for b in ('high', 'medium', 'low'):  # present high danger first
        r = by_band.get(b, {})
        p_att = int(r.get('p_attempts') or 0)
        pool_att = int(r.get('pool_attempts') or 0)
        bands.append(ShotQualityBand(
            band=b, attempts=p_att, goals=int(r.get('p_goals') or 0),
            share=(p_att / total) if total else 0.0,
            league_share=(pool_att / pool_total) if pool_total else 0.0,
        ))
    return PlayerShotQuality(player_id=player_id, season=season, pos_group=pos_group,
                             total_attempts=total, bands=bands)


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


def _player_contract_sync(player_id: int) -> PlayerContract:
    """Latest contract + present-valued surplus for one player (Trade tool P3/P4)."""
    contracts = bq_service.get_full_table_id("mart_player_contracts")
    value = bq_service.get_models_table_id("player_contract_value")
    rows = bq_service.query(f"""
        SELECT c.player_id, c.as_of_date, c.season, c.contract_team, c.cap_hit, c.aav,
               c.remaining_years, c.expiry_year, c.is_ufa, c.contract_type, c.contract_status,
               c.match_method,
               v.war_now, v.value_war, v.value_war_low, v.value_war_high,
               v.value_dollars, v.value_dollars_low, v.value_dollars_high,
               v.expected_value_now AS expected_aav_now, v.cost_dollars, v.surplus_current,
               v.total_discounted_surplus, v.surplus_low, v.surplus_high,
               v.total_discounted_surplus_share, v.surplus_flat_dollars, v.cap_share_schedule,
               v.confidence, v.is_grounded
        FROM {contracts} c
        LEFT JOIN {value} v ON c.player_id = v.player_id AND c.as_of_date = v.as_of_date
        WHERE c.player_id = {int(player_id)}
        ORDER BY c.as_of_date DESC
        LIMIT 1
    """)
    if not rows:
        raise HTTPException(status_code=404, detail="No contract on file for this player.")
    r = rows[0]
    sched = []
    if r.get("cap_share_schedule"):
        sched = [CapShareYear(**y) for y in json.loads(r["cap_share_schedule"])]
    return PlayerContract(
        player_id=int(r["player_id"]), as_of_date=r.get("as_of_date"), season=r.get("season"),
        contract_team=r.get("contract_team"), cap_hit=r.get("cap_hit"), aav=r.get("aav"),
        remaining_years=r.get("remaining_years"), expiry_year=r.get("expiry_year"),
        is_ufa=r.get("is_ufa"), contract_type=r.get("contract_type"),
        contract_status=r.get("contract_status"), match_method=r.get("match_method"),
        war_now=r.get("war_now"), value_war=r.get("value_war"),
        value_war_low=r.get("value_war_low"), value_war_high=r.get("value_war_high"),
        value_dollars=r.get("value_dollars"), value_dollars_low=r.get("value_dollars_low"),
        value_dollars_high=r.get("value_dollars_high"),
        expected_aav_now=r.get("expected_aav_now"), cost_dollars=r.get("cost_dollars"),
        surplus_current=r.get("surplus_current"),
        total_discounted_surplus=r.get("total_discounted_surplus"),
        surplus_low=r.get("surplus_low"), surplus_high=r.get("surplus_high"),
        total_discounted_surplus_capshare=r.get("total_discounted_surplus_share"),
        surplus_flat_dollars=r.get("surplus_flat_dollars"),
        cap_share_schedule=sched,
        confidence=r.get("confidence"), is_grounded=r.get("is_grounded"),
    )


@router.get("/{player_id}/contract", response_model=PlayerContract)
@cache(ttl=1800)
async def get_player_contract(player_id: int) -> PlayerContract:
    """A player's parsed contract and present-valued surplus (with a confidence band)."""
    return await run_in_threadpool(_player_contract_sync, player_id)
