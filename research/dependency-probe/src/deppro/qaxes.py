"""Link Q (Round 2) — QUALITY / LOCATION / DECISION axes per (focal A, season, partner B), 5v5.

Buildable axes (Q5 icing and Q6 zone-exit DROPPED on the pre-build attribution/availability check:
the frozen events carry no stoppage `reason` and icing is team-only; there is no exit/entry/carry
event type, and recovering it needs timing-inference — forbidden by the Round-1 feeding lesson):

  Q1 shot quality:  xg_per_unb (mean shot_xg over UNBLOCKED attempts), on_goal_rate (on-target /
                    attempts), blocked_share, missed_share.
  Q2 location:      slot_share (<=25 ft / unblocked), mean_dist (unblocked).
  Q4 finishing:     shooting_pct (goals / on-target) — reported WITH the Q1 xg context.
  Q7 penalties:     pen_taken60, pen_drawn60 (recovered committed_by / drawn_by attribution).

Reuses the Round-1 stint/on-ice/time-join machinery (deppro.behavior). Every ratio carries its
absolute denominator; denominator traps are banned (thin-denominator axes are flagged, not ranked).
"""
from __future__ import annotations

import polars as pl

from . import config
from . import behavior as B

QDIR = config.PARQUET / "qaxes"
_CNT = ["dur", "n_att", "n_unb", "n_ongoal", "n_blk", "n_miss", "n_goal", "sum_xg", "n_slot",
        "sum_dist", "n_pt", "n_pd"]


def _q_actor_events(season: str) -> pl.DataFrame:
    """Located shot + penalty events with actor and per-shot xg/dist/slot. Shots -> shooter; penalties
    contribute to committed_by (taken) and drawn_by (drawn) as two actor rows."""
    ev = (pl.scan_parquet(config.ATLAS_PARQUET / "events.parquet")
          .filter((pl.col("season_label") == season) & pl.col("is_primary_scope")
                  & (pl.col("situation_code") == "1551")
                  & pl.col("type_desc_key").is_in(B.SHOT_TYPES + ["penalty"]))
          .select("game_id", "event_id", "event_second", "type_desc_key", "x_coord", "y_coord",
                  "shooting_player_id", "scoring_player_id").collect())
    xg = pl.read_parquet(config.ATLAS_PARQUET / "shot_xg.parquet", columns=["game_id", "event_id", "xg"])
    epl = pl.read_parquet(config.ENRICH_DIR / "event_players.parquet",
                          columns=["game_id", "event_id", "committed_by_player_id", "drawn_by_player_id"])
    ev = ev.join(xg, on=["game_id", "event_id"], how="left").join(epl, on=["game_id", "event_id"], how="left")
    ev = ev.with_columns(
        dist=((89 - pl.col("x_coord").abs()) ** 2 + pl.col("y_coord") ** 2).sqrt(),
        unblocked=pl.col("type_desc_key").is_in(["shot-on-goal", "missed-shot", "goal"]),
        ongoal=pl.col("type_desc_key").is_in(["shot-on-goal", "goal"]),
        is_shot=pl.col("type_desc_key").is_in(B.SHOT_TYPES),
        is_pen=(pl.col("type_desc_key") == "penalty"))
    # shot actor = shooter/scorer
    shots = ev.filter(pl.col("is_shot")).with_columns(
        actor=pl.when(pl.col("type_desc_key") == "goal").then(pl.col("scoring_player_id"))
        .otherwise(pl.col("shooting_player_id"))).filter(pl.col("actor").is_not_null())
    # penalty actors (two rows): committed_by (taken), drawn_by (drawn)
    pt = ev.filter(pl.col("is_pen") & pl.col("committed_by_player_id").is_not_null()).with_columns(
        actor=pl.col("committed_by_player_id"), pen=pl.lit("T"))
    pd = ev.filter(pl.col("is_pen") & pl.col("drawn_by_player_id").is_not_null()).with_columns(
        actor=pl.col("drawn_by_player_id"), pen=pl.lit("D"))
    cols = ["game_id", "event_second", "actor", "type_desc_key", "dist", "unblocked", "ongoal", "xg"]
    out = pl.concat([shots.select(cols).with_columns(pen=pl.lit(None, dtype=pl.Utf8)),
                     pt.select(cols + ["pen"]), pd.select(cols + ["pen"])], how="vertical_relaxed")
    return out


