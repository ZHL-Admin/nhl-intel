"""Phase 2 · the keystone — is chemistry persistent at all?

Split-half (2.2) and year-over-year (2.3) persistence of the null-model pair RESIDUAL, under both
anchors, by strata, against placebos, with a pre-registered verdict (2.4) and descriptive exhibits
(2.5). All thresholds and verdict language are fixed in reports/phase2.md BEFORE results.

Split-half needs game resolution the season corpus lacks, so pair-half tables are derived here from
the frozen stints (odd/even shared games within a pair-season). Everything keys on the unique row id
`rid`; game order within a pair is by game_id (chronological within a season).
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import config, corpus
from . import nullmodel as nm

HALF_DIR = config.PARQUET / "pair_halves"
FROZEN_PAIRS = config.PARQUET / "frozen" / "pairs_corpus.parquet"
SEED = config.SEED
KEYS = ["a", "b", "team_id", "season_label"]
POS = ["D-D", "D-F", "F-F"]
STRATA = ["high_div", "mid_div", "low_div"]

# Pre-registered verdict thresholds (2.4), fixed before results.
SB_BAR = 0.30            # split-half Spearman-Brown reliability bar, 100-min tier
YOY_P = 0.05             # YoY permutation-test significance bar
N_PERM_YOY = 2000        # YoY permutation count (seed = SEED)
N_PERM_SH = 500          # split-half placebo shuffles (seed = SEED)
N_BOOT = 1000            # exhibit grouped-bootstrap resamples (seed = SEED)


# ---------------------------------------------------------------- pair-half table (2.2 input)
def build_pair_halves(season: str, write: bool = True) -> pl.DataFrame:
    """Per (a,b,team,season,half) aggregates, half = odd/even by game rank within the pair-season.
    Context (OZ, score mix, opp strength) recomputed per half; unfloored (analysis floors later)."""
    st = corpus._stints(season).with_columns(
        home_oz=(pl.col("start_type") == "OZ"), home_dz=(pl.col("start_type") == "DZ"))
    rmap = corpus._rapm_map(season)
    st = st.join(corpus._opp_rapm_per_stint(st, rmap), on="rid", how="left")

    def side(name):
        ids, xgf, xga, cf, ca, gf, ga, team, oz, dz, opp, sign = corpus._SIDES[name]
        base = st.select(
            rid=pl.col("rid"), game_id=pl.col("game_id"), sk=pl.col(ids), team_id=pl.col(team),
            dur=pl.col("duration_seconds"), xgf=pl.col(xgf), xga=pl.col(xga),
            oz=pl.col(oz), dz=pl.col(dz), opp_rapm=pl.col(opp),
            rel_score=pl.col("score_state") * sign)
        keys = pl.concat([
            base.select("rid",
                        a=pl.min_horizontal(pl.col("sk").list.get(i), pl.col("sk").list.get(j)),
                        b=pl.max_horizontal(pl.col("sk").list.get(i), pl.col("sk").list.get(j)))
            for i, j in corpus._PAIR_IDX])
        return keys.join(base.drop("sk"), on="rid")

    pk = pl.concat([side("home"), side("away")])
    # game rank within (a,b,team) -> half parity (0/1). dense rank over distinct game_id.
    games = (pk.select("a", "b", "team_id", "game_id").unique()
             .with_columns(rank=pl.col("game_id").rank("dense").over("a", "b", "team_id"))
             .with_columns(half=(pl.col("rank") % 2)))
    pk = pk.join(games.select("a", "b", "team_id", "game_id", "half"),
                 on=["a", "b", "team_id", "game_id"], how="left")
    agg = pk.group_by("a", "b", "team_id", "half").agg(
        toi=pl.col("dur").sum(), xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
        oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum(),
        opp_rapm=(pl.col("opp_rapm") * pl.col("dur")).sum() / pl.col("dur").sum(),
        toi_lead=pl.col("dur").filter(pl.col("rel_score") > 0).sum(),
        toi_tied=pl.col("dur").filter(pl.col("rel_score") == 0).sum(),
        toi_trail=pl.col("dur").filter(pl.col("rel_score") < 0).sum(),
        n_games=pl.col("game_id").n_unique()).with_columns(
        season_label=pl.lit(season),
        xg_share=pl.col("xgf") / (pl.col("xgf") + pl.col("xga")),
        oz_start_share=pl.when(pl.col("oz_starts") + pl.col("dz_starts") > 0)
        .then(pl.col("oz_starts") / (pl.col("oz_starts") + pl.col("dz_starts"))).otherwise(None),
        share_lead=pl.col("toi_lead") / pl.col("toi"), share_trail=pl.col("toi_trail") / pl.col("toi"))
    if write:
        HALF_DIR.mkdir(parents=True, exist_ok=True)
        agg.write_parquet(HALF_DIR / f"{season.replace('-', '_')}.parquet")
    return agg


# ---------------------------------------------------------------- diversity strata (2.1b)
def diversity_metric(season: str) -> pl.DataFrame:
    """Per (player, season): within-position top-partner TOI share (the O3 locking measure).
    Higher share = more locked = less partner diversity."""
    pf = corpus._pos_frame()
    posmap = dict(zip(pf["player_id"].to_list(), pf["pg"].to_list()))
    long = corpus.partner_toi_long(season).with_columns(
        pg=pl.col("pid").replace_strict(posmap, default="F", return_dtype=pl.Utf8),
        ppg=pl.col("partner").replace_strict(posmap, default="F", return_dtype=pl.Utf8))
    sp = (long.filter(pl.col("pg") == pl.col("ppg")).group_by("pid").agg(
        sp_total=pl.col("toi").sum(), sp_top=pl.col("toi").max())
        .filter(pl.col("sp_total") > 0)
        .with_columns(top_share=pl.col("sp_top") / pl.col("sp_total"), season_label=pl.lit(season)))
    return sp.select("pid", "season_label", "top_share")


def pair_strata(pairs: pl.DataFrame) -> pl.DataFrame:
    """Assign each pair a diversity metric = mean of the two players' within-position top-partner
    shares, then GLOBAL terciles. Stratum 'high_div' = LOW top-share tercile (most diverse usage)."""
    dm = pl.concat([diversity_metric(s) for s in sorted(pairs["season_label"].unique().to_list())],
                   how="vertical_relaxed")
    out = pairs
    for who in ("a", "b"):
        out = out.join(dm.rename({"pid": who, "top_share": f"{who}_topshare"}),
                       on=[who, "season_label"], how="left")
    out = out.with_columns(
        pair_lock=(pl.col("a_topshare") + pl.col("b_topshare")) / 2.0)
    q1, q2 = out["pair_lock"].quantile(1 / 3), out["pair_lock"].quantile(2 / 3)
    out = out.with_columns(
        stratum=pl.when(pl.col("pair_lock") <= q1).then(pl.lit("high_div"))
        .when(pl.col("pair_lock") <= q2).then(pl.lit("mid_div"))
        .otherwise(pl.lit("low_div")))
    return out.select("a", "b", "team_id", "season_label", "pair_lock", "stratum"), (float(q1), float(q2))


# ---------------------------------------------------------------- weighted-stat helpers
def _wcorr(x, y, w) -> float:
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    vx, vy = np.average((x - mx) ** 2, weights=w), np.average((y - my) ** 2, weights=w)
    if vx <= 0 or vy <= 0:
        return float("nan")
    return float(cov / np.sqrt(vx * vy))


def _spearman_brown(r: float) -> float:
    return float(2 * r / (1 + r)) if r > -1 else float("nan")


def _within_cell_perm(cell_id: np.ndarray, rng) -> np.ndarray:
    """Index array p such that y[p] permutes y WITHIN each cell (matched placebo)."""
    n = len(cell_id)
    perm_order = np.lexsort((rng.random(n), cell_id))     # positions grouped by cell, random inside
    slot_order = np.lexsort((np.arange(n), cell_id))      # positions grouped by cell, stable inside
    p = np.empty(n, dtype=np.int64)
    p[slot_order] = perm_order
    return p


def ensure_halves(seasons):
    for s in seasons:
        if not (HALF_DIR / f"{s.replace('-', '_')}.parquet").exists():
            build_pair_halves(s)


def _read_halves(seasons) -> pl.DataFrame:
    return pl.concat([pl.read_parquet(HALF_DIR / f"{s.replace('-', '_')}.parquet") for s in seasons],
                     how="vertical_relaxed")


# ---------------------------------------------------------------- 2.2 split-half persistence
def split_half(resid_season: pl.DataFrame, anchor: str, pairs: pl.DataFrame, strata_df: pl.DataFrame,
               seasons, tier_floor: int = 6000) -> dict:
    # Baseline is the pair-SEASON null prediction (one value per pair), subtracted from each half.
    # The null MUST NOT be re-predicted with half-specific context: score-state mix is endogenous
    # (post-outcome), so per-half re-prediction leaks performance into the baseline and flips the
    # split-half negative. With a per-pair-constant baseline, split-half reliability of the residual
    # equals that of the pair-season xG-share measurement itself (quality is a season constant and
    # cannot move a within-pair across-half correlation) — YoY (2.3) is what isolates chemistry.
    sctx = pairs.select(*KEYS, "pos_pair", "tier", pl.col("toi").alias("season_toi"))
    predtab = resid_season.select(*KEYS, "pred")
    h = (_read_halves(seasons).join(sctx, on=KEYS, how="inner")
         .join(strata_df.select(*KEYS, "stratum"), on=KEYS, how="left")
         .join(predtab, on=KEYS, how="inner")
         .filter((pl.col("season_toi") >= tier_floor) & ((pl.col("xgf") + pl.col("xga")) > 0))
         .with_columns(resid=pl.col("xg_share") - pl.col("pred")))
    idx = [*KEYS, "pos_pair", "tier", "season_toi", "stratum"]
    odd = h.filter(pl.col("half") == 1).select(*idx, r_odd="resid", x_odd="xg_share")
    even = h.filter(pl.col("half") == 0).select(*idx, r_even="resid", x_even="xg_share")
    w = odd.join(even, on=idx, how="inner")

    def block(df):
        if df.height < 20:
            return {"n": df.height, "r": None, "sb_reliability": None, "placebo_r_mean": None,
                    "raw_share_r": None, "raw_share_sb": None}
        ww = df["season_toi"].to_numpy().astype(float)
        r = _wcorr(df["r_odd"].to_numpy(), df["r_even"].to_numpy(), ww)          # residual (chemistry)
        rr = _wcorr(df["x_odd"].to_numpy(), df["x_even"].to_numpy(), ww)         # raw share (measurement)
        rng = np.random.default_rng(SEED)
        yy = df["r_even"].to_numpy()
        perms = [_wcorr(df["r_odd"].to_numpy(), yy[rng.permutation(len(yy))], ww) for _ in range(N_PERM_SH)]
        return {"n": df.height, "r": r, "sb_reliability": _spearman_brown(r),
                "raw_share_r": rr, "raw_share_sb": _spearman_brown(rr),
                "placebo_r_mean": float(np.mean(perms)), "placebo_r_sd": float(np.std(perms))}

    out = {"overall": block(w),
           "by_pos": {p: block(w.filter(pl.col("pos_pair") == p)) for p in POS},
           "by_tier": {str(t): block(w.filter(pl.col("tier") == t)) for t in (100, 200)},
           "by_stratum": {s: block(w.filter(pl.col("stratum") == s)) for s in STRATA}}
    return out


# ---------------------------------------------------------------- 2.3 year-over-year persistence
def yoy(resid_tbl: pl.DataFrame, anchor: str, strata_df: pl.DataFrame,
        floor: int = 6000, n_perm: int = N_PERM_YOY) -> dict:
    sidx = {s: i for i, s in enumerate(config.SEASONS_ALL)}
    r = (resid_tbl.filter(pl.col("toi") >= floor)
         .join(strata_df.select(*KEYS, "stratum"), on=KEYS, how="left")
         .with_columns(si=pl.col("season_label").replace_strict(sidx, return_dtype=pl.Int32))
         .select("a", "b", "team_id", "si", "pos_pair", "stratum",
                 residual="residual", toi="toi"))
    nxt = r.select("a", "b", (pl.col("si") - 1).alias("si"),
                   resid_next="residual", toi_next="toi", team_next="team_id", pos_next="pos_pair")
    trans = r.join(nxt, on=["a", "b", "si"], how="inner")
    if trans.height < 20:
        return {"n_transitions": trans.height, "same_pair_r": None}

    def block(df):
        if df.height < 20:
            return {"n": df.height, "same_pair_r": None, "placebo_r_mean": None, "p_value": None}
        x = df["residual"].to_numpy(); y = df["resid_next"].to_numpy()
        ww = np.minimum(df["toi"].to_numpy(), df["toi_next"].to_numpy()).astype(float)
        # matched cells = (destination team, position class)
        cell = df.select(pl.concat_str([pl.col("team_next").cast(pl.Utf8), pl.lit("|"),
                                        pl.col("pos_next")]).alias("c"))["c"].to_numpy()
        _, cell_id = np.unique(cell, return_inverse=True)
        obs = _wcorr(x, y, ww)
        rng = np.random.default_rng(SEED)
        perm = np.array([_wcorr(x, y[_within_cell_perm(cell_id, rng)], ww) for _ in range(n_perm)])
        pval = float((np.sum(perm >= obs) + 1) / (n_perm + 1))
        return {"n": df.height, "same_pair_r": obs, "placebo_r_mean": float(np.mean(perm)),
                "placebo_r_p95": float(np.quantile(perm, 0.95)), "p_value": pval}

    out = {"overall": block(trans),
           "by_pos": {p: block(trans.filter(pl.col("pos_pair") == p)) for p in POS},
           "by_stratum": {s: block(trans.filter(pl.col("stratum") == s)) for s in STRATA}}
    out["n_transitions"] = trans.height
    return out


# ---------------------------------------------------------------- 2.4 verdict (pre-registered)
def verdict(anchors_res: dict) -> dict:
    prim_sh = anchors_res["same"]["split_half"]["overall"]
    sb = prim_sh["sb_reliability"]
    yp = anchors_res["same"]["yoy"]["overall"]["p_value"]
    sh_pass = sb is not None and sb >= SB_BAR
    yoy_pass = yp is not None and yp < YOY_P
    v = {"primary_anchor": "same", "sb_reliability_100tier": sb, "sb_bar": SB_BAR,
         "yoy_p_value": yp, "yoy_bar": YOY_P, "split_half_pass": sh_pass, "yoy_pass": yoy_pass,
         # 2.1b contamination context (not verdict inputs; transparency): the same-anchor residual
         # split-half is depressed by anchor contamination. Report the baseline-free and clean-anchor
         # reliabilities alongside.
         "context": {"primary_raw_share_sb": prim_sh.get("raw_share_sb"),
                     "prior_anchor_residual_sb": anchors_res["prior"]["split_half"]["overall"]["sb_reliability"],
                     "prior_anchor_yoy_p": anchors_res["prior"]["yoy"]["overall"]["p_value"]}}

    def stratum_passes(anchor):
        s = anchors_res[anchor]["split_half"]["by_stratum"]["high_div"]["sb_reliability"]
        p = anchors_res[anchor]["yoy"]["by_stratum"]["high_div"]["p_value"]
        return (s is not None and s >= SB_BAR) and (p is not None and p < YOY_P)
    rescue_ok = stratum_passes("same") and stratum_passes("prior")
    v["rescue_high_div_both_anchors"] = rescue_ok

    if sh_pass and yoy_pass:
        v["outcome"] = "PASS"
        v["decision"] = ("Both bars cleared on the primary anchor, full population. The predictive "
                         "arm proceeds; Phases 3-5 run.")
    elif sh_pass and not yoy_pass:
        v["outcome"] = "SPLIT_HALF_ONLY"
        v["decision"] = ("Split-half clears 0.30 but YoY does not exceed its placebo at p<0.05. "
                         "Proceed with Phase 5 claim language pre-limited to WITHIN-ERA prediction; "
                         "bars unchanged.")
    elif (not sh_pass) and (not yoy_pass) and rescue_ok:
        v["outcome"] = "RESCUE_DIVERSE"
        v["decision"] = ("Both full-population bars fail, but the high-diversity stratum clears BOTH "
                         "bars under BOTH anchors. Project proceeds SCOPED TO DIVERSE PAIRS; locked "
                         "pairs carried descriptively only; the scope limit is stated in every "
                         "downstream claim.")
    elif (not sh_pass) and (not yoy_pass):
        v["outcome"] = "FAIL"
        v["decision"] = ("Both bars fail and the rescue stratum does not clear both bars under both "
                         "anchors. The predictive arm dies: Phases 3-5 cancel; Phase 6 packages the "
                         "corpus and the null finding.")
    else:  # split-half fails on primary but YoY passes — NOT an explicit 2.4 branch
        v["outcome"] = "UNDEFINED_BY_2.4__OWNER_RULES"
        v["decision"] = ("Primary-anchor split-half does NOT clear 0.30 while YoY DOES exceed its "
                         "placebo (p<0.05). 2.4 defines PASS (both), split-half-only, and both-fail, "
                         "but not this YoY-only case. The primary-anchor split-half is additionally "
                         "confounded by 2.1b anchor contamination (see context: raw-share and "
                         "prior-anchor reliabilities). Rescue clause "
                         + ("IS" if rescue_ok else "is NOT") + " triggered. Owner rules on survival.")
    return v


# ---------------------------------------------------------------- 2.5 exhibits
def _pair_games_2024(pairs_keys: pl.DataFrame) -> pl.DataFrame:
    """Per (a,b,team,game) xgf/xga for a given set of 2024-25 pairs (grouped-bootstrap input)."""
    st = corpus._stints("2024-25")

    def side(name):
        ids, xgf, xga, *_rest = corpus._SIDES[name]
        team = corpus._SIDES[name][7]
        base = st.select(rid="rid", game_id="game_id", sk=pl.col(ids), team_id=pl.col(team),
                         xgf=pl.col(xgf), xga=pl.col(xga))
        keys = pl.concat([base.select("rid",
                          a=pl.min_horizontal(pl.col("sk").list.get(i), pl.col("sk").list.get(j)),
                          b=pl.max_horizontal(pl.col("sk").list.get(i), pl.col("sk").list.get(j)))
                          for i, j in corpus._PAIR_IDX])
        return keys.join(base.drop("sk"), on="rid")
    pk = pl.concat([side("home"), side("away")]).join(pairs_keys, on=["a", "b", "team_id"], how="inner")
    return pk.group_by("a", "b", "team_id", "game_id").agg(xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum())


def exhibits(resid_same: pl.DataFrame) -> dict:
    names = dict(zip(*[pl.read_parquet(config.ATLAS_PARQUET / "top20_2024_25.parquet")[c].to_list()
                       for c in ("player_id", "name")])) if (
        config.ATLAS_PARQUET / "top20_2024_25.parquet").exists() else {}

    def nm_of(pid):
        return names.get(pid, str(pid))

    # top/bottom 15 residuals of 2024-25 among stable pairs (>=200 min), grouped-bootstrap CI
    r24 = resid_same.filter((pl.col("season_label") == "2024-25") & (pl.col("toi") >= 12000))
    top_df = r24.sort("residual", descending=True).head(15)
    bot_df = r24.sort("residual").head(15)
    sel = pl.concat([top_df, bot_df]).select("a", "b", "team_id").unique()
    pg = _pair_games_2024(sel).sort("a", "b", "team_id", "game_id")
    boot = {}
    rng = np.random.default_rng(SEED)
    for row in pl.concat([top_df, bot_df]).unique(subset=["a", "b", "team_id"]).iter_rows(named=True):
        g = pg.filter((pl.col("a") == row["a"]) & (pl.col("b") == row["b"]) & (pl.col("team_id") == row["team_id"]))
        f = g["xgf"].to_numpy(); ag = g["xga"].to_numpy(); ng = len(f)
        if ng < 2:
            boot[(row["a"], row["b"], row["team_id"])] = (None, None)
            continue
        idx = rng.integers(0, ng, size=(N_BOOT, ng))
        sf = f[idx].sum(axis=1); sa = ag[idx].sum(axis=1)
        share_b = np.where((sf + sa) > 0, sf / (sf + sa), np.nan)
        resid_b = share_b - row["pred"]
        boot[(row["a"], row["b"], row["team_id"])] = (float(np.nanquantile(resid_b, 0.025)),
                                                      float(np.nanquantile(resid_b, 0.975)))

    def pack(df):
        rows = []
        for row in df.iter_rows(named=True):
            lo, hi = boot.get((row["a"], row["b"], row["team_id"]), (None, None))
            rows.append({"a": row["a"], "b": row["b"], "team_id": row["team_id"],
                         "pair": f"{nm_of(row['a'])} + {nm_of(row['b'])}", "pos": row["pos_pair"],
                         "toi_min": round(row["toi"] / 60, 0), "xg_share": round(row["xg_share"], 3),
                         "residual": round(row["residual"], 4), "ci95": [None if lo is None else round(lo, 4),
                                                                        None if hi is None else round(hi, 4)]})
        return rows
    top = pack(top_df)
    bot = pack(bot_df)

    # long-tenure "famous" pairs: most cumulative shared TOI across seasons; pooled TOI-wtd residual
    ten = (resid_same.group_by("a", "b").agg(
        seasons_together=pl.len(), total_toi=pl.col("toi").sum(),
        pooled_resid=(pl.col("residual") * pl.col("toi")).sum() / pl.col("toi").sum())
        .filter(pl.col("seasons_together") >= 3).sort("total_toi", descending=True).head(15))
    tenure = [{"a": r["a"], "b": r["b"], "pair": f"{nm_of(r['a'])} + {nm_of(r['b'])}",
               "seasons_together": r["seasons_together"], "total_toi_min": round(r["total_toi"] / 60, 0),
               "pooled_residual": round(r["pooled_resid"], 4)} for r in ten.iter_rows(named=True)]

    return {"note": ("player names are not in the frozen inputs; only the 2024-25 top-20 are labelled, "
                     "the rest shown by player_id (full name resolution deferred to production dim)."),
            "top15_positive_2024_25": top, "bottom15_negative_2024_25": bot,
            "long_tenure_pairs": tenure}


# ---------------------------------------------------------------- driver
def run(seasons=None) -> dict:
    seasons = seasons or config.SEASONS_ALL
    ensure_halves(seasons)
    pairs = pl.read_parquet(FROZEN_PAIRS)
    strata_df, terciles = pair_strata(pairs.select(*KEYS))
    res = {"seed": SEED, "seasons": seasons,
           "housekeeping": {"syseff_durability_commit": "3ae4f52f7021ccd89c470ac5797cdc88ab8cf06a",
                            "made": True, "files": 51, "insertions": 17022},
           "strata_terciles_pair_lock": terciles, "anchors": {}}
    exhibit_resid = None
    for anchor in ("same", "prior"):
        pr, dropped = nm.attach_ratings(pairs, anchor)
        model, diag, resid = nm.fit_null(pr, anchor)
        if anchor == "same":
            exhibit_resid = resid
        res["anchors"][anchor] = {
            "null_fit": {k: diag[k] for k in ("n", "cv_r2_loso_weighted", "in_sample_r2_weighted",
                                              "residual_toi_wtd_mean", "residual_sd", "coefficients")},
            "dropped_missing_rating": dropped,
            "split_half": split_half(resid, anchor, pairs, strata_df, seasons),
            "yoy": yoy(resid, anchor, strata_df)}
    res["verdict"] = verdict(res["anchors"])
    res["exhibits"] = exhibits(exhibit_resid)
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "phase2_analysis.json", "w") as f:
        json.dump(res, f, indent=2)
    return res


if __name__ == "__main__":
    import sys
    if "--halves" in sys.argv:
        for s in config.SEASONS_ALL:
            print(f"{s}: pair-halves rows={build_pair_halves(s).height:,}", flush=True)
    else:
        r = run()
        v = r["verdict"]
        sh = r["anchors"]["same"]["split_half"]["overall"]
        yy = r["anchors"]["same"]["yoy"]["overall"]
        print("SPLIT-HALF (same, overall):", {k: (round(v, 4) if isinstance(v, float) else v)
                                              for k, v in sh.items()})
        print("YoY (same, overall):", {k: (round(vv, 4) if isinstance(vv, float) else vv)
                                        for k, vv in yy.items()})
        print("VERDICT:", v["outcome"], "|", v["decision"])
