"""Phase 2 addendum (exploratory) — the offense/defense asymmetry question.

A1 family-level discontinuity: pool the style metrics into an offensive and a defensive
family (+ deployment as calibration). For each Cohort C change and each placebo split, a
family's pooled standardized shift = mean over the family's metrics of
(|Δ_metric| / that metric's placebo-median |Δ|). Real-vs-placebo at the family level
(mean ratio, permutation p, 2000 perms, seed 20260711).

A2: new PK shot-location-against profile metric, in the defensive family + reported
individually with split-half reliability.

Same thresholds as Phase 2 (ratio>1.25 AND p<0.05); exploratory — can only add to the
watch-list or promote via those thresholds, never relax them.
"""
from __future__ import annotations

import json
import random

import polars as pl

from . import config, fingerprints as F, regime_ledger as R, phase2 as P2

random.seed(config.SEED)

OFFENSIVE = ["rush_share_for", "cycle_share_for", "forecheck_share_for",
             "point_shot_share_for", "pp_loc_inner_for", "pp_loc_outer_for", "pp_loc_point_for"]
DEFENSIVE = ["loc_inner_against", "loc_outer_against", "loc_point_against",
             "rush_share_against", "cycle_share_against",
             "pk_loc_inner_against", "pk_loc_outer_against", "pk_loc_point_against"]
DEPLOYMENT = ["top6_fwd_toi_share", "zone_start_polarization"]
ALL_METRICS = OFFENSIVE + DEFENSIVE + DEPLOYMENT
PK_METRICS = ["pk_loc_inner_against", "pk_loc_outer_against", "pk_loc_point_against"]


def metric_vector_ext(prim, deploy, pk, game_ids, team_id) -> dict:
    m = F.aggregate(prim, game_ids, team_id)
    m.update(F.deployment_over(deploy, game_ids, team_id))
    m.update(F.pk_location(pk, game_ids, team_id))
    return m


def _batch_metrics(units: pl.DataFrame, prim, deploy, pk, min_start_toi_min=50.0) -> dict:
    """Vectorised metric vectors for MANY units at once (one group-by per frame instead
    of one filter per unit). `units` = (unit_id, team_id, game_id). Returns {unit_id: {...}}."""
    F._positions()  # build _FWD_CACHE once
    # --- prim (score-close shares + pace + forecheck + pp) ---
    cols = ["att_forc", "rush_forc", "cycle_forc", "forecheck_forc", "point_shot_forc",
            "att_againstc", "rush_againstc", "cycle_againstc",
            "inner_againstc", "outer_againstc", "point_againstc",
            "cf_close", "ca_close", "toi_sec_close", "toi_sec",
            "att_pp", "inner_pp", "outer_pp", "point_pp", "oz_take", "forced_give"]
    pj = units.join(prim, on=["game_id", "team_id"], how="inner").group_by("unit_id").agg(
        [pl.col(c).sum().alias(c) for c in cols])
    def sh(n, d): return pl.when(pl.col(d) > 0).then(pl.col(n) / pl.col(d)).otherwise(None)
    pj = pj.with_columns(
        pace=pl.when(pl.col("toi_sec_close") > 0)
        .then((pl.col("cf_close") + pl.col("ca_close")) / pl.col("toi_sec_close") * 3600).otherwise(None),
        rush_share_for=sh("rush_forc", "att_forc"), cycle_share_for=sh("cycle_forc", "att_forc"),
        forecheck_share_for=sh("forecheck_forc", "att_forc"), point_shot_share_for=sh("point_shot_forc", "att_forc"),
        rush_share_against=sh("rush_againstc", "att_againstc"), cycle_share_against=sh("cycle_againstc", "att_againstc"),
        loc_inner_against=sh("inner_againstc", "att_againstc"), loc_outer_against=sh("outer_againstc", "att_againstc"),
        loc_point_against=sh("point_againstc", "att_againstc"),
        forecheck_pressure_per60=pl.when(pl.col("toi_sec") > 0)
        .then((pl.col("oz_take") + pl.col("forced_give")) / pl.col("toi_sec") * 3600).otherwise(None),
        pp_loc_inner_for=sh("inner_pp", "att_pp"), pp_loc_outer_for=sh("outer_pp", "att_pp"),
        pp_loc_point_for=sh("point_pp", "att_pp"))
    # --- deploy (top6 share + zone polarization) ---
    dj = (units.join(deploy, on=["game_id", "team_id"], how="inner")
          .group_by("unit_id", "pid").agg(toi=pl.col("toi_sec").sum(),
                                          oz=pl.col("oz_starts").sum(), dz=pl.col("dz_starts").sum())
          .with_columns(is_fwd=pl.col("pid").replace_strict(F._FWD_CACHE, default=True, return_dtype=pl.Boolean)))
    fwd = dj.filter("is_fwd").with_columns(
        rk=pl.col("toi").rank("ordinal", descending=True).over("unit_id"))
    top6 = fwd.group_by("unit_id").agg(
        top6=pl.col("toi").filter(pl.col("rk") <= 6).sum(), totfwd=pl.col("toi").sum())
    top6 = top6.with_columns(top6_fwd_toi_share=pl.when(pl.col("totfwd") > 0)
                             .then(pl.col("top6") / pl.col("totfwd")).otherwise(None))
    z = dj.filter((pl.col("toi") >= min_start_toi_min * 60) & ((pl.col("oz") + pl.col("dz")) > 0)).with_columns(
        oz_share=pl.col("oz") / (pl.col("oz") + pl.col("dz")))
    zpol = z.group_by("unit_id").agg(zone_start_polarization=pl.col("oz_share").std(), cnt=pl.len())
    zpol = zpol.with_columns(zone_start_polarization=pl.when(pl.col("cnt") > 2)
                             .then(pl.col("zone_start_polarization")).otherwise(None))
    # --- pk (shorthanded location-against) ---
    pkj = units.join(pk, on=["game_id", "team_id"], how="inner").group_by("unit_id").agg(
        att_pk=pl.col("att_pk_against").sum(), inn=pl.col("inner_pk_against").sum(),
        out=pl.col("outer_pk_against").sum(), pnt=pl.col("point_pk_against").sum())
    pkj = pkj.with_columns(
        pk_loc_inner_against=sh("inn", "att_pk"), pk_loc_outer_against=sh("out", "att_pk"),
        pk_loc_point_against=sh("pnt", "att_pk"))
    # --- merge ---
    out = (pj.join(top6.select("unit_id", "top6_fwd_toi_share"), on="unit_id", how="left")
           .join(zpol.select("unit_id", "zone_start_polarization"), on="unit_id", how="left")
           .join(pkj.select("unit_id", "pk_loc_inner_against", "pk_loc_outer_against", "pk_loc_point_against"),
                 on="unit_id", how="left"))
    res = {}
    for r in out.to_dicts():
        res[r["unit_id"]] = {m: r.get(m) for m in ALL_METRICS}
    return res


