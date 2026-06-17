"""Rankings endpoints: power ratings + deserved standings (Phase 3.1)."""

from typing import List, Optional

from fastapi import APIRouter, Query

from models.schemas import (
    PowerRatingRow, DeservedStandingRow, ValueRankingRow, CompositeComponent, GAR_LABELS,
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()

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


@router.get("/value", response_model=List[ValueRankingRow])
@cache(ttl=1800)
async def get_value_rankings(
    position: str = Query("ALL", description="ALL | F | D"),
    season: Optional[str] = Query(None, description="Season (default: latest single season)"),
    limit: int = Query(50, ge=1, le=200),
) -> List[ValueRankingRow]:
    """GAR/WAR leaderboard — actual goals above replacement ('what happened'). Companion to the
    composite/power rankings; GAR includes shooting luck by design (see value-gar.md)."""
    gar = bq_service.get_models_table_id('player_gar')
    rosters = bq_service.get_full_table_id('stg_rosters')
    mart = bq_service.get_full_table_id('mart_team_game_stats')
    if not season:
        season = bq_service.query(
            f"SELECT MAX(season_window) AS s FROM {gar} WHERE season_window LIKE '____-__'")[0]['s']
    groups = {"F": "('C','L','R')", "D": "('D')"}.get(position.upper(), "('C','L','R','D')")
    rows = bq_service.query(f"""
        WITH nm AS (
            SELECT player_id, ANY_VALUE(first_name || ' ' || last_name) AS name,
                   ARRAY_AGG(team_id ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS team_id
            FROM {rosters}
            WHERE SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
            GROUP BY player_id
        ),
        tm AS (SELECT team_id, ANY_VALUE(team_abbrev) AS abbrev FROM {mart} GROUP BY team_id)
        SELECT g.player_id, nm.name, tm.abbrev AS team_abbrev, g.position,
               g.gar, g.war, g.gar_sd, g.ev_offense, g.pp, g.ev_defense, g.pk, g.penalty, g.faceoff
        FROM {gar} g
        LEFT JOIN nm ON g.player_id = nm.player_id
        LEFT JOIN tm ON nm.team_id = tm.team_id
        WHERE g.season_window = '{season}' AND g.position IN {groups}
        ORDER BY g.gar DESC
        LIMIT {int(limit)}
    """)
    out = []
    for r in rows:
        comps = [CompositeComponent(key=k, label=lbl, value=float(r.get(k) or 0.0))
                 for k, lbl in GAR_LABELS]
        out.append(ValueRankingRow(
            player_id=r["player_id"], player_name=r.get("name"), team_abbrev=r.get("team_abbrev"),
            position=r.get("position"), gar=float(r["gar"]), war=float(r["war"]),
            gar_sd=float(r["gar_sd"]) if r.get("gar_sd") is not None else None, components=comps))
    return out
