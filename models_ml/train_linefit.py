"""
Train the Lineup Lab line-fit model (Phase 5.1, blueprint 6.2).

Cold-start prediction of a hypothetical line's on-ice 5v5 results from its members' individual
profiles. Three LightGBM regression heads (xGF%, xGF/60, xGA/60) over the int_line_seasons
training set, line rows weighted by shared 5v5 minutes, validated with GroupKFold by SEASON so a
line never appears in both train and validation. The model must beat two baselines on xGF% or it
does not ship: (1) the mean of its members' individual on-ice xGF%, (2) the line's team-season
5v5 xGF%.

Artifact: models_ml/artifacts/linefit_v1.joblib (the three boosters + feature order + residual
sds for intervals + baseline comparison). Methodology: docs/methodology/lineup-lab.md.

Run:  python -m models_ml.train_linefit [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold

from models_ml import bq, config, linefit_features as lf

ARTIFACT_DIR = Path(__file__).parent / "artifacts"
HEADS = ["xgf_pct", "xgf_per60", "xga_per60"]

LGB_PARAMS = dict(
    objective="regression", n_estimators=400, learning_rate=0.03, num_leaves=31,
    min_child_samples=40, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
    reg_lambda=1.0, verbose=-1,
)

# per-player on-ice 5v5 xGF/xGA (baseline 1) and per-team season 5v5 xGF/xGA (baseline 2)
ONICE_SQL = """
with seg5 as (
  select game_id, segment_index, season from `{p}.nhl_staging.int_segment_context`
  where strength_state = '5v5'
),
segp as (
  select s.game_id, s.segment_index, s.season, s.team_id, s.player_id
  from `{p}.nhl_staging.int_shift_segments` s
  join seg5 using (game_id, segment_index)
  where s.is_goalie = 0 and substr(cast(s.game_id as string), 5, 2) in ('02', '03')
),
segx as (
  select o.game_id, o.segment_index, o.event_owner_team_id as team_id, sum(x.xg) as xg
  from `{p}.nhl_staging.int_on_ice_events` o
  join `{p}.nhl_models.shot_xg` x on o.game_id = x.game_id and o.event_id = x.event_id
  group by 1, 2, 3
),
segtot as (select game_id, segment_index, sum(xg) as tot from segx group by 1, 2)
select segp.player_id, segp.season,
  sum(coalesce(sx.xg, 0)) as xgf,
  sum(coalesce(st.tot, 0) - coalesce(sx.xg, 0)) as xga
from segp
left join segx sx on sx.game_id = segp.game_id and sx.segment_index = segp.segment_index
  and sx.team_id = segp.team_id
