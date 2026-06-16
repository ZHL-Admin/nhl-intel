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


def trade_fit(player_id: int, team_id: int, season: Optional[str] = None) -> dict:
    """Score how well a player fills a team's needs (Phase 5.3)."""
    from models_ml.score_team_fit import score_team_fit as _fit
    return _fit(player_id, team_id, season)


# --- Matchup preview (Phase 5.3) --------------------------------------------
_IDENTITY_METRICS = ["pace", "forecheck_share_for", "rush_share_for", "shot_quality",
                     "shot_volume_per60", "hits_per60"]


def matchup_preview(game_id: int) -> dict:
    """Pregame preview for a scheduled (FUT/PRE) game, composed from existing tables."""
    import math
    from models_ml import config
    from insight_engine.templates import matchup as mtmpl

    games = bq_service.get_full_table_id("stg_games")
    g = bq_service.query(f"""
        SELECT season, game_state, home_team_id, away_team_id, home_team_abbrev, away_team_abbrev
        FROM {games} WHERE game_id = {int(game_id)}""")
    if not g:
        raise LookupError("game not found")
    g = g[0]
    if g["game_state"] not in ("FUT", "PRE"):
        raise ValueError("preview is only available for unplayed (FUT/PRE) games")
    season = g["season"]
    home_id, away_id = g["home_team_id"], g["away_team_id"]

    ratings = _team_ratings(season, [home_id, away_id])
    goalies = _starter_goalies(season, [home_id, away_id])
    ident = _identity(season, [home_id, away_id])
    series = _season_series(game_id, g["home_team_abbrev"], g["away_team_abbrev"])
    streaks = _notable_streaks(season, [home_id, away_id])

    # pregame home WP from the power-rating difference (config-documented logistic)
    home_wp = None
    if ratings.get(home_id) is not None and ratings.get(away_id) is not None:
        rdiff = ratings[home_id] + config.PREVIEW_HOME_ICE_GOALS - ratings[away_id]
        home_wp = round(1.0 / (1.0 + math.exp(-rdiff / config.PREVIEW_WP_SCALE)), 3)

    style = mtmpl.clash(ident.get(home_id, {}), ident.get(away_id, {}),
                        g["home_team_abbrev"], g["away_team_abbrev"])

    def side(team_id, abbr):
        gl = goalies.get(team_id, {})
        return {
            "team_id": team_id, "team_abbrev": abbr,
            "power_rating": ratings.get(team_id),
            "goalie_name": gl.get("name"), "goalie_last10_gsax": gl.get("last10_gsax"),
            "fingerprint_top": _fingerprint_top(ident.get(team_id, {})),
        }

    return {
        "game_id": game_id, "game_state": g["game_state"],
        "home": side(home_id, g["home_team_abbrev"]),
        "away": side(away_id, g["away_team_abbrev"]),
        "home_pregame_wp": home_wp, "style_clash": style,
        "season_series": series, "notable_streaks": streaks,
    }


def _team_ratings(season: str, team_ids: list[int]) -> dict[int, float]:
    t = bq_service.get_models_table_id("team_ratings")
    ids = ", ".join(str(int(i)) for i in team_ids)
    rows = bq_service.query(f"""
        SELECT team_id, total_rating FROM (
            SELECT team_id, total_rating,
                   ROW_NUMBER() OVER (PARTITION BY team_id ORDER BY game_date DESC) rn
            FROM {t} WHERE season = '{season}' AND team_id IN ({ids})
        ) WHERE rn = 1""")
    return {r["team_id"]: round(float(r["total_rating"]), 3) for r in rows}


def _starter_goalies(season: str, team_ids: list[int]) -> dict[int, dict]:
    gs = bq_service.get_full_table_id("mart_goalie_season")
    rosters = bq_service.get_full_table_id("stg_rosters")
    ids = ", ".join(str(int(i)) for i in team_ids)
    rows = bq_service.query(f"""
        WITH starters AS (
            SELECT team_id, goalie_id, last10_gsax, games_played,
                   ROW_NUMBER() OVER (PARTITION BY team_id ORDER BY games_played DESC) rn
            FROM {gs} WHERE season = '{season}' AND team_id IN ({ids})
        ),
        nm AS (SELECT player_id, ANY_VALUE(first_name||' '||last_name) name FROM {rosters} GROUP BY 1)
        SELECT s.team_id, s.goalie_id, s.last10_gsax, nm.name
        FROM starters s LEFT JOIN nm ON nm.player_id = s.goalie_id WHERE s.rn = 1""")
    return {r["team_id"]: {"name": r.get("name"),
                           "last10_gsax": round(float(r["last10_gsax"]), 2)
                           if r.get("last10_gsax") is not None else None} for r in rows}


def _identity(season: str, team_ids: list[int]) -> dict[int, dict]:
    t = bq_service.get_full_table_id("mart_team_identity")
    ids = ", ".join(str(int(i)) for i in team_ids)
    cols = ", ".join(f"{m}_pctile" for m in _IDENTITY_METRICS)
    rows = bq_service.query(f"""
        SELECT team_id, {cols} FROM {t}
        WHERE season = '{season}' AND team_id IN ({ids}) AND window_kind = 'season'""")
    return {r["team_id"]: {m: r.get(f"{m}_pctile") for m in _IDENTITY_METRICS} for r in rows}


_FINGERPRINT_LABEL = {
    "pace": "high pace", "forecheck_share_for": "forecheck-heavy", "rush_share_for": "rush attack",
    "shot_quality": "shot quality", "shot_volume_per60": "shot volume", "hits_per60": "physical",
}


def _fingerprint_top(ident: dict, n: int = 3) -> list[str]:
    ranked = sorted(((m, ident.get(m)) for m in _IDENTITY_METRICS if ident.get(m) is not None),
                    key=lambda kv: float(kv[1]), reverse=True)
    return [f"{_FINGERPRINT_LABEL[m]} ({round(float(v) * 100)}th)" for m, v in ranked[:n]
            if float(v) >= 0.5]


def _season_series(game_id: int, home_abbr: str, away_abbr: str) -> Optional[str]:
    ctx = bq_service.get_full_table_id("stg_game_context")
    rows = bq_service.query(f"""
        SELECT season_series_home_wins h, season_series_away_wins a
        FROM {ctx} WHERE game_id = {int(game_id)}""")
    if not rows or rows[0].get("h") is None:
        return None
    r = rows[0]
    return f"Season series: {home_abbr} {r['h']}–{r['a']} {away_abbr}"


def _notable_streaks(season: str, team_ids: list[int]) -> list[str]:
    sc = bq_service.get_models_table_id("streak_cards")
    ids = ", ".join(str(int(i)) for i in team_ids)
    rows = bq_service.query(f"""
        SELECT verdict FROM {sc}
        WHERE season = '{season}' AND team_id IN ({ids}) AND window_games = 10 AND is_notable = TRUE""")
    return [r["verdict"] for r in rows if r.get("verdict")]


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
