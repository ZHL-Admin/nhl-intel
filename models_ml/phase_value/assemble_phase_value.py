"""Stage 4 — goals accounting and assembly of nhl_models.player_phase_value + the overlap report.

Reads the Stage-3 component caches (artifacts/phase_value/components_<window>.parquet from
train_phase_value.py), prices the rate coefficients in goals/60 via the Stage-2 league constants
(nhl_models.phase_league_constants), joins the RAPM def_impact baseline, writes one row per
(player_id, season_window) to nhl_models.player_phase_value, and generates the Stage-4 overlap report.

Accounting (PV-D018, derived from the published constants — §6 to be confirmed by owner):
  deny is episodes-suppressed per 60 min of OUTSIDE exposure; a team spends s_out_min_per_60 of every
    60 ice-minutes outside, and each non-faceoff episode costs c_seq_xg_nonfo xG, so
      deny_g60     = deny     * (s_out_min_per_60 / 60) * c_seq_xg_nonfo
  suppress is xG-suppressed per 60 min of IN-ZONE exposure; a team spends s_in_min_per_60 of every 60
    ice-minutes defending in-zone, so
      suppress_g60 = suppress * (s_in_min_per_60 / 60)
  escape is published as a RATE in v1 (favourable episode-ends per 60 min in-zone), NOT priced in goals.
  pv_def_g60   = deny_g60 + suppress_g60   (goals saved per 60 of ice time; comparable to def_impact)

pv_def_g60_sd is LEFT NULL in this pass: the composite sd must come from SHARED bootstrap resamples
(deny and suppress are positively correlated through the same game-resampling; quadrature would
under-state it). That joint bootstrap is the next construction step — not shipped as a wrong number.

Run AFTER train_phase_value.py has cached the component frames.
  python -m models_ml.phase_value.assemble_phase_value            # writes the table + report
  python -m models_ml.phase_value.assemble_phase_value --dry-run  # report only, no BigQuery write
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

from models_ml import bq, config

MODEL_VERSION = "phase_value_v1"
ARTDIR = "artifacts/phase_value"
REPORT = "artifacts/phase_value/overlap_report.md"
CORR_TOI_MIN = 200          # qualified set for correlations (mirrors RAPM report threshold)
CORR_TOI_HIGH = 1000        # spec's high-cohort correlation threshold (reported alongside ≥200)
COMPONENTS = ["deny", "suppress", "escape", "deny_rush"]


def _constants():
    p = bq.project()
    df = bq.query_df(f"select constant_name, value from `{p}.nhl_models.phase_league_constants` "
                     f"where model_version='{MODEL_VERSION}'", bq.client())
    return dict(zip(df["constant_name"], df["value"].astype(float)))


def _load_components():
    frames = [pd.read_parquet(f) for f in sorted(glob.glob(f"{ARTDIR}/components_*.parquet"))]
    if not frames:
        raise SystemExit(f"no component caches in {ARTDIR}/ — run train_phase_value.py first")
    return pd.concat(frames, ignore_index=True)


def _price(df, k):
    # spec §8.1: deny_g60 = a*(s_out/60)*C_seq*cal ; suppress_g60 = b*(s_in/60)*cal ;
    #            escape rate only ; pv_def_g60 = deny_g60 + suppress_g60
    s_out, s_in, c_seq = k["s_out_min_per_60"], k["s_in_min_per_60"], k["c_seq_xg_nonfo"]
    cal = k.get("xg_calibration", 1.0)
    df["deny_g60"] = df["deny"] * (s_out / 60.0) * c_seq * cal
    df["suppress_g60"] = df["suppress"] * (s_in / 60.0) * cal
    df["escape_rate"] = df["escape"]                       # published as a rate (v1)
    df["pv_def_g60"] = df["deny_g60"] + df["suppress_g60"]
    # pv_def_g60_sd comes from train's within-resample composite bootstrap (§8.1); keep it if present
    if "pv_def_g60_sd" not in df.columns:
        df["pv_def_g60_sd"] = np.nan
    return df


def _def_impact():
    p = bq.project()
    return bq.query_df(f"select player_id, season_window, def_impact, toi_min "
                       f"from `{p}.nhl_models.player_impact`", bq.client())


def _weighted_corr(df, cols, wcol):
    w = df[wcol].to_numpy(float)
    M = df[cols].to_numpy(float)
    ok = np.isfinite(M).all(axis=1) & np.isfinite(w) & (w > 0)
    M, w = M[ok], w[ok]
    mu = np.average(M, axis=0, weights=w)
    Mc = M - mu
    cov = (Mc * w[:, None]).T @ Mc / w.sum()
    sd = np.sqrt(np.diag(cov))
    denom = np.outer(sd, sd)
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.where(denom > 0, cov / denom, np.nan)
    return corr, int(ok.sum())


def _corr_block(W, sub, label, thr):
    cols = COMPONENTS + ["pv_def_g60", "def_impact"]
    have = [c for c in cols if c in sub.columns]
    corr, n = _weighted_corr(sub, have, "def_in_sec")
    W(f"### {label} — exposure-weighted correlations (qualified: toi ≥ {thr} min, n={n})")
    W("| | " + " | ".join(have) + " |")
    W("|" + "---|" * (len(have) + 1))
    for i, r in enumerate(have):
        cells = " | ".join(f"{corr[i, j]:+.2f}" if np.isfinite(corr[i, j]) else "·" for j in range(len(have)))
        W(f"| **{r}** | {cells} |")
    W("")


def _report(assembled, diags, cap, k):
    L = []; W = L.append
    W("# Phase Value — Stage 4 overlap report (REPORT-ONLY; pre-validation review)\n")
    W(f"Model `{MODEL_VERSION}`. Components are defence-side, higher = better. Accounting priced with "
      f"s_out_min_per_60={k['s_out_min_per_60']:.2f}, s_in_min_per_60={k['s_in_min_per_60']:.2f}, "
      f"c_seq_xg_nonfo={k['c_seq_xg_nonfo']:.4f} (PV-D018).\n")

    # (d) wiring gate per target per window
    W("## (d) Wiring gate — team-season reconciliation per target (hard gate r ≥ 0.80)")
    W("Exposure-weighted actual vs model-predicted target aggregated by (defending team, season). This "
      "is a WIRING DIAGNOSTIC, not a reliability test: the single-season fits are the sharp check "
      "(r≈0.97–0.99); the 3-season window's softening (deny 0.819) is expected shrinkage from "
      "season-weighting + replacement pooling, and both the actual and predicted sides use the same "
      "0.3/0.6/1.0 season weights (PV-D019 / owner ruling 2).\n")
    W("| window | fit | wiring_r | gate | n_team_seasons |")
    W("|---|---|---|---|---|")
    for _, r in diags.sort_values(["window", "fit"]).iterrows():
        gate = "PASS" if r["wiring_r"] >= 0.80 else "**FAIL**"
        W(f"| {r['window']} | {r['fit']} | {r['wiring_r']:.3f} | {gate} | {int(r['n_team_seasons'])} |")
    W("")

    # (e) defence-coef spread vs mean bootstrap sd per fit per window
    W("## (e) Defence-coefficient spread vs mean bootstrap sd, per fit")
    W("spread/sd > 1 means between-player signal exceeds resample noise; near 1 = weak reliability.\n")
    W("| window | fit | coef_spread | mean_boot_sd | spread/sd |")
    W("|---|---|---|---|---|")
    for _, r in diags.sort_values(["window", "fit"]).iterrows():
        W(f"| {r['window']} | {r['fit']} | {r['coef_spread']:.4f} | {r['mean_boot_sd']:.4f} | {r['spread_over_sd']:.2f} |")
    W("")

    # (b) component correlation matrix incl vs def_impact, per window — BOTH cohorts (≥200 and ≥1000 min)
    W("## (b) Component overlap — correlation matrix incl. vs def_impact")
    W("Reported at two cohorts: the ≥200-min set and the spec's ≥1000-min cohort.\n")
    for win in sorted(assembled["season_window"].unique()):
        for thr in (CORR_TOI_MIN, CORR_TOI_HIGH):
            sub = assembled[(assembled["season_window"] == win) & (assembled["toi_min"] >= thr)]
            if len(sub) >= 20:
                _corr_block(W, sub, f"{win} (toi ≥ {thr})", thr)

    # (c) PV-D011 capture counts — per-EPISODE (k=1), from the design capture totals (PV-D019)
    W("## (c) PV-D011 captured counts (zero-duration goal episodes are kept)")
    W("Per-EPISODE totals (k=1) direct from the design (home+away direction-summed = each episode once; "
      "NOT the per-defender ×5 aggregation — PV-D019). The ≥5s floor is on stint-direction totals, never "
      "per-episode, so these zero-duration starts/xG remain in Fit A's counts and Fit B's xG mass.\n")
    W("| window | nonfo episodes | zero-dur starts | zerodur % | in-zone xG | zero-dur xG | zerodur xG % |")
    W("|---|---|---|---|---|---|---|")
    for _, s in cap.sort_values("window").iterrows():
        en, ez, xn, xz = s["ep_nonfo"], s["ep_nonfo_zerodur"], s["xg_inzone"], s["xg_inzone_zerodur"]
        W(f"| {s['window']} | {en:,.0f} | {ez:,.0f} | {ez/en*100:.2f}% | {xn:,.1f} | {xz:,.1f} | {xz/xn*100:.2f}% |")
    W("")

    # headline overlap summary vs def_impact
    W("## Headline: pv_def_g60 vs def_impact (3-season window)")
    win = [w for w in assembled["season_window"].unique() if "_" in w]
    if win:
        sub = assembled[(assembled["season_window"] == win[0]) & (assembled["toi_min"] >= CORR_TOI_MIN)].copy()
        m = sub[["pv_def_g60", "def_impact"]].dropna()
        r = m["pv_def_g60"].corr(m["def_impact"]) if len(m) > 2 else float("nan")
        W(f"n={len(m)} qualified players; Pearson r(pv_def_g60, def_impact) = **{r:+.3f}**. "
          "A modest positive correlation is the design expectation (shared defensive signal, different "
          "channels: PV prices transition frequency + in-episode intensity; def_impact prices shot xG only).\n")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"Wrote {REPORT}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="build the report only; do not write BigQuery")
    args = ap.parse_args()

    k = _constants()
    comp = _load_components()
    comp = _price(comp, k)
    di = _def_impact()
    assembled = comp.merge(di, on=["player_id", "season_window"], how="left")

    diags = pd.read_parquet(f"{ARTDIR}/diagnostics.parquet")
    cap = pd.read_parquet(f"{ARTDIR}/capture_totals.parquet")
    _report(assembled, diags, cap, k)

    out_cols = (["player_id", "season_window"] + COMPONENTS + [f"{c}_sd" for c in COMPONENTS]
                + ["deny_g60", "suppress_g60", "escape_rate", "pv_def_g60", "pv_def_g60_sd",
                   "def_out_sec", "def_in_sec", "def_ep_nonfo", "def_ep_nonfo_zerodur",
                   "def_xg_in", "def_xg_in_zerodur", "def_impact", "toi_min"])
    out = assembled[[c for c in out_cols if c in assembled.columns]].copy()
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = MODEL_VERSION
    print(f"assembled {len(out):,} player-window rows across {out['season_window'].nunique()} windows")
    if args.dry_run:
        print("--dry-run: not writing to BigQuery.")
        return
    bq.write_df(out, "player_phase_value", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "player_id"])
    print(f"Wrote {len(out):,} rows to {config.MODELS_DATASET}.player_phase_value.")


if __name__ == "__main__":
    main()
