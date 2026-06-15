"""Streak Doctor endpoints (Phase 3.3): active notable runs league-wide."""

from typing import List, Optional

from fastapi import APIRouter, Query

from models.schemas import StreakCard, StreakComponent
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()

DEFAULT_WINDOW = 10
# component key -> display label (matches the frontend ComponentStackBar segments)
STREAK_COMPONENTS = [
    ("shooting_luck", "Shooting luck"),
    ("goaltending", "Goaltending"),
    ("special_teams", "Special teams"),
    ("schedule", "Schedule"),
    ("play_change", "Play change"),
]


def card_from_row(r: dict, abbrev: Optional[str]) -> StreakCard:
    comps = [StreakComponent(key=k, label=lbl, value=r[k], share=r[f"{k}_share"])
             for k, lbl in STREAK_COMPONENTS]
    return StreakCard(
        team_id=r["team_id"], team_abbrev=abbrev, season=r["season"],
        window_games=r["window_games"], games=r["games"], run_word=r["run_word"],
        verdict=r["verdict"], total_deviation=r["total_deviation"],
        sustainability=r["sustainability"], is_notable=r["is_notable"],
        points_pace=r["points_pace"], points_pace_z=r["points_pace_z"],
        streak=r["streak"], components=comps,
    )


@router.get("/active", response_model=List[StreakCard])
@cache(ttl=1800)
async def get_active_streaks(
    season: Optional[str] = Query(None),
    window: int = Query(DEFAULT_WINDOW),
) -> List[StreakCard]:
    """Notable runs league-wide for the window, strongest first (Phase 3.3)."""
    cards = bq_service.get_models_table_id('streak_cards')
    mart = bq_service.get_full_table_id('mart_team_game_stats')
    if not season:
        season = bq_service.query(f"SELECT MAX(season) AS s FROM {cards}")[0]['s']
    rows = bq_service.query(f"""
        WITH abbrev AS (
            SELECT team_id, ANY_VALUE(team_abbrev) AS team_abbrev
            FROM {mart} WHERE season = '{season}' GROUP BY team_id
        )
        SELECT c.*, a.team_abbrev
        FROM {cards} c LEFT JOIN abbrev a USING (team_id)
        WHERE c.season = '{season}' AND c.window_games = {window} AND c.is_notable
        ORDER BY ABS(c.points_pace_z) DESC
    """)
    return [card_from_row(r, r.get('team_abbrev')) for r in rows]
