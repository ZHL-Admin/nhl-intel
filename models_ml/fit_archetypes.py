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

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from models_ml import bq, config
from models_ml.archetype_features import build, FEATURES

SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
BIC_RANGE = range(6, 13)
ARTIFACT = Path(__file__).parent / "artifacts" / "archetype_labeling_report.md"
PARAMS = Path(__file__).parent / "artifacts" / "archetypes_v1.json"
FEATURE_COLS = list(FEATURES.keys())


def fit_group(df: pd.DataFrame, pos: str):
    g = df[df["pos_group"] == pos].reset_index(drop=True)
    X = StandardScaler().fit_transform(g[FEATURE_COLS].to_numpy())
    best_k, best_bic, best_gmm = None, np.inf, None
    for k in BIC_RANGE:
        gmm = GaussianMixture(n_components=k, covariance_type="diag",
                              random_state=0, n_init=3, max_iter=300)
        gmm.fit(X)
        bic = gmm.bic(X)
        if bic < best_bic:
            best_k, best_bic, best_gmm = k, bic, gmm
    resp = best_gmm.predict_proba(X)          # soft memberships (n, k)
    hard = resp.argmax(axis=1)
    # standardized cluster means in feature space (cluster centroid z-scores)
    means = pd.DataFrame(best_gmm.means_, columns=FEATURE_COLS)
    return g, X, resp, hard, best_k, means


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
        g, X, resp, hard, k, means = groups[pos]
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


def save_params(groups: dict) -> None:
    """Persist k per group so --write reproduces the same clustering deterministically."""
    PARAMS.write_text(json.dumps({pos: groups[pos][4] for pos in groups}, indent=2))


def do_write(groups: dict) -> None:
    if not config.ARCHETYPE_NAMES:
        print("config.ARCHETYPE_NAMES is empty — fill it from the labeling report first.")
        return
    rows = []
    for pos in ["F", "D"]:
        g, X, resp, hard, k, means = groups[pos]
        for i, r in g.iterrows():
            mix = sorted(
                [(config.ARCHETYPE_NAMES.get(f"{pos}{c}", f"{pos}{c}"), float(resp[i, c]))
                 for c in range(k) if resp[i, c] >= 0.10],
                key=lambda t: t[1], reverse=True)
            if not mix:
                c = int(hard[i])
                mix = [(config.ARCHETYPE_NAMES.get(f"{pos}{c}", f"{pos}{c}"), 1.0)]
            rows.append({"player_id": int(r["player_id"]), "season": r["season"],
                         "pos_group": pos,
                         "archetypes": json.dumps([{"archetype": a, "weight": round(w, 3)}
                                                   for a, w in mix]),
                         "primary_archetype": mix[0][0]})
    out = pd.DataFrame(rows)
    out["model_version"] = "archetypes_v1"
    bq.write_df(out, "player_archetypes", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season", "player_id"])
    print(f"Wrote {len(out):,} rows to nhl_models.player_archetypes.")
    dist = out.groupby("primary_archetype").size().sort_values(ascending=False)
    print("\nArchetype distribution (primary):")
    print(dist.to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write player_archetypes (needs names)")
    args = ap.parse_args()
    df = build(SEASONS)
    print(f"{len(df):,} player-seasons "
          f"(F={int((df.pos_group=='F').sum())}, D={int((df.pos_group=='D').sum())})")
    groups = {pos: fit_group(df, pos) for pos in ["F", "D"]}
    for pos in ["F", "D"]:
        print(f"  {pos}: k={groups[pos][4]} chosen by BIC")
    save_params(groups)
    if args.write:
        do_write(groups)
    else:
        write_report(groups)
        print("\nNEXT: fill config.ARCHETYPE_NAMES from the report, then rerun with --write.")


if __name__ == "__main__":
    main()
