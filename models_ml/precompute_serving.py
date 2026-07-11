"""Precompute the serving tables the API's tool/search endpoints need.

These are the inputs that let the model-scoring + search endpoints run entirely on the local
DuckDB serving file (no BigQuery on the request path). All are pure functions of last night's
data, so they're materialized nightly into nhl_models / nhl_mart and ride the export.

Builds (idempotent, WRITE_TRUNCATE):
  dim_current_roster        search picker: current-season players, name + team + archetype.
  line_member_features      one row/(player,season) of line-fit model features (the expensive
                            build, so live line-fit just looks them up + runs the artifact).
  team_handedness           per (team,season,pos_group) L/R 5v5 TOI — player-fit positional gate.
  team_current_lines        per team: top forward trios / D pairs over last 10 games — for
                            /teams/{id}/lines and the player-fit line dimension.
  serving_game_skater_box   flattened per-game skater box lines — /games/{id}/skater-impact
                            (replaces the raw_boxscores nested UNNEST on the request path).

Run in COMPUTE mode (reads BigQuery): SERVING_BACKEND is forced to bigquery here.

    python -m models_ml.precompute_serving --all
    python -m models_ml.precompute_serving --only dim_current_roster,team_handedness
"""
from __future__ import annotations

import argparse
import os

# This job is a COMPUTE step: always read BigQuery, never the serving file.
os.environ["SERVING_BACKEND"] = "bigquery"

import pandas as pd  # noqa: E402

from models_ml import bq, config, linefit_features as lf  # noqa: E402

RECENT_SEASONS = 3


def _recent_seasons(p: str, n: int = RECENT_SEASONS) -> list[str]:
    df = bq.query_df(
        f"SELECT DISTINCT season FROM `{p}.nhl_staging.stg_games` ORDER BY season DESC LIMIT {n}"
    )
    return df["season"].tolist()


def _latest_season(p: str) -> str:
    return _recent_seasons(p, 1)[0]


# --------------------------------------------------------------------------- #
def build_dim_current_roster(p: str) -> pd.DataFrame:
    # The search picker's current-season player->team map. Membership is resolved LIVE-first
    # (int_player_current_team: live roster, else latest game), so an offseason trade shows the
    # NEW team before the player dresses. Identity (name/pos/headshot) prefers the live roster too.
    # Universe = current-season game players UNION anyone on a live roster, so a just-added player
    # is searchable. team_id is the resolved current team; performance is unaffected (membership
    # != performance — value/archetype lag until he plays for the new club).
    season = _latest_season(p)
    sql = f"""
    WITH latest AS (  -- current-season game-derived identity + team (historical path)
        SELECT player_id, team_id, headshot_url, first_name, last_name, position_code
        FROM (
            SELECT player_id, team_id, headshot_url, first_name, last_name, position_code,
                   ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY game_id DESC) AS rn
            FROM `{p}.nhl_staging.stg_rosters`
            WHERE season = '{season}' AND SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01','02','03')
        ) WHERE rn = 1
    ),
    live AS (  -- live-roster identity (preferred for trade-ins)
        SELECT player_id, first_name, last_name, full_name, position_code, headshot_url
        FROM `{p}.nhl_staging.stg_roster_current`
    ),
    res AS (SELECT player_id, current_team_id FROM `{p}.nhl_staging.int_player_current_team`),
    universe AS (
        SELECT player_id FROM latest
        UNION DISTINCT
        SELECT player_id FROM live
    ),
    tm AS (SELECT team_id, ANY_VALUE(team_abbrev) abbrev
           FROM `{p}.nhl_mart.mart_team_game_stats` WHERE season = '{season}' GROUP BY team_id)
    SELECT u.player_id,
           '{season}' AS season,
           COALESCE(live.first_name, latest.first_name) AS first_name,
           COALESCE(live.last_name, latest.last_name) AS last_name,
           COALESCE(live.full_name, latest.first_name || ' ' || latest.last_name) AS full_name,
           LOWER(COALESCE(live.full_name, latest.first_name || ' ' || latest.last_name)) AS name_lower,
           COALESCE(res.current_team_id, latest.team_id) AS team_id,
           tm.abbrev AS team_abbrev,
           COALESCE(live.position_code, latest.position_code) AS position_code,
           COALESCE(live.headshot_url, latest.headshot_url) AS headshot_url,
           a.primary_archetype AS primary_archetype
    FROM universe u
    LEFT JOIN live ON live.player_id = u.player_id
    LEFT JOIN latest ON latest.player_id = u.player_id
    LEFT JOIN res ON res.player_id = u.player_id
    LEFT JOIN tm ON COALESCE(res.current_team_id, latest.team_id) = tm.team_id
    LEFT JOIN `{p}.nhl_models.player_archetypes` a
      ON a.player_id = u.player_id AND a.season = '{season}'
    """
    return bq.query_df(sql)


