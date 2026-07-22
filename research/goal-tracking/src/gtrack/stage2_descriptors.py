"""Stage 2.1 — per-goal buildup descriptors, from the Stage 0 API only (fused_goals + goal_events).

AMENDMENT 2026-07-14: carrier-dependent fields use TRACKED clips (a AND b); counts are on all clips;
"release" means effective_release = release_frame if flight_detected else arrival_frame (release_source
stored). Each column is flagged tracked-only vs all-clips in COLUMN_UNIVERSE / the report.

Note (forced by the Stage-0 API surface): separation_gain is defined in the spec against nd_scorer at
2.0 s prior, but Stage 0 persisted only nd_scorer_rel (release) and nd_scorer_1s (1.0 s prior). With
"reads the Stage 0 API only" binding, separation_gain uses the 1.0 s window; a 2.0 s version would need
a Stage 0 field addendum. This is flagged, not applied silently.
"""
from __future__ import annotations

import polars as pl

from . import config, fuse

DESCRIPTORS = config.PARQUET / "goal_descriptors.parquet"

FINAL_CARRIER_FRAMES = 80        # 8.0 s
RUSH_PASS_FRAMES = 30            # 3.0 s of entry
CROSS_SLOT_DY = 15.0
BLUE = config.BLUE_LINE
GOAL_LINE = 89.0

COLUMN_UNIVERSE = {
    "pass_count": "all", "entry_type": "all", "entry_carrier_id": "all", "time_in_zone": "all",
    "pass_pattern": "tracked", "primary_carrier_id": "tracked", "separation_gain": "tracked",
}


def _passes_ranked(events: pl.DataFrame, eff: pl.DataFrame) -> pl.DataFrame:
    """Completed passes before effective_release, ranked latest-first per goal (rank 1 = last pass)."""
    p = (events.filter(pl.col("event_type") == "pass")
         .join(eff, on=["game_id", "event_id"], how="inner")
         .filter(pl.col("end_frame") <= pl.col("eff_rel"))
         .with_columns(rk=pl.col("end_frame").rank("ordinal", descending=True).over("game_id", "event_id")))
    return p


def _pattern(last: pl.DataFrame) -> pl.DataFrame:
    a = pl.col("attack_sign")
    sxa, exa = pl.col("start_x") * a, pl.col("end_x") * a
    sy, ey = pl.col("start_y"), pl.col("end_y")
    behind = sxa > GOAL_LINE
    cross = ((sy.sign() != ey.sign()) & ((ey - sy).abs() >= CROSS_SLOT_DY)
             & sxa.is_between(BLUE, GOAL_LINE) & exa.is_between(BLUE, GOAL_LINE))
    point = sxa.is_between(BLUE - 10, BLUE + 10)
    # low_to_high_to_net: prior pass moved outward to ~blue line, this one returns netward
    l2h = (pl.col("prior_exa").is_not_null() & (pl.col("prior_exa") < pl.col("prior_sxa"))
           & pl.col("prior_exa").is_between(BLUE - 10, BLUE + 15) & (exa > sxa))
    rush = pl.col("rush_flag") & (pl.col("end_frame") - pl.col("entry_frame")).is_between(0, RUSH_PASS_FRAMES)
    return last.with_columns(pass_pattern=pl.when(behind).then(pl.lit("behind_net_feed"))
                             .when(cross).then(pl.lit("cross_slot"))
                             .when(point).then(pl.lit("point_to_net"))
                             .when(l2h).then(pl.lit("low_to_high_to_net"))
                             .when(rush).then(pl.lit("rush_sequence"))
                             .otherwise(pl.lit("other")))


