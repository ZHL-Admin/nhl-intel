"""
Archetype refit v2 (supersedes fit_archetypes.py / archetypes_v1).

Clusters player-seasons on the ENRICHED feature vector (archetype_features_v2.FEATURES_V2), so
defensive/style signals — coach-trust deployment, rink-adjusted hits, penalty differential, on-ice
xGA suppression — now DRIVE classification rather than just decorate it. Forwards and defensemen
fit separately.

Stability guards (as v1): single-threaded BLAS for determinism, seed-selected by silhouette among
non-degenerate fits, covariance floor; reject any solution with a cluster < MIN_CLUSTER. k is
chosen by BIC over [6,12] (the v2 enrichment is meant to let the data pick k honestly), persisted
to artifacts/archetypes_v2.joblib so the report, --write and the API share one canonical fit.

Modes:
  (default)  fit + write the trait audit (artifacts/archetype_trait_audit_v2.md) and the v1->v2
             crosswalk, then STOP for human naming (governs A2).
  --write    after names live in config.ARCHETYPE_NAMES_V2, emit nhl_models.player_archetypes
             (model_version archetypes_v2), incl. the pre-tracking reduced-feature projection.

Run single-threaded:  VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1 python -m models_ml.fit_archetypes_v2
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from models_ml import bq, config
from models_ml.archetype_features_v2 import build_v2, FEATURES_V2

SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
HISTORICAL_SEASONS = ["2015-16", "2016-17", "2017-18", "2018-19", "2019-20", "2020-21"]
FEATURE_COLS = list(FEATURES_V2.keys())

K_RANGE = range(6, 13)         # BIC-selected k in [6, 12]
REG_COVAR = 1e-2
N_INIT = 3
MIN_CLUSTER = 15               # reject any fit with a degenerate (tiny) component
SEEDS = range(12)
UNIVERSAL = 0.80               # >=80% of members one-sided => the name may assert it
SEP = 0.80                     # near-twin separation threshold

ART_DIR = Path(__file__).parent / "artifacts"
MODEL_PATH = ART_DIR / "archetypes_v2.joblib"
AUDIT_PATH = ART_DIR / "archetype_trait_audit_v2.md"


def _select_fit(Xs: np.ndarray):
    """BIC-selected k in K_RANGE; per k the best-silhouette non-degenerate seed; reject degenerate."""
    from sklearn.metrics import silhouette_score
    per_k = []
    for k in K_RANGE:
        best = None
        for seed in SEEDS:
            gm = GaussianMixture(n_components=k, covariance_type="diag", reg_covar=REG_COVAR,
                                 random_state=seed, n_init=N_INIT, max_iter=500).fit(Xs)
            lab = gm.predict(Xs)
            if np.bincount(lab, minlength=k).min() < MIN_CLUSTER:
                continue
            sil = silhouette_score(Xs, lab)
            if best is None or sil > best[0]:
                best = (sil, seed, gm)
        if best is not None:
            _, seed, gm = best
            per_k.append((k, gm.bic(Xs), best[0], seed, gm))
    if not per_k:
        raise RuntimeError("no non-degenerate fit in k range")
    per_k.sort(key=lambda r: r[1])              # lowest BIC wins
    return per_k[0], per_k


def fit_group(df: pd.DataFrame, pos: str, model: dict | None = None):
    g = df[df["pos_group"] == pos].reset_index(drop=True)
    if model is None:
        scaler = StandardScaler().fit(g[FEATURE_COLS].to_numpy())
        Xs = scaler.transform(g[FEATURE_COLS].to_numpy())
        (k, bic, sil, seed, gmm), per_k = _select_fit(Xs)
        print(f"  {pos}: BIC-selected k={k} (sil {sil:.3f}, seed {seed}). "
              f"Per-k BIC: " + ", ".join(f"k{kk}:{bb:.0f}" for kk, bb, *_ in per_k))
    else:
        scaler, gmm = model["scaler"], model["gmm"]
    X = scaler.transform(g[FEATURE_COLS].to_numpy())
    resp = gmm.predict_proba(X)
    hard = resp.argmax(axis=1)
    means = pd.DataFrame(gmm.means_, columns=FEATURE_COLS)
    return g, X, resp, hard, gmm.n_components, means, scaler, gmm


def fit_or_load(df: pd.DataFrame) -> dict:
    saved = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None
    groups, to_save = {}, {}
    for pos in ["F", "D"]:
        groups[pos] = fit_group(df, pos, saved[pos] if saved else None)
        to_save[pos] = {"scaler": groups[pos][6], "gmm": groups[pos][7]}
    if saved is None:
        ART_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(to_save, MODEL_PATH)
        print(f"Saved canonical v2 clustering -> {MODEL_PATH}")
    return groups


def _names(ids):
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    df = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) as name
                         from `{bq.project()}.nhl_staging.stg_rosters`
                         where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


def _universal(X_pos: np.ndarray, mem: np.ndarray) -> list[tuple]:
    """Features where >=UNIVERSAL of members are on one side of 0 (the standardized median)."""
    out = []
    for fi, f in enumerate(FEATURE_COLS):
        z = X_pos[mem, fi]
        pos_share = (z > 0).mean()
        share, direction = (pos_share, "+") if pos_share >= 0.5 else (1 - pos_share, "-")
        if share >= UNIVERSAL:
            out.append((f, share, direction, float(np.median(z))))
    out.sort(key=lambda t: -abs(t[3]))
    return out


def _near_twin(means: pd.DataFrame, X_pos, hard, c: int):
    ctr = means.to_numpy()
    d = np.linalg.norm(ctr - ctr[c], axis=1)
    d[c] = np.inf
    nn = int(d.argmin())
    # features separating c and nn at >=SEP: each cluster >=SEP on its side of the centroid midpoint
    a, b = np.where(hard == c)[0], np.where(hard == nn)[0]
    seps = []
    for fi, f in enumerate(FEATURE_COLS):
        mid = (ctr[c, fi] + ctr[nn, fi]) / 2
        if ctr[c, fi] >= ctr[nn, fi]:
            sa, sb = (X_pos[a, fi] > mid).mean(), (X_pos[b, fi] < mid).mean()
        else:
            sa, sb = (X_pos[a, fi] < mid).mean(), (X_pos[b, fi] > mid).mean()
        if sa >= SEP and sb >= SEP:
            seps.append((f, abs(ctr[c, fi] - ctr[nn, fi])))
    seps.sort(key=lambda t: -t[1])
    return nn, seps


def write_audit(groups: dict) -> None:
    lines = ["# Archetype trait audit (v2)", "",
             "Per-cluster audit governing naming (A2). **Universal** = >=80% of the cluster's "
             "members on one side of the position median for that feature; a name may assert ONLY "
             "universal traits. **Distinctive** = centroid |z|, drives the descriptor, not the "
             "name. **Near-twin** = nearest cluster; if no feature separates them at >=80%, the "
             "pair is a MERGE candidate.", ""]
    suggestions = {}
    for pos in ["F", "D"]:
        g, X, resp, hard, k, means, scaler, gmm = groups[pos]
        lines.append(f"\n## {'Forwards' if pos == 'F' else 'Defensemen'} — k={k}\n")
        for c in range(k):
            key = f"{pos}{c}"
            mem = np.where(hard == c)[0]
            uni = _universal(X, mem)
            row = means.iloc[c]
            dist = row.reindex(row.abs().sort_values(ascending=False).index).head(6)
            nn, seps = _near_twin(means, X, hard, c)
            ex_idx = np.argsort(resp[:, c])[::-1][:10]
            ex = g.iloc[ex_idx]
            nm = _names(ex["player_id"].tolist())
            exs = ", ".join(f"{nm.get(r.player_id, r.player_id)} ({r.season})" for r in ex.itertuples())
            # boundary = lowest max-membership members of this cluster
            bnd_idx = sorted(mem, key=lambda i: resp[i].max())[:5]
            bnd = g.iloc[bnd_idx]
            nmb = _names(bnd["player_id"].tolist())
            bnds = ", ".join(f"{nmb.get(r.player_id, r.player_id)} ({r.season})" for r in bnd.itertuples())
            uni_str = "; ".join(f"{FEATURES_V2[f]} {d}{abs(z):.2f} ({s*100:.0f}%)"
                                for f, s, d, z in uni) or "(none — no name may assert a trait)"
            dist_str = ", ".join(f"{FEATURES_V2[f]} {row[f]:+.2f}" for f in dist.index)
            merge = "  ⚠ MERGE CANDIDATE" if not seps else ""
            sep_str = ("; ".join(f"{FEATURES_V2[f]} (Δ{dz:.2f})" for f, dz in seps[:4])
                       if seps else f"NONE — overlaps {pos}{nn}{merge}")
            suggestions[key] = uni[:3]
            lines += [f"### `{key}`  (n={len(mem)})",
                      f"- **Universal traits (name may assert these):** {uni_str}",
                      f"- Distinctive (descriptor): {dist_str}",
                      f"- Near-twin `{pos}{nn}` separated by: {sep_str}",
                      f"- Exemplars: {exs}",
                      f"- Boundary cases: {bnds}", ""]
    AUDIT_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {AUDIT_PATH}")
    return suggestions


def crosswalk(groups: dict) -> None:
    """How v2 clusters map onto the v1 (current) primary_archetype labels."""
    p = bq.project()
    v1 = bq.query_df(f"""select player_id, season, primary_archetype
                         from `{p}.nhl_models.player_archetypes`""")
    v1m = {(int(r.player_id), r.season): r.primary_archetype for r in v1.itertuples()}
    print("\n=== v1 -> v2 crosswalk (top v1 labels feeding each v2 cluster) ===")
    for pos in ["F", "D"]:
        g, X, resp, hard, k, means, scaler, gmm = groups[pos]
        for c in range(k):
            mem = np.where(hard == c)[0]
            labs = pd.Series([v1m.get((int(g.loc[i, "player_id"]), g.loc[i, "season"]))
                              for i in mem]).value_counts(normalize=True).head(3)
            mix = ", ".join(f"{lab} {sh*100:.0f}%" for lab, sh in labs.items())
            print(f"  {pos}{c} (n={len(mem)}): {mix}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="emit player_archetypes (needs names)")
    args = ap.parse_args()

    df = build_v2(SEASONS)
    df = df[df["toi_5v5"] >= config.ARCHETYPE_MIN_5V5_MIN].copy()
    print(f"{len(df)} tracking-era player-seasons (F={int((df.pos_group=='F').sum())}, "
          f"D={int((df.pos_group=='D').sum())})")
    groups = fit_or_load(df)

    if not args.write:
        write_audit(groups)
        crosswalk(groups)
        print("\nSTOP: confirm names before running --write. "
              "Fill config.ARCHETYPE_NAMES_V2 from the audit, then rerun with --write.")
        return

    _do_write(groups)


def _do_write(groups: dict) -> None:
    from models_ml.fit_archetypes import _rows_from_resp  # reuse v1 row builder
    raise SystemExit("A3 not yet wired — see fit_archetypes_v2._do_write")


if __name__ == "__main__":
    main()