def build_team_handedness(p: str) -> pd.DataFrame:
    seasons = ", ".join(f"'{s}'" for s in _recent_seasons(p))
    sql = f"""
    WITH toi AS (
        SELECT s.player_id, s.team_id, s.season,
               SUM(IF(c.strength_state='5v5', s.segment_duration, 0)) toi5,
               CASE WHEN s.position_code='D' THEN 'D' ELSE 'F' END pg
        FROM `{p}.nhl_staging.int_shift_segments` s
        JOIN `{p}.nhl_staging.int_segment_context` c USING (game_id, segment_index)
        WHERE s.is_goalie=0 AND s.season IN ({seasons})
          AND SUBSTR(CAST(s.game_id AS STRING),5,2) IN ('02','03')
        GROUP BY 1,2,3,5
    )
    SELECT t.team_id, t.season, t.pg AS pos_group,
           SUM(IF(b.shoots='L', t.toi5, 0)) AS l_toi,
           SUM(IF(b.shoots='R', t.toi5, 0)) AS r_toi
    FROM toi t JOIN `{p}.nhl_staging.stg_player_bio` b USING (player_id)
    WHERE b.shoots IN ('L','R')
    GROUP BY 1,2,3
    """
    return bq.query_df(sql)


def build_team_current_lines(p: str) -> pd.DataFrame:
    """Top 4 forward trios + top 3 defense pairs per team over its last 10 games (current season).

    Mirrors the backend current_lines() shape; precomputed so /teams/{id}/lines and the
    player-fit line dimension read it instead of scanning int_shift_segments at request time.
    """
    season = _latest_season(p)
    teams = bq.query_df(
        f"""SELECT DISTINCT team_id FROM `{p}.nhl_mart.mart_team_game_stats`
            WHERE season = '{season}'"""
    )["team_id"].astype(int).tolist()
    frames = []
    for team in teams:
        sql = f"""
        WITH g AS (
            SELECT game_id, game_date FROM `{p}.nhl_staging.stg_boxscores`
            WHERE (home_team_id={team} OR away_team_id={team}) AND season='{season}'
              AND SUBSTR(CAST(game_id AS STRING),5,2) IN ('02','03')
            ORDER BY game_date DESC LIMIT 10),
        seg5 AS (
            SELECT s.game_id, s.segment_index, s.player_id, s.position_code, c.segment_duration
            FROM `{p}.nhl_staging.int_shift_segments` s
            JOIN `{p}.nhl_staging.int_segment_context` c USING (game_id, segment_index)
            JOIN g USING (game_id)
            WHERE s.team_id={team} AND s.is_goalie=0 AND c.strength_state='5v5'),
        fwd AS (
            SELECT game_id, segment_index, ANY_VALUE(segment_duration) dur,
                   ARRAY_AGG(player_id ORDER BY player_id) members, COUNT(*) n
            FROM seg5 WHERE position_code IN ('C','L','R') GROUP BY 1,2),
        def AS (
            SELECT game_id, segment_index, ANY_VALUE(segment_duration) dur,
                   ARRAY_AGG(player_id ORDER BY player_id) members, COUNT(*) n
            FROM seg5 WHERE position_code='D' GROUP BY 1,2),
        trio AS (
            SELECT 'F3' line_type,
                   (SELECT STRING_AGG(CAST(m AS STRING), '-' ORDER BY m) FROM UNNEST(members) m) line_key,
                   SUM(dur)/60.0 minutes
            FROM fwd WHERE n=3 GROUP BY line_key ORDER BY minutes DESC LIMIT 4),
        pair AS (
            SELECT 'D2' line_type,
                   (SELECT STRING_AGG(CAST(m AS STRING), '-' ORDER BY m) FROM UNNEST(members) m) line_key,
                   SUM(dur)/60.0 minutes
            FROM def WHERE n=2 GROUP BY line_key ORDER BY minutes DESC LIMIT 3)
        SELECT {team} AS team_id, '{season}' AS season, line_type, line_key, minutes,
               ROW_NUMBER() OVER (PARTITION BY line_type ORDER BY minutes DESC) AS rnk
        FROM (SELECT * FROM trio UNION ALL SELECT * FROM pair)
        """
        df = bq.query_df(sql)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["team_id", "season", "line_type", "line_key", "minutes", "rnk"])


