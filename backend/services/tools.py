"""Service layer for the Phase 5 signature tools (Lineup Lab, trade fit, matchup previews).

Wraps the model-layer scoring jobs (models_ml.score_line, models_ml.score_team_fit) and the
BigQuery lookups the tool endpoints need. The model layer lives at the repo root, so we put the
root on sys.path here (the backend runs from backend/).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from google.cloud import bigquery

from services.bigquery import bq_service

FWD_POS = ("C", "L", "R")


def latest_roster_season() -> str:
    rows = bq_service.query(
        f"SELECT MAX(season) AS s FROM {bq_service.get_full_table_id('stg_rosters')}")
    return rows[0]["s"]


def search_players(q: str, limit: int = 20, season: Optional[str] = None) -> list[dict]:
    """Current-season roster players whose name matches `q` (prefix or substring)."""
    season = season or latest_roster_season()
    rosters = bq_service.get_full_table_id("stg_rosters")
    arch = bq_service.get_models_table_id("player_archetypes")
    sql = f"""
    WITH latest AS (
        SELECT player_id,
               ARRAY_AGG(STRUCT(team_id, headshot_url, first_name, last_name, position_code)
                         ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS r
        FROM {rosters}
        WHERE season = @season AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
        GROUP BY player_id
    )
    SELECT l.player_id, l.r.first_name AS first_name, l.r.last_name AS last_name,
           l.r.team_id AS team_id, l.r.position_code AS position,
           l.r.headshot_url AS headshot_url, a.primary_archetype AS archetype
    FROM latest l
    LEFT JOIN {arch} a ON a.player_id = l.player_id AND a.season = @season
    WHERE LOWER(l.r.first_name || ' ' || l.r.last_name) LIKE LOWER(@like)
    ORDER BY l.r.last_name, l.r.first_name
    LIMIT {int(limit)}
    """
    rows = bq_service.query(sql, params=[
        bigquery.ScalarQueryParameter("season", "STRING", season),
        bigquery.ScalarQueryParameter("like", "STRING", f"%{q}%"),
    ])
    out = []
    for r in rows:
        name = " ".join(p for p in [r.get("first_name"), r.get("last_name")] if p)
        out.append({
            "player_id": r["player_id"], "name": name, "team_id": r.get("team_id"),
            "team_abbrev": _abbrev(r.get("team_id")), "position": r.get("position"),
            "headshot_url": r.get("headshot_url"), "archetype": r.get("archetype"),
        })
    return out


def score_line(player_ids: list[int], season: Optional[str] = None) -> dict:
    """Project a line. Defers the heavy model import until first use."""
    from models_ml.score_line import score_line as _score
    season = season or latest_roster_season()
    return _score(player_ids, season)


# current trios/pairs over a team's last 10 games (the swap-widget / preview source)
_CURRENT_LINES_SQL = """
WITH g AS (
    SELECT game_id, game_date FROM {box}
    WHERE (home_team_id = @team OR away_team_id = @team) AND season = @season
      AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02', '03')
    ORDER BY game_date DESC LIMIT 10
),
seg5 AS (
    SELECT s.game_id, s.segment_index, s.player_id, s.position_code, c.segment_duration
    FROM {seg} s
    JOIN {ctx} c USING (game_id, segment_index)
    JOIN g USING (game_id)
    WHERE s.team_id = @team AND s.is_goalie = 0 AND c.strength_state = '5v5'
),
fwd AS (
    SELECT game_id, segment_index, ANY_VALUE(segment_duration) AS dur,
        ARRAY_AGG(player_id ORDER BY player_id) AS members, COUNT(*) AS n
    FROM seg5 WHERE position_code IN ('C', 'L', 'R') GROUP BY 1, 2
),
def AS (
    SELECT game_id, segment_index, ANY_VALUE(segment_duration) AS dur,
        ARRAY_AGG(player_id ORDER BY player_id) AS members, COUNT(*) AS n
    FROM seg5 WHERE position_code = 'D' GROUP BY 1, 2
),
trio AS (
    SELECT 'F3' AS line_type,
        (SELECT STRING_AGG(CAST(m AS STRING), '-' ORDER BY m) FROM UNNEST(members) m) AS line_key,
        ANY_VALUE(members) AS members, SUM(dur) / 60.0 AS minutes
    FROM fwd WHERE n = 3 GROUP BY line_key ORDER BY minutes DESC LIMIT 4
),
pair AS (
    SELECT 'D2' AS line_type,
        (SELECT STRING_AGG(CAST(m AS STRING), '-' ORDER BY m) FROM UNNEST(members) m) AS line_key,
        ANY_VALUE(members) AS members, SUM(dur) / 60.0 AS minutes
    FROM def WHERE n = 2 GROUP BY line_key ORDER BY minutes DESC LIMIT 3
)
SELECT * FROM trio UNION ALL SELECT * FROM pair
"""


def current_lines(team_id: int, season: Optional[str] = None) -> dict:
    """A team's current forward trios + defense pairs over its last 10 games, each projected."""
    season = season or latest_roster_season()
    sql = _CURRENT_LINES_SQL.format(
        box=bq_service.get_full_table_id("stg_boxscores"),
        seg=bq_service.get_full_table_id("int_shift_segments"),
        ctx=bq_service.get_full_table_id("int_segment_context"),
    )
    rows = bq_service.query(sql, params=[
        bigquery.ScalarQueryParameter("team", "INT64", team_id),
        bigquery.ScalarQueryParameter("season", "STRING", season),
    ])
    fwd, dfn = [], []
    for r in rows:
        ids = [int(m) for m in r["members"]]
        try:
            proj = score_line(ids, season)
        except Exception:
            proj = None
        names = [m["name"] for m in proj["members"]] if proj else []
        obs = proj.get("observed_blend") if proj else None
        line = {
            "line_type": r["line_type"], "player_ids": ids, "member_names": names,
            "minutes": round(float(r["minutes"]), 1),
            "observed_xgf_pct": obs["observed_xgf_pct"] if obs else None,
            "projection": proj,
        }
        (fwd if r["line_type"] == "F3" else dfn).append(line)
    return {"team_id": team_id, "season": season,
            "forward_lines": fwd, "defense_pairs": dfn}


_ABBREV_CACHE: dict[int, str] = {}


def _abbrev(team_id: Optional[int]) -> Optional[str]:
    if team_id is None:
        return None
    if not _ABBREV_CACHE:
        rows = bq_service.query(f"""
            SELECT team_id, ANY_VALUE(team_abbrev) AS a
            FROM {bq_service.get_full_table_id('mart_team_game_stats')} GROUP BY team_id""")
        for r in rows:
            _ABBREV_CACHE[r["team_id"]] = r["a"]
    return _ABBREV_CACHE.get(team_id)
