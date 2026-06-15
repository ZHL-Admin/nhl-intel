"""Rankings endpoints: power ratings + deserved standings (Phase 3.1)."""

from typing import List, Optional

from fastapi import APIRouter, Query

from models.schemas import PowerRatingRow, DeservedStandingRow
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