def build_serving_game_skater_box(p: str) -> pd.DataFrame:
    """Flattened per-game skater box lines for recent seasons (replaces raw_boxscores UNNEST)."""
    seasons_start = int(_recent_seasons(p)[-1][:4])
    sql = f"""
    WITH box AS (
        SELECT game_id,
               homeTeam.id AS home_id, homeTeam.abbrev AS home_abbrev,
               awayTeam.id AS away_id, awayTeam.abbrev AS away_abbrev,
               playerByGameStats AS pg
        FROM `{p}.nhl_raw.raw_boxscores`
        WHERE CAST(SUBSTR(CAST(game_id AS STRING),1,4) AS INT64) >= {seasons_start}
    )
    SELECT game_id, 'home' AS side, home_abbrev AS team_abbrev, sk.playerId AS player_id,
           sk.name.default AS player_name, sk.position, sk.toi,
           sk.goals, sk.assists, sk.points, sk.sog AS shots
    FROM box, UNNEST(pg.homeTeam.forwards) sk
    UNION ALL
    SELECT game_id, 'home', home_abbrev, sk.playerId, sk.name.default, sk.position, sk.toi,
           sk.goals, sk.assists, sk.points, sk.sog
    FROM box, UNNEST(pg.homeTeam.defense) sk
    UNION ALL
    SELECT game_id, 'away', away_abbrev, sk.playerId, sk.name.default, sk.position, sk.toi,
           sk.goals, sk.assists, sk.points, sk.sog
    FROM box, UNNEST(pg.awayTeam.forwards) sk
    UNION ALL
    SELECT game_id, 'away', away_abbrev, sk.playerId, sk.name.default, sk.position, sk.toi,
           sk.goals, sk.assists, sk.points, sk.sog
    FROM box, UNNEST(pg.awayTeam.defense) sk
    """
    return bq.query_df(sql)


def build_player_situation_toi(p: str) -> pd.DataFrame:
    """Per (player, season, situation) 5v5/PP/PK/all TOI minutes + games, from the shift segments.

    PP/PK are decided by comparing the player's team skater count to the opponent's in each
    segment. This is the per-situation TOI denominator the marts lack, so /players/{id}/situational
    can report real per-60 rates by situation. Recent seasons (matching the situational mart).
    """
    seasons = ", ".join(f"'{s}'" for s in _recent_seasons(p))
    sql = f"""
    WITH seg AS (
        SELECT s.player_id, s.season, s.game_id, s.segment_duration, s.team_skater_count,
               CASE WHEN s.team_id = c.home_team_id THEN c.away_skaters ELSE c.home_skaters END AS opp_sk,
               c.strength_state
        FROM `{p}.nhl_staging.int_shift_segments` s
        JOIN `{p}.nhl_staging.int_segment_context` c USING (game_id, segment_index)
        WHERE s.is_goalie = 0 AND s.season IN ({seasons})
          AND SUBSTR(CAST(s.game_id AS STRING),5,2) IN ('02','03')
    ),
    long AS (
        SELECT player_id, season, game_id, segment_duration, 'all' AS situation FROM seg
        UNION ALL SELECT player_id, season, game_id, segment_duration, '5v5' FROM seg WHERE strength_state='5v5'
        UNION ALL SELECT player_id, season, game_id, segment_duration, 'pp'  FROM seg WHERE team_skater_count > opp_sk
        UNION ALL SELECT player_id, season, game_id, segment_duration, 'pk'  FROM seg WHERE team_skater_count < opp_sk
    )
    SELECT player_id, season, situation,
           SUM(segment_duration)/60.0 AS toi_minutes,
           COUNT(DISTINCT game_id) AS games
    FROM long GROUP BY 1,2,3
    """
    return bq.query_df(sql)


