"""Service layer for the Phase 5 signature tools (Lineup Lab, player fit, matchup previews).

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
    from services import serving
    season = season or latest_roster_season()

    if serving.serving_backend() == "duckdb":
        # Indexed lookup against the precomputed current-season roster dimension (no
        # re-derivation of rosterSpots over raw play-by-play on every keystroke).
        rows = bq_service.query(
            "SELECT player_id, first_name, last_name, team_id, team_abbrev, "
            "position_code AS position, headshot_url, primary_archetype AS archetype "
            "FROM dim_current_roster WHERE name_lower LIKE @like "
            "ORDER BY last_name, first_name LIMIT " + str(int(limit)),
            params=[bigquery.ScalarQueryParameter("like", "STRING", f"%{q.lower()}%")])
        return [{
            "player_id": r["player_id"],
            "name": " ".join(p for p in [r.get("first_name"), r.get("last_name")] if p),
            "team_id": r.get("team_id"), "team_abbrev": r.get("team_abbrev"),
            "position": r.get("position"), "headshot_url": r.get("headshot_url"),
            "archetype": r.get("archetype"),
        } for r in rows]

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


# --- Better fits: per-slot same-caliber swap suggestions (Phase 5.2) ----------
def _positions(ids: list[int], season: str) -> dict[int, Optional[str]]:
    comp = bq_service.get_models_table_id("player_composite")
    idlist = ", ".join(str(int(i)) for i in ids) or "0"
    rows = bq_service.query(
        f"SELECT player_id, position FROM {comp} "
        f"WHERE season_window = @season AND player_id IN ({idlist})",
        params=[bigquery.ScalarQueryParameter("season", "STRING", season)])
    return {r["player_id"]: r.get("position") for r in rows}


def get_same_tier_candidates(player_id: int, line_ids: list[int], season: str, kind: str,
                             caliber_sd: float = 1.5, min_toi: float = 200.0,
                             limit: int = 12) -> list[dict]:
    """Skaters in the same archetype + composite-caliber band as `player_id`, same position
    group (`kind`='F' -> C/L/R, 'D' -> D), excluding anyone already in `line_ids`."""
    arch_t = bq_service.get_models_table_id("player_archetypes")
    comp_t = bq_service.get_models_table_id("player_composite")
    rost = bq_service.get_full_table_id("stg_rosters")

    ref = bq_service.query(
        f"""SELECT a.primary_archetype AS arch, c.total AS total, c.total_sd AS sd
            FROM {arch_t} a
            JOIN {comp_t} c ON a.player_id = c.player_id AND a.season = c.season_window
            WHERE a.player_id = {int(player_id)} AND a.season = @season""",
        params=[bigquery.ScalarQueryParameter("season", "STRING", season)])
    if not ref or ref[0].get("arch") is None:
        return []
    arch = ref[0]["arch"]
    total = float(ref[0]["total"])
    sd = float(ref[0]["sd"]) if ref[0].get("sd") else 3.0
    lo, hi = total - caliber_sd * sd, total + caliber_sd * sd
    positions = FWD_POS if kind == "F" else ("D",)
    pos_list = ", ".join(f"'{p}'" for p in positions)
    exclude = ", ".join(str(int(i)) for i in line_ids) or "0"

    from services import serving
    if serving.serving_backend() == "duckdb":
        rows = bq_service.query(
            f"""
            SELECT d.player_id, d.first_name AS fn, d.last_name AS ln, d.team_id,
                   d.position_code AS position, d.headshot_url, c.total AS total, c.toi_5v5 AS toi
            FROM dim_current_roster d
            JOIN player_composite c ON c.player_id = d.player_id AND c.season_window = @season
            WHERE d.primary_archetype = @arch AND d.position_code IN ({pos_list})
              AND c.total BETWEEN @lo AND @hi AND c.toi_5v5 >= @min_toi
              AND d.player_id NOT IN ({exclude})
            ORDER BY c.total DESC LIMIT {int(limit)}
            """,
            params=[
                bigquery.ScalarQueryParameter("season", "STRING", season),
                bigquery.ScalarQueryParameter("arch", "STRING", arch),
                bigquery.ScalarQueryParameter("lo", "FLOAT64", lo),
                bigquery.ScalarQueryParameter("hi", "FLOAT64", hi),
                bigquery.ScalarQueryParameter("min_toi", "FLOAT64", min_toi),
            ])
        out = []
        for r in rows:
            out.append({
                "player_id": r["player_id"],
                "name": " ".join(p for p in [r.get("fn"), r.get("ln")] if p),
                "team_id": r.get("team_id"), "team_abbrev": _abbrev(r.get("team_id")),
                "position": r.get("position"), "headshot_url": r.get("headshot_url"),
                "archetype": arch,
                "composite_total": round(float(r["total"]), 2) if r.get("total") is not None else None,
            })
        return out

    rows = bq_service.query(
        f"""
        WITH latest AS (
            SELECT player_id,
                   ARRAY_AGG(STRUCT(team_id, headshot_url, first_name, last_name, position_code)
                             ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS r
            FROM {rost}
            WHERE season = @season AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
            GROUP BY player_id
        )
        SELECT l.player_id, l.r.first_name AS fn, l.r.last_name AS ln, l.r.team_id AS team_id,
               l.r.position_code AS position, l.r.headshot_url AS headshot_url,
               c.total AS total, c.toi_5v5 AS toi
        FROM latest l
        JOIN {arch_t} a ON a.player_id = l.player_id AND a.season = @season
        JOIN {comp_t} c ON c.player_id = l.player_id AND c.season_window = @season
        WHERE a.primary_archetype = @arch
          AND l.r.position_code IN ({pos_list})
          AND c.total BETWEEN @lo AND @hi
          AND c.toi_5v5 >= @min_toi
          AND l.player_id NOT IN ({exclude})
        ORDER BY c.total DESC
        LIMIT {int(limit)}
        """,
        params=[
            bigquery.ScalarQueryParameter("season", "STRING", season),
            bigquery.ScalarQueryParameter("arch", "STRING", arch),
            bigquery.ScalarQueryParameter("lo", "FLOAT64", lo),
            bigquery.ScalarQueryParameter("hi", "FLOAT64", hi),
            bigquery.ScalarQueryParameter("min_toi", "FLOAT64", min_toi),
        ])
    out = []
    for r in rows:
        out.append({
            "player_id": r["player_id"],
            "name": " ".join(p for p in [r.get("fn"), r.get("ln")] if p),
            "team_id": r.get("team_id"), "team_abbrev": _abbrev(r.get("team_id")),
            "position": r.get("position"), "headshot_url": r.get("headshot_url"),
            "archetype": arch,
            "composite_total": round(float(r["total"]), 2) if r.get("total") is not None else None,
        })
    return out


def line_fit_suggestions(player_ids: list[int], season: Optional[str] = None,
                         pool_limit: int = 8, top_n: int = 5) -> dict:
    """Per-slot 'better fit' suggestions: same-caliber candidates ranked by the projected
    xGF% gain from swapping them in for the current member."""
    from models_ml.score_line import score_line as _score
    from insight_engine.templates.line_fit import swap_reasons

    season = season or latest_roster_season()
    ids = [int(i) for i in player_ids]
    if len(ids) == 3:
        sublines = [("F3", ids)]
    elif len(ids) == 2:
        sublines = [("D2", ids)]
    elif len(ids) == 5:
        pos = _positions(ids, season)
        fwds = [i for i in ids if pos.get(i) in FWD_POS]
        defs = [i for i in ids if pos.get(i) == "D"]
        if len(fwds) != 3 or len(defs) != 2:
            raise ValueError("a 5-skater unit must be 3 forwards + 2 defensemen")
        sublines = [("F3", fwds), ("D2", defs)]
    else:
        raise ValueError("line must be 2, 3, or 5 skaters")

    slots: list[dict] = []
    for line_type, sub in sublines:
        base = _score(sub, season, blend=False)
        base_xgf = base["projected_xgf_pct"]
        base_contribs = base.get("contribs", {})
        members = {m["player_id"]: m for m in base["members"]}
        kind = "F" if line_type == "F3" else "D"
        for idx, pid in enumerate(sub):
            pool = get_same_tier_candidates(pid, sub, season, kind, limit=pool_limit)
            cands = []
            for c in pool:
                swap_ids = [c["player_id"] if j == idx else x for j, x in enumerate(sub)]
                try:
                    sp = _score(swap_ids, season, blend=False)
                except Exception:
                    continue
                gain = sp["projected_xgf_pct"] - base_xgf
                if gain <= 0:
                    continue
                cands.append({
                    "player_id": c["player_id"], "name": c["name"],
                    "team_id": c["team_id"], "team_abbrev": c["team_abbrev"],
                    "position": c["position"], "headshot_url": c["headshot_url"],
                    "archetype": c["archetype"], "composite_total": c["composite_total"],
                    "swap_xgf_pct": round(sp["projected_xgf_pct"], 4),
                    "swap_grade": sp["grade"], "xgf_gain": round(gain, 4),
                    "reasons": swap_reasons(base_contribs, sp.get("contribs", {})),
                })
            cands.sort(key=lambda x: -x["xgf_gain"])
            mem = members.get(pid, {})
            slots.append({
                "slot_index": len(slots),
                "position": mem.get("position"),
                "current_player_id": pid,
                "current_player_name": mem.get("name"),
                "candidates": cands[:top_n],
            })
    return {"season": season,
            "line_type": "UNIT5" if len(ids) == 5 else sublines[0][0],
            "slots": slots}


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
    from services import serving
    season = season or latest_roster_season()
    if serving.serving_backend() == "duckdb":
        # Read the precomputed memberships (the int_shift_segments scan ran nightly).
        rows = bq_service.query(
            "SELECT line_type, line_key, minutes FROM team_current_lines "
            f"WHERE team_id = {int(team_id)} AND season = '{season}' ORDER BY line_type, rnk")
        rows = [{"line_type": r["line_type"],
                 "members": [int(x) for x in str(r["line_key"]).split("-")],
                 "minutes": r["minutes"]} for r in rows]
    else:
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


def best_team_fits(player_id: int, season: Optional[str] = None,
                   exclude_team_id: Optional[int] = None) -> list[dict]:
    """The teams whose gaps a player best fills, ranked (Phase 5.3)."""
    from models_ml.score_team_fit import best_team_fits as _best
    return _best(player_id, season, exclude_team_id=exclude_team_id)


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
