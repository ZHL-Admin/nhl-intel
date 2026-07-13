"""Link B (GATE) — is DEPENDENCE a stable individual trait? (shot-share axis only)

Dependence score per (player A, season): how much A's shoot-vs-defer choice swings across his
partners — the across-partner spread of shot-share, NOISE-CORRECTED (a player measured over few
attempts has an inflated raw spread; we subtract the binomial measurement variance so the score is
the reliable swing, not the sampling floor). High score = "his game changes a lot by partner";
low = "he plays his game regardless." Reported with absolute magnitude, in shot-share points.

Stability gate (pre-registered): split-half within season (odd/even shared games) >= 0.40 AND
same-team YoY >= 0.30, each beating a shuffled-identity (within position-season) placebo at p<0.05.
The ACROSS-team-change retention is reported prominently — it decides whether a Link-C predictor can
travel with the player or is a property of his situations. B.3 interpretation pass: who is dependent
(experience, player_type, TOI tier, offense/defense balance). Q3 (unit-grain deference) is carried
descriptively only; quality/location axes are NOT dependence features (they are Link-C controls).
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import config
from . import behavior as B
from .linkA import _wcorr
import chem.corpus as cc

FLOOR = 6000
MIN_PARTNERS = 3
N_PERM = 1000
SB_SPLIT = 0.40
SB_YOY = 0.30


def _load() -> pl.DataFrame:
    d = pl.concat([pl.read_parquet(p) for p in sorted(B.BEHAV_DIR.glob("*.parquet"))],
                  how="vertical_relaxed").filter(pl.col("shared_toi") >= FLOOR)
    keep = d.group_by("A", "season_label").len().filter(pl.col("len") >= MIN_PARTNERS)
    return d.join(keep.select("A", "season_label"), on=["A", "season_label"], how="inner")


def _dep(d: pl.DataFrame, share: str, na: str, nb: str, w: str, out: str) -> pl.DataFrame:
    """Noise-corrected across-partner dependence per (A,season): sqrt(max(0, wVar(share) − wMean(noise)))
    with noise = share(1−share)/(A+B attempts), weighted by w. Requires 2+ valid partners."""
    s = d.drop_nulls([share]).filter(pl.col(na) + pl.col(nb) > 0).with_columns(
        noise=pl.col(share) * (1 - pl.col(share)) / (pl.col(na) + pl.col(nb)))
    g = s.group_by("A", "season_label").agg(
        n_part=pl.len(),
        wmean=(pl.col(share) * pl.col(w)).sum() / pl.col(w).sum(),
        wsq=(pl.col(share) ** 2 * pl.col(w)).sum() / pl.col(w).sum(),
        wnoise=(pl.col("noise") * pl.col(w)).sum() / pl.col(w).sum())
    return g.filter(pl.col("n_part") >= 2).with_columns(
        **{out: (pl.col("wsq") - pl.col("wmean") ** 2 - pl.col("wnoise")).clip(0).sqrt()}).select(
        "A", "season_label", out, pl.col("n_part").alias(f"{out}_npart"))


def build_dependence(d: pl.DataFrame) -> pl.DataFrame:
    full = _dep(d, "A_shot_share", "n_shot", "B_shot", "shared_toi", "dep")
    odd = _dep(d, "A_shot_share_odd", "n_shot_odd", "B_shot_odd", "shared_toi", "dep_odd")
    even = _dep(d, "A_shot_share_even", "n_shot_even", "B_shot_even", "shared_toi", "dep_even")
    dep = full.join(odd, on=["A", "season_label"], how="left").join(even, on=["A", "season_label"], how="left")
    # position (global modal F/D) + primary team per (A,season) from role-fit rich profiles
    pf = cc._pos_frame().rename({"player_id": "A"})
    team = pl.concat([pl.read_parquet(p).select(A="pid", season_label="season_label", team_id="team_id")
                      for p in sorted(config.RICH_PROFILE_DIR.glob("*.parquet"))], how="vertical_relaxed")
    return dep.join(pf, on="A", how="left").with_columns(pg=pl.col("pg").fill_null("F")).join(
        team, on=["A", "season_label"], how="left")


def _z(df: pl.DataFrame, col: str) -> pl.DataFrame:
    return df.with_columns(**{f"{col}_z": (pl.col(col) - pl.col(col).mean().over("pg", "season_label"))
                              / pl.col(col).std().over("pg", "season_label")})


def _rel(x, y, w, cell_ids):
    r = _wcorr(x, y, w)
    rng = np.random.default_rng(config.SEED); n = len(y); slot = np.lexsort((np.arange(n), cell_ids))
    perms = np.empty(N_PERM)
    for k in range(N_PERM):
        src = np.lexsort((rng.random(n), cell_ids)); p = np.empty(n, dtype=np.int64); p[slot] = src
        perms[k] = _wcorr(x, y[p], w)
    return {"n": n, "r": r, "placebo_mean": float(np.mean(perms)),
            "p": float((np.sum(perms >= r) + 1) / (N_PERM + 1))}


def stability(dep: pl.DataFrame) -> dict:
    sidx = {s: i for i, s in enumerate(config.SEASONS_ALL)}
    # split-half (odd/even dep), z within (pg,season); placebo shuffles identity within pg-season
    sh = _z(_z(dep.drop_nulls(["dep_odd", "dep_even"]), "dep_odd"), "dep_even")
    cell = np.unique(sh.select(pl.concat_str(["pg", pl.lit("|"), "season_label"])).to_series().to_numpy(),
                     return_inverse=True)[1]
    w = np.ones(sh.height)
    split = _rel(sh["dep_odd_z"].to_numpy(), sh["dep_even_z"].to_numpy(), w, cell)
    # YoY: z the full dep within (pg, season), join consecutive seasons per player
    zf = _z(dep.drop_nulls(["dep"]), "dep").with_columns(si=pl.col("season_label").replace_strict(sidx, return_dtype=pl.Int32))
    nxt = zf.select("A", (pl.col("si") - 1).alias("si"), dep_z_n="dep_z", team_next="team_id", pg_n="pg")
    tr = zf.join(nxt, on=["A", "si"], how="inner").with_columns(same=(pl.col("team_id") == pl.col("team_next")))

    def yoy(sub):
        c = np.unique(sub.select(pl.concat_str(["pg", pl.lit("|"), pl.col("si").cast(pl.Utf8)])).to_series().to_numpy(),
                      return_inverse=True)[1]
        return _rel(sub["dep_z"].to_numpy(), sub["dep_z_n"].to_numpy(), np.ones(sub.height), c)
    same = yoy(tr.filter(pl.col("same")))
    across = yoy(tr.filter(~pl.col("same")))
    retention = across["r"] / same["r"] if same["r"] and same["r"] > 0 else None
    return {"split_half": split, "yoy_same_team": same, "yoy_across_team": across,
            "across_team_retention": retention}


def interpretation(dep: pl.DataFrame) -> dict:
    """B.3 who-is-dependent: correlate dependence with experience, player_type, TOI tier, off/def."""
    pt = pl.read_parquet(config.SYSEFF_PARQUET / "player_types.parquet").select(
        "player_id", "season_label", "player_type", "toi_5v5_min", "off_impact", "def_impact")
    # experience proxy = seasons since first appearance in the dependence corpus
    first = dep.group_by("A").agg(first_si=pl.col("season_label").replace_strict(
        {s: i for i, s in enumerate(config.SEASONS_ALL)}, return_dtype=pl.Int32).min())
    d = (_z(dep.drop_nulls(["dep"]), "dep").join(first, on="A", how="left")
         .join(pt.rename({"player_id": "A"}), on=["A", "season_label"], how="left")
         .with_columns(exp=pl.col("season_label").replace_strict(
             {s: i for i, s in enumerate(config.SEASONS_ALL)}, return_dtype=pl.Int32) - pl.col("first_si"),
             offdef=pl.col("off_impact") - pl.col("def_impact")))

    def corr(col):
        s = d.drop_nulls(["dep_z", col])
        return round(float(np.corrcoef(s["dep_z"], s[col])[0, 1]), 3) if s.height > 50 else None
    by_type = (d.drop_nulls(["player_type"]).group_by("player_type").agg(
        dep_z=pl.col("dep_z").mean(), n=pl.len()).filter(pl.col("n") >= 30).sort("dep_z").to_dicts())
    return {"corr_experience": corr("exp"), "corr_toi5v5": corr("toi_5v5_min"),
            "corr_offense_off_impact": corr("off_impact"), "corr_offdef_balance": corr("offdef"),
            "dep_by_player_type": by_type}


def run() -> dict:
    dep = build_dependence(_load())
    st = stability(dep)
    v_split = st["split_half"]["r"] >= SB_SPLIT and st["split_half"]["p"] < 0.05
    v_yoy = st["yoy_same_team"]["r"] >= SB_YOY and st["yoy_same_team"]["p"] < 0.05
    dm = dep.drop_nulls("dep")["dep"]
    res = {"seed": config.SEED_TAG, "floor_min": FLOOR // 60, "n_perm": N_PERM,
           "n_player_seasons": dep.drop_nulls("dep").height,
           "dependence_magnitude": {"median_dep_share_pts": float(dm.median()),
                                    "p90": float(dm.quantile(0.9)), "p10": float(dm.quantile(0.1))},
           "stability": st, "interpretation": interpretation(dep),
           "verdict": {"split_half_pass": v_split, "yoy_same_pass": v_yoy,
                       "bars": {"split_half": SB_SPLIT, "yoy_same": SB_YOY},
                       "outcome": "PASS" if (v_split and v_yoy) else "FAIL",
                       "across_team_retention": st["across_team_retention"]}}
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "linkB_analysis.json", "w") as f:
        json.dump(res, f, indent=2)
    return res


if __name__ == "__main__":
    r = run()
    st, v = r["stability"], r["verdict"]
    dm = r["dependence_magnitude"]
    print(f"player-seasons: {r['n_player_seasons']}  dependence median={dm['median_dep_share_pts']:.3f} "
          f"(p10={dm['p10']:.3f} p90={dm['p90']:.3f}) share-pts")
    print(f"  split-half r={st['split_half']['r']:.3f} (p={st['split_half']['p']:.3f}) bar={SB_SPLIT}")
    print(f"  YoY same-team r={st['yoy_same_team']['r']:.3f} (p={st['yoy_same_team']['p']:.3f}) bar={SB_YOY}")
    print(f"  YoY across-team r={st['yoy_across_team']['r']:.3f}  -> RETENTION={st['across_team_retention']}")
    print("  who-is-dependent:", r["interpretation"]["corr_experience"], "exp |",
          r["interpretation"]["corr_toi5v5"], "toi |", r["interpretation"]["corr_offdef_balance"], "off-def")
    print("VERDICT:", v["outcome"], f"(split {v['split_half_pass']}, yoy {v['yoy_same_pass']})")
