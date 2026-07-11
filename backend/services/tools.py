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

import math
from functools import lru_cache

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
    roster_current = bq_service.get_full_table_id("stg_roster_current")
    cur_team = bq_service.get_full_table_id("int_player_current_team")
    arch = bq_service.get_models_table_id("player_archetypes")
    # Membership comes from the live-roster-first resolution (int_player_current_team): a
    # traded player shows his NEW team before he dresses. Identity (name/pos/headshot) prefers
    # the live roster too, falling back to the latest game for anyone not on a live roster.
    sql = f"""
    WITH latest AS (
        SELECT player_id,
               ARRAY_AGG(STRUCT(team_id, headshot_url, first_name, last_name, position_code)
                         ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS r
        FROM {rosters}
        WHERE season = @season AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
        GROUP BY player_id
    ),
    live AS (
        SELECT player_id, team_id, first_name, last_name, position_code, headshot_url
        FROM {roster_current}
    ),
    res AS (SELECT player_id, current_team_id FROM {cur_team})
    SELECT l.player_id,
           COALESCE(live.first_name, l.r.first_name) AS first_name,
           COALESCE(live.last_name, l.r.last_name) AS last_name,
           COALESCE(res.current_team_id, l.r.team_id) AS team_id,
           COALESCE(live.position_code, l.r.position_code) AS position,
           COALESCE(live.headshot_url, l.r.headshot_url) AS headshot_url,
           a.primary_archetype AS archetype
    FROM latest l
    LEFT JOIN live ON live.player_id = l.player_id
    LEFT JOIN res ON res.player_id = l.player_id
    LEFT JOIN {arch} a ON a.player_id = l.player_id AND a.season = @season
    WHERE LOWER(COALESCE(live.first_name, l.r.first_name) || ' ' ||
                COALESCE(live.last_name, l.r.last_name)) LIKE LOWER(@like)
    ORDER BY COALESCE(live.last_name, l.r.last_name), COALESCE(live.first_name, l.r.first_name)
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
    from models_ml.textfmt import ordinal
    ranked = sorted(((m, ident.get(m)) for m in _IDENTITY_METRICS if ident.get(m) is not None),
                    key=lambda kv: float(kv[1]), reverse=True)
    return [f"{_FINGERPRINT_LABEL[m]} ({ordinal(round(float(v) * 100))})" for m, v in ranked[:n]
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


# ============================================================================================
# Roster Builder (POST /tools/roster-evaluate). An interactive depth-chart sandbox: project an
# arbitrary user-built roster forward and grade it, points-led (DELTA vs the team's real roster as
# the headline, absolute points secondary with a band). Reuses the offseason forecast engine
# (project_skater_war/goalie, build_lineup, lineup_value, forecast_band, inflate_arrival_bands,
# chemistry_adjustment, rating_to_points) + the new absolute_rating helper, and the Lineup Lab
# score_line for per-line fit grades. No cap/salary anywhere (explicitly out of scope).
# ============================================================================================

# Slot scheme: 4 forward lines (LW/C/RW), 3 defense pairs (LD/RD), starter + backup goalie. Only the
# 12F/6D/1-starter are ICED for value (N_GOALIE=1 — the backup dresses but the model counts one
# goalie's WAR, matching the calibration); anything else is a scratch with no on-ice value.
FWD_LINES = [[f"F{ln}{w}" for w in ("L", "C", "R")] for ln in range(1, 5)]
DEF_PAIRS = [[f"D{pr}{s}" for s in ("L", "R")] for pr in range(1, 4)]
FWD_SLOTS = [s for line in FWD_LINES for s in line]
DEF_SLOTS = [s for pair in DEF_PAIRS for s in pair]
ICED_SLOTS = FWD_SLOTS + DEF_SLOTS + ["G1"]
ALL_SLOTS = FWD_SLOTS + DEF_SLOTS + ["G1", "G2"]

# Position columns for the auto-optimizer: a forward fills the column of his natural position
# (C/L/R), a defenseman the column of his handedness side (left-shot -> LD, right-shot -> RD), best
# at the top. Short positions / surplus flex-fill the remaining slots (off-position / off-side), as
# real depth charts do — a hole is never left for a player who exists.
_FWD_COLS = {"L": ["F1L", "F2L", "F3L", "F4L"], "C": ["F1C", "F2C", "F3C", "F4C"],
             "R": ["F1R", "F2R", "F3R", "F4R"]}
_DEF_COLS = {"L": ["D1L", "D2L", "D3L"], "R": ["D1R", "D2R", "D3R"]}


def _pos_group_of_slot(slot: str) -> str:
    return "G" if slot.startswith("G") else ("D" if slot.startswith("D") else "F")


@lru_cache(maxsize=2)
def _forecast_inputs(base_season: str) -> dict:
    """The heavy, roster-independent projection inputs, loaded once per base season (the live tool
    re-evaluates on every edit, so this MUST be cached). All route through models_ml.bq, which reads
    the DuckDB serving file in the API process — the same path the offseason forecast uses."""
    from models_ml import bq, project_roster_forecast as J
    n_back = J.CFG["PROJ_WINDOWS"]
    return {
        "skater": J.load_skater_war_multi(bq, base_season, n_back),
        "goalie": J.load_goalie_war_multi(bq, base_season, n_back),
        "arch": J.load_archetypes(bq, base_season),
        "aging": J.load_aging(bq),
        "ages": J.load_ages(bq, base_season),
        "names": J.load_player_names(bq),
        "components": _load_components(base_season),
        "index": _league_player_index(base_season),
        "hand": _load_handedness(),
        "effpos": _load_effective_position(),
        "proj": _load_projections(),
    }


@lru_cache(maxsize=8)
def _team_predictive_base(team_id: int, base_season: str) -> Optional[float]:
    """R_measured: the team's 2-year recency-weighted, league-mean-regressed MEASURED rating — the best
    single predictor of next-season strength (Handoff 13). Anchors the hybrid. None if the team has no
    rating history (then the tool degrades to pure bottom-up). Uses seasons <= base_season."""
    from models_ml import project_roster_forecast as J
    CFG = J.CFG
    rows = bq_service.query(
        "SELECT season, total_rating FROM ("
        "  SELECT season, total_rating, ROW_NUMBER() OVER ("
        "    PARTITION BY season ORDER BY game_date DESC, games_played DESC) rn "
        "  FROM team_ratings WHERE team_id = @t AND season <= @s) WHERE rn = 1 "
        "ORDER BY season DESC",
        params=[bigquery.ScalarQueryParameter("t", "INT64", int(team_id)),
                bigquery.ScalarQueryParameter("s", "STRING", base_season)])
    ratings = [float(r["total_rating"]) for r in rows]
    if not ratings:
        return None
    W = CFG["ROSTER_BUILDER_BASE_W"]; K = CFG["ROSTER_BUILDER_BASE_K"]
    m = min(len(ratings), len(W))
    num = sum(W[j] * ratings[j] for j in range(m)); wt = sum(W[j] for j in range(m))
    base = num / wt
    return (wt * base) / (wt + K)   # regress toward league mean (0)


@lru_cache(maxsize=1)
def _load_projections() -> dict:
    """player_id -> {proj_war, proj_war_sd} from the Handoff-12 component model (roster_player_projection).
    This is the Roster Builder's projection — a regularized component Marcel with backtest-calibrated,
    heteroscedastic uncertainty — replacing make_player_proj's last-season-WAR + gar_sd/6. The offseason
    /trade/contract tools are untouched (documented temporary divergence)."""
    out: dict = {}
    try:
        for r in bq_service.query(
                "SELECT player_id, proj_war, proj_war_sd, proj_toi FROM roster_player_projection"):
            out[int(r["player_id"])] = {"war": float(r["proj_war"]), "sd": float(r["proj_war_sd"]),
                                        "toi": float(r.get("proj_toi") or 600.0)}
    except Exception:  # noqa: BLE001 — table absent (not yet precomputed) -> fall back to make_player_proj
        return {}
    return out


@lru_cache(maxsize=1)
def _load_handedness() -> dict:
    """player_id -> shoots ('L'/'R') from stg_player_bio — used to seat a defenseman on his natural
    side (left-shot = LD, right-shot = RD) when auto-optimizing the depth chart."""
    out: dict = {}
    for r in bq_service.query("SELECT player_id, shoots FROM stg_player_bio WHERE shoots IS NOT NULL"):
        out[int(r["player_id"])] = str(r["shoots"])
    return out


@lru_cache(maxsize=1)
def _load_effective_position() -> dict:
    """player_id -> {'effective', 'locked', 'fo_per_gp'} from the player_effective_position precompute:
    the position a forward ACTUALLY plays (C/L/R/F_FLEX), derived from faceoff volume rather than the
    listed roster feed (J.T. Compher lists as LW but takes center draws). Drives the position-aware
    binning + off-position penalties in _ice_from_pool and the effective-position match in roster_suggest.
    A player absent here (no faceoff rows) is not in the dict, so the caller falls back to listed position."""
    out: dict = {}
    try:
        rows = bq_service.query(
            "SELECT player_id, effective_position, locked, fo_per_gp FROM player_effective_position")
    except Exception:  # noqa: BLE001 — table absent (not yet precomputed/exported) -> fall back to listed
        return {}
    for r in rows:
        out[int(r["player_id"])] = {
            "effective": str(r["effective_position"]),
            "locked": bool(r["locked"]),
            "fo_per_gp": float(r["fo_per_gp"]) if r.get("fo_per_gp") is not None else 0.0,
        }
    return out


def _effective_fwd_pos(pid, listed, effpos) -> str:
    """Thin wrapper over the shared engine's effective_fwd_pos (single source of truth): a forward's
    effective position code ('C'/'L'/'R'/'F_FLEX'), from player_effective_position or the listed feed."""
    from models_ml import project_roster_forecast as J
    return J.effective_fwd_pos(pid, listed, effpos)


@lru_cache(maxsize=16)
def _seed_units(team_id: int, base_season: str) -> dict:
    """Observed 5v5 units for deployment-aware line seeding, keyed by a team + base season. MERGES the
    team's full-season int_line_seasons units (floor LINE_SEED_MIN_5V5_MINUTES) with its last-10-games
    team_current_lines units (proportional LINE_SEED_MIN_5V5_MINUTES_CURRENT floor). Returns
    {'F3': [(frozenset(ids), minutes)...], 'D2': [...]} sorted by shared minutes desc — so established
    season units seed first and recent-form units only fill gaps. Cached (the live tool re-evaluates on
    every edit; this must not re-query per keystroke). Both source tables are already exported to DuckDB."""
    from models_ml import project_roster_forecast as J
    CFG = J.CFG
    out: dict = {"F3": [], "D2": []}
    season_floor = CFG["LINE_SEED_MIN_5V5_MINUTES"]
    current_floor = CFG["LINE_SEED_MIN_5V5_MINUTES_CURRENT"]

    def _add(rows, floor):
        for r in rows:
            lt = r.get("line_type")
            if lt not in out:
                continue
            mins = float(r["minutes"])
            if mins < floor:
                continue
            members = frozenset(int(x) for x in str(r["line_key"]).split("-"))
            out[lt].append((members, mins))

    try:
        _add(bq_service.query(
            "SELECT line_type, line_key, minutes FROM int_line_seasons "
            f"WHERE team_id = {int(team_id)} AND season = '{base_season}'"), season_floor)
    except Exception:  # noqa: BLE001 — table absent -> no season units (still try current)
        pass
    try:
        _add(bq_service.query(
            "SELECT line_type, line_key, minutes FROM team_current_lines "
            f"WHERE team_id = {int(team_id)}"), current_floor)
    except Exception:  # noqa: BLE001 — table absent -> season units only
        pass
    for lt in out:
        out[lt].sort(key=lambda mm: -mm[1])
    return out


@lru_cache(maxsize=2)
def _load_components(base_season: str) -> dict:
    """player_id -> realized latest-window GAR components (goals scale) for the component breakdown.
    Skaters from player_gar; goalies' realized WAR from goalie_gar. Realized (not projected) — this is
    the 'what this roster is made of' decomposition, like the offseason tool's base_* components."""
    out: dict = {}
    for r in bq_service.query(
        "SELECT player_id, ev_offense, pp, ev_defense, pk, penalty, faceoff, goals, ixg "
        "FROM player_gar WHERE season_window = @s",
            params=[bigquery.ScalarQueryParameter("s", "STRING", base_season)]):
        out[int(r["player_id"])] = {k: float(r.get(k) or 0.0) for k in
                                    ("ev_offense", "pp", "ev_defense", "pk", "penalty", "faceoff",
                                     "goals", "ixg")}
    for r in bq_service.query(
        "SELECT goalie_id, war FROM goalie_gar WHERE season_window = @s",
            params=[bigquery.ScalarQueryParameter("s", "STRING", base_season)]):
        out.setdefault(int(r["goalie_id"]), {})["goalie_war"] = float(r.get("war") or 0.0)
    return out


