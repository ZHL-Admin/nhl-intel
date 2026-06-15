"""
Per-shot xG prediction with additive decomposition (Phase 2.2).

LightGBM's ``pred_contrib=True`` returns per-feature contributions in LOG-ODDS space plus
a trailing base value. We roll the feature contributions up into the named buckets from
xg_features.FEATURE_BUCKETS and convert them to PROBABILITY-space deltas by applying each
bucket sequentially from the base rate. The five bucket deltas plus base_rate sum exactly
to xg, so the product can say "0.21 xG: location +0.12, rebound +0.05, ...".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models_ml.xg_features import FEATURE_BUCKETS, feature_frame


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def predict_with_decomposition(model, df_feat: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with xg, base_rate, and one xg_contrib_<bucket> per bucket.
    Probability-space contributions + base_rate sum to xg by construction."""
    X = feature_frame(df_feat)
    contribs = model.predict(X, pred_contrib=True)  # (n, n_features + 1), log-odds
    feat_names = model.feature_name()
    name_to_idx = {n: i for i, n in enumerate(feat_names)}

    base = contribs[:, -1]
    cum = base.copy()
    out: dict[str, np.ndarray] = {"base_rate": _sigmoid(base)}
    for bucket, feats in FEATURE_BUCKETS.items():
        idx = [name_to_idx[f] for f in feats]
        delta = contribs[:, idx].sum(axis=1)
        before = _sigmoid(cum)
        cum = cum + delta
        after = _sigmoid(cum)
        out[f"xg_contrib_{bucket}"] = after - before
    out["xg"] = _sigmoid(cum)
    return pd.DataFrame(out, index=df_feat.index)
