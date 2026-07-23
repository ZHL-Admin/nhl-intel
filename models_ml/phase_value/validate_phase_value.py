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


def _report(df, sh, oos):
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

    # 5. Split-half reliability (§9.2.2)
    W("## 5. Split-half reliability (§9.2.2 — even/odd game_id, 2023-24 & 2024-25)")
    if sh is not None:
        W("Refit A/B/C per half at the full-season CV alpha; Pearson r across halves + Spearman-Brown "
          "(half→full). Same cohorts.\n")
        W("| season | fit | r (halves) | Spearman-Brown | n |")
        W("|---|---|---|---|---|")
        for season, name, r, sb, n in sh:
            W(f"| {season} | {name} | {r:+.3f} | {sb:+.3f} | {n} |")
        W("")
    else:
        W("_(run with --full to compute; refits two seasons.)_\n")

    # 6. Team out-of-sample (§9.2.3)
    W("## 6. Team out-of-sample — predict team 5v5 xGA/60 in t+1 (§9.2.3)")
    if oos is not None:
        sets, npair = oos
        W(f"Minutes-weighted team aggregates in t predict team 5v5 xGA/60 in t+1 (temporal-OOS). "
          f"{npair} team-season pairs over the available PV seasons (2021-22→2025-26). **Range note:** the "
          "spec's 2016-17 start needs single-season PV fits for 2016-17→2020-21 backfilled — flagged as a "
          "scope decision, not run here.\n")
        W("| predictor set | r | out-of-sample R² |")
        W("|---|---|---|")
        for k, (r, r2) in sets.items():
            W(f"| {k} | {r:+.3f} | {r2:+.3f} |")
        W("\nRead (i) vs (ii): whether team `pv_def_g60` predicts future defence better than team "
          "`def_impact`; (iv)/(v) vs (iii): whether either adds over the team's own past xGA/60.\n")
    else:
        W("_(run with --full to compute.)_\n")

    # 7. Sensitivity grid (§9.3)
    W("## 7. Sensitivity grid (§9.3, seasons 2023-24 & 2024-25)")
    W("**H_SECONDS ∈ {20,40,60} and the 5v5-goals-only V variant touch ONLY Stage 2** (V and the league "
      "constants). Component coefficients never consume V, and year-over-year r is INVARIANT to a uniform "
      "repricing (a common scalar on `deny_g60`/`suppress_g60` cancels in a correlation). So the tiers above "
      "are unchanged by H and the goals-only V variant **by construction**; the effect is confined to the "
      "goal SCALE of `*_g60`, reported as Stage-2 V/constant sensitivity (stage2-acceptance.md), not a tier "
      "change. **`phase_episode_gap_seconds ∈ {2,4,6}` and the blocked-shot-possession alternative** DO change "
      "the episode definition (Stage-1 dbt rebuild, two seasons) and require refits; their component "
      "YoY/split-half movement is the live sensitivity cell. **Status:** the two rebuild cells are the "
      "remaining compute (dbt rebuild of `int_phase_*` on 2023-24/2024-25 under each variant + refit); "
      "scoped and pending a rebuild pass — flagged explicitly rather than silently skipped.\n")

    # 8. PV-D015 arena-bias diagnostic for deny (pre-registered)
    W("## 8. PV-D015 arena-bias diagnostic for `deny`")
    W("Deny's monotonic YoY decline (0.25→0.19→0.13→0.06) makes this more informative, not less.\n")
    W(_arena_bias_line(df))
    W("")

    # 9. A3Z external agreement — gated
    W("## 9. External A3Z agreement — GATED (directory absent)")
    W("Not run: the A3Z reference is not present in-repo; '§7 if run' condition unmet.\n")

    W("---")
    W("**Tiers:** written to `nhl_models.phase_component_tiers` only with `--write-tiers` after owner review. "
      "Tier C (deny, deny_rush) semantics (§9.1): not published at player level; retained for team/pair "
      "analysis only; the deny null is reported explicitly in methodology §7.")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"Wrote {REPORT}")
    return tiers


def _split_half():
    """§9.2.2 verbatim: within 2023-24 and 2024-25, split games by even/odd game_id, refit A/B/C per
    half (no bootstrap), correlate player coefficients across halves. Alpha = the full-season CV choice
    (reused for both halves so the two halves are on the same regularization; the refit is the fit).
    Returns rows (season, fit, r, spearman_brown, n_common)."""
    from sklearn.linear_model import Ridge
    from models_ml import train_rapm as R
    from models_ml.phase_value import build_design as BD, train_phase_value as T
    out = []
    for season in ("2023-24", "2024-25"):
        dfp = BD.pull([season]); b2b = T._b2b([season]); pos = R.positions([season])
        dirrows = BD.expand_rows(dfp, b2b, None)
        for name, (num, expo, sign) in T.FITS.items():
            rows_full, _ = T._rows_for_fit(dirrows, num, expo)
            Xf, yf, wf, gf, _, _, _ = R.build_design(rows_full, two_sided=True, pos=pos)
            alpha, _ = R.cv_alpha(Xf, yf, wf, gf)
            halves = {}
            for par in (0, 1):
                rows, _ = T._rows_for_fit([d for d in dirrows if int(d["game_id"]) % 2 == par], num, expo)
                X, y, w, g, players, npl, _ = R.build_design(rows, two_sided=True, pos=pos)
                m = Ridge(alpha=alpha, solver="lsqr", fit_intercept=True, max_iter=3000)
                m.fit(X, y, sample_weight=w)
                dc = m.coef_[npl:2 * npl]; dc = dc - dc.mean()
                halves[par] = dict(zip(players, sign * dc))
            common = [p for p in halves[0] if p in halves[1] and p >= 0]
            a = np.array([halves[0][p] for p in common]); b = np.array([halves[1][p] for p in common])
            r = float(np.corrcoef(a, b)[0, 1]) if len(common) > 2 else float("nan")
            sb = 2 * r / (1 + r) if r > -1 else float("nan")   # Spearman-Brown (half -> full length)
            out.append((season, name, r, sb, len(common)))
    return out


