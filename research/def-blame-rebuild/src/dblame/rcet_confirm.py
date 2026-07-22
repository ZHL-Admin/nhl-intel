"""RCET spec — the three READ-ONLY confirms before any norm is built. Reports three facts and STOPS.
NO norm, NO trajectory, NO deviation. (a) qualifying entry-captured count; (b) does non-goal rush tracking
exist (+ norm comparison only if it does); (c) middle-lane-entry and drop-pass (carrier-change) frequency.
"""
from __future__ import annotations

import polars as pl

from . import config as C
from .data import universe
from . import rushdef as RD

CARRY = {"carried", "passed"}
MID_LANE_FT = 10.0   # |carrier entry lateral| below this = middle-lane (side-ambiguous), for reporting only


def _qualifying() -> pl.DataFrame:
    """5v5 + entry_type in {carried,passed} + entry captured (clean_entry) + rushdef bucket == EVEN."""
    u = universe()
    base = u.filter(pl.col("entry_type").is_in(list(CARRY)) & pl.col("clean_entry"))
    bucket = RD._threat_count(base.select("game_id", "event_id"))
    even = bucket.filter(pl.col("bucket") == "EVEN").select("game_id", "event_id")
    return base.join(even, on=["game_id", "event_id"], how="inner")


def confirm_a() -> dict:
    u = universe()
    n_5v5 = u.height
    et = u["entry_type"].value_counts().sort("count", descending=True).to_dicts()
    controlled = u.filter(pl.col("entry_type").is_in(list(CARRY)))
    controlled_clean = controlled.filter(pl.col("clean_entry"))
    q = _qualifying()
    return {"n_5v5_tracked_goals": n_5v5, "entry_type_breakdown": et,
            "controlled_carried_or_passed": controlled.height,
            "controlled_AND_entry_captured": controlled_clean.height,
            "qualifying_final_EVEN_bucket": q.height}


def confirm_b() -> dict:
    """Does tracking exist for NON-goal rushes? The frames parquets are keyed by (game_id, event_id). Every
    tracked event must be checked against the FULL GOAL table (GT_FUSED = ALL goals, pre-5v5-filter), NOT the
    5v5 universe — else non-5v5 goals (PP/OT/empty-net) masquerade as 'non-goal'. A truly non-goal tracked event
    is one absent from GT_FUSED entirely."""
    goal_keys = universe().select("game_id", "event_id").unique()               # 5v5 goals (the Phase-1 corpus)
    all_goal_keys = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id").unique()  # ALL goals, any strength
    frame_keys = []
    for fname in ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]:
        frame_keys.append(pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id"]).unique())
    frames = pl.concat(frame_keys).unique()
    non_5v5_goal_tracked = frames.join(goal_keys, on=["game_id", "event_id"], how="anti")
    truly_non_goal = frames.join(all_goal_keys, on=["game_id", "event_id"], how="anti")  # absent from EVERY goal
    return {"tracked_frame_events_total": frames.height, "all_goal_events(GT_FUSED)": all_goal_keys.height,
            "5v5_goal_universe": goal_keys.height,
            "tracked_but_not_5v5_goal": non_5v5_goal_tracked.height,
            "truly_non_goal_tracked": truly_non_goal.height,
            "non_goal_rush_tracking_exists": truly_non_goal.height > 0}


def confirm_c() -> dict:
    """On the qualifying set: (i) middle-lane entry frequency = |carrier lateral at entry| < MID_LANE_FT;
    (ii) drop-pass / carrier-change frequency = goals with >=1 attacking pass in [entry_frame, goal_frame]."""
    q = _qualifying().select("game_id", "event_id", "season", "entry_frame", "goal_frame", "attack_sign",
                             "scoring_team_id", "defending_team_id", "home_goalie_id", "away_goalie_id")
    # (i) carrier lateral at entry: the puck's lateral at the entry frame (carrier ~ puck at entry)
    lat_rows = []
    for season, fname in zip(C.SEASONS, ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]):
        gs = q.filter(pl.col("season") == season)
        if not gs.height:
            continue
        gids = gs["game_id"].unique().to_list()
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "y_std"])
              .filter(pl.col("is_puck") & pl.col("game_id").is_in(gids))
              .join(gs.select("game_id", "event_id", "entry_frame", "attack_sign"), on=["game_id", "event_id"], how="inner")
              .filter(pl.col("frame_index") == pl.col("entry_frame"))
              .with_columns(lat=pl.col("attack_sign") * pl.col("y_std")))
        lat_rows.append(fr.select("game_id", "event_id", "lat"))
    lat = pl.concat(lat_rows) if lat_rows else pl.DataFrame(schema={"game_id": pl.Int64, "event_id": pl.Int64, "lat": pl.Float64})
    n_lat = lat.height
    mid = int((lat["lat"].abs() < MID_LANE_FT).sum()) if n_lat else 0
    lat_q = {k: round(float(lat["lat"].abs().quantile(v)), 1) for k, v in
             {"p25": .25, "p50": .5, "p75": .75}.items()} if n_lat else {}
    # (ii) attacking passes in the entry->shot window
    ps = pl.read_parquet(C.PARQUET / "passes.parquet")
    pj = (ps.join(q.select("game_id", "event_id", "entry_frame", "goal_frame"), on=["game_id", "event_id"], how="inner")
          .filter((pl.col("start_frame") >= pl.col("entry_frame")) & (pl.col("start_frame") <= pl.col("goal_frame"))))
    pass_per_goal = pj.group_by("game_id", "event_id").agg(n_pass=pl.len())
    with_pass = pass_per_goal.filter(pl.col("n_pass") >= 1).height
    return {"n_with_entry_lateral": n_lat, "middle_lane_entries(|lat|<10ft)": mid,
            "middle_lane_frac": round(mid / n_lat, 3) if n_lat else None, "abs_entry_lateral_iqr": lat_q,
            "goals_qualifying": q.height, "goals_with_>=1_attacking_pass_entry_to_shot": with_pass,
            "carrier_change_frac": round(with_pass / q.height, 3) if q.height else None}


