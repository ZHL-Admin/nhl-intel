"""Link 2 · EYE-TEST-FIRST aggregation and leaderboard (NO stability test yet).

Aggregates per-player, per-season defensive blame across the three tape-validated ledgers, reported SEPARATELY
(coverage / turnover / rush-defense rate) and COMBINED, over 5v5 goals-against, min 25 tracked 5v5 on-ice GA
(the blame-exposure denominator; ~1.75x that in actual 5v5 GA). Rate = blame carried / tracked on-ice GA — a
per-goal-against blame rate, so LOW is good (a shutdown defender carries little blame on the goals he is on
ice for). Auxiliary real-context columns: actual on-ice 5v5 GA, on-ice xGA/60, GA/60, 5v5 TOI tier.

Read against the owner's sharpened eye test: success is that the metric sorts by DEFENSIVE REPUTATION —
stay-at-home / shutdown types grade WELL (low blame); offense-first puck-movers grading middling-to-poor is
CORRECT and valuable (it is the thing reputation cannot otherwise reveal), not a failure. Elite ≠ top; the bar
is that known-defensive players are not clustered at the most-blamed end.
"""
from __future__ import annotations

import polars as pl

from . import config as C, events2 as E2
from .meta import load as load_meta
from .tracks import TRACKS

SEASONS = ["2024-25", "2025-26"]
MIN_GA = 25
OUT = C.REPORTS


def _bq():
    from google.cloud import bigquery
    return bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)


def aggregate() -> pl.DataFrame:
    bq = _bq()
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "season", "strength_state",
                                               "home_goalie_id", "away_goalie_id")
    smap = fused.select("game_id", "event_id", "season")

    # --- blame per (player, season, ledger) from the three-ledger record ---
    rec = pl.read_parquet(E2.REC).join(smap, on=["game_id", "event_id"], how="left")
    led = {"COVERAGE": "cov_blame", "TURNOVER": "turn_blame", "RUSH_DEFENSE": "rush_blame"}
    blame = (rec.with_columns(lk=pl.col("event_type").replace_strict(
                {"E1": "COVERAGE", "E2": "COVERAGE", "E3": "COVERAGE", "R3": "COVERAGE", "R6": "COVERAGE",
                 "FTA": "COVERAGE", "OUT_OF_ZONE": "COVERAGE", "TURNOVER": "TURNOVER", "RUSH_DEFENSE": "RUSH_DEFENSE"},
                default="COVERAGE"))
             .group_by("player_id", "season", "lk").agg(b=pl.col("severity").sum())
             .pivot(values="b", index=["player_id", "season"], on="lk").fill_null(0.0))
    for k in ["COVERAGE", "TURNOVER", "RUSH_DEFENSE"]:
        if k not in blame.columns:
            blame = blame.with_columns(pl.lit(0.0).alias(k))
    blame = blame.rename({"COVERAGE": "cov_blame", "TURNOVER": "turn_blame", "RUSH_DEFENSE": "rush_blame"})

    # --- tracked on-ice GA per (player, season): goals the defender was tracked on the ice for ---
    trk = (pl.read_parquet(TRACKS).select("game_id", "event_id", "player_id", "season").unique()
           .group_by("player_id", "season").agg(trk_ga=pl.len()))

    # --- real on-ice 5v5 GA per (player, season): unnest on_ice_against for goal events, keep 5v5, drop goalie ---
    ev = pl.DataFrame([{"game_id": r.game_id, "event_id": r.event_id, "player_id": r.player_id}
                       for r in bq.query(f"""select e.game_id, e.event_id, d as player_id
                      from `{C.BQ_PROJECT}.nhl_staging.int_on_ice_events` e, unnest(e.on_ice_against) as d
                      where e.type_desc_key='goal' and e.game_id >= 2024020000""").result()],
                      schema={"game_id": pl.Int64, "event_id": pl.Int64, "player_id": pl.Int64})
    v5 = fused.filter(pl.col("strength_state") == "5v5")
    goalies = pl.concat([v5.select(pid="home_goalie_id"), v5.select(pid="away_goalie_id")]).unique()["pid"].to_list()
    realga = (ev.join(v5.select("game_id", "event_id", "season"), on=["game_id", "event_id"], how="inner")
              .filter(~pl.col("player_id").is_in(goalies))
              .group_by("player_id", "season").agg(real_ga=pl.len()))

    # --- real 5v5 TOI + on-ice xGA per (player, season) ---
    on = pl.DataFrame([{"player_id": r.player_id, "season": r.season, "toi_sec": r.toi_sec, "xga": r.xga}
                       for r in bq.query(f"""select player_id, season, sum(toi_5v5_sec) toi_sec, sum(on_xga) xga
                      from `{C.BQ_PROJECT}.nhl_staging.int_player_onice_game`
                      where season in ('2024-25','2025-26') group by 1,2""").result()],
                      schema={"player_id": pl.Int64, "season": pl.Utf8, "toi_sec": pl.Float64, "xga": pl.Float64})

    # --- season-correct name + sweater, and position ---
    nmq = pl.DataFrame([{"player_id": r.player_id, "season": r.season, "nm": r.nm, "sw": r.sw}
                        for r in bq.query(f"""select player_id, season, min(concat(first_name,' ',last_name)) nm,
                       max(sweater_number) sw
                       from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where season in ('2024-25','2025-26') group by 1,2""").result()],
                       schema={"player_id": pl.Int64, "season": pl.Utf8, "nm": pl.Utf8, "sw": pl.Int64})
    isdef = load_meta().select("player_id", "is_def")

    ck = [pl.col("player_id").cast(pl.Int64), pl.col("season").cast(pl.Utf8)]
    trk = trk.with_columns(ck); blame = blame.with_columns(ck); realga = realga.with_columns(ck)
    on = on.with_columns(ck); nmq = nmq.with_columns(ck)
    df = (trk.join(blame, on=["player_id", "season"], how="left")
          .join(realga, on=["player_id", "season"], how="left")
          .join(on, on=["player_id", "season"], how="left")
          .join(nmq, on=["player_id", "season"], how="left")
          .join(isdef.with_columns(pl.col("player_id").cast(pl.Int64)), on="player_id", how="left")
          .with_columns(pl.col(["cov_blame", "turn_blame", "rush_blame", "real_ga", "toi_sec", "xga"]).fill_null(0.0)))
    df = df.with_columns(
        cov_rate=pl.col("cov_blame") / pl.col("trk_ga"),
        turn_rate=pl.col("turn_blame") / pl.col("trk_ga"),
        rush_rate=pl.col("rush_blame") / pl.col("trk_ga"),
        combined_rate=(pl.col("cov_blame") + pl.col("turn_blame") + pl.col("rush_blame")) / pl.col("trk_ga"),
        toi_min=pl.col("toi_sec") / 60.0,
        xga60=pl.when(pl.col("toi_sec") > 0).then(pl.col("xga") / (pl.col("toi_sec") / 3600.0)).otherwise(None),
        ga60=pl.when(pl.col("toi_sec") > 0).then(pl.col("real_ga") / (pl.col("toi_sec") / 3600.0)).otherwise(None),
        pos=pl.when(pl.col("is_def")).then(pl.lit("D")).otherwise(pl.lit("F")))
    df = df.filter((pl.col("trk_ga") >= MIN_GA) & pl.col("nm").is_not_null() & (pl.col("nm") != "0.0"))
    # TOI tier within (season, position): T1 = heaviest 5v5 minutes
    df = df.with_columns(toi_tier=("T" + (pl.col("toi_min").rank(descending=True).over(["season", "pos"])
          / pl.len().over(["season", "pos"]) * 4).ceil().clip(1, 4).cast(pl.Int64).cast(pl.Utf8)))
    return df