def build_qaxes(season: str, write: bool = True) -> pl.DataFrame:
    st = B._stints(season)
    ev = B._locate_in_stint(_q_actor_events(season), st)
    onice = B._onice(st)

    pse = ev.group_by("rid", pl.col("actor").alias("pid")).agg(
        n_att=(pl.col("type_desc_key").is_in(B.SHOT_TYPES)).sum(),
        n_unb=pl.col("unblocked").fill_null(False).sum(),
        n_ongoal=pl.col("ongoal").fill_null(False).sum(),
        n_blk=(pl.col("type_desc_key") == "blocked-shot").sum(),
        n_miss=(pl.col("type_desc_key") == "missed-shot").sum(),
        n_goal=(pl.col("type_desc_key") == "goal").sum(),
        sum_xg=pl.col("xg").filter(pl.col("unblocked").fill_null(False)).sum(),
        n_slot=(pl.col("unblocked").fill_null(False) & (pl.col("dist") <= 25)).sum(),
        sum_dist=pl.col("dist").filter(pl.col("unblocked").fill_null(False)).sum(),
        n_pt=(pl.col("pen") == "T").sum(), n_pd=(pl.col("pen") == "D").sum())
    af = (onice.join(pse, on=["rid", "pid"], how="left")
          .with_columns([pl.col(c).fill_null(0) for c in _CNT if c != "dur"]).rename({"pid": "A"}))
    partners = onice.select("rid", "side", B="pid")
    dp = af.join(partners, on=["rid", "side"], how="inner").filter(pl.col("A") != pl.col("B"))
    g = dp.group_by("A", "B", "game_id").agg([pl.col(c).sum() for c in _CNT])
    g = g.with_columns(half=(pl.col("game_id").rank("dense").over("A", "B") % 2))

    def roll(df, sfx):
        a = df.group_by("A", "B").agg([pl.col(c).sum().alias(f"{c}{sfx}") for c in _CNT])
        return _rates(a, sfx)
    agg = (roll(g, "").join(roll(g.filter(pl.col("half") == 1), "_odd"), on=["A", "B"], how="left")
           .join(roll(g.filter(pl.col("half") == 0), "_even"), on=["A", "B"], how="left")
           .rename({"dur": "shared_toi"}).with_columns(season_label=pl.lit(season)))
    if write:
        QDIR.mkdir(parents=True, exist_ok=True)
        agg.write_parquet(QDIR / f"{season.replace('-', '_')}.parquet")
    return agg


def _rates(a: pl.DataFrame, s: str) -> pl.DataFrame:
    unb = pl.col(f"n_unb{s}"); att = pl.col(f"n_att{s}"); og = pl.col(f"n_ongoal{s}")
    return a.with_columns(
        xg_per_unb=pl.when(unb > 0).then(pl.col(f"sum_xg{s}") / unb).otherwise(None),
        on_goal_rate=pl.when(att > 0).then(og / att).otherwise(None),
        blocked_share=pl.when(att > 0).then(pl.col(f"n_blk{s}") / att).otherwise(None),
        missed_share=pl.when(att > 0).then(pl.col(f"n_miss{s}") / att).otherwise(None),
        slot_share=pl.when(unb > 0).then(pl.col(f"n_slot{s}") / unb).otherwise(None),
        mean_dist=pl.when(unb > 0).then(pl.col(f"sum_dist{s}") / unb).otherwise(None),
        shooting_pct=pl.when(og > 0).then(pl.col(f"n_goal{s}") / og).otherwise(None),
        pen_taken60=pl.col(f"n_pt{s}") / pl.col(f"dur{s}") * 3600.0,
        pen_drawn60=pl.col(f"n_pd{s}") / pl.col(f"dur{s}") * 3600.0,
    ).rename({c: f"{c}{s}" for c in ["xg_per_unb", "on_goal_rate", "blocked_share", "missed_share",
                                     "slot_share", "mean_dist", "shooting_pct", "pen_taken60", "pen_drawn60"]})


# axes + the denominator they lean on (for the denominator-trap disclosure)
AXES = ["xg_per_unb", "on_goal_rate", "blocked_share", "missed_share", "slot_share", "mean_dist",
        "shooting_pct", "pen_taken60", "pen_drawn60"]
AXIS_DENOM = {"xg_per_unb": "n_unb", "on_goal_rate": "n_att", "blocked_share": "n_att",
              "missed_share": "n_att", "slot_share": "n_unb", "mean_dist": "n_unb",
              "shooting_pct": "n_ongoal", "pen_taken60": "shared_toi", "pen_drawn60": "shared_toi"}


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or config.SEASONS_PRIMARY:
        q = build_qaxes(s)
        print(f"{s}: (A,B) rows={q.height:,}", flush=True)