def run() -> dict:
    a, b, c = confirm_a(), confirm_b(), confirm_c()
    L = []; W = L.append
    W("# RCET — three read-only confirms (no norm, no trajectory, no deviation)\n")
    W("## (a) Qualifying entry-captured count\n")
    W(f"- 5v5 tracked goals: **{a['n_5v5_tracked_goals']:,}**")
    W(f"- entry_type breakdown: {a['entry_type_breakdown']}")
    W(f"- entry_type ∈ {{carried, passed}}: **{a['controlled_carried_or_passed']:,}**")
    W(f"- + entry captured (clean_entry): **{a['controlled_AND_entry_captured']:,}**")
    W(f"- + rushdef bucket = EVEN → **QUALIFYING = {a['qualifying_final_EVEN_bucket']:,}**\n")
    W("## (b) Non-goal rush tracking?\n")
    W(f"- tracked-frame events total: {b['tracked_frame_events_total']:,} · ALL goals (GT_FUSED, any strength): "
      f"{b['all_goal_events(GT_FUSED)']:,} · 5v5-goal universe: {b['5v5_goal_universe']:,}")
    W(f"- tracked-but-not-5v5-goal: {b['tracked_but_not_5v5_goal']:,} (these are NON-5v5 GOALS — PP/OT/empty-net — "
      "not non-goal events)")
    W(f"- **truly non-goal tracked events (absent from EVERY goal): {b['truly_non_goal_tracked']:,}** → non-goal "
      f"rush tracking exists: **{b['non_goal_rush_tracking_exists']}**")
    W("  (False → no all-rush norm to compare; the norm-comparison arm of confirm (b) is **N/A**. Per the Issue-1 "
      "ruling: note the mild selection honestly and proceed — the goals-only norm is still meaningful because most "
      "goal-rushes are ordinary rush-defense.)\n")
    W("## (c) Middle-lane entry + drop-pass (carrier-change) frequency (on the qualifying set)\n")
    W(f"- goals with a measurable entry-lateral: {c['n_with_entry_lateral']:,}")
    W(f"- **middle-lane entries (|carrier lateral at entry| < 10 ft): {c['middle_lane_entries(|lat|<10ft)']:,} "
      f"({c['middle_lane_frac']})** · |entry lateral| IQR: {c['abs_entry_lateral_iqr']}")
    W(f"- **carrier change (≥1 attacking pass, entry→shot): {c['goals_with_>=1_attacking_pass_entry_to_shot']:,} "
      f"of {c['goals_qualifying']:,} ({c['carrier_change_frac']})**\n")
    W("## STOP — three facts reported. No norm, no trajectory, no deviation computed.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "rcet_confirms.md").write_text("\n".join(L))
    return {"a": a, "b": b, "c": c}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