@lru_cache(maxsize=2)
def _league_player_index(season: str) -> dict:
    """player_id -> {name, position, team_id, headshot} for every current-roster player, so a placed
    player carries his real identity (name/position/headshot) regardless of which slot he sits in."""
    out: dict = {}
    for r in bq_service.query(
        "SELECT player_id, full_name, position_code, team_id, headshot_url "
        "FROM dim_current_roster WHERE season = @s",
            params=[bigquery.ScalarQueryParameter("s", "STRING", season)]):
        out[int(r["player_id"])] = {
            "name": r.get("full_name"), "position": r.get("position_code") or "F",
            "team_id": r.get("team_id"), "headshot": r.get("headshot_url")}
    return out


def _team_current_members(team_id: int, season: str) -> list[dict]:
    """The team's CURRENT roster (dim_current_roster) — the baseline the canvas pre-loads and the
    delta is measured against. Matches GET /teams/{id}/roster's membership source."""
    rows = bq_service.query(
        "SELECT player_id, full_name, position_code FROM dim_current_roster "
        "WHERE team_id = @t AND season = @s",
        params=[bigquery.ScalarQueryParameter("t", "INT64", int(team_id)),
                bigquery.ScalarQueryParameter("s", "STRING", season)])
    return [{"player_id": int(r["player_id"]), "name": r.get("full_name"),
             "position": r.get("position_code") or "F"} for r in rows]


