"""Stage 2.2 — player buildup signatures (shares with counts), from the Stage 0 API + Stage 2.1
descriptors. Two universes per player-season, kept SEPARATE (never merged silently):
  involvement='pbp'     : goals where the player is the pbp scorer or assister.
  involvement='carrier' : goals where he is the reconstructed primary carrier on a CLEAN clip.
Gate: no per-player signature below MIN_INVOLVED involved goals (the player page renders nothing below).
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import config, fuse, stage2_descriptors as D

SIGNATURES = config.PARQUET / "player_signatures.parquet"
MIN_INVOLVED = 15
NET_FRONT_FT = 10.0
FIELDS = ["finisher_share", "feeder_share", "carrier_share", "rush_share",
          "royal_road_share", "entry_driver_share", "net_front_share"]


NETFRONT_CACHE = config.PARQUET / "release_netfront.parquet"


def _release_netfront(refresh: bool = False) -> pl.DataFrame:
    """Per (goal, player): is the player within 10 ft of crease center at release? (release_entities_json).
    Parsing 26k JSON snapshots is the one slow step, so it is cached to parquet and reused."""
    if NETFRONT_CACHE.exists() and not refresh:
        return pl.read_parquet(NETFRONT_CACHE)
    g = pl.read_parquet(fuse.FUSED).select("game_id", "event_id", "attack_sign", "release_entities_json")
    rows = []
    for r in g.iter_rows(named=True):
        sign = r["attack_sign"]
        if sign is None or not r["release_entities_json"]:
            continue
        cx = 89.0 * sign
        for e in json.loads(r["release_entities_json"]):
            if e.get("is_puck") or e.get("id") in (None, 1):
                continue
            d = float(np.hypot(e["x"] - cx, e["y"]))
            rows.append({"game_id": r["game_id"], "event_id": r["event_id"], "player_id": e["id"],
                         "net_front": d <= NET_FRONT_FT})
    out = pl.DataFrame(rows)
    config.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(NETFRONT_CACHE)
    return out


def _passed_to_scorer() -> pl.DataFrame:
    """Per (goal, passer): did this player complete a reconstructed pass to the recorded scorer?"""
    ev = pl.read_parquet(fuse.EVENTS).filter(pl.col("event_type") == "pass")
    sc = pl.read_parquet(fuse.FUSED).select("game_id", "event_id", "scorer_id")
    p = ev.join(sc, on=["game_id", "event_id"], how="left").filter(pl.col("receiver_id") == pl.col("scorer_id"))
    return p.select("game_id", "event_id", player_id="passer_id").unique().with_columns(passed_to_scorer=pl.lit(True))


def _involved(desc: pl.DataFrame) -> pl.DataFrame:
    """Long table: one row per (player, goal, involvement)."""
    pbp = pl.concat([
        desc.select("game_id", "event_id", "season", player_id=pl.col("scorer_id")),
        desc.select("game_id", "event_id", "season", player_id=pl.col("assist1_id")),
        desc.select("game_id", "event_id", "season", player_id=pl.col("assist2_id")),
    ]).drop_nulls("player_id").with_columns(involvement=pl.lit("pbp")).unique(["game_id", "event_id", "player_id"])
    carrier = (desc.filter(pl.col("is_clean") & pl.col("primary_carrier_id").is_not_null())
               .select("game_id", "event_id", "season", player_id="primary_carrier_id")
               .with_columns(involvement=pl.lit("carrier")))
    return pl.concat([pbp, carrier])


FLAG_COLS = ["is_finisher", "is_feeder", "is_carrier", "is_rush", "is_royal", "is_entry_driver", "is_net_front"]


def flags() -> pl.DataFrame:
    """Per (player, goal, involvement): the boolean signature flags + game_date (for reliability)."""
    desc = pl.read_parquet(D.DESCRIPTORS)
    nf = _release_netfront()
    p2s = _passed_to_scorer()
    inv = _involved(desc)
    gd = pl.read_parquet(fuse.FUSED).select("game_id", "event_id", "game_date")
    ctx = desc.select("game_id", "event_id", "scorer_id", "assist1_id", "assist2_id", "primary_carrier_id",
                      "entry_carrier_id", "rush_flag", "pass_pattern")
    x = (inv.join(ctx, on=["game_id", "event_id"], how="left")
         .join(nf, on=["game_id", "event_id", "player_id"], how="left")
         .join(p2s, on=["game_id", "event_id", "player_id"], how="left")
         .join(gd, on=["game_id", "event_id"], how="left"))
    return x.with_columns(
        is_finisher=pl.col("scorer_id") == pl.col("player_id"),
        is_carrier=pl.col("primary_carrier_id") == pl.col("player_id"),
        is_entry_driver=pl.col("entry_carrier_id") == pl.col("player_id"),
        is_rush=pl.col("rush_flag"),
        is_royal=pl.col("pass_pattern") == "cross_slot",
        is_net_front=pl.col("net_front").fill_null(False),
        is_feeder=((pl.col("assist1_id") == pl.col("player_id")) | (pl.col("assist2_id") == pl.col("player_id")))
        & pl.col("passed_to_scorer").fill_null(False))


def build() -> dict:
    x = flags()
    sig = (x.group_by("player_id", "season", "involvement").agg(
        n_involved=pl.len(),
        finisher_share=pl.col("is_finisher").mean(), feeder_share=pl.col("is_feeder").mean(),
        carrier_share=pl.col("is_carrier").mean(), rush_share=pl.col("is_rush").mean(),
        royal_road_share=pl.col("is_royal").mean(), entry_driver_share=pl.col("is_entry_driver").mean(),
        net_front_share=pl.col("is_net_front").mean(),
        finisher_n=pl.col("is_finisher").sum(), feeder_n=pl.col("is_feeder").sum(),
        carrier_n=pl.col("is_carrier").sum(), rush_n=pl.col("is_rush").sum(),
        royal_road_n=pl.col("is_royal").sum(), entry_driver_n=pl.col("is_entry_driver").sum(),
        net_front_n=pl.col("is_net_front").sum()))
    # pooled (all seasons) rows too
    pooled = (x.group_by("player_id", "involvement").agg(
        n_involved=pl.len(),
        finisher_share=pl.col("is_finisher").mean(), feeder_share=pl.col("is_feeder").mean(),
        carrier_share=pl.col("is_carrier").mean(), rush_share=pl.col("is_rush").mean(),
        royal_road_share=pl.col("is_royal").mean(), entry_driver_share=pl.col("is_entry_driver").mean(),
        net_front_share=pl.col("is_net_front").mean(),
        finisher_n=pl.col("is_finisher").sum(), feeder_n=pl.col("is_feeder").sum(),
        carrier_n=pl.col("is_carrier").sum(), rush_n=pl.col("is_rush").sum(),
        royal_road_n=pl.col("is_royal").sum(), entry_driver_n=pl.col("is_entry_driver").sum(),
        net_front_n=pl.col("is_net_front").sum()).with_columns(season=pl.lit("pooled")))
    allsig = pl.concat([sig, pooled], how="diagonal").with_columns(gate_ok=pl.col("n_involved") >= MIN_INVOLVED)
    config.PARQUET.mkdir(parents=True, exist_ok=True)
    allsig.write_parquet(SIGNATURES)

    pl_pooled = allsig.filter((pl.col("season") == "pooled") & (pl.col("involvement") == "pbp"))
    return {"rows": allsig.height, "pbp_players_pooled": pl_pooled["player_id"].n_unique(),
            "pbp_gated": int(pl_pooled["gate_ok"].sum()),
            "carrier_gated": int(allsig.filter((pl.col("season") == "pooled") & (pl.col("involvement") == "carrier"))["gate_ok"].sum())}


if __name__ == "__main__":
    r = build()
    print(f"signatures: {r['rows']:,} rows | pbp pooled players {r['pbp_players_pooled']} "
          f"({r['pbp_gated']} clear >=15) | carrier pooled gated {r['carrier_gated']}")