def _fmt(df: pl.DataFrame) -> pl.DataFrame:
    return df.select(
        player=pl.col("nm") + " #" + pl.col("sw").cast(pl.Int64, strict=False).cast(pl.Utf8),
        pos="pos", comb=pl.col("combined_rate").round(3), cov=pl.col("cov_rate").round(3),
        turn=pl.col("turn_rate").round(3), rush=pl.col("rush_rate").round(3),
        trk_ga="trk_ga", real_ga=pl.col("real_ga").cast(pl.Int64),
        ga60=pl.col("ga60").round(2), xga60=pl.col("xga60").round(2),
        toi_min=pl.col("toi_min").round(0).cast(pl.Int64), tier="toi_tier")


def write() -> dict:
    df = aggregate()
    OUT.mkdir(parents=True, exist_ok=True)
    L = []; W = L.append
    W("# Link 2 — Defensive-blame leaderboard · EYE-TEST-FIRST (no stability test run)\n")
    W(f"Per-player per-season blame across three tape-validated ledgers, over 5v5 GA, **min {MIN_GA} tracked "
      "on-ice 5v5 GA** (blame-exposure denominator; ~1.75x in actual 5v5 GA). **Rate = blame / tracked on-ice "
      "GA — LOW is good** (a shutdown defender carries little blame on the goals he is on ice for). Columns: "
      "**comb** combined blame rate · cov/turn/rush per-ledger rates · trk_ga (tracked) / real_ga (actual 5v5) "
      "on-ice GA · ga60, xga60 (real 5v5 per-60) · toi_min (5v5) + TOI tier (T1 = heaviest).\n")
    W("**Eye-test standard (owner):** success is sorting by DEFENSIVE REPUTATION — stay-at-home/shutdown types "
      "grade WELL (low blame); offense-first puck-movers grading middling-to-poor is CORRECT and valuable, not "
      "a failure. Elite is not required at the very top; the bar is that known-defensive players are NOT "
      "clustered at the most-blamed end.\n")
    counts = {}
    for season in SEASONS:
        for pos in ["D", "F"]:
            sub = df.filter((pl.col("season") == season) & (pl.col("pos") == pos)).sort("combined_rate")
            counts[f"{season} {pos}"] = sub.height
            fmt = _fmt(sub)
            csv = OUT / f"leaderboard_{season.replace('-', '')}_{pos}.csv"
            fmt.write_csv(csv)
            W(f"\n## {season} · {pos} — {sub.height} qualified (min {MIN_GA} trk GA). Full CSV: `{csv.name}`\n")
            with pl.Config(tbl_rows=-1, tbl_cols=-1, fmt_str_lengths=30, tbl_width_chars=300, tbl_hide_dataframe_shape=True):
                W(f"### LEAST blame (best {min(40, sub.height)}) — should skew to defensive-reputation players\n")
                W("```")
                W(str(_fmt(sub.head(40))))
                W("```")
                W(f"### MOST blame (worst {min(40, sub.height)}) — puck-movers/offense-first grading here is expected\n")
                W("```")
                W(str(_fmt(sub.tail(40).reverse())))
                W("```")
    W("\n## STOP — owner reads this against reputation. No stability test run (eye-test-first gate).\n")
    (OUT / "leaderboard.md").write_text("\n".join(L))
    return {"counts": counts, "report": str(OUT / "leaderboard.md")}


if __name__ == "__main__":
    r = write()
    print("qualified counts:", r["counts"])
    print("wrote", r["report"])