def build() -> dict:
    g = pl.read_parquet(fuse.FUSED)
    ev = pl.read_parquet(fuse.EVENTS)
    g = g.with_columns(
        eff_rel=pl.when(pl.col("flight_detected")).then(pl.col("release_frame")).otherwise(pl.col("arrival_frame")),
        release_source=pl.when(pl.col("flight_detected")).then(pl.lit("flight")).otherwise(pl.lit("arrival")),
        tracked=pl.col("q_a") & pl.col("q_b"),
        is_clean=pl.col("q_a") & pl.col("q_b") & pl.col("q_d"))       # Stage-0 CLEAN = a AND b AND d
    eff = g.select("game_id", "event_id", "eff_rel", "attack_sign", "rush_flag", "entry_frame")

    # last + prior completed pass before effective_release
    pr = _passes_ranked(ev, eff)
    last = pr.filter(pl.col("rk") == 1).join(g.select("game_id", "event_id", "attack_sign", "rush_flag", "entry_frame"),
                                             on=["game_id", "event_id"], how="left")
    prior = pr.filter(pl.col("rk") == 2).select(
        "game_id", "event_id", prior_sxa=pl.col("start_x") * pl.col("attack_sign"),
        prior_exa=pl.col("end_x") * pl.col("attack_sign"))
    last = last.join(prior, on=["game_id", "event_id"], how="left")
    last = _pattern(last).select("game_id", "event_id", "pass_pattern",
                                 last_pass_from=pl.col("passer_id"), last_pass_to=pl.col("receiver_id"))

    # primary carrier in the final 8.0 s (segment overlap)
    seg = (ev.filter(pl.col("event_type") == "segment")
           .join(eff.select("game_id", "event_id", "eff_rel"), on=["game_id", "event_id"], how="inner")
           .with_columns(lo=(pl.col("eff_rel") - FINAL_CARRIER_FRAMES),
                         ov=(pl.min_horizontal("end_frame", "eff_rel")
                             - pl.max_horizontal("start_frame", pl.col("eff_rel") - FINAL_CARRIER_FRAMES) + 1))
           .filter(pl.col("ov") > 0))
    prim = (seg.group_by("game_id", "event_id", "player_id").agg(t=pl.col("ov").sum())
            .sort("t", descending=True).group_by("game_id", "event_id").first()
            .select("game_id", "event_id", primary_carrier_id=pl.col("player_id")))

    out = (g.select("game_id", "event_id", "season", "scorer_id", "assist1_id", "assist2_id",
                    "scoring_team_id", "tracked", "release_source", "n_passes", "entry_type",
                    "entry_carrier_id", "entry_to_goal", "rush_flag", "is_clean", "nd_scorer_rel",
                    "nd_scorer_1s")
           .rename({"n_passes": "pass_count", "entry_to_goal": "time_in_zone"})
           .with_columns(separation_gain=pl.col("nd_scorer_rel") - pl.col("nd_scorer_1s"))
           .join(last, on=["game_id", "event_id"], how="left")
           .join(prim, on=["game_id", "event_id"], how="left"))
    # carrier-dependent fields only valid on TRACKED clips
    out = out.with_columns(
        pass_pattern=pl.when(pl.col("tracked")).then(pl.col("pass_pattern")).otherwise(None),
        primary_carrier_id=pl.when(pl.col("tracked")).then(pl.col("primary_carrier_id")).otherwise(None),
        separation_gain=pl.when(pl.col("tracked")).then(pl.col("separation_gain")).otherwise(None))
    config.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(DESCRIPTORS)

    tr = out.filter(pl.col("tracked"))
    return {"n": out.height, "tracked": tr.height,
            "pattern_rates": tr.group_by("pass_pattern").len().sort("len", descending=True).to_dicts(),
            "entry_rates": out.group_by("entry_type").len().sort("len", descending=True).to_dicts(),
            "sep_gain_median": float(tr["separation_gain"].drop_nulls().median()),
            "primary_carrier_cov": int(tr["primary_carrier_id"].drop_nulls().len())}


if __name__ == "__main__":
    r = build()
    print(f"descriptors: {r['n']:,} goals ({r['tracked']:,} tracked)")
    print("pass_pattern (tracked):", {d["pass_pattern"]: d["len"] for d in r["pattern_rates"]})
    print("entry_type (all):", {d["entry_type"]: d["len"] for d in r["entry_rates"]})
    print(f"separation_gain median (1.0s window): {r['sep_gain_median']:.2f} ft | primary_carrier cov {r['primary_carrier_cov']:,}")