def _proj(pid, position, inp):
    """Project one placed player. Identity/base_war/pos come from make_player_proj; the projected WAR
    and its (calibrated, heteroscedastic) sd are OVERRIDDEN by the Handoff-12 component model when the
    player has a projection row. A player absent from the table (no GAR history) keeps the make_player_proj
    no-track replacement + wide fallback band."""
    from models_ml import project_roster_forecast as J
    name = (inp["index"].get(int(pid), {}) or {}).get("name") or inp["names"].get(int(pid))
    p = J.make_player_proj(int(pid), name, position, inp["skater"], inp["goalie"],
                           inp["aging"], inp["ages"], inp["arch"], project_value=True)
    # Display the EFFECTIVE (faceoff-derived) position for a forward — a listed-LW who plays center
    # (Compher) shows as C. Value is untouched (position is not a value input); F_FLEX / no-evidence
    # forwards keep their listed position. The assignment reads effpos directly, so this is display-only.
    p.position = J.apply_effective_position(p.position, int(pid), inp.get("effpos", {}))
    pr = inp["proj"].get(int(pid))
    if pr is not None:
        p.projected_war = pr["war"]
        p.war_sd = pr["sd"]
        p.no_track_record = False
    return p


def _place(p, slot, slot_map):
    p.slot = slot
    slot_map[slot] = p


