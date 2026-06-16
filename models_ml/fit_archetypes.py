"""
Player archetypes via per-position Gaussian mixtures (Phase 4.2, blueprint 4.5).

Feature vector per player-season (skaters >= ARCHETYPE_MIN_5V5_MIN 5v5 minutes; tracking era
2021-22..2025-26). Standardize within position group (F and D separately), fit a Gaussian
mixture, choose k by BIC in [6, 12], and take SOFT memberships.

Two phases:
  1. (default) HAND-LABELING: print per-cluster standardized feature means + 10 exemplars to
     models_ml/artifacts/archetype_labeling_report.md, then STOP. A human fills
     config.ARCHETYPE_NAMES (keys "F0".."F{k-1}", "D0".."D{k-1}").
  2. --write: once names exist, write nhl_models.player_archetypes (player, season, sorted
     list of (archetype, weight)).

Run:
  python -m models_ml.fit_archetypes            # produce the labeling report, then stop
  python -m models_ml.fit_archetypes --write    # after config.ARCHETYPE_NAMES is filled
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from models_ml import bq, config
from models_ml.archetype_features import build, FEATURES

SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
# Pre-tracking seasons assigned by reduced-feature projection (segment data starts 2015-16;
# Edge starts 2021-22). 2010-2014 has no segments, so no archetype there.
HISTORICAL_SEASONS = ["2015-16", "2016-17", "2017-18", "2018-19", "2019-20", "2020-21"]
# k per position. BIC over [6,12] with a degenerate-cluster guard prefers 12 for both, but
# that selection is boundary-sensitive to float noise (a cluster dipping under the size floor
# flips the choice), so we FIX k for reproducibility and persist the fitted model below.
FORCED_K = {"F": 12, "D": 12}
REG_COVAR = 1e-2        # covariance floor: stops a component collapsing onto an outlier
N_INIT = 3
MIN_CLUSTER = 15        # reject a fit with any degenerate (tiny) component
SEEDS = range(12)       # GMM has many optima; pick the best-SEPARATED reproducible one
# Raw likelihood/BIC favours a muddy optimum with a giant catch-all scorer cluster; we instead
# select the seed with the highest silhouette (best-separated, balanced archetypes) among fits
# with no degenerate cluster, then persist it. Run with single-threaded BLAS
# (VECLIB_MAXIMUM_THREADS=1 etc.) so the selected fit is bitwise reproducible.
ARTIFACT = Path(__file__).parent / "artifacts" / "archetype_labeling_report.md"
MODEL_PATH = Path(__file__).parent / "artifacts" / "archetypes_v1.joblib"
FEATURE_COLS = list(FEATURES.keys())


def fit_group(df: pd.DataFrame, pos: str, model: dict | None = None):
    """Fit (or apply a saved) per-position GMM. Returns g, resp, hard, k, means.
    If `model` (scaler+gmm for this pos) is given, applies it instead of refitting, so the
    labeling report, the names, and player_archetypes share one canonical clustering."""
    g = df[df["pos_group"] == pos].reset_index(drop=True)
    if model is None:
        scaler = StandardScaler().fit(g[FEATURE_COLS].to_numpy())
        Xs = scaler.transform(g[FEATURE_COLS].to_numpy())
        best = None
        for seed in SEEDS:
            cand = GaussianMixture(n_components=FORCED_K[pos], covariance_type="diag",
                                   reg_covar=REG_COVAR, random_state=seed, n_init=N_INIT,
                                   max_iter=500).fit(Xs)
            if np.bincount(cand.predict(Xs), minlength=FORCED_K[pos]).min() < MIN_CLUSTER:
                continue
            sil = silhouette_score(Xs, cand.predict(Xs))
            if best is None or sil > best[0]:
                best = (sil, seed, cand)
        _, seed, gmm = best
        print(f"  {pos}: selected seed {seed} (silhouette {best[0]:.3f})")
    else:
        scaler, gmm = model["scaler"], model["gmm"]
    X = scaler.transform(g[FEATURE_COLS].to_numpy())
    resp = gmm.predict_proba(X)
    hard = resp.argmax(axis=1)
    means = pd.DataFrame(gmm.means_, columns=FEATURE_COLS)
    return g, X, resp, hard, gmm.n_components, means, scaler, gmm


def fit_or_load(df: pd.DataFrame) -> dict:
    """Return {pos: (g, X, resp, hard, k, means, scaler, gmm)}, loading the persisted model
    if present (reproducible) and otherwise fitting + saving it."""
    saved = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None
    groups, to_save = {}, {}
    for pos in ["F", "D"]:
        groups[pos] = fit_group(df, pos, saved[pos] if saved else None)
        to_save[pos] = {"scaler": groups[pos][6], "gmm": groups[pos][7]}
    if saved is None:
        joblib.dump(to_save, MODEL_PATH)
        print(f"Saved canonical clustering -> {MODEL_PATH}")
    return groups


def names_for(ids):
    ids = [int(i) for i in ids]
    df = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) as name
                         from `{bq.project()}.nhl_staging.stg_rosters`
                         where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


def write_report(groups: dict) -> None:
    lines = ["# Archetype labeling report (Phase 4.2)", "",
             "Gaussian-mixture clusters of player-seasons (2021-22..2025-26, >= "
             f"{config.ARCHETYPE_MIN_5V5_MIN} 5v5 min), F and D separately. Cluster means are",
             "in standard deviations (z-scores) so + = above the position average. Fill",
             "`config.ARCHETYPE_NAMES` with a short label per cluster key, then run",
             "`python -m models_ml.fit_archetypes --write`.", ""]
    for pos in ["F", "D"]:
        g, X, resp, hard, k, means, scaler, gmm = groups[pos]
        lines.append(f"\n## {('Forwards' if pos == 'F' else 'Defensemen')} — {k} clusters\n")
        for c in range(k):
            key = f"{pos}{c}"
            n = int((hard == c).sum())
            # most distinctive features (largest |z| centroid)
            row = means.iloc[c]
            top = row.reindex(row.abs().sort_values(ascending=False).index).head(6)
            feat_str = ", ".join(f"{FEATURES[f]} {row[f]:+.2f}" for f in top.index)
            # 10 exemplars = highest membership in this cluster
            idx = np.argsort(resp[:, c])[::-1][:10]
            ex = g.iloc[idx]
            nm = names_for(ex["player_id"].tolist())
            exs = ", ".join(f"{nm.get(r.player_id, r.player_id)} ({r.season})"
                            for r in ex.itertuples())
            lines += [f"### `{key}`  (n={n})  — NAME: ____________",
                      f"- Distinctive: {feat_str}",
                      f"- Exemplars: {exs}", ""]
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {ARTIFACT}")


def _rows_from_resp(g, resp, pos, edge_imputed):
    """Build player_archetypes rows from a soft-membership matrix."""
    k = resp.shape[1]
    g = g.reset_index(drop=True)
    out = []
    for i in range(len(g)):
        mix = sorted(
            [(config.ARCHETYPE_NAMES.get(f"{pos}{c}", f"{pos}{c}"), float(resp[i, c]))
             for c in range(k) if resp[i, c] >= 0.10],
            key=lambda t: t[1], reverse=True)
        if not mix:
            c = int(resp[i].argmax())
            mix = [(config.ARCHETYPE_NAMES.get(f"{pos}{c}", f"{pos}{c}"), 1.0)]
        out.append({"player_id": int(g.loc[i, "player_id"]), "season": g.loc[i, "season"],
                    "pos_group": pos, "edge_imputed": edge_imputed,
                    "archetypes": json.dumps([{"archetype": a, "weight": round(w, 3)}
                                              for a, w in mix]),
                    "primary_archetype": mix[0][0]})
    return out


def _score_historical(groups: dict) -> list:
    """Assign 2015-16..2020-21 player-seasons with the LOCKED model, but with the Edge (and
    RAPM, absent pre-2021) features NEUTRALISED to the scaler means — a reduced-feature
    projection. The burst-defined clusters (F1 Elite Speed Driver, D2 Elite Offensive D)
    cannot be identified without burst speed, so those players collapse into their nearest
    non-burst cluster; rows are flagged edge_imputed=true."""
    df = build(HISTORICAL_SEASONS)
    rows = []
    for pos in ["F", "D"]:
        scaler, gmm = groups[pos][6], groups[pos][7]
        g = df[df["pos_group"] == pos].reset_index(drop=True)
        if g.empty:
            continue
        X = g[FEATURE_COLS].to_numpy(dtype="float64").copy()
        means = scaler.mean_
        for j in range(X.shape[1]):                       # neutralise any NaN to the train mean
            col = X[:, j]
            col[np.isnan(col)] = means[j]
            X[:, j] = col
        resp = gmm.predict_proba(scaler.transform(X))
        rows += _rows_from_resp(g, resp, pos, edge_imputed=True)
    return rows


def do_write(groups: dict) -> None:
    if not config.ARCHETYPE_NAMES:
        print("config.ARCHETYPE_NAMES is empty — fill it from the labeling report first.")
        return
    rows = []
    for pos in ["F", "D"]:
        g, X, resp, hard, k, means, scaler, gmm = groups[pos]
        rows += _rows_from_resp(g, resp, pos, edge_imputed=False)
    rows += _score_historical(groups)            # pre-tracking seasons, reduced-feature
    out = pd.DataFrame(rows)
    out["model_version"] = "archetypes_v1"
    bq.write_df(out, "player_archetypes", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season", "player_id"])
    print(f"Wrote {len(out):,} rows to nhl_models.player_archetypes "
          f"({int((~out.edge_imputed).sum())} tracking, {int(out.edge_imputed.sum())} historical).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write player_archetypes (needs names)")
    args = ap.parse_args()
    df = build(SEASONS)
    print(f"{len(df):,} player-seasons "
          f"(F={int((df.pos_group=='F').sum())}, D={int((df.pos_group=='D').sum())})")
    groups = fit_or_load(df)
    for pos in ["F", "D"]:
        print(f"  {pos}: k={groups[pos][4]}")
    if args.write:
        do_write(groups)
    else:
        write_report(groups)
        print("\nNEXT: fill config.ARCHETYPE_NAMES from the report, then rerun with --write.")


if __name__ == "__main__":
    main()