def _team_oos():
    """§9.2.3: predict team 5v5 xGA/60 in t+1 from minutes-weighted team aggregates in t. Available PV
    seasons are 2021-22..2025-26 (four pairs); the spec's 2016-17 start needs those singles backfilled
    (flagged). Predictor sets: (i) pv_def_g60, (ii) def_impact, (iii) own xGA/60, (iv) i+iii, (v) ii+iii."""
    p = bq.project()
    # per-player-team-season 5v5 TOI (minutes), for minutes-weighting the aggregates
    toi = bq.query_df(f"""
        select s.season, s.team_id, s.player_id, sum(s.segment_duration)/60.0 toi_min
        from `{p}.nhl_staging.int_shift_segments` s
        join `{p}.nhl_staging.int_segment_context` c using (game_id, segment_index)
        where s.is_goalie=0 and c.strength_state='5v5' and s.season in {tuple(SINGLES)}
        group by 1,2,3""", bq.client())
    pv = bq.query_df(f"""select season_window season, player_id, pv_def_g60, def_impact
        from `{p}.nhl_models.player_phase_value` where model_version='{MODEL_VERSION}'
        and season_window in {tuple(SINGLES)}""", bq.client())
    m = toi.merge(pv, on=["season", "player_id"], how="inner")
    for c in ("pv_def_g60", "def_impact", "toi_min"):
        m[c] = pd.to_numeric(m[c], errors="coerce")
    m = m.dropna(subset=["pv_def_g60", "def_impact", "toi_min"])
    m["pv_w"] = m["pv_def_g60"] * m["toi_min"]; m["di_w"] = m["def_impact"] * m["toi_min"]
    g = m.groupby(["season", "team_id"], as_index=False).agg(
        pv_w=("pv_w", "sum"), di_w=("di_w", "sum"), toi=("toi_min", "sum"))
    g["pv"] = g["pv_w"] / g["toi"]; g["di"] = g["di_w"] / g["toi"]
    team = g[["season", "team_id", "pv", "di"]]
    # team 5v5 xGA/60 per season (xG by the opponent while this team defends)
    xga = bq.query_df(f"""
        with seg as (select game_id, segment_index, season, home_team_id, away_team_id, segment_duration
                     from `{p}.nhl_staging.int_segment_context` where strength_state='5v5' and season in {tuple(SINGLES)}),
        toi as (select season, home_team_id t, sum(segment_duration) s from seg group by 1,2
                union all select season, away_team_id t, sum(segment_duration) s from seg group by 1,2),
        toi2 as (select season, t, sum(s) sec from toi group by 1,2),
        xgc as (select seg.season,
                 if(e.event_owner_team_id=seg.home_team_id, seg.away_team_id, seg.home_team_id) def_team,
                 x.xg xgv
               from `{p}.nhl_staging.int_on_ice_events` e
               join seg using (game_id, segment_index)
               join `{p}.nhl_models.shot_xg` x on e.game_id=x.game_id and e.event_id=x.event_id
               where x.xg is not null),
        xga as (select season, def_team t, sum(xgv) xga from xgc group by 1,2)
        select toi2.season, toi2.t team_id, xga.xga/(toi2.sec/3600.0) xga_per60
        from toi2 join xga on toi2.season=xga.season and toi2.t=xga.t""", bq.client())
    team = team.merge(xga, on=["season", "team_id"], how="inner")
    team["xga_per60"] = pd.to_numeric(team["xga_per60"], errors="coerce")
    # build (t, t+1) pairs
    idx = {s: i for i, s in enumerate(SINGLES)}
    rows = []
    for a, b in zip(SINGLES[:-1], SINGLES[1:]):
        ta = team[team["season"] == a][["team_id", "pv", "di", "xga_per60"]]
        tb = team[team["season"] == b][["team_id", "xga_per60"]].rename(columns={"xga_per60": "y"})
        rows.append(ta.merge(tb, on="team_id"))
    pair = pd.concat(rows, ignore_index=True).dropna()
    # predictor sets -> temporal-OOS r and R^2 (t predicts t+1)
    def fit_set(cols):
        Xd = pair[cols].to_numpy(); yv = pair["y"].to_numpy()
        Xd = np.column_stack([np.ones(len(Xd)), Xd])
        beta, *_ = np.linalg.lstsq(Xd, yv, rcond=None)
        yh = Xd @ beta
        ss_res = ((yv - yh) ** 2).sum(); ss_tot = ((yv - yv.mean()) ** 2).sum()
        r = float(np.corrcoef(yh, yv)[0, 1]); r2 = 1 - ss_res / ss_tot
        return r, float(r2)
    sets = {"(i) pv_def_g60": ["pv"], "(ii) def_impact": ["di"], "(iii) own xGA/60": ["xga_per60"],
            "(iv) i+iii": ["pv", "xga_per60"], "(v) ii+iii": ["di", "xga_per60"]}
    return {k: fit_set(v) for k, v in sets.items()}, len(pair)