def _ice_from_pool(players, inp, seed_units=None):
    """Auto-optimize the depth chart, POSITION- and DEPLOYMENT-AWARE. Forwards: SEED observed trios
    (real 5v5 units from seed_units, so a team that splits its stars is reproduced instead of WAR-
    stacked), then ASSIGN the rest by a soft-penalty assignment over EFFECTIVE positions (a listed-LW
    who takes center draws ices at C). Defensemen: seed observed pairs, then handedness side, with
    surplus / short positions flex-filling the rest. A hole is never dropped — an unfilled slot is
    replacement level. seed_units None -> pure Phase-1 assignment. Returns slot->PlayerProj + scratch."""
    from models_ml import project_roster_forecast as J
    CFG = J.CFG
    war = lambda p: p.projected_war  # noqa: E731
    hand = inp["hand"]
    effpos = inp.get("effpos", {})
    units = seed_units or {}
    slot_map: dict = {}

    # Forwards: seed observed trios, then assign the remaining slots (both share the pure engine).
    fwd_by_side = J.seed_and_assign_forwards([p for p in players if p.pos_group == "F"],
                                             units.get("F3", []), effpos, hand, CFG)
    for side, col_slots in _FWD_COLS.items():
        for slot, p in zip(col_slots, fwd_by_side[side]):
            _place(p, slot, slot_map)

    # Defensemen: seed observed pairs, then handedness (left-shot -> LD, right-shot -> RD); a full side
    # overflows to the other side (a 5th lefty plays his off side) — all handled inside the shared engine,
    # which returns <= 3 per side. A hole (pool short a side) stays empty -> replacement in _iced_lineup.
    def_by_side = J.seed_and_assign_defense([p for p in players if p.pos_group == "D"],
                                            units.get("D2", []), hand, CFG, n_pairs=len(_DEF_COLS["L"]))
    for side, col_slots in _DEF_COLS.items():
        for slot, p in zip(col_slots, def_by_side[side]):
            _place(p, slot, slot_map)

    for slot, p in zip(("G1", "G2"), sorted((p for p in players if p.pos_group == "G"),
                                            key=war, reverse=True)):
        _place(p, slot, slot_map)

    used = {p.player_id for p in slot_map.values() if p.player_id}
    scratch = [p for p in players if p.player_id and p.player_id not in used]
    return slot_map, scratch


def _ice_from_slots(roster, inp):
    """Honor the user's explicit slot assignments (the canvas IS the lineup). Returns slot->PlayerProj
    (empty iced slots become replacement holes) and the scratch pool (slots outside the iced set)."""
    from models_ml import project_roster_forecast as J
    CFG = J.CFG
    slot_map: dict = {}
    scratch = []
    seen = set()
    for entry in roster:
        pid = entry.get("player_id")
        slot = entry.get("slot")
        if pid is None or pid in seen:
            continue
        seen.add(pid)
        pos = (inp["index"].get(int(pid), {}) or {}).get("position")
        if slot in ALL_SLOTS:
            pos = pos or _slot_default_pos(slot)
            p = _proj(pid, pos, inp)
            p.slot = slot
            slot_map[slot] = p
        else:  # scratch / bench
            scratch.append(_proj(pid, pos or "F", inp))
    return slot_map, scratch


def _slot_default_pos(slot: str) -> str:
    if slot.startswith("G"):
        return "G"
    if slot.startswith("D"):
        return "D"
    return {"L": "L", "C": "C", "R": "R"}.get(slot[-1], "C")


def _replacement(slot, CFG):
    from models_ml.project_roster_forecast import PlayerProj
    pg = _pos_group_of_slot(slot)
    return PlayerProj(None, None, pg if pg != "F" else "C", pg, pg == "G",
                      CFG["REPLACEMENT_WAR"], CFG["REPLACEMENT_WAR"], 0.0, False,
                      replacement=True, slot=slot)


def _iced_lineup(slot_map, CFG):
    """The 19 iced PlayerProjs in slot order, holes filled with replacement (the slot always exists)."""
    return [slot_map.get(s) or _replacement(s, CFG) for s in ICED_SLOTS]


@lru_cache(maxsize=1)
def _latest_line_features():
    """Each player's MOST RECENT line-fit profile across seasons (line_member_features), indexed by
    player_id. Using the latest available profile — rather than forcing one season — means a line still
    grades when a member lacks the current-season profile (an injured/low-TOI veteran like an out-most-
    of-the-year captain, or a rookie who only has the current season). Normal lines are unchanged: for a
    player with a current profile, latest == current."""
    from models_ml import bq as mlbq
    df = mlbq.query_df(
        f"SELECT * FROM `{mlbq.project()}.nhl_models.line_member_features` ORDER BY season")
    df = df.groupby("player_id", as_index=False).tail(1)   # latest season row per player
    return df.set_index("player_id", drop=False)


def _fit_from_rows(mem_df, line_type):
    """Grade + xGF% for a line from its members' feature rows (any seasons). One model predict, no
    SHAP/explanation — the lightweight path used by both the display grades and the suggestions."""
    import pandas as pd
    from models_ml import score_line as SL, linefit_features as lf
    art = SL._load()
    feat = lf.aggregate_line(mem_df, line_type)
    X = pd.DataFrame([[feat.get(c, 0.0) for c in art["feature_columns"]]],
                     columns=art["feature_columns"]).astype("float64").fillna(0.0)
    xgf = float(art["boosters"]["xgf_pct"].predict(X)[0])
    return {"grade": SL._grade(xgf), "xgf_pct": round(xgf, 4)}


def _line_grade(ids, season=None):
    """Per-line cold-start fit grade (Lineup Lab), from each member's most-recent profile. Returns None
    only if a member has NO line-fit profile in any season (never a fabricated grade)."""
    keys = [int(i) for i in ids]
    line_type = "F3" if len(keys) == 3 else ("D2" if len(keys) == 2 else None)
    if line_type is None:
        return None
    idx = _latest_line_features()
    if any(k not in idx.index for k in keys):
        return None
    try:
        return _fit_from_rows(idx.loc[keys], line_type)
    except Exception:  # noqa: BLE001 — degrade gracefully, never a fabricated grade
        return None


