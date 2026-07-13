"""Link 2 (GATE) — do units over-perform their parts, stably within a season? And does two-way role
composition explain it beyond controls?

2.2 Unit over-performance = observed trio 5v5 xG share − additive-plus-curvature null from members'
    rapm_variant + context (the reused Chemistry null, unit grain).
2.3 GATE: within-season split-half of the unit RESIDUAL (odd/even games, TOI-weighted) vs shuffled
    placebo. Baseline is the unit-SEASON prediction (constant per unit) subtracted from each half —
    NOT re-predicted with endogenous per-half context (the Chemistry Phase-2 straddling fix). Bar
    (pre-stated): split-half >= 0.30 beating placebo at p<0.05.
2.4 Regress unit over-performance on (a) two-way role-composition features (complementarity/spread &
    coverage across offense/physicality/possession/discipline, from the individual axes) and (b)
    non-role controls (combined rapm, combined shooting talent, handedness mix). Incremental CV R² of
    composition beyond controls.
2.6 Three-way ceiling verdict (pre-stated below).

The opponent-mirror suppression axis is UNIT-imposed (Link 1b, retention 0.12-0.47) and is NOT used
as a per-player composition feature — only individual, player-carried axes feed composition.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold

from . import config
from . import profiles as P
from . import units as U

SEED = config.SEED
FLOOR = U.TRIO_FLOOR_SEC          # 100 shared minutes
SB_BAR = 0.30                     # pre-stated 2.3/2.5 gate
N_PERM = 1000                     # scoped placebo count (reported)
# individual, player-carried role families (NO unit-suppression axes)
FAMILIES = {"offense": ["cf60", "xg60", "mean_dist", "slot_share"],
            "physical": ["hit60", "hittaken60"],
            "possession": ["tk60", "gv60"],
            "discipline": ["pentake60", "pendrawn60"]}
COMP_AXES = [a for axes in FAMILIES.values() for a in axes]


def _load_units() -> pl.DataFrame:
    files = sorted(U.UNIT_DIR.glob("trio_*.parquet"))
    return pl.concat([pl.read_parquet(f) for f in files], how="vertical_relaxed").filter(
        pl.col("toi") >= FLOOR)


def _rapm(anchor: str = "same") -> pl.DataFrame:
    """Member rating table. 'same' = same-season rapm (contaminated: rapm was fit on on-ice results
    that include this unit's shared minutes). 'prior' = prior-season rapm mapped to season t (clean;
    not informed by the unit's current outcomes — the Chemistry Phase-2 fix for the split-half
    straddling artifact). Members without a prior season drop under the prior anchor."""
    r = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet").select(
        "player_id", "season", off="off_impact", deff="def_impact")
    if anchor == "same":
        return r
    sidx = {s: i for i, s in enumerate(config.SEASONS_ALL)}
    seasondf = pl.DataFrame({"si": list(range(len(config.SEASONS_ALL))), "season": config.SEASONS_ALL})
    r = r.with_columns(si=pl.col("season").replace_strict(sidx, return_dtype=pl.Int32))
    return (r.select("player_id", (pl.col("si") + 1).alias("si"), "off", "deff")
            .join(seasondf, on="si", how="inner").select("player_id", "season", "off", "deff"))


def _member_axes() -> pl.DataFrame:
    """z-scored (within pos,season) individual role axes per (player, season) from the rich profiles."""
    prof = pl.concat([pl.read_parquet(p) for p in sorted(P.RICH_DIR.glob("*.parquet"))],
                     how="vertical_relaxed")
    stats = prof.group_by("pg", "season_label").agg(
        [pl.col(a).mean().alias(f"{a}__m") for a in COMP_AXES]
        + [pl.col(a).std().alias(f"{a}__s") for a in COMP_AXES])
    d = prof.join(stats, on=["pg", "season_label"], how="left")
    z = d.select("pid", "season_label",
                 *[((pl.col(a) - pl.col(f"{a}__m")) / pl.col(f"{a}__s")).alias(a) for a in COMP_AXES],
                 xg60_raw=pl.col("xg60"))
    return z


# ---------------------------------------------------------------- 2.2 null + residual
def build_residuals(units: pl.DataFrame, anchor: str = "same") -> tuple[pl.DataFrame, dict]:
    r = _rapm(anchor)
    u = units
    for i in (1, 2, 3):
        u = u.join(r.rename({"player_id": f"f{i}", "season": "season_label",
                             "off": f"off{i}", "deff": f"def{i}"}),
                   on=[f"f{i}", "season_label"], how="left")
    n0 = u.height
    u = u.drop_nulls([f"{p}{i}" for i in (1, 2, 3) for p in ("off", "def")])
    dropped = n0 - u.height
    u = u.with_columns(
        sum_off=pl.col("off1") + pl.col("off2") + pl.col("off3"),
        sum_def=pl.col("def1") + pl.col("def2") + pl.col("def3"),
        q1=pl.col("off1") + pl.col("def1"), q2=pl.col("off2") + pl.col("def2"),
        q3=pl.col("off3") + pl.col("def3"))
    u = u.with_columns(
        ssum=(pl.col("q1") + pl.col("q2") + pl.col("q3")) ** 2,                       # curvature
        prod=pl.col("q1") * pl.col("q2") + pl.col("q1") * pl.col("q3") + pl.col("q2") * pl.col("q3"))
    feats = ["sum_off", "sum_def", "ssum", "prod", "oz_start_share", "share_lead", "share_trail",
             "opp_rapm"]
    u = u.with_columns(oz_start_share=pl.col("oz_start_share").fill_null(0.5))
    seasons = sorted(u["season_label"].unique().to_list())
    Xc = u.select(feats).to_numpy()
    seasoncols = np.column_stack([(u["season_label"] == s).to_numpy().astype(float) for s in seasons[1:]])
    X = np.hstack([Xc, seasoncols])
    y = u["xg_share"].to_numpy(); w = u["toi"].to_numpy().astype(float)
    groups = np.array([seasons.index(s) for s in u["season_label"].to_list()])
    # LOSO CV R² (fit quality)
    oof = np.zeros(len(y))
    gkf = GroupKFold(n_splits=len(seasons))
    for tr, te in gkf.split(X, y, groups):
        m = RidgeCV(alphas=(0.1, 1, 10, 100)).fit(X[tr], y[tr], sample_weight=w[tr])
        oof[te] = m.predict(X[te])
    model = RidgeCV(alphas=(0.1, 1, 10, 100)).fit(X, y, sample_weight=w)
    pred = model.predict(X)
    u = u.with_columns(pred=pl.Series(pred), residual=pl.col("xg_share") - pl.Series(pred))
    diag = {"anchor": anchor, "n_units": u.height, "dropped_missing_rapm": dropped,
            "cv_r2_loso": float(1 - np.sum(w * (y - oof) ** 2) / np.sum(w * (y - np.average(y, weights=w)) ** 2)),
            "residual_toi_wtd_mean": float(np.average(u["residual"].to_numpy(), weights=w)),
            "residual_sd": float(u["residual"].std())}
    return u, diag


# ---------------------------------------------------------------- 2.3 within-season split-half gate
def _wcorr(x, y, w):
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    vx, vy = np.average((x - mx) ** 2, weights=w), np.average((y - my) ** 2, weights=w)
    return float(cov / np.sqrt(vx * vy)) if vx > 0 and vy > 0 else float("nan")


def split_half(units_resid: pl.DataFrame) -> dict:
    d = units_resid.filter(
        (pl.col("xgf_odd").fill_null(0) + pl.col("xga_odd").fill_null(0) > 0)
        & (pl.col("xgf_even").fill_null(0) + pl.col("xga_even").fill_null(0) > 0))
    # residual per half = half observed share - unit-season null prediction (constant baseline)
    d = d.with_columns(r_odd=pl.col("xg_share_odd") - pl.col("pred"),
                       r_even=pl.col("xg_share_even") - pl.col("pred"))
    x, y = d["r_odd"].to_numpy(), d["r_even"].to_numpy()
    xr, yr = d["xg_share_odd"].to_numpy(), d["xg_share_even"].to_numpy()
    w = d["toi"].to_numpy().astype(float)
    r = _wcorr(x, y, w); raw = _wcorr(xr, yr, w)
    rng = np.random.default_rng(SEED)
    perm = np.array([_wcorr(x, y[rng.permutation(len(y))], w) for _ in range(N_PERM)])
    p = float((np.sum(perm >= r) + 1) / (N_PERM + 1))
    sb = float(2 * r / (1 + r)) if r > -1 else float("nan")
    return {"n": d.height, "residual_split_half_r": r, "residual_split_half_sb": sb,
            "raw_share_split_half_r": raw, "placebo_r_mean": float(np.mean(perm)),
            "p_value": p, "n_perm": N_PERM, "bar": SB_BAR,
            "passes": (r >= SB_BAR and p < 0.05)}


# ---------------------------------------------------------------- 2.4 composition regression
def composition_features(units_resid: pl.DataFrame) -> pl.DataFrame:
    z = _member_axes()
    u = units_resid
    for i in (1, 2, 3):
        u = u.join(z.rename({"pid": f"f{i}", **{a: f"{a}_{i}" for a in COMP_AXES},
                             "xg60_raw": f"xg60raw_{i}"}),
                   on=[f"f{i}", "season_label"], how="left")
    # per-family complementarity (spread across members) + coverage (max member)
    exprs = []
    for fam, axes in FAMILIES.items():
        # family score per member = mean of its axes; spread = std across 3 members; coverage = max
        for i in (1, 2, 3):
            exprs.append(pl.mean_horizontal([pl.col(f"{a}_{i}") for a in axes]).alias(f"{fam}_m{i}"))
    u = u.with_columns(exprs)
    comp = []
    for fam in FAMILIES:
        ms = [pl.col(f"{fam}_m{i}") for i in (1, 2, 3)]
        u = u.with_columns(
            **{f"{fam}_spread": pl.concat_list(ms).list.std(),
               f"{fam}_cover": pl.concat_list(ms).list.max(),
               f"{fam}_mean": pl.mean_horizontal(ms)})
        comp += [f"{fam}_spread", f"{fam}_cover", f"{fam}_mean"]
    # controls
    u = u.with_columns(
        ctrl_rapm=pl.col("sum_off") + pl.col("sum_def"),
        ctrl_shoot=pl.mean_horizontal([pl.col(f"xg60raw_{i}") for i in (1, 2, 3)]))
    return u, comp


def regression(units_resid: pl.DataFrame) -> dict:
    u, comp = composition_features(units_resid)
    hb = _handedness(u)
    u = hb
    ctrl = ["ctrl_rapm", "ctrl_shoot", "hand_R_frac"]
    u = u.drop_nulls(comp + ctrl)
    y = u["residual"].to_numpy(); w = u["toi"].to_numpy().astype(float)
    groups = np.array([sorted(u["season_label"].unique().to_list()).index(s)
                       for s in u["season_label"].to_list()])
    seasons = sorted(u["season_label"].unique().to_list())

    def cv_r2(cols):
        X = u.select(cols).to_numpy()
        oof = np.zeros(len(y))
        for tr, te in GroupKFold(n_splits=len(seasons)).split(X, y, groups):
            m = RidgeCV(alphas=(0.1, 1, 10, 100)).fit(X[tr], y[tr], sample_weight=w[tr])
            oof[te] = m.predict(X[te])
        ss = np.sum(w * (y - oof) ** 2); tot = np.sum(w * (y - np.average(y, weights=w)) ** 2)
        return float(1 - ss / tot)
    r2_ctrl = cv_r2(ctrl)
    r2_both = cv_r2(ctrl + comp)
    return {"n": u.height, "cv_r2_controls": r2_ctrl, "cv_r2_controls_plus_composition": r2_both,
            "incremental_r2_composition": r2_both - r2_ctrl, "controls": ctrl, "composition": comp}


def _handedness(u: pl.DataFrame) -> pl.DataFrame:
    bio = pl.read_parquet(U.config.PARQUET / "enriched" / "player_bio.parquet").select(
        "player_id", "shoots")
    for i in (1, 2, 3):
        u = u.join(bio.rename({"player_id": f"f{i}", "shoots": f"sh{i}"}), on=f"f{i}", how="left")
    return u.with_columns(hand_R_frac=(
        (pl.col("sh1") == "R").cast(pl.Float64) + (pl.col("sh2") == "R").cast(pl.Float64)
        + (pl.col("sh3") == "R").cast(pl.Float64)) / 3.0).with_columns(
        hand_R_frac=pl.col("hand_R_frac").fill_null(0.33))


# ---------------------------------------------------------------- 2.6 verdict
def verdict(sh: dict, reg: dict) -> dict:
    stable = sh["passes"]
    material = reg["incremental_r2_composition"] >= 0.01      # pre-stated materiality floor
    weak_real = (not stable) and (sh["residual_split_half_r"] is not None
                                  and sh["residual_split_half_r"] > 0 and sh["p_value"] < 0.05)
    if not stable:
        outcome = "III_UNIT_NULL"
        decision = (
            "Units do not over-perform their parts STABLY ENOUGH to build on: the clean-anchor "
            f"residual split-half is {sh['residual_split_half_r']:.2f}, below the pre-stated 0.30 "
            "usability bar. " + (
                "It IS a real, placebo-beating signal (p<0.05) — units over-perform WEAKLY — but "
                "reliability this low cannot anchor a predictive composition model. "
                if weak_real else "It does not beat placebo. ")
            + "Per 2.6(iii) the role-composition FIT theory does not bear weight at the unit level on "
            "public event data; Link 1's two-way role PROFILES remain a valid descriptive asset.")
        return {"units_over_perform_stably": stable, "weak_real_signal": weak_real,
                "composition_material": material, "materiality_floor_incremental_r2": 0.01,
                "outcome": outcome, "decision": decision}
    if material:
        outcome, decision = "I_VIABLE", (
            "Units over-perform stably AND two-way role composition explains a material share beyond "
            "controls. Full four-link project is viable on public data, scoped to on-puck two-way "
            "role-fit.")
    else:
        outcome, decision = "II_BLOCKED_TRACKING", (
            "Units over-perform stably BUT composition explains little beyond controls: the fit lives "
            "in the still-invisible tier (off-puck movement, passing). Full project BLOCKED pending "
            "tracking data; what tracking would add is stated in the report.")
    return {"units_over_perform_stably": stable, "composition_material": material,
            "materiality_floor_incremental_r2": 0.01, "outcome": outcome, "decision": decision}


def run() -> dict:
    units = _load_units()
    anchors = {}
    for anchor in ("same", "prior"):
        ur, diag = build_residuals(units, anchor)
        anchors[anchor] = {"null_fit": diag, "split_half": split_half(ur), "residuals": ur}
    # Gate on the CLEAN (prior) anchor — the same-season anchor is contaminated (its residual
    # split-half straddles; Chemistry Phase-2 lesson). The prior anchor is the fair test.
    gate_sh = anchors["prior"]["split_half"]
    reg = regression(anchors["prior"]["residuals"])       # composition on the clean-anchor residual
    fm = {s: U.five_man_distribution(s) for s in config.SEASONS_PRIMARY}
    res = {"seed": SEED, "floor_min": FLOOR // 60, "n_perm": N_PERM,
           "unit_counts": {"trio_seasons_ge100min": units.height},
           "five_man_distribution": fm,
           "null_fit": {a: anchors[a]["null_fit"] for a in ("same", "prior")},
           "split_half": {a: anchors[a]["split_half"] for a in ("same", "prior")},
           "gate_anchor": "prior", "regression": reg,
           "verdict": verdict(gate_sh, reg)}
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "link2_analysis.json", "w") as f:
        json.dump(res, f, indent=2)
    return res


if __name__ == "__main__":
    r = run()
    reg, v = r["regression"], r["verdict"]
    print(f"trios>=100min: {r['unit_counts']['trio_seasons_ge100min']}")
    for a in ("same", "prior"):
        sh = r["split_half"][a]
        print(f"  [{a:5s}] null CV R2={r['null_fit'][a]['cv_r2_loso']:.3f} n={sh['n']} | "
              f"residual split-half r={sh['residual_split_half_r']:.3f} (raw {sh['raw_share_split_half_r']:.3f}) "
              f"placebo={sh['placebo_r_mean']:.3f} p={sh['p_value']:.4f} pass={sh['passes']}")
    print(f"GATE anchor: {r['gate_anchor']}")
    print(f"REGRESSION incremental R2 (composition beyond controls)={reg['incremental_r2_composition']:.4f} "
          f"[controls {reg['cv_r2_controls']:.3f} -> +comp {reg['cv_r2_controls_plus_composition']:.3f}]")
    print(f"VERDICT: {v['outcome']} — {v['decision']}")
