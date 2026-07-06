"""player_prior_quality: each skater's PRIOR-SEASON shrunk WAR rate, per season (spec 7.2).

For season S, a skater's quality is the Marcel WAR rate computed as of S-1 (data through S-1 only)
— so quality-of-competition / quality-of-teammates built from it is leak-free by construction.
Rookies (no prior history) get 0.0 (replacement), matching forecast conventions. WAR-per-5v5-hour
units, consistent with baselines.py.

Grain: (player_id, season, prior_war_rate). Read-only over nhl_models.player_gar. Weekly (Monday
gated); the current run only needs seasons already present in player_gar, so it does not depend on
the current night's GAR recompute.

Run:  python -m models_ml.compute_prior_quality [--dry-run]   (make prior-quality)
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, baselines


def compute(gar: pd.DataFrame) -> pd.DataFrame:
    panel = baselines.skater_panel(gar)
    seasons = sorted(panel["season_window"].unique(), key=baselines.season_year)
    rows = []
    for s in seasons:
        present = panel[panel["season_window"] == s][["player_id", "pos_group"]].drop_duplicates()
        marcel = baselines.marcel_skaters(panel, s)               # rate as of s-1 (data through s-1)
        rate = {int(i): float(v) for i, v in marcel["marcel_rate"].items()}
        for _, r in present.iterrows():
            pid = int(r["player_id"])
            rows.append({"player_id": pid, "season": s, "pos_group": r["pos_group"],
                         "prior_war_rate": rate.get(pid, 0.0)})          # rookies (no history) -> 0.0
    out = pd.DataFrame(rows)
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = "prior_quality_v1"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    gar = bq.query_df("select * from nhl_models.player_gar")
    out = compute(gar)
    n_rookie = int((out["prior_war_rate"] == 0.0).sum())
    print(f"player_prior_quality: {len(out)} rows, {out['season'].nunique()} seasons, "
          f"{n_rookie} rookie/zero rows")
    if args.dry_run:
        print("[dry-run] not written")
        return out
    bq.write_df(out, "player_prior_quality", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season", "player_id"])
    print("wrote nhl_models.player_prior_quality")
    return out


if __name__ == "__main__":
    import os
    os.environ.setdefault("SERVING_BACKEND", "duckdb")
    main()
