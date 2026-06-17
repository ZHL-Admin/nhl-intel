"""
Goalie skills radar (Part B2) -> nhl_models.goalie_radar.

One row per (goalie_id, season) with a variable-length spoke list, percentiled WITHIN GOALIES
(goalies never share an axis with skaters and are never ranked across them). Same JSON-spoke shape
as the skater radar.

Spokes:
  1 Overall GSAx (per game)            skill
  2 High-Danger GSAx (per game)        skill
  3 Mid/Low-Danger GSAx (per game)     skill   (aggregated from mart_goalie_game_stats)
  4 Workload (shots faced /game)       usage
  5 Consistency (game-to-game GSAx)    skill   (index from per-game GSAx sd; higher = steadier)
  6 NHL Edge Save% (last 10)           skill   (2nd opinion; tracking-era only, ABSENT otherwise)
  7 Quality of Defense Faced (xGA/shot) proxy

A0 finding: there is NO Edge high-danger goalie save% in the data (Edge has no goalie HD split);
spoke 6 uses the overall Edge last-10 save% as the independent second opinion, labelled as such.

Run:  python -m models_ml.compute_goalie_radar [--dry-run]
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from models_ml import bq, config

MIN_GAMES = 15

SPOKES = [
    ("gsax",          "Overall GSAx",            "skill"),
    ("hd_gsax",       "High-Danger GSAx",        "skill"),
    ("midlow_gsax",   "Mid/Low-Danger GSAx",     "skill"),
    ("workload",      "Workload (shots/game)",   "usage"),
    ("consistency",   "Consistency",             "skill"),
    ("edge_save",     "NHL Edge Save% (last 10)","skill"),    # tracking-era only
    ("quality_faced", "Quality of Defense Faced","proxy"),
]

SQL = """
with gl as (
  select goalie_id, season, games_played, shots_faced, xga, gsax, our_hd_gsax,
         edge_last10_save_pct
  from `{p}.nhl_mart.mart_goalie_season`
),
gm as (   -- per-game GSAx -> consistency sd; mid/low GSAx aggregated from game stats
  select goalie_id, season,
    sum(med_gsax) + sum(low_gsax) as midlow_gsax_total,
    stddev_samp(gsax) as gsax_game_sd, count(*) as gp
  from `{p}.nhl_mart.mart_goalie_game_stats`
  where substr(cast(game_id as string), 5, 2) in ('02', '03')
  group by 1, 2
)
select gl.*, gm.midlow_gsax_total, gm.gsax_game_sd
from gl left join gm using (goalie_id, season)
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    p = bq.project()

    df = bq.query_df(SQL.format(p=p))
    for c in ["games_played", "shots_faced", "xga", "gsax", "our_hd_gsax",
              "edge_last10_save_pct", "midlow_gsax_total", "gsax_game_sd"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df["games_played"] >= MIN_GAMES].copy()
    g = df["games_played"].replace(0, np.nan)

    raw = pd.DataFrame(index=df.index)
    raw["gsax"] = df["gsax"] / g
    raw["hd_gsax"] = df["our_hd_gsax"] / g
    raw["midlow_gsax"] = df["midlow_gsax_total"] / g
    raw["workload"] = df["shots_faced"] / g
    # consistency: steadier (lower game-to-game GSAx sd) ranks higher -> negate before ranking
    raw["consistency"] = -df["gsax_game_sd"]
    raw["edge_save"] = df["edge_last10_save_pct"]
    raw["quality_faced"] = df["xga"] / df["shots_faced"].replace(0, np.nan)

    pctl = pd.DataFrame(index=df.index)
    for key, *_ in SPOKES:
        pctl[key] = raw.groupby(df["season"])[key].rank(pct=True) * 100.0

    rows = []
    for i in df.index:
        spokes = []
        for key, label, tag in SPOKES:
            val = raw.at[i, key]
            if not np.isfinite(val):
                continue
            # consistency display value = the sd itself (positive), percentile already steadier-is-higher
            disp = -val if key == "consistency" else val
            spokes.append({"key": key, "label": label, "tag": tag,
                           "value": round(float(disp), 4),
                           "percentile": round(float(pctl.at[i, key]), 1) if np.isfinite(pctl.at[i, key]) else None,
                           "sd": None, "present": True})
        rows.append({"goalie_id": int(df.at[i, "goalie_id"]), "season": df.at[i, "season"],
                     "games_played": int(df.at[i, "games_played"]),
                     "spokes": json.dumps(spokes),
                     "baseline": f"percentile within goalies, {df.at[i,'season']}",
                     "n_spokes": len(spokes)})
    out = pd.DataFrame(rows)
    out["model_version"] = "goalie_radar_v1"
    print(f"goalie_radar: {len(out)} goalie-seasons (>= {MIN_GAMES} GP)")
    allspokes = [s for js in out["spokes"] for s in json.loads(js)]
    cov = pd.Series([s["key"] for s in allspokes]).value_counts()
    for key, label, _ in SPOKES:
        print(f"  {label:26s} {int(cov.get(key, 0)):5d}")

    if args.dry_run:
        print("[dry-run] not written")
        return
    bq.write_df(out, "goalie_radar", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season", "goalie_id"])
    print(f"Wrote {len(out)} rows to nhl_models.goalie_radar.")


if __name__ == "__main__":
    main()
