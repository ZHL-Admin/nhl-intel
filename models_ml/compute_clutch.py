"""
Leverage-weighted (clutch) production (Phase 4.3, blueprint 4.4).

Per player-season, re-weight each of the player's shots by how much was at stake
(leverage / the player's own mean leverage) and compare to unweighted individual xG:

  raw_ixg     = sum(xg)
  clutch_ixg  = sum(xg * leverage) / mean(leverage)        # weight averages to 1
  clutch_delta= clutch_ixg - raw_ixg                        # >0 = produces in big moments

A permutation test guards against selling noise as signal: shuffle the player's leverage
values across their own shots N times and recompute clutch_delta; the two-sided p-value is the
share of shuffles whose |delta| >= the observed |delta|. Leverage exists for 2015-16+ only.

Output: nhl_models.player_clutch (player_id, season_window, n_shots, raw_ixg, clutch_ixg,
clutch_delta, p_value, mean_leverage).

Run:  python -m models_ml.compute_clutch [--perms 1000] [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq

SINGLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
WINDOW = ["2023-24", "2024-25", "2025-26"]
WINDOW_LABEL = "2023-24_2025-26"
MIN_SHOTS = 30
DEFAULT_PERMS = 1000
SEED = 17


def pull(seasons: list[str]) -> pd.DataFrame:
    df = bq.query_df(f"""
        select shooter_id as player_id, season, xg, leverage
        from `{bq.project()}.nhl_staging.int_event_leverage`
        where leverage is not null and shooter_id is not null
          and season in ({", ".join(f"'{s}'" for s in seasons)})
    """)
    df["xg"] = pd.to_numeric(df["xg"]).astype("float64")
    df["leverage"] = pd.to_numeric(df["leverage"]).astype("float64")
    return df


def clutch_for_group(xg: np.ndarray, lev: np.ndarray, perms: int,
                     rng: np.random.Generator) -> tuple[float, float, float, float]:
    """Return raw_ixg, clutch_ixg, clutch_delta, p_value for one player's shots."""
    mean_lev = lev.mean()
    raw = xg.sum()
    if mean_lev <= 0:
        return raw, raw, 0.0, 1.0
    clutch = (xg * lev).sum() / mean_lev
    delta = clutch - raw
    # permutation null: shuffle leverage across the player's shots. Only sum(xg*perm(lev))
    # varies; build a (perms x n) permutation matrix of lev and dot with xg.
    n = len(xg)
    perm_sums = np.empty(perms)
    for i in range(perms):
        perm_sums[i] = (xg * rng.permutation(lev)).sum()
    perm_delta = perm_sums / mean_lev - raw
    p = float((np.abs(perm_delta) >= abs(delta)).mean())
    return float(raw), float(clutch), float(delta), p


def compute(df: pd.DataFrame, label: str, perms: int) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []
    for pid, g in df.groupby("player_id"):
        if len(g) < MIN_SHOTS:
            continue
        xg = g["xg"].to_numpy()
        lev = g["leverage"].to_numpy()
        raw, clutch, delta, p = clutch_for_group(xg, lev, perms, rng)
        rows.append({"player_id": int(pid), "season_window": label, "n_shots": len(g),
                     "raw_ixg": raw, "clutch_ixg": clutch, "clutch_delta": delta,
                     "p_value": p, "mean_leverage": float(lev.mean())})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=DEFAULT_PERMS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    frames = []
    for s in SINGLE_SEASONS:
        frames.append(compute(pull([s]), s, args.perms))
    frames.append(compute(pull(WINDOW), WINDOW_LABEL, args.perms))
    out = pd.concat(frames, ignore_index=True)

    w = out[out["season_window"] == WINDOW_LABEL].copy()
    names = _names(w["player_id"].tolist())
    sig = w[w["p_value"] < 0.10].sort_values("clutch_delta", ascending=False)
    print(f"{len(out):,} player-seasons. p-value histogram (window): "
          f"{np.histogram(w['p_value'], bins=[0,.2,.4,.6,.8,1.0])[0].tolist()} (expect ~uniform)")
    print("\nMost clutch (window, p<0.10):")
    for _, r in sig.head(8).iterrows():
        print(f"  {names.get(r['player_id'], r['player_id']):22s} +{r['clutch_delta']:.2f} xG "
              f"(p={r['p_value']:.3f}, {r['n_shots']} shots)")

    if args.dry_run:
        print(f"\n[dry-run] {len(out):,} rows not written")
        return
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = "clutch_v1"
    bq.write_df(out, "player_clutch", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "player_id"])
    print(f"\nWrote {len(out):,} rows to nhl_models.player_clutch.")


def _names(ids):
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    df = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) as name
                         from `{bq.project()}.nhl_staging.stg_rosters`
                         where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


if __name__ == "__main__":
    main()
