"""Link 1 re-gate on the UL-P1-enriched role space (§1b).

Same pre-registered bars as §1 (split-half >= 0.50, same-team YoY >= 0.40, each beating a
shuffled-identity placebo at p<0.05, seed 20260713), now on the RICH axis set: shot axes + recovered
INDIVIDUAL two-way axes (possession/defense/discipline) + UNIT-level opponent-mirror suppression.
Reported at RAW-AXIS grain (so "which recovered axes clear" is explicit), plus a refit PCA role
space on the individual axes. Player-vs-team (same- vs across-team YoY) is reported for every axis —
the two-way and unit axes are the ones whose player-vs-team split we most need before Link 2.

Rink-scorer-bias caveat carried: takeaway/giveaway/hit counts vary by arena; treat magnitudes as
proxies, not truth (the stability test is about repeatability, which bias inflates less than levels).
Faceoff win% is season-grain (all-strength, stats-REST) -> YoY only, no split-half.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl
from sklearn.decomposition import PCA

from . import config
from . import profiles as P
from .link1 import _corr, _perm_p, _spearman_brown, SB_SPLIT, SB_YOY, N_PERM, TOI_FLOOR, MIN_GAMES, N_COMP

RICH_DIR = P.RICH_DIR
INDIV = P.RICH_INDIV_AXES          # shot + two-way individual axes (fed to PCA)
UNIT = P.UNIT_AXES                  # ca60, xga60 (unit-level; reported, not in PCA)
ALL_AXES = INDIV + UNIT
NEW_AXES = P.INDIV_NEW + UNIT       # the recovered axes (the point of the re-gate)


def _load() -> pl.DataFrame:
    return pl.concat([pl.read_parquet(p) for p in sorted(RICH_DIR.glob("*.parquet"))],
                     how="vertical_relaxed")


def _season_stats(prof, axes):
    return prof.group_by("pg", "season_label").agg(
        [pl.col(a).mean().alias(f"{a}__m") for a in axes]
        + [pl.col(a).std().alias(f"{a}__s") for a in axes])


def _z(prof, stats, axes, src):
    d = prof.join(stats, on=["pg", "season_label"], how="left")
    return d.with_columns([((pl.col(f"{a}{src}") - pl.col(f"{a}__m")) / pl.col(f"{a}__s")).alias(f"z_{a}")
                           for a in axes])


# ---------------------------------------------------------------- raw-axis stability (the re-gate)
def raw_axis_stability(prof) -> dict:
    stats = _season_stats(prof, ALL_AXES)
    sidx = {s: i for i, s in enumerate(config.SEASONS_ALL)}
    rng = np.random.default_rng(config.SEED)
    out = {}
    for pos in ("F", "D"):
        base = prof.filter(pl.col("pg") == pos)
        zf = _z(base, stats, ALL_AXES, "").with_columns(si=pl.col("season_label").replace_strict(sidx, return_dtype=pl.Int32))
        zo = _z(base.filter(pl.col("games") >= MIN_GAMES), stats, ALL_AXES, "_odd")
        ze = _z(base.filter(pl.col("games") >= MIN_GAMES), stats, ALL_AXES, "_even")
        sh = zo.join(ze, on=["pid", "season_label"], how="inner", suffix="_e")
        # YoY transitions
        nxt = zf.select("pid", (pl.col("si") - 1).alias("si"), team_next="team_id",
                        *[pl.col(f"z_{a}").alias(f"z_{a}_n") for a in ALL_AXES])
        tr = zf.filter(pl.col("toi") >= TOI_FLOOR).join(nxt, on=["pid", "si"], how="inner").with_columns(
            same=(pl.col("team_id") == pl.col("team_next")))
        res = {}
        for a in ALL_AXES:
            sx = sh.drop_nulls([f"z_{a}", f"z_{a}_e"])
            r_sh = _corr(sx[f"z_{a}"].to_numpy(), sx[f"z_{a}_e"].to_numpy())
            p_sh, pm_sh = _perm_p(sx[f"z_{a}"].to_numpy(), sx[f"z_{a}_e"].to_numpy(), r_sh, rng, n=N_PERM)
            ax = {"split_half_r": r_sh, "split_half_sb": _spearman_brown(r_sh), "split_p": p_sh,
                  "n_split": sx.height, "unit_level": a in UNIT}
            for label in ("same", "across"):
                sub = tr.filter(pl.col("same") if label == "same" else ~pl.col("same")).drop_nulls([f"z_{a}", f"z_{a}_n"])
                r = _corr(sub[f"z_{a}"].to_numpy(), sub[f"z_{a}_n"].to_numpy())
                pv, pm = _perm_p(sub[f"z_{a}"].to_numpy(), sub[f"z_{a}_n"].to_numpy(), r, rng, n=N_PERM)
                ax[f"yoy_{label}_r"] = r; ax[f"yoy_{label}_p"] = pv; ax[f"yoy_{label}_n"] = sub.height
            ax["retained_frac"] = (ax["yoy_across_r"] / ax["yoy_same_r"]
                                   if ax["yoy_same_r"] and ax["yoy_same_r"] > 0 else None)
            res[a] = ax
        out[pos] = res
    return out


# ---------------------------------------------------------------- rich PCA role space
def role_space(prof) -> dict:
    stats = _season_stats(prof, INDIV)
    spaces = {}
    for pos in ("F", "D"):
        base = _z(prof.filter((pl.col("pg") == pos) & (pl.col("toi") >= TOI_FLOOR)), stats, INDIV, "")
        base = base.drop_nulls([f"z_{a}" for a in INDIV])
        X = base.select([f"z_{a}" for a in INDIV]).to_numpy()
        pca = PCA(n_components=N_COMP, random_state=config.SEED).fit(X)
        spaces[pos] = {"explained": [round(float(v), 3) for v in pca.explained_variance_ratio_],
                       "loadings": {f"PC{i+1}": dict(zip(INDIV, [round(float(x), 3) for x in pca.components_[i]]))
                                    for i in range(N_COMP)}}
    return spaces


def _verdict(stab) -> dict:
    """Which NAMED axes clear both bars (split-half>=0.50 & same-team YoY>=0.40, each beat placebo)."""
    rows = []
    for pos in ("F", "D"):
        for a in ALL_AXES:
            s = stab[pos][a]
            clears = (s["split_half_r"] >= SB_SPLIT and s["split_p"] < 0.05
                      and s["yoy_same_r"] >= SB_YOY and s["yoy_same_p"] < 0.05)
            rows.append({"pos": pos, "axis": a, "new": a in NEW_AXES, "unit": a in UNIT,
                         "split_r": round(s["split_half_r"], 3), "yoy_same_r": round(s["yoy_same_r"], 3),
                         "retained": None if s["retained_frac"] is None else round(s["retained_frac"], 2),
                         "clears": clears})
    new_clear = [r for r in rows if r["new"] and r["clears"]]
    return {"rows": rows, "n_axes": len(rows), "n_clear": sum(r["clears"] for r in rows),
            "new_axes_cleared": [f"{r['pos']}:{r['axis']}" for r in new_clear],
            "n_new_cleared": len(new_clear)}


def run() -> dict:
    prof = _load()
    stab = raw_axis_stability(prof)
    res = {"seed": config.SEED, "axes": ALL_AXES, "new_axes": NEW_AXES,
           "role_space": role_space(prof), "raw_axis_stability": stab, "verdict": _verdict(stab)}
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "link1_rich_analysis.json", "w") as f:
        json.dump(res, f, indent=2)
    return res


if __name__ == "__main__":
    r = run()
    print("RICH role-space explained var:",
          {p: r["role_space"][p]["explained"][:3] for p in ("F", "D")})
    print("\naxis stability (split_half_r / yoy_same_r / retained; * = recovered axis):")
    for row in r["verdict"]["rows"]:
        star = "*" if row["new"] else " "
        u = "U" if row["unit"] else " "
        flag = "CLEARS" if row["clears"] else ""
        print(f" {star}{u} {row['pos']} {row['axis']:11s} split={row['split_r']:+.2f} yoy={row['yoy_same_r']:+.2f} ret={row['retained']} {flag}")
    v = r["verdict"]
    print(f"\nCleared {v['n_clear']}/{v['n_axes']} axes; recovered axes cleared: {v['n_new_cleared']} -> {v['new_axes_cleared']}")
