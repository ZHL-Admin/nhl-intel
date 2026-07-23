"""§9.3 sensitivity — refit deny/suppress/escape on 2023-24 & 2024-25 under a variant episode definition
and report YoY + split-half movement vs the baseline. The variant tables live in a `phase_schema` dataset
(nhl_staging_sens) built by dbt with --target sens --defer (prod is read-only); baseline = nhl_staging.

Run (after the dbt variant build):
  python -m models_ml.phase_value.sensitivity --phase-schema nhl_staging      --label baseline_gap4_opp
  python -m models_ml.phase_value.sensitivity --phase-schema nhl_staging_sens --label gap2
Appends to artifacts/phase_value/sensitivity.parquet (keyed by --label).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from models_ml import train_rapm as R
from models_ml.phase_value import build_design as BD, train_phase_value as T

SEASONS = ("2023-24", "2024-25")
ARTPATH = "artifacts/phase_value/sensitivity.parquet"


def _fit_value(rows, sign, pos, alpha=None):
    X, y, w, g, players, npl, _ = R.build_design(rows, two_sided=True, pos=pos)
    if alpha is None:
        alpha, _ = R.cv_alpha(X, y, w, g)
    m = Ridge(alpha=alpha, solver="lsqr", fit_intercept=True, max_iter=3000)
    m.fit(X, y, sample_weight=w)
    dc = m.coef_[npl:2 * npl]; dc = dc - dc.mean()
    return dict(zip(players, sign * dc)), alpha


def _r(a, b):
    common = [p for p in a if p in b and p >= 0]
    if len(common) < 10:
        return float("nan")
    return float(np.corrcoef([a[p] for p in common], [b[p] for p in common])[0, 1])


def run(phase_schema, label):
    full, halves = {}, {}
    for season in SEASONS:
        df = BD.pull([season], phase_schema=phase_schema)
        b2b = T._b2b([season]); pos = R.positions([season])
        dr = BD.expand_rows(df, b2b, None)
        for name, (num, expo, sign) in T.FITS.items():
            rows, _ = T._rows_for_fit(dr, num, expo)
            full[(season, name)], alpha = _fit_value(rows, sign, pos)
            hv = {}
            for par in (0, 1):
                r2, _ = T._rows_for_fit([d for d in dr if int(d["game_id"]) % 2 == par], num, expo)
                hv[par], _ = _fit_value(r2, sign, pos, alpha=alpha)   # halves share the full-season alpha
            halves[(season, name)] = hv
    out = []
    for name in T.FITS:
        yoy = _r(full[(SEASONS[0], name)], full[(SEASONS[1], name)])
        sb = []
        for season in SEASONS:
            hv = halves[(season, name)]; r = _r(hv[0], hv[1])
            sb.append(2 * r / (1 + r) if r > -1 else float("nan"))
        out.append(dict(variant=label, component=name, yoy_r=round(yoy, 3),
                        sh_2324=round(sb[0], 3), sh_2425=round(sb[1], 3)))
    return pd.DataFrame(out)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase-schema", default="nhl_staging")
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    out = run(args.phase_schema, args.label)
    print(out.to_string(index=False))
    os.makedirs("artifacts/phase_value", exist_ok=True)
    if os.path.exists(ARTPATH):
        prev = pd.read_parquet(ARTPATH)
        out = pd.concat([prev[prev["variant"] != args.label], out], ignore_index=True)
    out.to_parquet(ARTPATH, index=False)
    print(f"appended '{args.label}' to {ARTPATH}")


if __name__ == "__main__":
    main()
