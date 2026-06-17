"""
Per-player Overall — a within-position percentile SUMMARY for the player detail card ONLY.

Overall is a weighted average of a player's within-position component percentiles, RE-PERCENTILED
within position so "Overall" is itself a 0-100 within-position percentile (averaging percentiles
compresses the top; re-percentiling restores a true 0-100 spread). It SUMMARIZES; it must never
hide the divergence between its components, so:
  * it is ALWAYS shown beside the component percentiles it was built from (enforced in the FE), and
  * it is NEVER a leaderboard sort key — there is deliberately no /rankings/overall endpoint.

Skaters (-> nhl_models.player_overall): weighted average of within-position-group percentiles in
  Play-Driving (RAPM-based composite value, "what repeats") and Production (GAR, "what happened"),
  weights config.OVERALL_WEIGHTS (production 0.55 / play-driving 0.45 — production is the more
  stable lens, GAR_STABILITY_YOY). The two component percentiles are computed with the SAME
  percent_rank / qualified pool as the player-card value block, so they match the on-screen numbers.

Goalies (-> nhl_models.goalie_overall): goalies have no play-driving axis, so Overall averages the
  goalie's within-goalie radar-axis percentiles (GSAx, high-danger GSAx, workload, consistency),
  weights config.OVERALL_WEIGHTS_GOALIE. The component percentiles are read straight from
  nhl_models.goalie_radar so they match the radar shown on the goalie card.

Run:  python -m models_ml.compute_overall [--dry-run]
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from models_ml import bq, config

FLOOR = config.GAR_CONFIG["MIN_TOI_5V5_FOR_RANKING"]
W = config.OVERALL_WEIGHTS
WG = config.OVERALL_WEIGHTS_GOALIE
GOALIE_AXES = ["gsax", "hd_gsax", "workload", "consistency"]   # radar spoke keys averaged for goalie Overall

# Skater Overall in one BigQuery pass. percent_rank() + the qualified-pool filter mirror the
# player-card value block (backend players._value_block) EXACTLY, so the stored component
# percentiles equal the numbers rendered beside Overall on the page (consistency rule).
SKATER_SQL = """
with base as (
  select g.player_id, g.season_window,
    case when g.position = 'D' then 'D' else 'F' end as pos_group,
    g.gar,
    (coalesce(c.ev_offense, 0) + coalesce(c.ev_defense, 0)
     + coalesce(c.pp, 0) + coalesce(c.pk, 0)) as impact_goals
  from `{p}.nhl_models.player_gar` g
  left join `{p}.nhl_models.player_composite` c
    on g.player_id = c.player_id and g.season_window = c.season_window
  where g.toi_5v5 >= {floor} and g.position in ('C', 'L', 'R', 'D')
),
ranked as (
  select *,
    percent_rank() over (partition by season_window, pos_group order by gar) as production_percentile,
    percent_rank() over (partition by season_window, pos_group order by impact_goals) as play_driving_percentile
  from base
),
combined as (
  select *, ({w_prod} * production_percentile + {w_play} * play_driving_percentile) as overall_raw
  from ranked
)
select player_id, season_window, pos_group,
  production_percentile, play_driving_percentile,
  percent_rank() over (partition by season_window, pos_group order by overall_raw) as overall_percentile
from combined
"""


def compute_skaters() -> pd.DataFrame:
    df = bq.query_df(SKATER_SQL.format(p=bq.project(), floor=FLOOR,
                                       w_prod=W["production"], w_play=W["play_driving"]))
    for c in ["production_percentile", "play_driving_percentile", "overall_percentile"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    df["w_production"] = W["production"]
    df["w_play_driving"] = W["play_driving"]
    df["model_version"] = "overall_v1"
    return df


def compute_goalies() -> pd.DataFrame:
    """Goalie Overall from the within-goalie radar-axis percentiles (so the components shown beside
    Overall ARE the goalie radar spokes on the card). Re-percentiled within goalies per season."""
    radar = bq.query_df(f"select goalie_id, season, spokes from `{bq.project()}.nhl_models.goalie_radar`")
    rows = []
    for _, r in radar.iterrows():
        spokes = {s["key"]: s.get("percentile") for s in json.loads(r["spokes"])}
        avail = [(a, spokes[a]) for a in GOALIE_AXES if spokes.get(a) is not None]
        if not avail:
            continue
        wsum = sum(WG[a] for a, _ in avail)
        overall_raw = sum(WG[a] * pct for a, pct in avail) / wsum   # 0-100; renormalized over available
        rows.append({
            "goalie_id": int(r["goalie_id"]), "season_window": r["season"],
            "overall_raw": overall_raw,
            **{f"{a}_percentile": (spokes.get(a) / 100.0 if spokes.get(a) is not None else None)
               for a in GOALIE_AXES},
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # re-percentile Overall within goalies, per season
    df["overall_percentile"] = (df.groupby("season_window")["overall_raw"].rank(pct=True))
    df = df.drop(columns=["overall_raw"])
    for a in GOALIE_AXES:
        df[f"w_{a}"] = WG[a]
    df["model_version"] = "goalie_overall_v1"
    return df


def _report(sk: pd.DataFrame, go: pd.DataFrame) -> None:
    names = {}
    ids = sk["player_id"].tolist() + go["goalie_id"].tolist() if not go.empty else sk["player_id"].tolist()
    if ids:
        nm = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) name
            from `{bq.project()}.nhl_staging.stg_rosters`
            where player_id in ({",".join(str(int(i)) for i in set(ids))}) group by 1""")
        names = dict(zip(nm["player_id"], nm["name"]))
    s = sk[sk["season_window"] == "2025-26"].sort_values("overall_percentile", ascending=False).head(8)
    print("\n=== Skater Overall top-8 (2025-26) — pct shown 0-100 ===")
    for _, r in s.iterrows():
        print(f"  {names.get(r['player_id'], r['player_id']):22s} [{r['pos_group']}] "
              f"Overall {r['overall_percentile']*100:5.1f}  "
              f"(Production {r['production_percentile']*100:5.1f} / Play-Driving {r['play_driving_percentile']*100:5.1f})")
    if not go.empty:
        g = go[go["season_window"] == "2025-26"].sort_values("overall_percentile", ascending=False).head(6)
        print("\n=== Goalie Overall top-6 (2025-26) ===")
        for _, r in g.iterrows():
            print(f"  {names.get(r['goalie_id'], r['goalie_id']):22s} Overall {r['overall_percentile']*100:5.1f}  "
                  f"(GSAx {r['gsax_percentile']*100 if pd.notna(r['gsax_percentile']) else float('nan'):.0f} / "
                  f"HD {r['hd_gsax_percentile']*100 if pd.notna(r['hd_gsax_percentile']) else float('nan'):.0f})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sk = compute_skaters()
    go = compute_goalies()
    print(f"player_overall: {len(sk):,} rows ; goalie_overall: {len(go):,} rows")
    _report(sk, go)

    if args.dry_run:
        print("\n[dry-run] not written")
        return
    bq.write_df(sk, "player_overall", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "player_id"])
    if not go.empty:
        bq.write_df(go, "goalie_overall", write_disposition="WRITE_TRUNCATE",
                    clustering_fields=["season_window", "goalie_id"])
    print(f"\nWrote {len(sk):,} -> nhl_models.player_overall, {len(go):,} -> nhl_models.goalie_overall.")


if __name__ == "__main__":
    main()
