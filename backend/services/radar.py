"""Service for the skills radar (Part B): reads nhl_models.player_radar / goalie_radar."""

from __future__ import annotations

import json
from typing import Optional

from services.bigquery import bq_service


def _latest(table: str, id_col: str, entity_id: int) -> Optional[str]:
    rows = bq_service.query(
        f"SELECT MAX(season) AS s FROM {bq_service.get_models_table_id(table)} "
        f"WHERE {id_col} = {int(entity_id)}")
    return rows[0]["s"] if rows and rows[0]["s"] else None


def player_radar(player_id: int, season: Optional[str] = None) -> Optional[dict]:
    season = season or _latest("player_radar", "player_id", player_id)
    if not season:
        return None
    rows = bq_service.query(
        f"SELECT * FROM {bq_service.get_models_table_id('player_radar')} "
        f"WHERE player_id = {int(player_id)} AND season = '{season}'")
    if not rows:
        return None
    r = rows[0]
    return {
        "player_id": r["player_id"], "season": r["season"], "pos_group": r.get("pos_group"),
        "spokes": json.loads(r["spokes"]),
        "overall_label": r.get("overall_label"), "offensive_label": r.get("offensive_label"),
        "defensive_label": r.get("defensive_label"), "descriptor": r.get("descriptor"),
        "baseline": r.get("baseline"),
    }


def goalie_radar(goalie_id: int, season: Optional[str] = None) -> Optional[dict]:
    season = season or _latest("goalie_radar", "goalie_id", goalie_id)
    if not season:
        return None
    rows = bq_service.query(
        f"SELECT * FROM {bq_service.get_models_table_id('goalie_radar')} "
        f"WHERE goalie_id = {int(goalie_id)} AND season = '{season}'")
    if not rows:
        return None
    r = rows[0]
    return {"goalie_id": r["goalie_id"], "season": r["season"],
            "games_played": r.get("games_played"), "spokes": json.loads(r["spokes"]),
            "baseline": r.get("baseline")}
