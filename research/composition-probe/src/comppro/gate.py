"""THE GATE (Steps 2-4) — does RECIPE beat recipe, holding talent+style fixed, and repeat?

Step 2 recipe per forward trio: multiset of members' style archetypes + COMPLEMENTARITY (dispersion
across functional families) + a REDUNDANCY score on offensive-volume + shot-location (two slot-shooters
overlap). Step 3: trio residual = observed xG share − additive-plus-curvature null (members'
rapm_variant + context); (a) does composition add CV R2 beyond talent+deployment+opponent controls
(vs Link 2's ~1%); (b) matched balanced-vs-redundant paired contrast + bootstrap CI. Step 4: era-split
repeat (2015-19 vs 2020-25) + within-season split-half of the trio residual.

Scope 2015-16..2025-26 (where validated style axes exist; the spec's 2010-2017/2018-2025 split is
adapted to 2015-2019 vs 2020-2025 — pre-2015 style axes are not validated, role-fit UL-P2). Reuses the
role-fit trio units (odd/even + score context) and the Chemistry additive-plus-curvature null idea.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold

from . import config
from . import styles as S

FLOOR = 6000               # 100 shared min (role-fit-confirmed trio unit)
MEMBER_FAM = {fam: axes for fam, axes in S.FAMILIES.items()}


def _rapm(anchor="same") -> pl.DataFrame:
    r = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet").select(
        "player_id", "season", off="off_impact", deff="def_impact")
    if anchor == "same":
        return r
    sidx = {s: i for i, s in enumerate(config.SEASONS)}
    sd = pl.DataFrame({"si": list(range(len(config.SEASONS))), "season": config.SEASONS})
    r = r.filter(pl.col("season").is_in(config.SEASONS)).with_columns(
        si=pl.col("season").replace_strict(sidx, return_dtype=pl.Int32))
    return (r.select("player_id", (pl.col("si") + 1).alias("si"), "off", "deff")
            .join(sd, on="si", how="inner").select("player_id", "season", "off", "deff"))


def load_recipes() -> pl.DataFrame:
    trios = pl.concat([pl.read_parquet(p) for p in sorted(config.TRIO_UNIT_DIR.glob("trio_*.parquet"))],
                      how="vertical_relaxed").filter(pl.col("toi") >= FLOOR)
    arch = pl.read_parquet(S.ARCH_PARQUET)               # pid, season_label, archetype, z_axes
    r = _rapm("same")
    for i in (1, 2, 3):
        r_i = r.rename({"player_id": f"f{i}", "season": "season_label", "off": f"off{i}", "deff": f"def{i}"})
        trios = trios.join(r_i, on=[f"f{i}", "season_label"], how="left")
        a_i = arch.rename({"pid": f"f{i}", **{f"z_{a}": f"z_{a}_{i}" for a in S.AXES},
                           "archetype": f"arch{i}"})
        trios = trios.join(a_i, on=[f"f{i}", "season_label"], how="left")
    n0 = trios.height
    trios = trios.drop_nulls([f"{p}{i}" for i in (1, 2, 3) for p in ("off", "def")]
                             + [f"arch{i}" for i in (1, 2, 3)])
    dropped = n0 - trios.height
    # recipe = sorted multiset of archetypes
    trios = trios.with_columns(
        recipe=pl.concat_list([pl.col("arch1"), pl.col("arch2"), pl.col("arch3")]).list.sort()
        .list.eval(pl.element().cast(pl.Utf8)).list.join("-"))
    # per-family member scores + dispersions (complementarity / redundancy)
    for fam, axes in MEMBER_FAM.items():
        for i in (1, 2, 3):
            trios = trios.with_columns(
                **{f"{fam}_m{i}": pl.mean_horizontal([pl.col(f"z_{a}_{i}") for a in axes])})
        ms = [pl.col(f"{fam}_m{i}") for i in (1, 2, 3)]
        trios = trios.with_columns(**{f"{fam}_disp": pl.concat_list(ms).list.std()})
    trios = trios.with_columns(
        complementarity=pl.mean_horizontal([pl.col(f"{f}_disp") for f in MEMBER_FAM]),
        vol_loc_dispersion=(pl.col("volume_disp") + pl.col("location_disp")) / 2)  # low = redundant
    # talent + curvature + context for the null
    trios = trios.with_columns(
        sum_off=pl.col("off1") + pl.col("off2") + pl.col("off3"),
        sum_def=pl.col("def1") + pl.col("def2") + pl.col("def3"),
        q1=pl.col("off1") + pl.col("def1"), q2=pl.col("off2") + pl.col("def2"),
        q3=pl.col("off3") + pl.col("def3"))
    trios = trios.with_columns(
        ssum=(pl.col("q1") + pl.col("q2") + pl.col("q3")) ** 2,
        prod=pl.col("q1") * pl.col("q2") + pl.col("q1") * pl.col("q3") + pl.col("q2") * pl.col("q3"))
    return trios, dropped


def _residual(trios: pl.DataFrame) -> pl.DataFrame:
    """additive-plus-curvature null: xG share ~ sum_off+sum_def+curvature+context+season. residual."""
    feats = ["sum_off", "sum_def", "ssum", "prod", "oz_start_share", "share_lead", "share_trail", "opp_rapm"]
    seasons = sorted(trios["season_label"].unique().to_list())
    Xc = trios.select([pl.col(f).fill_null(pl.col(f).median()) for f in feats]).to_numpy()
    sea = np.column_stack([(trios["season_label"] == s).to_numpy().astype(float) for s in seasons[1:]])
    X = np.hstack([Xc, sea]); y = trios["xg_share"].to_numpy(); w = trios["toi"].to_numpy().astype(float)
    m = RidgeCV(alphas=(0.1, 1, 10, 100)).fit(X, y, sample_weight=w)
    return trios.with_columns(residual=pl.col("xg_share") - pl.Series(m.predict(X)))


def _cv_r2(df, cols, target="residual"):
    d = df.drop_nulls(cols + [target])
    y = d[target].to_numpy(); w = d["toi"].to_numpy().astype(float)
    seasons = sorted(d["season_label"].unique().to_list())
    groups = np.array([seasons.index(s) for s in d["season_label"].to_list()])
    X = d.select(cols).to_numpy(); oof = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=len(seasons)).split(X, y, groups):
        mm = RidgeCV(alphas=(0.1, 1, 10, 100)).fit(X[tr], y[tr], sample_weight=w[tr])
        oof[te] = mm.predict(X[te])
    ss = np.sum(w * (y - oof) ** 2); tot = np.sum(w * (y - np.average(y, weights=w)) ** 2)
    return float(1 - ss / tot)


def regression(trios: pl.DataFrame) -> dict:
    controls = ["sum_off", "sum_def", "prod", "ssum", "oz_start_share", "share_lead", "share_trail", "opp_rapm"]
    comp = ["complementarity", "vol_loc_dispersion"]
    r2c = _cv_r2(trios, controls); r2b = _cv_r2(trios, controls + comp)
    return {"cv_r2_controls": r2c, "cv_r2_controls_plus_composition": r2b,
            "incremental_r2_composition": r2b - r2c, "link2_reference_incremental_r2": 0.011}


def matched_contrast(trios: pl.DataFrame, n_boot=2000) -> dict:
    """Matched balanced-vs-redundant: within (talent tercile x season), pair the top-complementarity
    third vs the bottom third; compare residuals. Bootstrap CI on the difference."""
    d = trios.drop_nulls(["complementarity", "residual"]).with_columns(
        q=pl.col("sum_off") + pl.col("sum_def"))
    d = d.with_columns(tal=pl.col("q").qcut(3, labels=["lo", "mid", "hi"]).over("season_label"))
    d = d.with_columns(comp_t=pl.col("complementarity").qcut(3, labels=["red", "mid", "bal"])
                       .over("season_label", "tal"))
    bal = d.filter(pl.col("comp_t") == "bal"); red = d.filter(pl.col("comp_t") == "red")
    diff = float(np.average(bal["residual"].to_numpy(), weights=bal["toi"].to_numpy().astype(float))
                 - np.average(red["residual"].to_numpy(), weights=red["toi"].to_numpy().astype(float)))
    rng = np.random.default_rng(config.SEED)
    br, rr = bal["residual"].to_numpy(), red["residual"].to_numpy()
    bw, rw = bal["toi"].to_numpy().astype(float), red["toi"].to_numpy().astype(float)
    boot = []
    for _ in range(n_boot):
        bi = rng.integers(0, len(br), len(br)); ri = rng.integers(0, len(rr), len(rr))
        boot.append(np.average(br[bi], weights=bw[bi]) - np.average(rr[ri], weights=rw[ri]))
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"n_balanced": bal.height, "n_redundant": red.height,
            "balanced_minus_redundant_residual": diff, "ci95": [float(lo), float(hi)],
            "ci_excludes_zero": bool(lo > 0 or hi < 0)}


def era_split(trios: pl.DataFrame) -> dict:
    """Fit the composition coefficient on one era, evaluate sign/magnitude on the other, and vice versa."""
    comp = ["complementarity", "vol_loc_dispersion"]
    ctrl = ["sum_off", "sum_def", "prod", "ssum", "oz_start_share", "share_lead", "share_trail", "opp_rapm"]

    def coef(df):
        d = df.drop_nulls(comp + ctrl + ["residual"])
        X = d.select(ctrl + comp).to_numpy(); y = d["residual"].to_numpy(); w = d["toi"].to_numpy().astype(float)
        m = RidgeCV(alphas=(0.1, 1, 10, 100)).fit(X, y, sample_weight=w)
        return {"complementarity": float(m.coef_[len(ctrl)]), "vol_loc": float(m.coef_[len(ctrl) + 1])}
    early = trios.filter(pl.col("season_label").is_in(config.ERA_EARLY))
    late = trios.filter(pl.col("season_label").is_in(config.ERA_LATE))
    ce, cl = coef(early), coef(late)
    consistent = (np.sign(ce["complementarity"]) == np.sign(cl["complementarity"]) and abs(ce["complementarity"]) > 1e-4)
    return {"n_early": early.height, "n_late": late.height, "coef_early": ce, "coef_late": cl,
            "complementarity_sign_consistent": bool(consistent)}


def split_half(trios: pl.DataFrame) -> dict:
    """within-season split-half of the trio residual (odd/even), constant unit baseline (Chemistry fix)."""
    d = trios.filter((pl.col("xgf_odd") + pl.col("xga_odd") > 0) & (pl.col("xgf_even") + pl.col("xga_even") > 0))
    # residual baseline is the unit-season null prediction (constant per unit; Chemistry straddling fix)
    pred = d["xg_share"] - d["residual"]
    x = (d["xg_share_odd"].to_numpy() - pred.to_numpy()); y = (d["xg_share_even"].to_numpy() - pred.to_numpy())
    w = d["toi"].to_numpy().astype(float)
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    r = float(cov / np.sqrt(np.average((x - mx) ** 2, weights=w) * np.average((y - my) ** 2, weights=w)))
    return {"n": d.height, "residual_split_half_r": r}


def verdict(reg, mc, era) -> dict:
    inc = reg["incremental_r2_composition"]
    replicate = era["complementarity_sign_consistent"]
    ci_excl = mc["ci_excludes_zero"]
    comp_coef = era["coef_late"]["complementarity"]
    # pre-stated language: PASS >=3% + replicate + CI excl 0; HARD "~0 or negative" beyond controls;
    # WEAK "~1-3% band or fails replicate". "~0" is operationalized as <0.5% incremental R2 with the
    # matched contrast not excluding zero (this only sharpens the pre-stated "~0", not the PASS/WEAK bar).
    if inc >= 0.03 and replicate and ci_excl:
        out = "PASS"
    elif (inc < 0.005 or comp_coef <= 0) and not ci_excl:
        out = "HARD_NULL"
    else:
        out = "WEAK_CONFIRM_NULL"
    return {"incremental_r2": inc, "replicates_across_era": replicate, "ci_excludes_zero": ci_excl,
            "complementarity_coef_late": comp_coef, "outcome": out}


def run() -> dict:
    trios, dropped = load_recipes()
    trios = _residual(trios)
    # recipe recurrence
    rc = trios.group_by("recipe").len().sort("len", descending=True)
    res = {"seed": config.SEED_TAG, "floor_min": FLOOR // 60, "scope": "2015-16..2025-26",
           "era_split_note": "spec's 2010-17/2018-25 adapted to 2015-19 vs 2020-25 (style axes only "
           "validated 2015+; role-fit UL-P2)",
           "n_trios": trios.height, "dropped": dropped,
           "recipe_recurrence": {"n_distinct_recipes": rc.height,
                                 "median_trios_per_recipe": float(rc["len"].median()),
                                 "top5": rc.head(5).to_dicts(),
                                 "frac_recipes_recurring_ge3": float((rc["len"] >= 3).mean())},
           "regression": regression(trios), "matched_contrast": matched_contrast(trios),
           "era_split": era_split(trios), "within_season_split_half": split_half(trios)}
    res["verdict"] = verdict(res["regression"], res["matched_contrast"], res["era_split"])
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "gate_analysis.json", "w") as f:
        json.dump(res, f, indent=2)
    return res


if __name__ == "__main__":
    r = run()
    print(f"trios={r['n_trios']} (dropped {r['dropped']}) | distinct recipes={r['recipe_recurrence']['n_distinct_recipes']} "
          f"median trios/recipe={r['recipe_recurrence']['median_trios_per_recipe']}")
    rg, mc, er, sh, v = r["regression"], r["matched_contrast"], r["era_split"], r["within_season_split_half"], r["verdict"]
    print(f"REGRESSION incremental composition R2={rg['incremental_r2_composition']:.4f} (Link2 ref ~0.011) "
          f"[ctrl {rg['cv_r2_controls']:.3f} -> +comp {rg['cv_r2_controls_plus_composition']:.3f}]")
    print(f"MATCHED balanced-redundant residual diff={mc['balanced_minus_redundant_residual']:+.4f} "
          f"CI{mc['ci95']} excl0={mc['ci_excludes_zero']}")
    print(f"ERA coef complementarity early={er['coef_early']['complementarity']:+.4f} late={er['coef_late']['complementarity']:+.4f} "
          f"sign-consistent={er['complementarity_sign_consistent']}")
    print(f"within-season split-half residual r={sh['residual_split_half_r']:+.3f}")
    print("VERDICT:", v["outcome"])