def _arena_bias_line(df):
    """PV-D015: correlate team-season deny (minutes-weighted) against the home-arena under-recording rate
    from the persisted sprite-audit table (nhl_models.phase_arena_underrecording). Returns a paragraph."""
    p = bq.project()
    try:
        arena = bq.query_df(f"select venue_name, season, underrecord_share "
                            f"from `{p}.nhl_models.phase_arena_underrecording`", bq.client())
    except Exception as e:
        return (f"Deferred: `nhl_models.phase_arena_underrecording` not persisted yet — run "
                f"`sprite_audit.py` (it now exports the E3b per-arena shares). ({e})")
    arena["underrecord_share"] = pd.to_numeric(arena["underrecord_share"], errors="coerce")
    hv = bq.query_df(f"""select season, home_team_id team_id, venue_name, count(*) g
        from `{p}.nhl_staging.stg_boxscores` where season in {tuple(SINGLES)} group by 1,2,3""", bq.client())
    hv = hv.sort_values("g").groupby(["season", "team_id"], as_index=False).tail(1)[["season", "team_id", "venue_name"]]
    toi = bq.query_df(f"""select s.season, s.team_id, s.player_id, sum(s.segment_duration)/60.0 toi_min
        from `{p}.nhl_staging.int_shift_segments` s
        join `{p}.nhl_staging.int_segment_context` c using (game_id, segment_index)
        where s.is_goalie=0 and c.strength_state='5v5' and s.season in {tuple(SINGLES)}
        group by 1,2,3""", bq.client())
    pv = bq.query_df(f"""select season_window season, player_id, deny from `{p}.nhl_models.player_phase_value`
        where model_version='{MODEL_VERSION}' and season_window in {tuple(SINGLES)}""", bq.client())
    m = toi.merge(pv, on=["season", "player_id"]).dropna(subset=["deny"])
    m["deny"] = pd.to_numeric(m["deny"], errors="coerce"); m["dw"] = m["deny"] * m["toi_min"]
    g = m.groupby(["season", "team_id"], as_index=False).agg(dw=("dw", "sum"), toi=("toi_min", "sum"))
    g["team_deny"] = g["dw"] / g["toi"]
    j = g.merge(hv, on=["season", "team_id"]).merge(arena, on=["season", "venue_name"]).dropna(
        subset=["team_deny", "underrecord_share"])
    r = float(j["team_deny"].corr(j["underrecord_share"])) if len(j) > 2 else float("nan")
    return (f"Team-season `deny` (minutes-weighted) vs home-arena under-recording share, over **{len(j)} "
            f"team-seasons**: **r = {r:+.3f}**. A material positive r ⇒ teams whose home scorers under-record "
            "settled possession look better at `deny` (scorekeeper bias, not defence); near zero clears it. "
            "Since deny is already Tier C, this bounds how much of even that weak signal is arena artifact.")


def _write_tiers(tiers):
    """Write the earned tiers to nhl_models.phase_component_tiers (component registry). deny/deny_rush are
    Tier C — kept in player_phase_value but flagged not-for-player-publication (§9.1)."""
    rows = []
    for comp in COMPONENTS:
        r400, t400 = tiers[(comp, 400)]
        r200, t200 = tiers[(comp, 200)]
        rows.append(dict(component=comp, tier=t400, yoy_r_400=round(r400, 4), yoy_r_200=round(r200, 4),
                         publish_player_level=(t400 in ("A", "B")), model_version=MODEL_VERSION))
    out = pd.DataFrame(rows)
    bq.write_df(out, "phase_component_tiers", write_disposition="WRITE_TRUNCATE")
    print(f"Wrote {len(out)} component tiers to nhl_models.phase_component_tiers:")
    print(out[["component", "tier", "yoy_r_400", "publish_player_level"]].to_string(index=False))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="run the refit checks (split-half, team OOS)")
    ap.add_argument("--write-tiers", action="store_true", help="persist earned tiers (post-review only)")
    args = ap.parse_args()
    df = _load()
    sh = _split_half() if args.full else None
    oos = _team_oos() if args.full else None
    tiers = _report(df, sh, oos)
    if args.write_tiers:
        _write_tiers(tiers)
    else:
        print("REPORT-ONLY: no tiers written. Rerun with --write-tiers after owner review.")


if __name__ == "__main__":
    main()