def _player_out(p, base_ids, ages, hand):
    on_new_team = bool(p.player_id) and p.player_id not in base_ids
    return {
        "player_id": p.player_id, "name": p.name, "pos": p.position, "slot": p.slot,
        "shoots": hand.get(p.player_id) if p.player_id else None,
        "age": ages.get(p.player_id) if p.player_id else None,
        "base_war": round(p.base_war, 3), "projected_war": round(p.projected_war, 3),
        "war_sd": round(p.war_sd, 3), "no_track_record": p.no_track_record,
        "on_new_team": on_new_team, "replacement": p.replacement,
    }


def _components(iced, comp):
    """Additive 4-bucket partition of the iced roster's REALIZED value (WAR units), shared scale:
      finishing      = goals above expected (finishing talent)
      special_teams  = pp + pk + penalties + faceoffs
      goaltending    = the starting goalie's realized WAR
      play_5v5       = the 5v5 process residual (skater total minus finishing and special teams)
    So play_5v5 + finishing + special_teams + goaltending == the roster's total realized WAR."""
    from models_ml import project_roster_forecast as J
    gpw = J.CFG["GOALS_PER_WIN"]
    skaters = [p for p in iced if p.player_id and p.pos_group != "G"]
    goalies = [p for p in iced if p.player_id and p.pos_group == "G"]
    g = lambda p, k: (comp.get(p.player_id, {}) or {}).get(k, 0.0)  # noqa: E731
    fin = sum(g(p, "goals") - g(p, "ixg") for p in skaters) / gpw
    st = sum(g(p, "pp") + g(p, "pk") + g(p, "penalty") + g(p, "faceoff") for p in skaters) / gpw
    skater_total = sum(g(p, "ev_offense") + g(p, "ev_defense") + g(p, "pp") + g(p, "pk")
                       + g(p, "penalty") + g(p, "faceoff") for p in skaters) / gpw
    goaltending = sum(g(p, "goalie_war") for p in goalies)
    return {"play_5v5": round(skater_total - fin - st, 3), "finishing": round(fin, 3),
            "special_teams": round(st, 3), "goaltending": round(goaltending, 3)}


def _evaluate_roster(slot_map, base_iced, base_ids, inp, season):
    """Core: from a slot->PlayerProj map, build the iced lineup, widen arrival bands, score the lines,
    and return the projection payload (absolute rating + points + band, components, positional values,
    chemistry, per-line grades). base_iced/base_ids are the team's real roster for arrival detection
    and the chemistry reference."""
    from models_ml import project_roster_forecast as J
    CFG = J.CFG
    SLOPE = CFG["FORECAST_POINTS"]["slope"]
    W2R = CFG["WAR_TO_RATING"]
    iced = _iced_lineup(slot_map, CFG)

    total_war = J.lineup_value(iced, "projected_war")
    chem_delta = J._chemistry_delta(base_iced, iced, season)
    chem = J.chemistry_adjustment(chem_delta, CFG)
    rating = J.absolute_rating(total_war, chem, CFG)

    iced_ids = {p.player_id for p in iced if p.player_id}
    arrivals = len(iced_ids - base_ids)
    departures = len(base_ids - iced_ids)

    # ABSOLUTE band (wide, honest — the noisy full-season figure): the iced players' calibrated
    # projection sds quadratured to points, scaled by the fitted team multiplier kappa (the common
    # season-ahead error does not shrink with sqrt(N)), plus the irreducible 82-game luck floor.
    # Calibrated so a 1-sigma interval covers ~68% of real team-seasons (Handoff 12).
    talent_quad_war = math.sqrt(sum(p.war_sd ** 2 for p in iced))
    abs_band = math.sqrt((CFG["ROSTER_BUILDER_BAND_KAPPA"] * SLOPE * W2R * talent_quad_war) ** 2
                         + CFG["SEASON_LUCK_FLOOR_PTS"] ** 2)
    proj_points = J.rating_to_points(rating, CFG)

    ages, hand = inp["ages"], inp["hand"]
    # Per-line fit grades (display) — absolute line quality, separate from the chemistry nudge.
    fwd_lines = []
    for line in FWD_LINES:
        members = [slot_map[s] for s in line if s in slot_map and slot_map[s].player_id]
        fwd_lines.append({
            "slots": [_player_out(slot_map.get(s) or _replacement(s, CFG), base_ids, ages, hand) for s in line],
            "fit": _line_grade([p.player_id for p in members], season) if len(members) >= 2 else None,
        })
    def_pairs = []
    for pair in DEF_PAIRS:
        members = [slot_map[s] for s in pair if s in slot_map and slot_map[s].player_id]
        def_pairs.append({
            "slots": [_player_out(slot_map.get(s) or _replacement(s, CFG), base_ids, ages, hand) for s in pair],
            "fit": _line_grade([p.player_id for p in members], season) if len(members) == 2 else None,
        })

    iced_f = [p for p in iced if p.pos_group == "F"]
    iced_d = [p for p in iced if p.pos_group == "D"]
    iced_g = [p for p in iced if p.pos_group == "G"]
    return {
        "rating_abs": round(rating, 4),
        "projected_points": proj_points,
        "points_low": max(0, round(proj_points - abs_band)),
        "points_high": min(164, round(proj_points + abs_band)),
        "abs_band": round(abs_band, 2),
        "band_goals": round(abs_band / SLOPE, 4),
        "total_lineup_war": round(total_war, 3),
        "chemistry_adj": round(chem, 4),
        "components": _components(iced, inp["components"]),
        "positional": {
            "forward_war": round(J.lineup_value(iced_f, "projected_war"), 3),
            "defense_war": round(J.lineup_value(iced_d, "projected_war"), 3),
            "goaltending_war": round(J.lineup_value(iced_g, "projected_war"), 3),
        },
        "forward_lines": fwd_lines,
        "defense_pairs": def_pairs,
        "goalies": {
            "starter": _player_out(slot_map.get("G1") or _replacement("G1", CFG), base_ids, ages, hand),
            "backup": _player_out(slot_map["G2"], base_ids, ages, hand) if "G2" in slot_map else None,
        },
        "arrivals": arrivals, "departures": departures,
        "_rating": rating,  # internal, popped before serialization
        "_iced": iced,      # internal, for the delta band (changed players)
    }


