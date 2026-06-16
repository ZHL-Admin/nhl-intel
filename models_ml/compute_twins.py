"""
Career twins (Phase 4.4, blueprint 5.4).

For each current player at age A, find the most similar players THROUGH the same age A. Each
player's through-age-A vector is the expanding mean (by age) of his rate production plus static
bio/style: points/82, goals/82, assists/82, sequence-type shares, height, weight, F/D. Vectors
are standardised league-wide; similarity is cosine; k=5 nearest with >= 2 seasons through A.

Twins drawn across the 2021 tracking boundary carry `reduced_features=true` (sequence-share /
Edge coverage differs for the older side) — surfaced as "pre-tracking comparable" in the UI.
Each twin's subsequent 3-season points/82 is attached as the realised outcome.

Output: nhl_models.player_twins (player_id, twin_id, through_age, similarity, reduced_features,
twin_next3_points82).

Run:  python -m models_ml.compute_twins [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq

MIN_GAMES = 20
MIN_SEASONS = 2
K = 5
CURRENT_SEASON = "2025-26"
TRACKING_YEAR = 2021
FEATURES = ["points82", "goals82", "assists82", "rush_share", "forecheck_share",
            "cycle_share", "point_share", "height_in", "weight_lb", "is_def"]

PULL_SQL = """
with pg as (
  select player_id, season,
    sum(individual_goals) as g, sum(first_assists + second_assists) as a,
    sum(seq_rush_attempts) as rush, sum(seq_forecheck_attempts) as fore,
    sum(seq_cycle_attempts) as cyc, sum(seq_point_shot_attempts) as pt,
    sum(individual_shot_attempts) as shots, count(*) as gp,
    any_value(position_code) as pos
  from `{p}.nhl_mart.mart_player_game_stats`
  where substr(cast(game_id as string), 5, 2) in ('02', '03')
  group by 1, 2
  having count(*) >= {min_games}
),
bio as (select player_id, birth_date, height_in, weight_lb from `{p}.nhl_staging.stg_player_bio`)
select pg.*, b.height_in, b.weight_lb,
  cast(substr(pg.season, 1, 4) as int64) as season_start,
  date_diff(date(cast(substr(pg.season,1,4) as int64),10,1), b.birth_date, day)/365.25 as age_exact
