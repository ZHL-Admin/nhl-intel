"""Leakage-clean xG refit for Phase 3.2 REPORTING ONLY (non-destructive).

Production xg_v1 trains on 2010-11..2023-24, so its 2022-23/2023-24 metrics are
in-sample. This refit reuses the EXACT production pipeline (models_ml.xg_features)
but trains on <= 2020-21 (early-stop val 2021-22) so 2022-23..2025-26 are fully
out-of-sample. It writes nothing to production; reports AUC + calibration only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.metrics import roc_auc_score

from atlas import config, sources

# Reuse the production feature pipeline (Phase 3 explicitly permits reading the xG interface).
sys.path.insert(0, str(config.PROJECT_ROOT.parents[1]))
from models_ml.xg_features import (  # noqa: E402
    CATEGORICAL, PULL_SQL, build_features, feature_columns, feature_frame,
)

TRAIN_MAX = "2020-21"
VAL = "2021-22"
REPORT = ["2022-23", "2023-24", "2024-25", "2025-26"]


def _pull() -> "object":
    sql = PULL_SQL.format(project=sources.BQ_PROJECT, where="")
    from google.cloud import bigquery
    c = bigquery.Client.from_service_account_json(str(sources.SA_KEYFILE), project=sources.BQ_PROJECT)
    try:
        tbl = c.query(sql).result().to_arrow(create_bqstorage_client=True)
    finally:
        c.close()
    return tbl.to_pandas()


def _calib(y, p, bins=10):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1)); edges[0], edges[-1] = -1, 2
    idx = np.digitize(p, edges[1:-1])
    return [{"bin": b + 1, "n": int((idx == b).sum()),
             "pred": float(p[idx == b].mean()), "actual": float(y[idx == b].mean())}
            for b in range(bins) if (idx == b).any()]


def main() -> int:
    print("pulling shots (production pipeline)...", flush=True)
    df = build_features(_pull())
    tr = df[df.season <= TRAIN_MAX]
    va = df[df.season == VAL]
    print(f"train(<= {TRAIN_MAX})={len(tr):,} val({VAL})={len(va):,}", flush=True)
    dtr = lgb.Dataset(feature_frame(tr), label=tr["is_goal"].to_numpy("float64"),
                      categorical_feature=CATEGORICAL, free_raw_data=False)
    dva = lgb.Dataset(feature_frame(va), label=va["is_goal"].to_numpy("float64"),
                      categorical_feature=CATEGORICAL, reference=dtr, free_raw_data=False)
    params = dict(objective="binary", metric="binary_logloss", verbosity=-1,
                  num_leaves=63, learning_rate=0.05, min_child_samples=200, num_threads=0)
    model = lgb.train(params, dtr, num_boost_round=2000, valid_sets=[dva],
                      callbacks=[lgb.early_stopping(50, verbose=False)])
    out = {"train_max": TRAIN_MAX, "val": VAL, "n_train": int(len(tr)),
           "iters": model.best_iteration, "by_season": {}}
    for s in REPORT:
        part = df[df.season == s]
        if not len(part):
            continue
        p = model.predict(feature_frame(part)); y = part["is_goal"].to_numpy()
        out["by_season"][s] = {"n": int(len(part)), "auc": float(roc_auc_score(y, p)),
                               "goal_rate": float(y.mean()), "mean_xg": float(p.mean()),
                               "calibration": _calib(y, p)}
        print(f"  {s}: n={len(part):,} AUC={out['by_season'][s]['auc']:.4f}", flush=True)
    (config.REPORTS_DIR / "xg_refit_leakage_clean.json").write_text(json.dumps(out, indent=2))
    print("wrote reports/xg_refit_leakage_clean.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
