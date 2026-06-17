"""Goalie endpoints on the in-house GSAx layer (Phase 2.5)."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import (
    GoalieSeason, GoalieGameLogRow, GoalieRadar, GoalieValue, CompositeComponent,
    OverallSummary, OverallComponent, GOALIE_GAR_LABELS, PreviewStat, GoaliePreview,
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()

# Goalie Overall axis key -> label (mirrors the goalie radar spokes the components match on-card).
_GOALIE_OVERALL_LABELS = [
    ("gsax", "Overall GSAx"), ("hd_gsax", "High-Danger GSAx"),
    ("workload", "Workload"), ("consistency", "Consistency"),
]


def _goalie_value(goalie_id: int, season: str):
    """Goalie GAR/WAR block on the cross-position scale (goals saved above a backup), with a
    within-goalie WAR percentile for context. Wide band by construction (principle 6)."""
    gg = bq_service.get_models_table_id('goalie_gar')
    from models_ml import config as mlcfg
    min_games = mlcfg.GOALIE_GAR_CONFIG["MIN_GAMES_FOR_RANKING"]
    keys = ", ".join(k for k, _ in GOALIE_GAR_LABELS)
    rows = bq_service.query(f"""
        WITH ranked AS (
            SELECT goalie_id, gar, war, gar_sd, war_sd, raw_war, {keys},
                   PERCENT_RANK() OVER (ORDER BY war) AS war_percentile
            FROM {gg}
            WHERE season_window = '{season}' AND games_played >= {min_games}
        )
        SELECT * FROM ranked WHERE goalie_id = {goalie_id} LIMIT 1""")
    if not rows:
        raw = bq_service.query(f"""SELECT goalie_id, gar, war, gar_sd, war_sd, raw_war, {keys}
            FROM {gg} WHERE goalie_id = {goalie_id} AND season_window = '{season}' LIMIT 1""")
        if not raw:
            return None
        rows = raw
    r = rows[0]
    comps = [CompositeComponent(key=k, label=lbl, value=float(r.get(k) or 0.0))
             for k, lbl in GOALIE_GAR_LABELS]
    return GoalieValue(
        gar=float(r["gar"]), war=float(r["war"]),
        gar_sd=float(r.get("gar_sd") or 0.0), war_sd=float(r.get("war_sd") or 0.0),
        components=comps,
        war_percentile=float(r["war_percentile"]) if r.get("war_percentile") is not None else None,
        raw_war=float(r["raw_war"]) if r.get("raw_war") is not None else None)


def _goalie_overall(goalie_id: int, season: str):
    """Within-goalie Overall summary (card-only). Components are the goalie radar-axis percentiles
    so they match the radar on the card; always shown together (the FE enforces it)."""
    rows = bq_service.query(f"""
        SELECT * FROM {bq_service.get_models_table_id('goalie_overall')}
        WHERE goalie_id = {goalie_id} AND season_window = '{season}' LIMIT 1""")
    if not rows:
        return None
    r = rows[0]
    return OverallSummary(
        overall_percentile=float(r["overall_percentile"]), pos_group="G",
        components=[OverallComponent(key=k, label=lbl,
                    percentile=float(r[f"{k}_percentile"]) if r.get(f"{k}_percentile") is not None else None)
                    for k, lbl in _GOALIE_OVERALL_LABELS],
        weights={k: float(r[f"w_{k}"]) for k, _ in _GOALIE_OVERALL_LABELS if r.get(f"w_{k}") is not None})


def _goalie_preview_sync(goalie_id: int, season: Optional[str]) -> GoaliePreview:
    mart = bq_service.get_full_table_id('mart_goalie_season')
    if not season:
        r = bq_service.query(f"SELECT MAX(season) AS s FROM {mart} WHERE goalie_id = {int(goalie_id)}")
        season = r[0]['s'] if r and r[0]['s'] else None
    if not season:
        raise HTTPException(status_code=404, detail="Goalie season not found")

    rows = bq_service.query(f"""
        WITH base AS (
            SELECT goalie_id, games_played, save_pct, gsax, our_hd_gsax, goals_against
            FROM {mart} WHERE season = '{season}'
        ),
        qual AS (SELECT * FROM base WHERE games_played >= 10),
        ranked AS (
            SELECT goalie_id, COUNT(*) OVER () AS n,
                   RANK() OVER (ORDER BY save_pct DESC) AS sv_rank,
                   RANK() OVER (ORDER BY gsax DESC) AS gsax_rank,
                   RANK() OVER (ORDER BY our_hd_gsax DESC) AS hd_rank
            FROM qual
        )
        SELECT b.goalie_id, b.games_played, b.save_pct, b.gsax, b.our_hd_gsax, b.goals_against,
               r.n, r.sv_rank, r.gsax_rank, r.hd_rank
        FROM base b LEFT JOIN ranked r USING (goalie_id)
        WHERE b.goalie_id = {int(goalie_id)}
    """)
    if not rows:
        raise HTTPException(status_code=404, detail="Goalie season not found")
    r = rows[0]
    n = r.get('n')
    bio = bq_service.query(
        f"SELECT birth_date, shoots FROM {bq_service.get_full_table_id('stg_player_bio')} "
        f"WHERE player_id = {int(goalie_id)} LIMIT 1")
    b = bio[0] if bio else {}

    def stat(key, label, value, fmt, rank):
        return PreviewStat(key=key, label=label,
                           value=None if value is None else float(value),
                           fmt=fmt, rank=rank, n=(n if rank is not None else None))

    stats = [
        stat('gp', 'GP', r.get('games_played'), 'int', None),
        stat('sv_pct', 'SV%', r.get('save_pct'), 'pct3', r.get('sv_rank')),
        stat('gsax', 'GSAx', r.get('gsax'), 'plus', r.get('gsax_rank')),
        stat('hd_gsax', 'HD GSAx', r.get('our_hd_gsax'), 'plus', r.get('hd_rank')),
        stat('ga', 'GA', r.get('goals_against'), 'int', None),
    ]
    age = None
    if b.get('birth_date') and season and '-' in season:
        try:
            sy = int(season.split('-')[0]); bd = b['birth_date']
            a = sy - bd.year - (1 if (10, 1) < (bd.month, bd.day) else 0)
            age = a if 15 <= a <= 50 else None
        except Exception:
            age = None
    return GoaliePreview(goalie_id=goalie_id, season=season, age=age,
                         catches=b.get('shoots'), stats=stats)


@router.get("/{goalie_id}/preview", response_model=GoaliePreview)
@cache(ttl=1800)
async def get_goalie_preview(
    goalie_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> GoaliePreview:
    """Goalie base stats with within-goalie ranks for the inline row expansion."""
    return await run_in_threadpool(_goalie_preview_sync, goalie_id, season)


@router.get("/{goalie_id}/radar", response_model=GoalieRadar)
@cache(ttl=1800)
async def get_goalie_radar(
    goalie_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> GoalieRadar:
    """Goalie skills radar: spokes percentiled within goalies (Part B)."""
    from services.radar import goalie_radar as _radar
    payload = await run_in_threadpool(_radar, goalie_id, season)
    if payload is None:
        raise HTTPException(status_code=404, detail="No radar for this goalie")
    return GoalieRadar(**payload)


def _goalie_name(goalie_id: int) -> Optional[str]:
    rows = bq_service.query(f"""
        SELECT first_name || ' ' || last_name AS name
        FROM {bq_service.get_full_table_id('stg_rosters')}
        WHERE player_id = {goalie_id}
        LIMIT 1
    """)
    return rows[0]['name'] if rows else None


@router.get("/{goalie_id}", response_model=GoalieSeason)
@cache(ttl=3600)
async def get_goalie_season(
    goalie_id: int,
    season: Optional[str] = Query(None, description="Season (e.g. 2024-25); defaults to latest"),
) -> GoalieSeason:
    """Season GSAx line for a goalie, with the NHL Edge second opinion."""
    season_filter = f"AND season = '{season}'" if season else ""
    rows = bq_service.query(f"""
        SELECT * FROM {bq_service.get_full_table_id('mart_goalie_season')}
        WHERE goalie_id = {goalie_id} {season_filter}
        ORDER BY season DESC
        LIMIT 1
    """)
    if not rows:
        raise HTTPException(status_code=404, detail="Goalie season not found")
    r = rows[0]
    resolved = r['season']
    base = {k: r.get(k) for k in GoalieSeason.model_fields if k not in ('goalie_name', 'value', 'overall')}
    return GoalieSeason(goalie_name=_goalie_name(goalie_id),
                        value=_goalie_value(goalie_id, resolved),
                        overall=_goalie_overall(goalie_id, resolved), **base)


@router.get("/{goalie_id}/gamelog", response_model=List[GoalieGameLogRow])
@cache(ttl=600)
async def get_goalie_gamelog(
    goalie_id: int,
    season: Optional[str] = Query(None),
    limit: int = Query(40, ge=1, le=200),
) -> List[GoalieGameLogRow]:
    """Per-game GSAx log for a goalie, most recent first."""
    season_filter = f"AND season = '{season}'" if season else ""
    rows = bq_service.query(f"""
        SELECT game_id, game_date, season, team_id, shots_faced, saves, goals_against,
               save_pct, xga, gsax, high_gsax, high_shots, high_saves
        FROM {bq_service.get_full_table_id('mart_goalie_game_stats')}
        WHERE goalie_id = {goalie_id} {season_filter}
        ORDER BY game_date DESC
        LIMIT {limit}
    """)
    return [GoalieGameLogRow(**{k: r.get(k) for k in GoalieGameLogRow.model_fields}) for r in rows]
