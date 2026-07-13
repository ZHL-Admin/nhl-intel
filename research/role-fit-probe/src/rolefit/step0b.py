"""Step 0b — re-audit of event attribution (reproducer for the runnable parts).

Reproduces: (1) the ingested-table per-event player-attribution rates; (2) the opponent-mirror
time-join feasibility on a sample game; (3) the playmaking-shadow sequence count. The raw-vs-ingested
delta itself is established by reading production SQL (dbt/models/staging/stg_play_by_play.sql and
deployment-atlas/src/atlas/sources.py::materialize_events) — see reports/probe.md §0b and
reports/upstream-ledger.md UL-P1; that part is not runnable here (no BigQuery fetch in this probe).
"""
from __future__ import annotations

import polars as pl

from . import config
import chem.corpus as cc

EVENTS = config.ATLAS_PARQUET / "events.parquet"
STINTS = config.ATLAS_PARQUET / "stints.parquet"
PCOLS = ["shooting_player_id", "scoring_player_id", "assist1_player_id",
         "blocking_player_id", "hitting_player_id", "player_id", "event_owner_team_id"]
# note: blocking_/hitting_/player_id are NOT in events.parquet (that IS the finding) — guarded below.


def ingested_attribution() -> pl.DataFrame:
    ev = pl.scan_parquet(EVENTS)
    have = ev.collect_schema().names()
    cols = [c for c in PCOLS if c in have]
    return (ev.group_by("type_desc_key").agg(
        [pl.len().alias("n")] + [(pl.col(c).is_not_null()).mean().round(3).alias(c) for c in cols])
        .sort("n", descending=True).collect())


def mirror_join_sample() -> dict:
    st = pl.scan_parquet(STINTS).filter((pl.col("season_label") == "2024-25")
                                        & (pl.col("strength_state") == "5v5")).select(
        "game_id", "start_seconds", "end_seconds", "home_skater_ids", "away_skater_ids").collect()
    ev = pl.scan_parquet(EVENTS).filter((pl.col("season_label") == "2024-25")
                                        & (pl.col("type_desc_key") == "shot-on-goal")
                                        & (pl.col("situation_code") == "1551")).select(
        "game_id", "event_second", "shooting_player_id").collect()
    g = ev["game_id"].min()
    evg, stg = ev.filter(pl.col("game_id") == g), st.filter(pl.col("game_id") == g)
    matched = on = 0
    for r in evg.iter_rows(named=True):
        row = stg.filter((pl.col("start_seconds") <= r["event_second"])
                         & (pl.col("end_seconds") > r["event_second"]))
        if row.height:
            matched += 1
            rr = row.row(0, named=True)
            if r["shooting_player_id"] in (set(rr["home_skater_ids"]) | set(rr["away_skater_ids"])):
                on += 1
    return {"game": g, "shots": evg.height, "matched": matched, "shooter_on_ice": on}


def playmaking_shadow(n_sec: int = 4) -> dict:
    ev = (pl.scan_parquet(EVENTS).filter(pl.col("season_label") == "2024-25")
          .select("game_id", "event_second", "type_desc_key", "event_owner_team_id")
          .collect().sort("game_id", "event_second"))
    ev = ev.with_columns(nt=pl.col("type_desc_key").shift(-1).over("game_id"),
                         ns=pl.col("event_second").shift(-1).over("game_id"),
                         nteam=pl.col("event_owner_team_id").shift(-1).over("game_id"))
    tk = ev.filter(pl.col("type_desc_key") == "takeaway")
    hit = tk.filter((pl.col("nteam") == pl.col("event_owner_team_id"))
                    & ((pl.col("ns") - pl.col("event_second")) <= n_sec)
                    & pl.col("nt").is_in(["shot-on-goal", "missed-shot", "goal", "blocked-shot"]))
    return {"takeaways": tk.height, f"followed_by_shot_within_{n_sec}s": hit.height,
            "share": round(hit.height / max(tk.height, 1), 3)}


def run():
    print("=== ingested-table player attribution (events.parquet) ===")
    print(ingested_attribution())
    print("\n=== opponent-mirror time-join (sample game) ===", mirror_join_sample())
    print("=== playmaking-shadow sequence (2024-25) ===", playmaking_shadow())
    print("\nRaw-vs-ingested delta + recovery: see probe.md §0b and upstream-ledger.md UL-P1.")


if __name__ == "__main__":
    run()