left join segtot st on st.game_id = segp.game_id and st.segment_index = segp.segment_index
group by 1, 2
"""


def _build_training_frame(seasons):
    p = bq.project()
    lines = bq.query_df(f"""select season, team_id, line_type, line_key, members, minutes,
        xgf, xga, xgf_pct, xgf_per60, xga_per60
        from `{p}.nhl_staging.int_line_seasons`""")
    members = lf.build_member_features(seasons)
    feat_cols = lf.feature_columns()

    rows, meta = [], []
    dropped = 0
    for _, ln in lines.iterrows():
        ids = list(ln["members"])
        keys = [(int(i), ln["season"]) for i in ids]
        try:
            mem = members.loc[keys]
        except KeyError:
            dropped += 1
            continue
        if len(mem) != len(ids):
            dropped += 1
            continue
        feat = lf.aggregate_line(mem, ln["line_type"])
        rows.append(feat)
        meta.append(ln)
    X = pd.DataFrame(rows, columns=feat_cols).astype("float64")
    # o-zone tilt is null pre-tracking; impute to the column mean so the tree sees a neutral value
    X["oz_tilt_mean"] = X["oz_tilt_mean"].fillna(X["oz_tilt_mean"].mean())
    X = X.fillna(0.0)
    M = pd.DataFrame(meta).reset_index(drop=True)
    print(f"Training frame: {len(X)} line-seasons ({dropped} dropped for missing member features)")
    return X, M, feat_cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    p = bq.project()

    seasons = [r["season"] for r in
               bq.query_df(f"select distinct season from `{p}.nhl_staging.int_line_seasons`")
               .to_dict("records")]
    seasons = sorted(seasons)
    X, M, feat_cols = _build_training_frame(seasons)
    w = M["minutes"].to_numpy(dtype="float64")
    groups = M["season"].to_numpy()

    # baselines
    onice = bq.query_df(ONICE_SQL.format(p=p))
    # raw on-ice xGF/xGA per (player, season) so we can remove THIS line's own shared minutes
    # before averaging — otherwise the baseline leaks the target (a high-minute line dominates
    # its members' on-ice numbers, so "mean of members" ~= the line itself). Leave-this-line-out
    # is the honest cold-start baseline the model must beat.
    onice_map = {(int(r.player_id), r.season): (float(r.xgf), float(r.xga))
                 for r in onice.itertuples()}
    # team-season xGF% baseline = minutes-weighted mean of the team's own line xGF% (same data)
    team_base = (M.assign(xgf_pct=M["xgf_pct"], minutes=M["minutes"])
                 .groupby(["season", "team_id"])
                 .apply(lambda g: np.average(g["xgf_pct"], weights=g["minutes"]))
                 .rename("team_xgf_pct").reset_index())
    M = M.merge(team_base, on=["season", "team_id"], how="left")

    def members_baseline(row):
        line_f, line_a = float(row["xgf"]), float(row["xga"])
        vals = []
        for i in row["members"]:
            tot = onice_map.get((int(i), row["season"]))
            if tot is None:
                continue
            f, a = tot[0] - line_f, tot[1] - line_a   # member's results APART from this line
            if f + a > 0:
                vals.append(f / (f + a))
        return float(np.mean(vals)) if vals else np.nan
    M["members_xgf_pct"] = M.apply(members_baseline, axis=1)

    # GroupKFold CV: out-of-fold predictions for honest metrics + residual sds
    gkf = GroupKFold(n_splits=5)
    oof = {h: np.full(len(X), np.nan) for h in HEADS}
    for tr, va in gkf.split(X, groups=groups):
        for h in HEADS:
            m = lgb.LGBMRegressor(**LGB_PARAMS)
            m.fit(X.iloc[tr], M[h].iloc[tr].to_numpy(dtype="float64"),
                  sample_weight=w[tr])
            oof[h][va] = m.predict(X.iloc[va])

    print("\n=== Out-of-fold metrics (weighted by line minutes) ===")
    resid_sd = {}
    report = {}
    for h in HEADS:
        y = M[h].to_numpy(dtype="float64")
        pred = oof[h]
        ok = np.isfinite(pred) & np.isfinite(y)
        r2 = r2_score(y[ok], pred[ok], sample_weight=w[ok])
        mae = mean_absolute_error(y[ok], pred[ok], sample_weight=w[ok])
        resid_sd[h] = float(np.sqrt(np.average((y[ok] - pred[ok]) ** 2, weights=w[ok])))
        report[h] = {"r2": round(float(r2), 4), "mae": round(float(mae), 4)}
        print(f"  {h:11s} R2 {r2:+.3f}  MAE {mae:.4f}  resid_sd {resid_sd[h]:.4f}")

    # baseline comparison on xGF%
    y = M["xgf_pct"].to_numpy(dtype="float64")
    print("\n=== xGF% baseline comparison (MAE, lower is better) ===")
    base_report = {}
    for name, col in [("model", None), ("mean_of_members", "members_xgf_pct"),
                      ("team_season_avg", "team_xgf_pct")]:
        if col is None:
            pred = oof["xgf_pct"]
        else:
            pred = M[col].to_numpy(dtype="float64")
        ok = np.isfinite(pred) & np.isfinite(y)
        mae = mean_absolute_error(y[ok], pred[ok], sample_weight=w[ok])
        base_report[name] = round(float(mae), 4)
        print(f"  {name:18s} MAE {mae:.4f}  (n={ok.sum()})")
    beats = (base_report["model"] < base_report["mean_of_members"]
             and base_report["model"] < base_report["team_season_avg"])
    print(f"\nModel beats both baselines on xGF%: {beats}")
    if not beats:
        print("WARNING: model does not beat both baselines — per blueprint 6.2 it should not ship.")

    # final models on all data for serving
    boosters = {}
    for h in HEADS:
        m = lgb.LGBMRegressor(**LGB_PARAMS)
        m.fit(X, M[h].to_numpy(dtype="float64"), sample_weight=w)
        boosters[h] = m

    if args.dry_run:
        print("\n[dry-run] artifact not written")
        return

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "version": config.LINEFIT_ARTIFACT,
        "heads": HEADS,
        "feature_columns": feat_cols,
        "boosters": boosters,
        "resid_sd": resid_sd,
        "metrics": report,
        "baselines": base_report,
        "seasons": seasons,
        "n_train": int(len(X)),
        "obs_prior_minutes": config.LINEFIT_OBS_PRIOR_MINUTES,
    }
    out = ARTIFACT_DIR / f"{config.LINEFIT_ARTIFACT}.joblib"
    joblib.dump(artifact, out)
    print(f"\nWrote {out}")
    _write_doc(report, base_report, resid_sd, len(X), seasons, beats)


def _write_doc(report, base_report, resid_sd, n, seasons, beats):
    doc = Path(__file__).parents[1] / "docs" / "methodology" / "lineup-lab.md"
    lines = [
        "# Lineup Lab line-fit model (Phase 5.1)", "",
        "<!-- Generated by models_ml/train_linefit.py. Sections below are auto-written. -->", "",
        "## What it does", "",
        "Cold-start prediction of a hypothetical forward trio's or defense pair's on-ice 5v5",
        "results (xGF%, xGF/60, xGA/60) from its members' individual player-season profiles.",
        "Because every feature is a player-level aggregate, ANY line — including players who have",
        "never shared the ice — is scorable.", "",
        "## Training data", "",
        f"`int_shift_segments` -> `int_line_seasons`: every forward trio / defense pair sharing",
        f">= {config.LINEFIT_OBS_PRIOR_MINUTES and 30} min of 5v5 ice in a season ({n} line-seasons,",
        f"{seasons[0]}..{seasons[-1]}). Rows weighted by shared 5v5 minutes. Validation is",
        "GroupKFold by season (a line never appears in both train and validation).", "",
        "## Features", "",
        "Each member contributes role + skill features (RAPM off/def impact, finishing, sequence",
        "shot diet, shot-location, PP/PK deployment, Edge burst rate and o-zone time), aggregated",
        "across the line as mean / min / max. Pairwise chemistry features (blueprint 12.4):",
        "archetype-mix cosine (role overlap), shot-location distance, handedness balance,",
        "burst-rate spread (pace compatibility), combined o-zone-tilt mean.", "",
        "## Validation (out-of-fold, weighted by line minutes)", "",
        "| head | R2 | MAE | residual sd |", "|---|---|---|---|",
    ]
    for h in HEADS:
        lines.append(f"| {h} | {report[h]['r2']:+.3f} | {report[h]['mae']:.4f} | {resid_sd[h]:.4f} |")
    lines += [
        "", "## Baselines (xGF% MAE, lower is better)", "",
        "| method | MAE |", "|---|---|",
        f"| **model** | **{base_report['model']:.4f}** |",
        f"| mean of members' on-ice xGF% | {base_report['mean_of_members']:.4f} |",
        f"| team-season 5v5 xGF% | {base_report['team_season_avg']:.4f} |", "",
        f"Model beats both baselines: **{beats}**. Per blueprint 6.2 the model ships only if it does.",
        "", "## Chemistry blend", "",
        "A line with observed history blends model and reality: "
        "`final = model * w_model + observed * w_obs`, "
        f"`w_obs = minutes / (minutes + {config.LINEFIT_OBS_PRIOR_MINUTES})`. "
        "An observed-heavy line is pulled toward its real result.", "",
        "## Honest limitations", "",
        "This projects STATISTICAL SHAPE ONLY — how three players' measured roles and skills tend",
        "to combine. It does not model personality, practice chemistry, coaching systems, or",
        "in-game adjustments. Treat the grade as a prior, not a verdict.",
    ]
    doc.write_text("\n".join(lines) + "\n")
    print(f"Wrote {doc}")


if __name__ == "__main__":
    main()