from pg join bio b on pg.player_id = b.player_id
where b.height_in is not null
"""


def pull() -> pd.DataFrame:
    df = bq.query_df(PULL_SQL.format(p=bq.project(), min_games=MIN_GAMES))
    for c in ["g", "a", "rush", "fore", "cyc", "pt", "shots", "gp", "height_in", "weight_lb"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    df["age"] = np.floor(pd.to_numeric(df["age_exact"])).astype("int64")
    df["points82"] = (df["g"] + df["a"]) / df["gp"] * 82
    df["goals82"] = df["g"] / df["gp"] * 82
    df["assists82"] = df["a"] / df["gp"] * 82
    seq = (df["rush"] + df["fore"] + df["cyc"] + df["pt"]).replace(0, np.nan)
    df["rush_share"] = (df["rush"] / seq).fillna(0)
    df["forecheck_share"] = (df["fore"] / seq).fillna(0)
    df["cycle_share"] = (df["cyc"] / seq).fillna(0)
    df["point_share"] = (df["pt"] / seq).fillna(0)
    df["is_def"] = (df["pos"] == "D").astype("float64")
    return df


def cumulative_by_age(df: pd.DataFrame) -> pd.DataFrame:
    """Per (player, age): expanding mean of rate features through that age + static bio."""
    df = df.sort_values(["player_id", "age"])
    rate = ["points82", "goals82", "assists82", "rush_share", "forecheck_share",
            "cycle_share", "point_share"]
    g = df.groupby("player_id")
    for c in rate:
        df[c + "_cum"] = g[c].transform(lambda s: s.expanding().mean())
    df["n_through"] = g.cumcount() + 1
    df["min_season_through"] = g["season_start"].transform(lambda s: s.expanding().min())
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    df = pull()
    cum = cumulative_by_age(df)
    # feature matrix per (player, age) using cumulative rates + static bio
    feat_cols = ["points82_cum", "goals82_cum", "assists82_cum", "rush_share_cum",
                 "forecheck_share_cum", "cycle_share_cum", "point_share_cum",
                 "height_in", "weight_lb", "is_def"]
    X = cum[feat_cols].to_numpy(dtype="float64")
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    cum_z = (X - mu) / sd

    # current players + their latest age
    cur = df[df["season"] == CURRENT_SEASON][["player_id", "age"]].drop_duplicates("player_id")
    cum = cum.reset_index(drop=True)
    rows = []
    # index cum rows by (player, age)
    cum["ridx"] = np.arange(len(cum))
    for _, t in cur.iterrows():
        A = int(t["age"])
        tgt = cum[(cum["player_id"] == t["player_id"]) & (cum["age"] == A)]
        if tgt.empty or int(tgt["n_through"].iloc[0]) < MIN_SEASONS:
            continue
        ti = int(tgt["ridx"].iloc[0])
        cand = cum[(cum["age"] == A) & (cum["n_through"] >= MIN_SEASONS)
                   & (cum["player_id"] != t["player_id"])]
        if cand.empty:
            continue
        ci = cand["ridx"].to_numpy()
        tv = cum_z[ti]
        cv = cum_z[ci]
        sim = (cv @ tv) / (np.linalg.norm(cv, axis=1) * np.linalg.norm(tv) + 1e-9)
        order = np.argsort(sim)[::-1][:K]
        for o in order:
            cr = cand.iloc[o]
            tw_id = int(cr["player_id"])
            # subsequent 3-season outcome for the twin (ages A+1..A+3)
            nxt = df[(df["player_id"] == tw_id) & (df["age"] > A) & (df["age"] <= A + 3)]
            rows.append({
                "player_id": int(t["player_id"]), "twin_id": tw_id, "through_age": A,
                "similarity": float(sim[o]),
                "reduced_features": bool(cr["min_season_through"] < TRACKING_YEAR),
                "twin_next3_points82": float(nxt["points82"].mean()) if len(nxt) else None,
            })
    out = pd.DataFrame(rows)
    if out.empty:
        print("No twins computed.")
        return

    names = _names(out["player_id"].tolist() + out["twin_id"].tolist())
    star = 8478402  # McDavid
    ex = out[out["player_id"] == star].sort_values("similarity", ascending=False)
    print(f"{len(out)} twin links for {out['player_id'].nunique()} players.")
    if len(ex):
        print(f"\n{names.get(star)} twins (through age {int(ex['through_age'].iloc[0])}):")
        for _, r in ex.iterrows():
            tag = " [reduced]" if r["reduced_features"] else ""
            print(f"  {names.get(r['twin_id'], r['twin_id']):22s} sim {r['similarity']:.3f}{tag}"
                  f"  next3 {r['twin_next3_points82']:.0f}" if r['twin_next3_points82'] else
                  f"  {names.get(r['twin_id'], r['twin_id']):22s} sim {r['similarity']:.3f}{tag}")

    if args.dry_run:
        print(f"\n[dry-run] {len(out)} rows not written")
        return
    out["player_id"] = out["player_id"].astype("int64")
    out["twin_id"] = out["twin_id"].astype("int64")
    out["model_version"] = "twins_v1"
    bq.write_df(out, "player_twins", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["player_id"])
    print(f"\nWrote {len(out)} rows to nhl_models.player_twins.")


def _names(ids):
    ids = list({int(i) for i in ids})
    df = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) as name
                         from `{bq.project()}.nhl_staging.stg_rosters`
                         where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


if __name__ == "__main__":
    main()