@lru_cache(maxsize=2)
def _league_projections(base_season: str) -> dict:
    """player_id -> PlayerProj for every current-roster player, projected forward — the candidate pool
    for slot suggestions. Cached per base season (the live tool calls this on every picker open)."""
    inp = _forecast_inputs(base_season)
    out = {}
    for pid, meta in inp["index"].items():
        out[pid] = _proj(pid, meta.get("position", "F"), inp)
    return out


@lru_cache(maxsize=2)
def _tier_bounds(base_season: str) -> dict:
    """Projected-WAR boundaries between depth-chart tiers, from the league distribution: forwards split
    into 4 lines (32 teams x 3 = 96 per line), defensemen into 3 pairs (64 per pair). Used to keep a
    slot's suggestions caliber-appropriate — a top-line star is never offered for a 4th-line hole."""
    proj = _league_projections(base_season)
    f = sorted((p.projected_war for p in proj.values() if p.pos_group == "F"), reverse=True)
    d = sorted((p.projected_war for p in proj.values() if p.pos_group == "D"), reverse=True)
    at = lambda lst, r: lst[min(r, len(lst) - 1)] if lst else 0.0  # noqa: E731
    return {"F": [at(f, 96), at(f, 192), at(f, 288)], "D": [at(d, 64), at(d, 128)]}


def _slot_tier(slot: str) -> tuple[str, int]:
    if slot.startswith("F"):
        return "F", int(slot[1])
    if slot.startswith("D"):
        return "D", int(slot[1])
    return "G", 1


def _caliber_window(pos_group: str, line_idx: int, bounds: dict, slack: float = 0.35) -> tuple[float, float]:
    """[floor, ceiling] projected WAR for a line/pair. The top line/pair is unbounded above (stars
    welcome); every lower tier is capped just above the boundary with the tier above it, so a player is
    only suggested where his caliber actually fits."""
    b = bounds[pos_group]
    ceil = float("inf") if line_idx == 1 else b[line_idx - 2] + slack
    floor = (b[line_idx - 1] - slack) if (line_idx - 1) < len(b) else -1.0
    return floor, ceil


def _suggest_out(p, inp, fit) -> dict:
    meta = inp["index"].get(p.player_id, {}) or {}
    return {
        "player_id": p.player_id, "name": p.name, "pos": p.position,
        "team_id": meta.get("team_id"), "team_abbrev": _abbrev(meta.get("team_id")),
        "headshot_url": meta.get("headshot"),
        "projected_war": round(p.projected_war, 3), "war_sd": round(p.war_sd, 3),
        "grade": (fit or {}).get("grade"), "xgf_pct": (fit or {}).get("xgf_pct"),
    }


SUGGEST_POOL = 40          # candidates (by caliber) scored for line fit per slot — bounds latency
GRADE_RANK = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}   # fit grade -> sort bucket (unscored = 0)


def _batch_line_fit(candidate_ids, linemate_ids, season=None):
    """Cold-start line-fit GRADE + xGF% for many candidates at once: one vectorized model predict over
    the whole candidate pool (no per-candidate SHAP/explanation), so we can rank by FIT first. Uses each
    player's most-recent profile (see _latest_line_features), so a linemate/candidate missing the current
    season still scores. Returns {candidate_id: (grade, xgf_pct)}; players with no profile are omitted."""
    import pandas as pd
    from models_ml import score_line as SL, linefit_features as lf
    n = len(linemate_ids) + 1
    line_type = "F3" if n == 3 else ("D2" if n == 2 else None)
    if line_type is None:
        return {}
    idx = _latest_line_features()
    if any(int(i) not in idx.index for i in linemate_ids):
        return {}
    lm_rows = idx.loc[[int(i) for i in linemate_ids]]
    art = SL._load(); fcols = art["feature_columns"]
    rows, ids = [], []
    for cid in candidate_ids:
        if int(cid) not in idx.index:
            continue
        feat = lf.aggregate_line(pd.concat([idx.loc[[int(cid)]], lm_rows]), line_type)
        rows.append([feat.get(c, 0.0) for c in fcols]); ids.append(int(cid))
    if not rows:
        return {}
    X = pd.DataFrame(rows, columns=fcols).astype("float64").fillna(0.0)
    preds = art["boosters"]["xgf_pct"].predict(X)
    return {cid: (SL._grade(float(x)), float(x)) for cid, x in zip(ids, preds)}


