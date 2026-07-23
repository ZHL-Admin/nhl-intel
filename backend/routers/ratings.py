"""Ratings endpoint (RINK THEORY rebuild §4.2) — the site's single standing number.

One new read-only route. It merges the two EXISTING queries that already back
/rankings/power (latest team_ratings row → total_rating + the four weighted
component contributions) and /rankings/deserved (luck_delta = actual − deserved
points), and stamps the payload with data_through = MAX(game_date). No existing
route, service, or serving table is modified.
"""

import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# Season looks like "2025-26". Validating the one user-supplied param before it is
# interpolated into SQL keeps this new route injection-safe on its own terms.
_SEASON_RE = re.compile(r"^\d{4}-\d{2}$")

from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()


class TeamRatingRow(BaseModel):
    """One team's standing number: overall rating, its four weighted component
    contributions (they sum to `rating`), and luck (actual − deserved points)."""
    rank: int
    team_id: int
    team_abbrev: Optional[str] = None
    rating: float
    comp_5v5: float = Field(description="Weighted 5v5-play contribution")
    comp_finishing: float
    comp_goaltending: float
    comp_special_teams: float
    luck: Optional[float] = Field(None, description="Actual minus deserved points")


class RatingsPayload(BaseModel):
    """The /ratings payload for the Power Ratings table and the Home rail."""
    season: str
    data_through: Optional[str] = Field(None, description="MAX(game_date) — data recency, not a run time")
    teams: List[TeamRatingRow]


def _latest_season() -> str:
    rows = bq_service.query(
        f"SELECT MAX(season) AS s FROM {bq_service.get_models_table_id('team_ratings')}")
    return rows[0]['s']


@router.get("", response_model=RatingsPayload)
@cache(ttl=1800)
async def get_ratings(
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> RatingsPayload:
    """Power ratings + luck, one row per team, highest rating first.

    Merges the existing /rankings/power (latest row per team: total_rating and the
    four contrib_* components) and /rankings/deserved (luck_delta) queries; stamps
    the payload with DATA THROUGH = MAX(game_date)."""
    if season is not None and not _SEASON_RE.match(season):
        raise HTTPException(status_code=400, detail="season must look like '2025-26'")
    season = season or _latest_season()
    mart = bq_service.get_full_table_id('mart_team_game_stats')
    ratings = bq_service.get_models_table_id('team_ratings')
    deserved = bq_service.get_models_table_id('deserved_standings')
    sql = f"""
    WITH abbrev AS (
        SELECT team_id, ANY_VALUE(team_abbrev) AS team_abbrev
        FROM {mart}
        WHERE season = '{season}'
        GROUP BY team_id
    ),
    latest AS (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY team_id ORDER BY game_date DESC) AS rn
        FROM {ratings}
        WHERE season = '{season}'
    )
    SELECT l.team_id, a.team_abbrev, l.total_rating,
           l.contrib_play_5v5, l.contrib_finishing,
           l.contrib_goaltending, l.contrib_special_teams,
           d.luck_delta
    FROM latest l
    LEFT JOIN abbrev a USING (team_id)
    LEFT JOIN {deserved} d ON d.team_id = l.team_id AND d.season = l.season
    WHERE l.rn = 1
    ORDER BY l.total_rating DESC
    """
    rows = bq_service.query(sql)
    data_through = bq_service.query(
        f"SELECT CAST(CAST(MAX(game_date) AS DATE) AS STRING) AS d FROM {ratings} WHERE season = '{season}'")
    teams = [
        TeamRatingRow(
            rank=i + 1,
            team_id=r.get('team_id'),
            team_abbrev=r.get('team_abbrev'),
            rating=r.get('total_rating'),
            comp_5v5=r.get('contrib_play_5v5'),
            comp_finishing=r.get('contrib_finishing'),
            comp_goaltending=r.get('contrib_goaltending'),
            comp_special_teams=r.get('contrib_special_teams'),
            luck=r.get('luck_delta'),
        )
        for i, r in enumerate(rows)
    ]
    return RatingsPayload(
        season=season,
        data_through=(data_through[0]['d'] if data_through else None),
        teams=teams,
    )