def _shifts(prim, deploy, pk, tg, reg):
    """Return per-metric real |Δ| (49 changes) and placebo |Δ| (one-regime splits).
    Vectorised: assemble every unit's (game,team) rows, compute all metric vectors in one
    batched pass, then difference the two sides of each comparison. Seed-identical to the
    per-unit version (same iteration order + same random.randint sequence)."""
    changes = P2.cohort_C_changes(tg)
    rows, cmp_meta = [], []
    for i, c in enumerate(changes):
        for side, gids in (("old", c["old_games"]), ("new", c["new_games"])):
            rows += [{"unit_id": f"chg{i}_{side}", "team_id": c["team_id"], "game_id": g} for g in gids]
        cmp_meta.append((f"chg{i}", "real"))
    for j, row in enumerate(P2.one_regime_team_seasons(reg).iter_rows(named=True)):
        g = (reg.filter((pl.col("team_id") == row["team_id"])
                        & (pl.col("season_label") == row["season_label"]))
             .sort("game_id")["game_id"].unique(maintain_order=True).to_list())
        if len(g) < 30:
            continue
        cut = random.randint(len(g) // 3, 2 * len(g) // 3)
        for side, gg in (("h1", g[:cut]), ("h2", g[cut:])):
            rows += [{"unit_id": f"plc{j}_{side}", "team_id": row["team_id"], "game_id": x} for x in gg]
        cmp_meta.append((f"plc{j}", "placebo"))
    units = pl.DataFrame(rows, schema={"unit_id": pl.Utf8, "team_id": pl.Int64, "game_id": pl.Int64})
    mv = _batch_metrics(units, prim, deploy, pk)
    real = {m: [] for m in ALL_METRICS}; placebo = {m: [] for m in ALL_METRICS}
    for cmp_id, kind in cmp_meta:
        a = mv.get(f"{cmp_id}_old", mv.get(f"{cmp_id}_h1", {}))
        b = mv.get(f"{cmp_id}_new", mv.get(f"{cmp_id}_h2", {}))
        tgt = real if kind == "real" else placebo
        for m in ALL_METRICS:
            va, vb = a.get(m), b.get(m)
            tgt[m].append(abs(vb - va) if (va is not None and vb is not None) else None)
    return changes, real, placebo


def _family_pooled(units, family, placebo_median):
    """Per unit: mean over family metrics of |Δ|/placebo_median (skip None/0-scale)."""
    out = []
    for i in range(len(next(iter(units.values())))):
        vals = []
        for m in family:
            d = units[m][i]; pm = placebo_median.get(m)
            if d is not None and pm:
                vals.append(d / pm)
        if vals:
            out.append(sum(vals) / len(vals))
    return out


def run(seasons=None) -> dict:
    seasons = seasons or config.SEASONS_ALL
    prim = P2._load(F.PRIM_DIR, seasons)
    deploy = P2._load(F.DEPLOY_DIR, seasons)
    pk = P2._load(F.PK_DIR, seasons)
    gc = R.assemble_game_coaches(); tg = R.to_team_games(gc)
    raw = R.build_ledger(tg.filter(pl.col("coach").is_not_null()))
    raw_annot, _ = R.consolidate_ledger(raw, k=4)
    reg = P2.consolidated_regime_games(tg, raw_annot)

    changes, real, placebo = _shifts(prim, deploy, pk, tg, reg)
    placebo_median = {m: P2._median([x for x in placebo[m] if x is not None])
                      if any(x is not None for x in placebo[m]) else None for m in ALL_METRICS}

    # A1 family-level
    families = {"offensive": OFFENSIVE, "defensive": DEFENSIVE, "deployment": DEPLOYMENT}
    fam_out = {}
    for name, fam in families.items():
        rr = _family_pooled(real, fam, placebo_median)
        pp = _family_pooled(placebo, fam, placebo_median)
        ratio = P2._mean(rr) / P2._mean(pp) if pp and P2._mean(pp) else None
        fam_out[name] = {
            "n_metrics": len(fam), "n_real": len(rr), "n_placebo": len(pp),
            "mean_real_pooled": round(P2._mean(rr), 4), "mean_placebo_pooled": round(P2._mean(pp), 4),
            "median_real_pooled": round(P2._median(rr), 4), "median_placebo_pooled": round(P2._median(pp), 4),
            "ratio_mean": round(ratio, 3) if ratio else None,
            "perm_p": round(P2._perm_p(rr, pp), 4),
            "coaching_sensitive": (ratio and ratio > 1.25) and P2._perm_p(rr, pp) < 0.05,
        }

    # A2 individual PK metrics — discontinuity + reliability
    pk_individual = {}
    for m in PK_METRICS:
        rr = [x for x in real[m] if x is not None]
        pp = [x for x in placebo[m] if x is not None]
        mr, mp = P2._mean(rr), P2._mean(pp)
        pk_individual[m] = {
            "n_real": len(rr), "n_placebo": len(pp),
            "median_real": round(P2._median(rr), 5), "median_placebo": round(P2._median(pp), 5),
            "ratio_mean": round(mr / mp, 3) if mp else None,
            "perm_p": round(P2._perm_p(rr, pp), 4),
            "coaching_sensitive": (mr / mp > 1.25 if mp else False) and P2._perm_p(rr, pp) < 0.05,
        }
    pk_reliability = _pk_reliability(reg, prim, deploy, pk, placebo_median)

    out = {"A1_families": fam_out, "A2_pk_individual": pk_individual,
           "A2_pk_reliability": pk_reliability, "n_real_changes": len(changes)}
    (config.REPORTS / "phase2_addendum_analysis.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def _pk_reliability(reg, prim, deploy, pk, placebo_median=None) -> dict:
    regimes = (reg.group_by("team_id", "consolidated_start_game_id")
               .agg(n=pl.len()).filter(pl.col("n") >= 40))
    rows, ids = [], []
    for i, row in enumerate(regimes.iter_rows(named=True)):
        g = (reg.filter((pl.col("team_id") == row["team_id"])
                        & (pl.col("consolidated_start_game_id") == row["consolidated_start_game_id"]))
             .sort("game_id")["game_id"].unique(maintain_order=True).to_list())
        for side, gg in (("odd", g[0::2]), ("even", g[1::2])):
            rows += [{"unit_id": f"r{i}_{side}", "team_id": row["team_id"], "game_id": x} for x in gg]
        ids.append(i)
    units = pl.DataFrame(rows, schema={"unit_id": pl.Utf8, "team_id": pl.Int64, "game_id": pl.Int64})
    mv = _batch_metrics(units, prim, deploy, pk)
    pairs = {m: ([], []) for m in PK_METRICS}
    for i in ids:
        a, b = mv.get(f"r{i}_odd", {}), mv.get(f"r{i}_even", {})
        for m in PK_METRICS:
            if a.get(m) is not None and b.get(m) is not None:
                pairs[m][0].append(a[m]); pairs[m][1].append(b[m])
    return {m: {"n_regimes": len(pairs[m][0]),
                "split_half_r": round(P2._pearson(*pairs[m]), 3) if len(pairs[m][0]) > 5 else None}
            for m in PK_METRICS}


if __name__ == "__main__":
    r = run()
    for f, v in r["A1_families"].items():
        print(f, "ratio", v["ratio_mean"], "p", v["perm_p"], "sensitive", v["coaching_sensitive"], flush=True)