def roster_slot_suggestions(team_id: int, slot: str, roster: Optional[list[dict]] = None,
                            season: Optional[str] = None, top_n: int = 9) -> dict:
    """Line-aware 'great fit' suggestions for one slot. Caliber is tiered to the slot's line/pair (no
    star on a bottom line); when the line already has members, candidates are ranked by the cold-start
    line fit (score_line xGF) with those linemates, else by projected value within the tier. Reads only."""
    base_season = season or J_latest_completed()
    inp = _forecast_inputs(base_season)
    proj = _league_projections(base_season)
    pos_group, line_idx = _slot_tier(slot)

    placed_ids = {int(e["player_id"]) for e in (roster or []) if e.get("player_id") is not None}
    slot_to_pid = {e.get("slot"): int(e["player_id"]) for e in (roster or [])
                   if e.get("slot") and e.get("player_id") is not None}
    if pos_group == "F":
        line_slots = [f"F{line_idx}{w}" for w in ("L", "C", "R")]
    elif pos_group == "D":
        line_slots = [f"D{line_idx}{s}" for s in ("L", "R")]
    else:
        line_slots = []
    linemate_ids = [slot_to_pid[s] for s in line_slots if s != slot and s in slot_to_pid]

    if pos_group == "G":
        cands = sorted((p for pid, p in proj.items() if p.pos_group == "G" and pid not in placed_ids),
                       key=lambda p: p.projected_war, reverse=True)[:top_n]
        return {"slot": slot, "suggestions": [_suggest_out(p, inp, None) for p in cands]}

    # Respect the slot's exact position, using the EFFECTIVE position (what a player actually plays):
    # a center slot suggests centers, a wing slot that side's wings, a D slot that handedness side
    # (LD = left-shot). A listed-LW who takes center draws (effective C) is offered for C slots; an
    # F_FLEX forward (no strong faceoff signal) matches ANY forward slot. Cross-position is wrong.
    target = slot[-1]   # 'L' / 'C' / 'R' for F, 'L' / 'R' for D
    hand = inp["hand"]
    effpos = inp.get("effpos", {})

    def _pos_ok(p):
        if pos_group == "F":
            ep = _effective_fwd_pos(p.player_id, p.position, effpos)
            return ep == target or ep == "F_FLEX"
        if pos_group == "D":
            return hand.get(p.player_id, target) == target   # unknown-hand D matches either side
        return True

    floor, ceil = _caliber_window(pos_group, line_idx, _tier_bounds(base_season))
    pool = [p for pid, p in proj.items() if p.pos_group == pos_group and _pos_ok(p) and pid not in placed_ids
            and p.player_id and floor <= p.projected_war <= ceil]
    pool.sort(key=lambda p: p.projected_war, reverse=True)
    pool = pool[:SUGGEST_POOL]   # caliber-bounded candidate pool to line-fit score

    if linemate_ids:
        # Rank by FIT GRADE first, then by skill (projected WAR) within a grade — so a strong-fit
        # player outranks a higher-skill but worse-fit one, but among equal-fit players the more
        # skilled shows first. (A,A,B,C with skills 4,5,3,1 -> the two A's and the B lead.)
        fits = _batch_line_fit([p.player_id for p in pool], linemate_ids, base_season)
        ranked = sorted(
            pool,
            key=lambda p: (GRADE_RANK.get((fits.get(p.player_id) or (None, None))[0], 0), p.projected_war),
            reverse=True)
        out = []
        for p in ranked[:top_n]:
            g, x = fits.get(p.player_id, (None, None))
            out.append(_suggest_out(p, inp, {"grade": g, "xgf_pct": x} if g else None))
        return {"slot": slot, "suggestions": out}
    return {"slot": slot, "suggestions": [_suggest_out(p, inp, None) for p in pool[:top_n]]}


def J_latest_completed() -> str:
    from models_ml import bq, project_roster_forecast as J
    return J.latest_completed_season(bq)


