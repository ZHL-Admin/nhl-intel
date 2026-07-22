"""Stage 0.2 — the fused goal table.

Builds data/parquet/fused_goals.parquet (one row per goal) and goal_events.parquet (one row per
reconstructed event per goal) over EVERY goal in the tracking views. Labels are the stg_play_by_play
anchor (LAW 2); tracking supplies context. Strength state is ice-derived from Atlas stints where a
stint covers the goal second, else the sprite situationCode (source_flag records which).

BigQuery reads are cached once to data/cache; ``build(from_cache=True)`` re-derives offline.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import bq, config, reconstruct as R

FUSED = config.PARQUET / "fused_goals.parquet"
EVENTS = config.PARQUET / "goal_events.parquet"

_FRAME_COLS = "game_id,event_id,frame_index,is_puck,player_id,team_id,x_std,y_std"


# ------------------------------------------------------------------ cached pulls
def pull_pbp() -> pl.DataFrame:
    return bq.cached_query("pbp_goals", f"""
        with fg as (select distinct game_id, event_id
                    from `{config.BQ_PROJECT}.{config.STAGING}.stg_ppt_tracking_frames`)
        select p.game_id, p.event_id, p.season, p.game_date, p.period_number, p.period_type,
               p.time_in_period, p.time_remaining, p.situation_code, p.home_team_defending_side,
               p.shot_type, p.x_coord, p.y_coord, p.scoring_player_id, p.assist1_player_id,
               p.assist2_player_id, p.goalie_in_net_id, p.event_owner_team_id
        from `{config.BQ_PROJECT}.{config.STAGING}.stg_play_by_play` p
        join fg using (game_id, event_id)
        where p.type_desc_key='goal'
    """)


def pull_goal_meta() -> pl.DataFrame:
    raw = bq.cached_query("goal_meta_raw", f"""
        select game_id, event_id, season, frame_count, goal_metadata
        from `{config.BQ_PROJECT}.{config.RAW}.raw_ppt_replay`
    """)
    is_home, sc, sht = [], [], []
    for md in raw["goal_metadata"].to_list():
        d = json.loads(md)
        is_home.append(bool(d.get("isHome")))
        sc.append(d.get("situationCode"))
        sht.append(d.get("shotType"))
    return raw.select("game_id", "event_id", "season", "frame_count").with_columns(
        is_home=pl.Series(is_home), md_situation_code=pl.Series(sc), md_shot_type=pl.Series(sht))


def pull_frames_season(season: str) -> pl.DataFrame:
    tag = season.replace("-", "_")
    return bq.cached_query(f"frames_{tag}", f"""
        select {_FRAME_COLS} from `{config.BQ_PROJECT}.{config.STAGING}.stg_ppt_tracking_frames`
        where season='{season}'
    """)


def load_stints() -> pl.DataFrame:
    return pl.read_parquet(config.STINTS, columns=[
        "game_id", "start_seconds", "end_seconds", "strength_state",
        "home_goalie_id", "away_goalie_id"])


# ------------------------------------------------------------------ helpers
def _abs_second(period_number: int, time_in_period: str) -> int:
    m, s = time_in_period.split(":")
    return (period_number - 1) * 1200 + int(m) * 60 + int(s)


def _clock_remaining(time_remaining: str | None) -> int | None:
    if not time_remaining:
        return None
    m, s = time_remaining.split(":")
    return int(m) * 60 + int(s)


def _sitcode_strength(code: str | None) -> str | None:
    # situationCode digits = [away_goalie, away_skaters, home_skaters, home_goalie]
    if not code or len(code) != 4 or not code.isdigit():
        return None
    return f"{code[2]}v{code[1]}"   # home skaters v away skaters


# ------------------------------------------------------------------ build
def build(from_cache: bool = True) -> dict:
    pbp = pull_pbp()
    meta = pull_goal_meta().select("game_id", "event_id", "is_home", "md_situation_code", "md_shot_type", "frame_count")
    stints = load_stints()

    goal_rows, event_rows = [], []
    n_stint = n_sitcode = 0

    for season in config.SEASONS:
        frames = pull_frames_season(season)
        # per-goal team ids present in the tracking (for home/away assignment)
        teams = (frames.filter(~pl.col("is_puck"))
                 .group_by("game_id", "event_id")
                 .agg(team_ids=pl.col("team_id").drop_nulls().unique()))
        team_map = {(r["game_id"], r["event_id"]): r["team_ids"] for r in teams.iter_rows(named=True)}
        parts = frames.partition_by("game_id", "event_id", as_dict=True, include_key=False)

        pbp_s = pbp.filter(pl.col("season") == season)
        pbp_map = {(r["game_id"], r["event_id"]): r for r in pbp_s.iter_rows(named=True)}
        meta_map = {(r["game_id"], r["event_id"]): r for r in meta.iter_rows(named=True)}
        st_s = stints.filter(pl.col("game_id").is_in(pbp_s["game_id"].unique().to_list()))
        st_by_game = {}
        for k, df in st_s.partition_by("game_id", as_dict=True, include_key=True).items():
            st_by_game[k[0] if isinstance(k, tuple) else k] = df

        for key, fr in parts.items():
            gid, eid = key
            pr = pbp_map.get((gid, eid))
            mt = meta_map.get((gid, eid), {})
            if pr is None:
                continue
            asec = _abs_second(pr["period_number"], pr["time_in_period"])
            # strength state + goalies from covering stint, else situationCode
            strength = None; src = "situationCode"; hg = ag = None
            gdf = st_by_game.get(gid)
            if gdf is not None:
                cover = gdf.filter((pl.col("start_seconds") <= asec) & (pl.col("end_seconds") > asec))
                if cover.height:
                    strength = cover["strength_state"][0]; src = "stint"
                    hg = cover["home_goalie_id"][0]; ag = cover["away_goalie_id"][0]
            if src == "stint":
                n_stint += 1
            else:
                strength = _sitcode_strength(pr["situation_code"]) or _sitcode_strength(mt.get("md_situation_code"))
                n_sitcode += 1

            # home/away team ids
            scoring_team = pr["event_owner_team_id"]
            tids = team_map.get((gid, eid), [])
            other = next((t for t in tids if t != scoring_team), None)
            is_home = bool(mt.get("is_home"))
            home_team = scoring_team if is_home else other
            away_team = other if is_home else scoring_team

            ctx = {"scorer_id": pr["scoring_player_id"], "scoring_team_id": scoring_team,
                   "def_goalie_id": pr["goalie_in_net_id"], "home_goalie_id": hg, "away_goalie_id": ag}
            o = R.reconstruct_goal(fr, ctx)

            goal_rows.append({
                "game_id": gid, "event_id": eid, "season": season, "game_date": pr["game_date"],
                "home_team_id": home_team, "away_team_id": away_team, "scoring_team_id": scoring_team,
                "period": pr["period_number"], "period_type": pr["period_type"],
                "game_clock_seconds": _clock_remaining(pr["time_remaining"]), "abs_game_seconds": asec,
                "strength_state": strength, "strength_source": src,
                "home_goalie_id": hg, "away_goalie_id": ag,
                # labels (authoritative, LAW 2)
                "scorer_id": pr["scoring_player_id"], "assist1_id": pr["assist1_player_id"],
                "assist2_id": pr["assist2_player_id"], "shot_type": pr["shot_type"],
                "pbp_shot_x": pr["x_coord"], "pbp_shot_y": pr["y_coord"], "goalie_id": pr["goalie_in_net_id"],
                # reconstruction anchors
                "n_frames": o["n_frames"], "attack_sign": o["attack_sign"], "smooth_method": o["smooth_method"],
                "reconstruction_ok": o["reconstruction_ok"],
                "release_frame": o["release_frame"], "release_x": o["release_x"], "release_y": o["release_y"],
                "arrival_frame": o["arrival_frame"], "arrival_x": o["arrival_x"], "arrival_y": o["arrival_y"],
                "release_arrival_gap": o["release_arrival_gap"], "flight_detected": o["flight_detected"],
                "n_segments": len(o["segments"]), "n_passes": o["n_passes"],
                "entry_type": (o["entry"] or {}).get("entry_type"), "entry_frame": (o["entry"] or {}).get("frame"),
                "entry_x": (o["entry"] or {}).get("x"), "entry_y": (o["entry"] or {}).get("y"),
                "entry_carrier_id": (o["entry"] or {}).get("carrier_id"),
                # derived geometry
                "ew_disp_2s": o["ew_disp_2s"], "screen_opp": o["screen_opp"], "screen_own": o["screen_own"],
                "screen_count_rel": o["screen_count_rel"], "nd_scorer_rel": o["nd_scorer_rel"],
                "nd_scorer_1s": o["nd_scorer_1s"], "goalie_depth_rel": o["goalie_depth_rel"],
                "goalie_lat_speed_rel": o["goalie_lat_speed_rel"], "scorer_speed_recep": o["scorer_speed_recep"],
                "scorer_speed_rel": o["scorer_speed_rel"], "release_clock": o["release_clock"],
                "entry_to_goal": o["entry_to_goal"], "rush_flag": o["rush_flag"],
                # quality inputs (scored in quality.py)
                "q_a": o["q_a"], "q_b": o["q_b"], "q_c_crowd": o["q_c_crowd"], "q_d": o["q_d"],
                # geometry snapshots (all entities at release & arrival)
                "release_entities_json": json.dumps(o["release_entities"]),
                "arrival_entities_json": json.dumps(o["arrival_entities"]),
            })

            for i, sg in enumerate(o["segments"]):
                event_rows.append({"game_id": gid, "event_id": eid, "season": season, "event_type": "segment",
                                   "event_index": i, "player_id": sg["player_id"], "team_id": sg["team_id"],
                                   "start_frame": sg["start_frame"], "end_frame": sg["end_frame"]})
            for i, pz in enumerate(o["passes"]):
                event_rows.append({"game_id": gid, "event_id": eid, "season": season, "event_type": "pass",
                                   "event_index": i, "passer_id": pz["passer_id"], "receiver_id": pz["receiver_id"],
                                   "team_id": pz["team_id"], "start_frame": pz["start_frame"], "end_frame": pz["end_frame"],
                                   "start_x": pz["start_x"], "start_y": pz["start_y"], "end_x": pz["end_x"], "end_y": pz["end_y"]})
            en = o["entry"]
            if en:
                event_rows.append({"game_id": gid, "event_id": eid, "season": season, "event_type": "entry",
                                   "player_id": en.get("carrier_id"), "frame": en.get("frame"),
                                   "x": en.get("x"), "y": en.get("y"), "entry_type": en.get("entry_type")})
            event_rows.append({"game_id": gid, "event_id": eid, "season": season, "event_type": "release",
                               "frame": o["release_frame"], "x": o["release_x"], "y": o["release_y"]})
            event_rows.append({"game_id": gid, "event_id": eid, "season": season, "event_type": "arrival",
                               "frame": o["arrival_frame"], "x": o["arrival_x"], "y": o["arrival_y"]})

    goals = pl.DataFrame(goal_rows)
    events = pl.DataFrame(event_rows)
    config.PARQUET.mkdir(parents=True, exist_ok=True)
    goals.write_parquet(FUSED)
    events.write_parquet(EVENTS)
    return {"n_goals": goals.height, "n_events": events.height,
            "strength_stint": n_stint, "strength_sitcode": n_sitcode,
            "by_season": goals.group_by("season").len().sort("season").to_dicts()}


if __name__ == "__main__":
    import time
    t = time.time()
    r = build()
    print(f"built {r['n_goals']:,} goals / {r['n_events']:,} events in {time.time()-t:.0f}s")
    print(f"strength: stint={r['strength_stint']:,} situationCode={r['strength_sitcode']:,}")
    print(r["by_season"])
