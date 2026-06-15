"""
Train the in-house xG model (Phase 2.2).

Gradient-boosted (LightGBM) binary classifier over ~16 seasons of unblocked, non-empty-net,
non-shootout shots. Per-shot additive decomposition is provided at scoring time
(models_ml/xg_decompose.py); this job fits and validates the classifier and writes the
artifact + feature manifest + methodology metrics.

Splits (by season string, which sorts chronologically):
  train   2010-11 .. 2023-14   (<= 2023-24)
  val     2024-25              (hyperparameter grid + early stopping)
  holdout 2025-26              (reported only, never tuned on)

Run:  python -m models_ml.train_xg [--sample N] [--dry-run]
Outputs: models_ml/artifacts/xg_v1.txt, xg_v1_manifest.json, docs/methodology/xg-model.md
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

from models_ml import bq, config
from models_ml.xg_decompose import predict_with_decomposition
from models_ml.xg_features import (
    CATEGORICAL, build_features, build_pull_sql, feature_columns, feature_frame,
)

MODEL_VERSION = "xg_v1"
ARTIFACT_DIR = Path(__file__).parent / "artifacts"
METHODOLOGY = Path(__file__).parent.parent / "docs" / "methodology" / "xg-model.md"

TRAIN_MAX_SEASON = "2023-24"   # inclusive
VAL_SEASON = "2024-25"
HOLDOUT_SEASON = "2025-26"

# Small validation grid (kept interpretable / fast).
GRID = [
    {"num_leaves": 31, "learning_rate": 0.05, "min_child_samples": 200},
    {"num_leaves": 63, "learning_rate": 0.05, "min_child_samples": 200},
    {"num_leaves": 63, "learning_rate": 0.03, "min_child_samples": 500},
    {"num_leaves": 127, "learning_rate": 0.03, "min_child_samples": 500},
]
BASE_PARAMS = dict(
    objective="binary", metric="binary_logloss", verbosity=-1,
    feature_pre_filter=False, num_threads=0,
)


def load_data(sample: int | None) -> pd.DataFrame:
    sql = build_pull_sql(bq.project())
    if sample:
        sql += f"\norder by farm_fingerprint(cast(iss.event_id as string)) limit {sample}"
    df = bq.query_df(sql)
    return build_features(df)


def split(df: pd.DataFrame):
    tr = df[df.season <= TRAIN_MAX_SEASON]
    va = df[df.season == VAL_SEASON]
    ho = df[df.season == HOLDOUT_SEASON]
    return tr, va, ho


def make_dataset(df: pd.DataFrame, ref: lgb.Dataset | None = None) -> lgb.Dataset:
    return lgb.Dataset(
        feature_frame(df), label=df["is_goal"].to_numpy(dtype="float64"),
        categorical_feature=CATEGORICAL, reference=ref, free_raw_data=False,
    )


def calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    idx = np.digitize(p, edges[1:-1])
    rows = []
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        rows.append({
            "bin": b + 1, "n": int(m.sum()),
            "pred": float(p[m].mean()), "actual": float(y[m].mean()),
        })
    return rows


def per_season_totals(df: pd.DataFrame, p: np.ndarray) -> list[dict]:
    tmp = df[["season", "is_goal"]].copy()
    tmp["xg"] = p
    g = tmp.groupby("season").agg(shots=("is_goal", "size"),
                                  actual=("is_goal", "sum"),
                                  predicted=("xg", "sum")).reset_index()
    g["pct_err"] = 100 * (g["predicted"] - g["actual"]) / g["actual"]
    return g.to_dict("records")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=None,
                    help="sample N shots (smoke test); omit for the full ~1.6M")
    ap.add_argument("--dry-run", action="store_true", help="print the pull SQL and exit")
    args = ap.parse_args()

    if args.dry_run:
        print(build_pull_sql(bq.project()))
        return

    print("Pulling shots...")
    df = load_data(args.sample)
    tr, va, ho = split(df)
    print(f"rows: train={len(tr):,} val={len(va):,} holdout={len(ho):,} "
          f"| train goal rate={tr.is_goal.mean():.4f}")

    dtr = make_dataset(tr)
    dva = make_dataset(va, ref=dtr)

    best = None
    print("\nGrid (val log-loss):")
    for params in GRID:
        p = {**BASE_PARAMS, **params}
        booster = lgb.train(
            p, dtr, num_boost_round=2000, valid_sets=[dva],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
        )
        ll = booster.best_score["valid_0"]["binary_logloss"]
        print(f"  {params} -> logloss={ll:.5f} (iters={booster.best_iteration})")
        if best is None or ll < best["ll"]:
            best = {"ll": ll, "params": params, "booster": booster,
                    "iters": booster.best_iteration}

    print(f"\nBest: {best['params']} logloss={best['ll']:.5f} iters={best['iters']}")
    model = best["booster"]

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACT_DIR / f"{MODEL_VERSION}.txt"
    model.save_model(str(artifact_path))

    # Metrics on val + holdout
    metrics = {}
    for name, part in [("val", va), ("holdout", ho)]:
        if len(part) == 0:
            continue
        p = model.predict(feature_frame(part))
        y = part["is_goal"].values
        metrics[name] = {
            "n": int(len(part)),
            "log_loss": float(log_loss(y, p)),
            "auc": float(roc_auc_score(y, p)),
            "calibration": calibration_table(y, p),
        }

    season_totals = per_season_totals(df, model.predict(feature_frame(df)))

    manifest = {
        "model_version": MODEL_VERSION,
        "features": feature_columns(),
        "categorical": CATEGORICAL,
        "params": {**BASE_PARAMS, **best["params"], "num_boost_round": best["iters"]},
        "train_max_season": TRAIN_MAX_SEASON,
        "val_season": VAL_SEASON,
        "holdout_season": HOLDOUT_SEASON,
        "n_train": int(len(tr)),
        "metrics": {k: {kk: vv for kk, vv in v.items() if kk != "calibration"}
                    for k, v in metrics.items()},
    }
    (ARTIFACT_DIR / f"{MODEL_VERSION}_manifest.json").write_text(json.dumps(manifest, indent=2))

    write_methodology(metrics, season_totals, best, len(tr))
    print(f"\nSaved {artifact_path.name} + manifest; wrote {METHODOLOGY}")
    for name, m in metrics.items():
        print(f"  {name}: logloss={m['log_loss']:.5f} auc={m['auc']:.4f} n={m['n']:,}")


def write_methodology(metrics, season_totals, best, n_train) -> None:
    lines = [
        "# In-house xG model (Phase 2.2)", "",
        "Gradient-boosted (LightGBM) binary classifier over unblocked, non-empty-net,",
        "non-shootout shots. Empty-net shots are excluded from training and scoring and",
        "carry `xg = NULL` (and are dropped from team xG totals). Blocked shots are",
        "excluded entirely (their coordinates are the block location). Shootouts excluded.",
        "",
        "## Splits", "",
        f"- train: 2010-11 .. {TRAIN_MAX_SEASON} ({n_train:,} shots)",
        f"- val: {VAL_SEASON} (hyperparameter grid + early stopping)",
        f"- holdout: {HOLDOUT_SEASON} (reported only)",
        "",
        "## Features", "",
        "Grouped into the decomposition buckets exposed per shot:",
        "- **location**: distance to net (|x| normalised to the 89 ft goal line) and absolute angle",
        "- **shot_type**: wrist / slap / snap / backhand / tip-in / deflected / wrap-around / other",
        "- **strength**: 5v5 / PP / SH / other (relative to the shooting team)",
        "- **sequence**: rebound, rush, forecheck, cross-ice (royal road), time since faceoff/turnover",
        "- **game_state**: period, shooting-team home flag, score differential (clipped ±3)",
        "",
        f"Chosen hyperparameters: `{best['params']}`, {best['iters']} boosting rounds.",
        "",
        "## Metrics", "",
        "| split | n | log-loss | AUC |",
        "|---|---|---|---|",
    ]
    for name, m in metrics.items():
        lines.append(f"| {name} | {m['n']:,} | {m['log_loss']:.5f} | {m['auc']:.4f} |")
    lines += ["", "## Calibration (10 bins, predicted vs actual goal rate)", ""]
    for name, m in metrics.items():
        lines += [f"### {name}", "", "| bin | n | predicted | actual |", "|---|---|---|---|"]
        for r in m["calibration"]:
            lines.append(f"| {r['bin']} | {r['n']:,} | {r['pred']:.4f} | {r['actual']:.4f} |")
        lines.append("")
    lines += ["## Predicted vs actual goals per season", "",
              "(total xG vs actual goals; should agree within ~3%)", "",
              "| season | shots | actual | predicted | % err |", "|---|---|---|---|---|"]
    for r in season_totals:
        lines.append(f"| {r['season']} | {r['shots']:,} | {int(r['actual']):,} | "
                     f"{r['predicted']:.1f} | {r['pct_err']:+.1f}% |")
    lines += ["", "## Decomposition", "",
              "Per shot, LightGBM `pred_contrib` log-odds contributions are rolled up into the",
              "five buckets above and converted to probability-space deltas applied sequentially",
              "from the base rate (location -> shot_type -> strength -> sequence -> game_state).",
              "The five deltas plus `base_rate` sum to `xg`. Stored in `nhl_models.shot_xg`.", ""]
    METHODOLOGY.parent.mkdir(parents=True, exist_ok=True)
    METHODOLOGY.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