def roster_evaluate(team_id: int, roster: Optional[list[dict]] = None, optimize: bool = False,
                    season: Optional[str] = None) -> dict:
    """Evaluate a user-built roster for `team_id`. roster = [{player_id, slot}] (slot in the F/D/G
    scheme); None or optimize=True auto-builds the optimal lineup from the placed pool (or the team's
    current roster when nothing is placed). Returns the points-led projection with the DELTA vs the
    team's real roster as the headline (absolute points secondary, banded). Reads only."""
    from models_ml import bq, project_roster_forecast as J
    CFG = J.CFG
    base_season = season or J.latest_completed_season(bq)
    inp = _forecast_inputs(base_season)

    # Baseline: the team's CURRENT roster, auto-optimized — the reference the delta is measured against.
    base_members = _team_current_members(team_id, base_season)
    if not base_members:
        raise ValueError(f"no current roster for team {team_id}")
    seed_units = _seed_units(team_id, base_season)   # observed 5v5 units for deployment-aware seeding
    base_players = [_proj(m["player_id"], m["position"], inp) for m in base_members]
    base_slotmap, _ = _ice_from_pool(base_players, inp, seed_units)
    base_iced = _iced_lineup(base_slotmap, CFG)
    base_ids = {m["player_id"] for m in base_members}
    base_total = J.lineup_value(base_iced, "projected_war")
    base_rating = J.absolute_rating(base_total, 0.0, CFG)  # baseline is its own reference (chem delta 0)
    base_points = J.rating_to_points(base_rating, CFG)

    # The built roster. roster is None -> the canvas mirrors the real roster (never a cold empty state);
    # roster == [] is an explicitly emptied canvas (all replacement holes), NOT the baseline.
    if optimize:
        pool_src = roster if roster is not None else [{"player_id": m["player_id"]} for m in base_members]
        pool = [_proj(e["player_id"], (inp["index"].get(int(e["player_id"]), {}) or {}).get("position", "F"), inp)
                for e in pool_src if e.get("player_id") is not None]
        built_slotmap, scratch = _ice_from_pool(pool, inp, seed_units)
    elif roster is not None:
        built_slotmap, scratch = _ice_from_slots(roster, inp)
    else:
        built_slotmap, scratch = base_slotmap, []

    payload = _evaluate_roster(built_slotmap, base_iced, base_ids, inp, base_season)
    built_R_bu = payload.pop("_rating")   # R_bottomup(built) — the parts-sum rating
    built_iced = payload.pop("_iced")
    SLOPE = CFG["FORECAST_POINTS"]["slope"]; W2R = CFG["WAR_TO_RATING"]

    # HYBRID (Handoff 13): anchor on the team's MEASURED predictive rating, use player projections only
    # for the change vs the real roster, and fade to pure bottom-up as the roster turns over.
    #   projected_rating = R_bottomup(built) + w * (R_measured - R_bottomup(actual))
    # base_rating here is R_bottomup(actual). The offset is the coaching/system/integration the parts-sum
    # can't see; w (retained value share) fades it as players are swapped out. No changes -> w=1 ->
    # projected_rating == R_measured (the baseline IS the team's measured level). Fully hypothetical ->
    # w=0 -> pure bottom-up. The math degrades automatically; no special-casing.
    r_measured = _team_predictive_base(team_id, base_season)
    if r_measured is None:
        r_measured = base_rating   # no rating history -> pure bottom-up (offset 0)
    offset = r_measured - base_rating

    # w is MINUTES-weighted (projected ice time), so the team-system offset fades with how much of the
    # roster's ICE TIME turns over, not its value — a single swap keeps ~95% of minutes (system intact),
    # a full rebuild -> 0. Players absent from the projection table get a depth-minutes default.
    toi_of = lambda pid: (inp["proj"].get(pid, {}) or {}).get("toi", 600.0)  # noqa: E731
    base_min = {p.player_id: toi_of(p.player_id) for p in base_iced if p.player_id}
    built_ids = {p.player_id for p in built_iced if p.player_id}
    denom = sum(base_min.values()) or 1.0
    w = max(0.0, min(1.0, sum(m for pid, m in base_min.items() if pid in built_ids) / denom))

    projected_rating = built_R_bu + w * offset
    projected_points = J.rating_to_points(projected_rating, CFG)
    baseline_points = J.rating_to_points(r_measured, CFG)   # the w=1 baseline = team's measured level
    points_delta = round(SLOPE * (projected_rating - r_measured), 1)

    # ABSOLUTE band (context, wide): strength uncertainty interpolated anchor<->bottom-up by w, in
    # quadrature with the irreducible luck floor. Calibrated to ~68% coverage on real team-seasons (w=1).
    strength_sd = w * CFG["ROSTER_BUILDER_STRENGTH_ANCHOR"] + (1.0 - w) * CFG["ROSTER_BUILDER_STRENGTH_BU"]
    abs_band = math.sqrt(strength_sd ** 2 + CFG["SEASON_LUCK_FLOOR_PTS"] ** 2)
    payload["projected_points"] = projected_points
    payload["points_low"] = max(0, round(projected_points - abs_band))
    payload["points_high"] = min(164, round(projected_points + abs_band))
    payload["abs_band"] = round(abs_band, 2)
    payload["band_goals"] = round(abs_band / SLOPE, 4)
    payload["rating_abs"] = round(projected_rating, 4)

    # DELTA band (tight headline): only the CHANGED players' projection sds (stayers cancel exactly),
    # plus a small term from the team-effect offset fading as the roster turns over. No luck floor — a
    # talent comparison, not a realized-season bet. A single swap is ~+/-1 point.
    base_by_id = {p.player_id: p for p in base_iced if p.player_id}
    built_by_id = {p.player_id: p for p in built_iced if p.player_id}
    changed = set(base_by_id) ^ set(built_by_id)
    changed_var = sum((base_by_id.get(pid) or built_by_id.get(pid)).war_sd ** 2 for pid in changed)
    changed_talent_pts = SLOPE * W2R * math.sqrt(changed_var)
    offset_fade_pts = CFG["ROSTER_BUILDER_DELTA_OFFSET_W"] * (1.0 - w) * abs(offset) * SLOPE
    delta_band = math.sqrt(changed_talent_pts ** 2 + offset_fade_pts ** 2)

    payload["points_delta"] = points_delta
    payload["delta_band"] = round(delta_band, 2)
    payload["delta_low"] = round(points_delta - delta_band, 1)
    payload["delta_high"] = round(points_delta + delta_band, 1)
    payload["baseline_points"] = baseline_points
    payload["baseline_rating"] = round(r_measured, 4)
    payload["r_bottomup"] = round(built_R_bu, 4)
    payload["retained_share"] = round(w, 3)
    payload["base_season"] = base_season
    payload["team_id"] = team_id
    payload["scratches"] = [_player_out(p, base_ids, inp["ages"], inp["hand"]) for p in scratch]
    payload["negligible"] = abs(projected_rating - r_measured) < 1e-6 and not (roster and not optimize)
    return payload
