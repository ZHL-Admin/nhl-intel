"""Rankings endpoints: power ratings + deserved standings (Phase 3.1)."""

from typing import List, Optional

from fastapi import APIRouter, Query

from models.schemas import (
    PowerRatingRow, DeservedStandingRow, ValueRankingRow, CompositeComponent, GAR_LABELS,
    GOALIE_GAR_LABELS,
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()

# Name + latest-team CTE shared by the value-ranking queries (NHL game types only — strips the
# 2026 Olympic/4-Nations national-team pollution from a player's "latest team").
_NM_TM_CTE = """
nm AS (
    SELECT player_id, ANY_VALUE(first_name || ' ' || last_name) AS name,
           ARRAY_AGG(team_id ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS team_id
    FROM {rosters}
    WHERE SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
    GROUP BY player_id
),
tm AS (SELECT team_id, ANY_VALUE(team_abbrev) AS abbrev FROM {mart} GROUP BY team_id)
"""

# Per-team abbrev (latest seen in the mart for the season) joined onto rating rows.
_ABBREV_CTE = """
abbrev AS (
    SELECT team_id, ANY_VALUE(team_abbrev) AS team_abbrev
    FROM {mart}
    WHERE season = '{season}'
    GROUP BY team_id
)
"""


def _latest_season() -> str:
    rows = bq_service.query(
        f"SELECT MAX(season) AS s FROM {bq_service.get_models_table_id('team_ratings')}")
    return rows[0]['s']


@router.get("/power", response_model=List[PowerRatingRow])
@cache(ttl=1800)
async def get_power_rankings(
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> List[PowerRatingRow]:
    """Current power ratings (latest row per team), highest first."""
    season = season or _latest_season()
    mart = bq_service.get_full_table_id('mart_team_game_stats')
    ratings = bq_service.get_models_table_id('team_ratings')
    sql = f"""
    WITH {_ABBREV_CTE.format(mart=mart, season=season)},
    latest AS (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY team_id ORDER BY game_date DESC) AS rn
        FROM {ratings}
        WHERE season = '{season}'
    )
    SELECT l.team_id, a.team_abbrev, l.season, l.games_played,
           l.total_rating, l.rating_se, l.trajectory_15d,
           l.play_5v5, l.finishing, l.goaltending, l.special_teams,
           l.contrib_play_5v5, l.contrib_finishing,
           l.contrib_goaltending, l.contrib_special_teams
    FROM latest l
    LEFT JOIN abbrev a USING (team_id)
    WHERE l.rn = 1
    ORDER BY l.total_rating DESC
    """
    rows = bq_service.query(sql)
    return [PowerRatingRow(**{k: r.get(k) for k in PowerRatingRow.model_fields}) for r in rows]


@router.get("/deserved", response_model=List[DeservedStandingRow])
@cache(ttl=1800)
async def get_deserved_standings(
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> List[DeservedStandingRow]:
    """Actual vs deserved points, ordered by deserved points."""
    season = season or _latest_season()
    mart = bq_service.get_full_table_id('mart_team_game_stats')
    deserved = bq_service.get_models_table_id('deserved_standings')
    sql = f"""
    WITH {_ABBREV_CTE.format(mart=mart, season=season)}
    SELECT d.team_id, a.team_abbrev, d.season, d.games, d.actual_points,
           d.deserved_points, d.deserved_p10, d.deserved_p90, d.luck_delta
    FROM {deserved} d
    LEFT JOIN abbrev a USING (team_id)
    WHERE d.season = '{season}'
    ORDER BY d.deserved_points DESC
    """
    rows = bq_service.query(sql)
    return [DeservedStandingRow(**{k: r.get(k) for k in DeservedStandingRow.model_fields})
            for r in rows]


def _confidence_k() -> float:
    from models_ml import config as mlcfg
    return float(mlcfg.CONFIDENCE_SORT_K)


def _order_expr(sort: str) -> str:
    """SQL ORDER BY for the value tables. 'confidence' ranks by the lower-confidence bound
    war − k·war_sd ('value we are confident about') so a low-variance skater is not buried under a
    high-variance goalie of equal point estimate; 'point' ranks by the raw point estimate."""
    if sort == "point":
        return "g.war DESC"
    return f"(g.war - {_confidence_k()} * COALESCE(g.war_sd, 0)) DESC"


def _conf_key(r: ValueRankingRow) -> float:
    """The confidence-aware sort key for an already-built row (used by the mixed merge)."""
    return r.war - _confidence_k() * (r.war_sd or 0.0)


def _skater_value_rows(position: str, season: str, limit: int, sort: str = "confidence") -> List[ValueRankingRow]:
    """Skater GAR rows (component_kind=skater), qualified by the 5v5-TOI ranking floor."""
    from models_ml import config as mlcfg
    floor = mlcfg.GAR_CONFIG["MIN_TOI_5V5_FOR_RANKING"]
    gar = bq_service.get_models_table_id('player_gar')
    rosters = bq_service.get_full_table_id('stg_rosters')
    mart = bq_service.get_full_table_id('mart_team_game_stats')
    groups = {"F": "('C','L','R')", "D": "('D')"}.get(position.upper(), "('C','L','R','D')")
    rows = bq_service.query(f"""
        WITH {_NM_TM_CTE.format(rosters=rosters, mart=mart)}
        SELECT g.player_id, nm.name, tm.abbrev AS team_abbrev, g.position,
               g.gar, g.war, g.gar_sd, g.war_sd,
               g.ev_offense, g.pp, g.ev_defense, g.pk, g.penalty, g.faceoff
        FROM {gar} g
        LEFT JOIN nm ON g.player_id = nm.player_id
        LEFT JOIN tm ON nm.team_id = tm.team_id
        WHERE g.season_window = '{season}' AND g.position IN {groups} AND g.toi_5v5 >= {floor}
        ORDER BY {_order_expr(sort)}
        LIMIT {int(limit)}
    """)
    out = []
    for r in rows:
        comps = [CompositeComponent(key=k, label=lbl, value=float(r.get(k) or 0.0))
                 for k, lbl in GAR_LABELS]
        out.append(ValueRankingRow(
            player_id=r["player_id"], player_name=r.get("name"), team_abbrev=r.get("team_abbrev"),
            position=r.get("position"), entity_kind="skater", component_kind="skater",
            gar=float(r["gar"]), war=float(r["war"]),
            gar_sd=float(r["gar_sd"]) if r.get("gar_sd") is not None else None,
            war_sd=float(r["war_sd"]) if r.get("war_sd") is not None else None, components=comps))
    return out


def _goalie_value_rows(season: str, limit: int, sort: str = "confidence") -> List[ValueRankingRow]:
    """Goalie GAR rows (component_kind=goalie, distinct save-tier vocabulary), qualified by games.
    GAR/WAR here are the RELIABILITY-SHRUNK estimates (the honest point estimate); see value-gar.md."""
    from models_ml import config as mlcfg
    min_games = mlcfg.GOALIE_GAR_CONFIG["MIN_GAMES_FOR_RANKING"]
    gg = bq_service.get_models_table_id('goalie_gar')
    rosters = bq_service.get_full_table_id('stg_rosters')
    mart = bq_service.get_full_table_id('mart_team_game_stats')
    keys = ", ".join(f"g.{k}" for k, _ in GOALIE_GAR_LABELS)
    rows = bq_service.query(f"""
        WITH {_NM_TM_CTE.format(rosters=rosters, mart=mart)}
        SELECT g.goalie_id AS player_id, nm.name, tm.abbrev AS team_abbrev,
               g.gar, g.war, g.gar_sd, g.war_sd, {keys}
        FROM {gg} g
        LEFT JOIN nm ON g.goalie_id = nm.player_id
        LEFT JOIN tm ON nm.team_id = tm.team_id
        WHERE g.season_window = '{season}' AND g.games_played >= {min_games}
        ORDER BY {_order_expr(sort)}
        LIMIT {int(limit)}
    """)
    out = []
    for r in rows:
        comps = [CompositeComponent(key=k, label=lbl, value=float(r.get(k) or 0.0))
                 for k, lbl in GOALIE_GAR_LABELS]
        out.append(ValueRankingRow(
            player_id=r["player_id"], player_name=r.get("name"), team_abbrev=r.get("team_abbrev"),
            position="G", entity_kind="goalie", component_kind="goalie",
            gar=float(r["gar"]), war=float(r["war"]),
            gar_sd=float(r["gar_sd"]) if r.get("gar_sd") is not None else None,
            war_sd=float(r["war_sd"]) if r.get("war_sd") is not None else None, components=comps))
    return out


@router.get("/value", response_model=List[ValueRankingRow])
@cache(ttl=1800)
async def get_value_rankings(
    scope: str = Query("skaters", description="skaters | goalies | all (mixed, WAR-sorted)"),
    position: str = Query("ALL", description="ALL | F | D (skaters scope only)"),
    season: Optional[str] = Query(None, description="Season (default: latest single season)"),
    sort: str = Query("confidence", description="confidence (default) | point"),
    limit: int = Query(50, ge=1, le=200),
) -> List[ValueRankingRow]:
    """Value leaderboard — goals/wins above replacement.

    - scope=skaters: skater GAR ('what happened'), sortable by position; skater component vocabulary.
    - scope=goalies: goalie GAR (reliability-SHRUNK goals saved above a backup); save-tier vocabulary.
    - scope=all: a MIXED skater+goalie list ranked by WAR — the ONLY cross-position-comparable unit
      (skater GAR and goalie GAR are different units and are never sorted together).

    sort=confidence (DEFAULT): rank by the lower-confidence bound war − k·war_sd ('value we are
    confident about'), so a tight-band skater is not buried under a wide-band goalie of equal point
    estimate. sort=point ranks by the raw (shrunk) point estimate. The DISPLAYED number is always
    the point estimate; only the ORDER changes. See value-gar.md."""
    gar = bq_service.get_models_table_id('player_gar')
    scope = scope.lower()
    sort = "point" if sort.lower() == "point" else "confidence"
    if not season:
        season = bq_service.query(
            f"SELECT MAX(season_window) AS s FROM {gar} WHERE season_window LIKE '____-__'")[0]['s']

    if scope == "goalies":
        return _goalie_value_rows(season, limit, sort)
    if scope == "skaters":
        return _skater_value_rows(position, season, limit, sort)

    # scope == "all": merge both tables. We over-fetch `limit` from each side (each already ordered
    # by the chosen key), then take the global top `limit`.
    return merge_value_rows(
        _skater_value_rows("ALL", season, limit, sort), _goalie_value_rows(season, limit, sort),
        limit, sort)


def merge_value_rows(
    skaters: List[ValueRankingRow], goalies: List[ValueRankingRow], limit: int, sort: str = "confidence",
) -> List[ValueRankingRow]:
    """Merge skater + goalie value rows and return the global top `limit`.

    The sort key is always WAR-DERIVED — never GAR — because skater GAR and goalie GAR are different
    units and are not comparable; only WAR (= GAR/GOALS_PER_WIN, a shared divisor) is. The DEFAULT
    is the confidence-aware lower bound war − k·war_sd (so a ±0.8 skater outranks a ±2.2 goalie of
    equal WAR point estimate); 'point' falls back to raw WAR. Pure + hermetic so both the
    WAR-not-GAR invariant and the confidence-default are unit-tested (tests/test_value_overall.py)."""
    key = (lambda r: r.war) if sort == "point" else _conf_key
    merged = list(skaters) + list(goalies)
    merged.sort(key=key, reverse=True)
    return merged[:limit]
