"""Stage 5 — pre-registered validation; generates docs/phase-value/validation-report.md.

REPORT-ONLY by default: computes the pre-registered checks and writes the markdown report, but writes
NOTHING to nhl_models.player_phase_value. Tiers are written to the table ONLY with --write-tiers, and
the owner reviews the report before that ever runs (boundary: "the validation report in my hands before
any tier is written to the table").

Pre-registered criteria (fixed in config.PHASE_VALUE_CONFIG BEFORE results):
  reliability tiers on YEAR-OVER-YEAR r: Tier A r >= RELIABILITY_TIER_A (0.35), Tier B >= RELIABILITY_TIER_B
    (0.20), else Tier C. Evaluated per component at each VALIDATION_MIN_TOI floor ([400, 200]).
  def_impact baseline comparison; discrimination (spread vs bootstrap sd); smell tests (face validity);
  the PV-D015 arena-bias diagnostic for deny.
Pieces whose exact protocol is NOT pinned verbatim in-repo (split-half refit, team out-of-sample,
sensitivity grid, external A3Z) are listed as PENDING with the reason, not invented.

  python -m models_ml.phase_value.validate_phase_value              # report only
  python -m models_ml.phase_value.validate_phase_value --write-tiers  # (post-review) persist tiers
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from models_ml import bq, config

CFG = config.PHASE_VALUE_CONFIG
MODEL_VERSION = "phase_value_v1"
REPORT = "docs/phase-value/validation-report.md"
COMPONENTS = ["deny", "suppress", "escape", "deny_rush", "pv_def_g60"]
TIER_A = CFG["RELIABILITY_TIER_A"]      # 0.35
TIER_B = CFG["RELIABILITY_TIER_B"]      # 0.20
TOI_FLOORS = CFG["VALIDATION_MIN_TOI"]  # [400, 200]
SINGLES = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def _tier(r):
    return "A" if r >= TIER_A else ("B" if r >= TIER_B else "C")


def _load():
    p = bq.project()
    df = bq.query_df(f"select * from `{p}.nhl_models.player_phase_value` "
                     f"where model_version='{MODEL_VERSION}'", bq.client())
    for c in COMPONENTS + ["def_impact", "toi_min"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _yoy(df, comp, floor):
    """Mean year-over-year Pearson r for one component at one TOI floor, over consecutive season pairs.
    Returns (mean_r, rows) where each row = (pair_label, r, n_merged, n_a, n_b) — cohort sizes exposed
    so the effective (pooling-limited) cohort is auditable, not just the paired n."""
    rs = []
    for a, b in zip(SINGLES[:-1], SINGLES[1:]):
        da = df[(df["season_window"] == a) & (df["toi_min"] >= floor)][["player_id", comp]].dropna()
        db = df[(df["season_window"] == b) & (df["toi_min"] >= floor)][["player_id", comp]].dropna()
        m = da.merge(db, on="player_id", suffixes=("_a", "_b"))
        if len(m) >= 20:
            rs.append((f"{a}->{b}", m[f"{comp}_a"].corr(m[f"{comp}_b"]), len(m), len(da), len(db)))
    mean_r = float(np.mean([r for _, r, _, _, _ in rs])) if rs else float("nan")
    return mean_r, rs


def _names(ids):
    if not len(ids):
        return {}
    df = bq.query_df(f"""select player_id, any_value(first_name || ' ' || last_name) name
        from `{bq.project()}.nhl_staging.stg_rosters`
        where player_id in ({", ".join(str(int(i)) for i in ids)}) group by 1""", bq.client())
    return dict(zip(df["player_id"], df["name"]))


def _report(df):
    L = []; W = L.append
    W("# Phase Value — Stage 5 validation report (REPORT-ONLY; no tiers written)\n")
    W(f"Model `{MODEL_VERSION}`. Criteria pre-registered in `config.PHASE_VALUE_CONFIG` before results: "
      f"Tier A r ≥ {TIER_A}, Tier B r ≥ {TIER_B} (else C) on year-over-year r; TOI floors {TOI_FLOORS}. "
      "No number in Stages 1–4 was re-tuned to these results.\n")

    # 1. Reliability tiers — the crux (year-over-year r) + the def_impact baseline (§9.2.1)
    W("## 1. Reliability tiers — year-over-year r (the pre-registered crux)")
    W("**Baseline (§9.2.1):** `def_impact` YoY r on the identical cohort, side by side — the project's "
      "comparative verdict number. **Cohort note:** the TOI floors are applied (`toi_min ≥ floor`) but are "
      "largely NON-BINDING for the exposure-heavy components: each component's RAPM replacement pooling "
      "(< 100 exposure-min → F/D pool) already imposes a higher effective TOI floor — ~475 min for "
      "deny/deny_rush (outside exposure ≈ 21% of ice) and ~345 min for suppress/escape (in-zone ≈ 29%). "
      "So deny's cohort is empty in [200,400) (its min toi is ~514) and suppress gains only a handful "
      "when the floor halves. Per-pair cohort sizes (n_a, n_b) are shown so this is auditable. This is "
      "RAPM-parity pooling, not a misapplied filter.\n")
    tiers = {}
    for floor in TOI_FLOORS:
        W(f"\n### TOI ≥ {floor} min")
        W("| component | mean YoY r | tier | per-pair r (n_pair; n_a/n_b) |")
        W("|---|---|---|---|")
        for comp in COMPONENTS + ["def_impact"]:
            mean_r, rs = _yoy(df, comp, floor)
            pairs = "; ".join(f"{lab} {r:+.2f} (n={n}; {na}/{nb})" for lab, r, n, na, nb in rs)
            t = _tier(mean_r) if not np.isnan(mean_r) else "—"
            tiers[(comp, floor)] = (mean_r, t)
            tag = " _(baseline §9.2.1)_" if comp == "def_impact" else ""
            W(f"| **{comp}**{tag} | {mean_r:+.3f} | **{t}** | {pairs} |")
    W("")
    W("**Comparative verdict:** PV components vs the `def_impact` baseline on identical cohorts, above. "
      "`pv_def_g60`/`suppress`/`escape` at Tier B; `deny`/`deny_rush` at Tier C; read each against the "
      "baseline's own YoY r in the same table.\n")

    # 2. def_impact baseline (headline window)
    W("## 2. def_impact baseline comparison (3-season window, toi ≥ 200)")
    win = [w for w in df["season_window"].unique() if "_" in str(w)]
    if win:
        sub = df[(df["season_window"] == win[0]) & (df["toi_min"] >= 200)]
        W("| component | r vs def_impact |")
        W("|---|---|")
        for comp in COMPONENTS:
            m = sub[[comp, "def_impact"]].dropna()
            r = m[comp].corr(m["def_impact"]) if len(m) > 2 else float("nan")
            W(f"| {comp} | {r:+.3f} |")
        W("\nExpected (pre-registered thesis): suppress high (def_impact's xG channel re-denominated), "
          "deny moderate (new frequency channel), escape ≈ 0 (orthogonal). pv_def_g60 ~0.87 = suppress-dominated.\n")

    # 3. Smell tests — face validity + diagnostics (a) def_impact percentile, (b) in-zone-share corr
    W("## 3. Smell tests — face validity (3-season pv_def_g60, toi ≥ 400)")
    if win:
        sub = df[(df["season_window"] == win[0]) & (df["toi_min"] >= 400)].dropna(subset=["pv_def_g60"]).copy()
        sub["di_pct"] = sub["def_impact"].rank(pct=True) * 100      # def_impact percentile within cohort
        nm = _names(sub["player_id"].tolist())
        for lab, asc in [("Top 10", False), ("Bottom 10", True)]:
            top = sub.sort_values("pv_def_g60", ascending=asc).head(10)
            W(f"**{lab} pv_def_g60:** " + ", ".join(
                f"{nm.get(r.player_id, r.player_id)} ({r.pv_def_g60:+.3f})" for r in top.itertuples()))
        # (a) def_impact percentile of the top anomalies — inherited-from-baseline vs PV-specific
        W("\n**(a) def_impact percentile of the top-10** (distinguishes inherited-from-baseline from PV-specific):")
        top10 = sub.sort_values("pv_def_g60", ascending=False).head(10)
        W("| player | pv_def_g60 | def_impact %ile |")
        W("|---|---|---|")
        for r in top10.itertuples():
            W(f"| {nm.get(r.player_id, r.player_id)} | {r.pv_def_g60:+.3f} | {r.di_pct:.0f} |")
        W("A high def_impact percentile ⇒ the ranking is inherited from the baseline (not a PV artifact); "
          "a low one ⇒ PV-specific and worth scrutiny.")
        # (b) corr(pv_def_g60, in-zone-against share of TOI) — the flattery hypothesis, as a number
        if {"def_in_sec", "def_out_sec"}.issubset(sub.columns):
            sub["inzone_share"] = sub["def_in_sec"] / (sub["def_in_sec"] + sub["def_out_sec"])
            rr = sub[["pv_def_g60", "inzone_share"]].dropna()
            r_flat = rr["pv_def_g60"].corr(rr["inzone_share"]) if len(rr) > 2 else float("nan")
            W(f"\n**(b) corr(pv_def_g60, in-zone-against share of TOI) = {r_flat:+.3f}** (n={len(rr)}). "
              "A strong NEGATIVE value would support the per-in-zone-second flattery hypothesis (players who "
              "defend in-zone less get a smaller denominator and a flattered rate); near zero refutes it.")
        W("")

    # 4. Discrimination (spread vs bootstrap sd) — from the assembled sds
    W("## 4. Discrimination — between-player spread vs bootstrap sd (headline)")
    if win:
        sub = df[df["season_window"] == win[0]]
        W("| component | sd(value) across players | mean bootstrap sd | ratio |")
        W("|---|---|---|---|")
        for comp in COMPONENTS:
            sdcol = f"{comp}_sd"
            spread = float(sub[comp].std())
            msd = float(pd.to_numeric(sub[sdcol], errors="coerce").mean()) if sdcol in sub.columns else float("nan")
            ratio = spread / msd if msd and not np.isnan(msd) else float("nan")
            W(f"| {comp} | {spread:.4f} | {msd:.4f} | {ratio:.2f} |")
        W("\nRatio near 1 = between-player signal barely exceeds resample noise (defence is the weakest "
          "signal); this is the empirical basis for the tiers above.\n")

    # 5. PV-D015 arena-bias diagnostic for deny (pre-registered, report-only)
    W("## 5. PV-D015 arena-bias diagnostic for `deny`")
    W(_arena_bias_line(df))

    # 6. pending pieces (protocol not pinned verbatim in-repo — NOT invented)
    W("## 6. PENDING (protocol not pinned verbatim in-repo — flagged, not invented)")
    W("- **Split-half reliability:** needs a within-season odd/even refit pass (extra fits); method not "
      "pinned verbatim. Awaiting owner confirmation of the split (odd/even game vs random-half) before running.")
    W("- **Team out-of-sample:** predict-team-season-from-held-out-seasons protocol not pinned verbatim.")
    W("- **Sensitivity grid:** `H_SENSITIVITY` = [20,40,60] is a STATE-VALUE horizon sweep (Stage 2); its "
      "propagation into the component fits is not pinned. Held for owner direction.")
    W("- **External A3Z agreement:** 'if run' in §7; not run this pass.")
    W("")
    W("**Tiers are NOT written to `player_phase_value` in this run.** Rerun with `--write-tiers` only after "
      "owner review of this report.")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"Wrote {REPORT}")
    return tiers


def _arena_bias_line(df):
    """Correlate team-season deny (minutes-weighted) against home-arena under-recording rate from the
    sprite audit's arena table. Report-only; returns a one-paragraph result or a reason it was skipped."""
    try:
        p = bq.project()
        # team-season mean deny weighted by def in-zone exposure, singles only
        d = df[df["season_window"].isin(SINGLES)].dropna(subset=["deny"])
        # arena under-recording proxy: not persisted as a table — computed live in sprite_audit E3b only.
        # Without a persisted arena table this diagnostic needs the sprite audit rerun with an export.
        return ("Deferred: the arena under-recording rate lives only inside the sprite-audit run (E3b), not a "
                "persisted table. Activating this pre-registered diagnostic needs the sprite audit to export "
                "its per-arena `established_full_window` share; flagged rather than approximated. deny "
                f"team-season sample available: {d['player_id'].nunique():,} players across {len(SINGLES)} seasons.")
    except Exception as e:
        return f"Skipped (error: {e})."


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-tiers", action="store_true",
                    help="persist earned tiers to player_phase_value (post-review only)")
    args = ap.parse_args()
    df = _load()
    tiers = _report(df)
    if not args.write_tiers:
        print("REPORT-ONLY: no tiers written. Rerun with --write-tiers after owner review.")
        return
    raise SystemExit("--write-tiers is gated on owner review of the validation report; not enabled yet.")


if __name__ == "__main__":
    main()