def build_player_effective_position(p: str) -> pd.DataFrame:
    """One row per player: the position he ACTUALLY plays, from faceoff volume (not the listed feed).

    The NHL roster feed lists a nominal position (J.T. Compher as LW) that is often not where a player
    lines up. Faceoff volume is the cleanest C/W deployment signal — a center takes draws every shift,
    a winger almost never. Over the last EFFECTIVE_POSITION['FO_WINDOW_SEASONS'] seasons (regular +
    playoffs, GP-weighted), classify each forward by faceoffs-per-game into C / L / R / F_FLEX and mark
    `locked` when the evidence is strong. Defensemen pass through unchanged (effective = listed, locked).
    Skaters with no faceoff rows are simply ABSENT (the builder then falls back to the listed position).

    Reads nhl_staging.stg_statsrest_faceoffs (season-level splits) + stg_player_bio (shoots, for the
    listed-C winger side rule). Built in BigQuery compute mode, exported to DuckDB nightly.
    """
    ep = config.EFFECTIVE_POSITION
    n_win = int(ep["FO_WINDOW_SEASONS"])
    center, winger, min_gp = float(ep["FO_CENTER_PER_GP"]), float(ep["FO_WINGER_PER_GP"]), int(ep["FO_MIN_GP"])
    sql = f"""
    WITH win AS (  -- the last N seasons present in the faceoff source (GP-weighted window)
        SELECT DISTINCT season_id FROM `{p}.nhl_staging.stg_statsrest_faceoffs`
        ORDER BY season_id DESC LIMIT {n_win}
    ),
    agg AS (
        SELECT f.player_id,
               ANY_VALUE(f.player_name) AS player_name,
               -- latest listed position across the window (regular season preferred within a season)
               ARRAY_AGG(f.position_code ORDER BY f.season_id DESC, f.game_type ASC LIMIT 1)[OFFSET(0)]
                   AS listed_position,
               SUM(f.total_faceoffs) AS total_faceoffs,
               SUM(f.games_played) AS gp_window
        FROM `{p}.nhl_staging.stg_statsrest_faceoffs` f
        JOIN win USING (season_id)
        WHERE f.game_type IN (2, 3) AND f.player_id IS NOT NULL
        GROUP BY f.player_id
    ),
    bio AS (SELECT player_id, shoots FROM `{p}.nhl_staging.stg_player_bio`),
    c AS (
        SELECT a.player_id, a.player_name, a.listed_position, a.gp_window,
               SAFE_DIVIDE(a.total_faceoffs, NULLIF(a.gp_window, 0)) AS fo_per_gp,
               b.shoots
        FROM agg a LEFT JOIN bio b USING (player_id)
    )
    SELECT
        player_id, player_name, listed_position, gp_window,
        ROUND(fo_per_gp, 3) AS fo_per_gp,
        CASE
            WHEN listed_position = 'D' THEN 'D'
            WHEN listed_position = 'G' THEN 'G'
            WHEN gp_window >= {min_gp} AND fo_per_gp >= {center} THEN 'C'
            WHEN gp_window >= {min_gp} AND fo_per_gp <= {winger} THEN
                CASE WHEN listed_position IN ('L', 'R') THEN listed_position
                     WHEN shoots = 'L' THEN 'L'
                     WHEN shoots = 'R' THEN 'R'
                     ELSE 'F_FLEX' END
            ELSE 'F_FLEX'
        END AS effective_position,
        CASE
            WHEN listed_position IN ('D', 'G') THEN TRUE
            WHEN gp_window >= {min_gp} AND fo_per_gp >= {center} THEN TRUE
            WHEN gp_window >= {min_gp} AND fo_per_gp <= {winger}
                 AND (listed_position IN ('L', 'R') OR shoots IN ('L', 'R')) THEN TRUE
            ELSE FALSE
        END AS locked
    FROM c
    """
    return bq.query_df(sql)


def build_line_member_features(p: str) -> pd.DataFrame:
    """One row per (player_id, season) of line-fit model features for recent seasons."""
    seasons = _recent_seasons(p)
    df = lf.build_member_features(seasons).reset_index()
    # Drop columns that don't round-trip cleanly / aren't needed by the scorer.
    return df


BUILDERS = {
    "dim_current_roster": (build_dim_current_roster, "nhl_models"),
    "line_member_features": (build_line_member_features, "nhl_models"),
    "team_handedness": (build_team_handedness, "nhl_models"),
    "team_current_lines": (build_team_current_lines, "nhl_models"),
    "serving_game_skater_box": (build_serving_game_skater_box, "nhl_models"),
    "player_situation_toi": (build_player_situation_toi, "nhl_models"),
    "player_effective_position": (build_player_effective_position, "nhl_models"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="build every serving table")
    ap.add_argument("--only", help="comma-separated subset of table names")
    ap.add_argument("--dry-run", action="store_true", help="build the df, print shape, do not write")
    args = ap.parse_args()

    names = (list(BUILDERS) if args.all
             else [s.strip() for s in args.only.split(",")] if args.only else [])
    if not names:
        ap.error("pass --all or --only <names>")

    p = bq.project()
    for name in names:
        if name not in BUILDERS:
            print(f"  ! unknown table {name}; known: {list(BUILDERS)}")
            continue
        builder, dataset = BUILDERS[name]
        print(f"building {name} ...", flush=True)
        df = builder(p)
        print(f"  {name}: {len(df):,} rows x {len(df.columns)} cols", flush=True)
        if args.dry_run:
            continue
        bq.write_df(df, name)  # writes to nhl_models (config.MODELS_DATASET)
        print(f"  wrote nhl_models.{name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
