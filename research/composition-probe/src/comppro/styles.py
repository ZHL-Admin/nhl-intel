"""Step 1 — a fine STYLE vocabulary for forwards, from already-validated role-fit two-way axes.

Style fingerprint per forward-season (200+ 5v5 min) = the role-fit two-way axes across the five
functional families (shot location/danger, offensive volume, physicality, possession, discipline) +
finishing/playmaking + handedness. K-means into ~16 archetypes (a finer vocabulary than the 6-10 role
types used before). Nothing is invented — every axis is a validated role-fit feature. Stability is
checked two ways (reuse of the role-fit method): the axis-level split-half/YoY is already strong
(role-fit retained ~0.79), and here we report how often the discrete archetype ASSIGNMENT repeats
(odd/even within season, and YoY) — a style vocabulary a recipe is built on must be stable.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl
from sklearn.cluster import KMeans

from . import config

# style axes (validated role-fit two-way features), grouped by functional family
FAMILIES = {"location": ["mean_dist", "slot_share", "xg_per_shot"],
            "volume": ["cf60", "xg60"], "physical": ["hit60", "hittaken60"],
            "possession": ["tk60", "gv60"], "discipline": ["pentake60", "pendrawn60"],
            "finish_play": ["goals60", "assists60"]}
AXES = [a for v in FAMILIES.values() for a in v]
K = 16                      # target 12-20 style archetypes
MIN_TOI = 12000            # 200 5v5 minutes
ARCH_PARQUET = config.PARQUET / "archetypes.parquet"


def _load_forwards() -> pl.DataFrame:
    prof = pl.concat([pl.read_parquet(p) for p in sorted(config.RICH_PROFILE_DIR.glob("*.parquet"))],
                     how="vertical_relaxed").filter((pl.col("pg") == "F") & (pl.col("toi") >= MIN_TOI))
    bio = pl.read_parquet(config.ENRICH_DIR / "player_bio.parquet").select(
        pid="player_id", shoots_R=(pl.col("shoots") == "R").cast(pl.Float64))
    return prof.join(bio, on="pid", how="left").with_columns(shoots_R=pl.col("shoots_R").fill_null(0.5))


def _zmat(df: pl.DataFrame, axes, src="") -> np.ndarray:
    """z-score each axis within season (forwards), return matrix; drops handedness (already 0/1)."""
    d = df
    for a in axes:
        col = f"{a}{src}"
        d = d.with_columns(((pl.col(col) - pl.col(col).mean().over("season_label"))
                            / pl.col(col).std().over("season_label")).alias(f"z_{a}{src}"))
    return d


def fit_vocabulary():
    df = _load_forwards()
    d = _zmat(df, AXES, "").drop_nulls([f"z_{a}" for a in AXES])
    X = np.column_stack([d[f"z_{a}"].to_numpy() for a in AXES] + [d["shoots_R"].to_numpy()])
    km = KMeans(n_clusters=K, random_state=config.SEED, n_init=10).fit(X)
    d = d.with_columns(archetype=pl.Series(km.labels_))
    # name each archetype by its dominant z-axes (centroid)
    centers = km.cluster_centers_[:, :len(AXES)]
    names = {}
    for k in range(K):
        top = sorted(zip(AXES, centers[k]), key=lambda kv: -abs(kv[1]))[:3]
        names[k] = ", ".join(f"{a}{'+' if v > 0 else '-'}" for a, v in top)
    return d, km, names


def stability(d: pl.DataFrame, km) -> dict:
    df = _load_forwards()
    # assign odd/even style vectors to nearest centroid; agreement with full assignment
    def assign(src):
        z = _zmat(df, AXES, src).drop_nulls([f"z_{a}{src}" for a in AXES])
        X = np.column_stack([z[f"z_{a}{src}"].to_numpy() for a in AXES] + [z["shoots_R"].to_numpy()])
        return z.select("pid", "season_label").with_columns(a=pl.Series(km.predict(X)))
    odd, even = assign("_odd"), assign("_even")
    j = odd.join(even, on=["pid", "season_label"], how="inner", suffix="_e")
    split_agree = float((j["a"] == j["a_e"]).mean())
    # YoY: same archetype next season
    sidx = {s: i for i, s in enumerate(config.SEASONS)}
    full = d.select("pid", "season_label", "archetype").with_columns(
        si=pl.col("season_label").replace_strict(sidx, return_dtype=pl.Int32))
    nxt = full.select("pid", (pl.col("si") - 1).alias("si"), a_next="archetype")
    yoy = full.join(nxt, on=["pid", "si"], how="inner")
    yoy_agree = float((yoy["archetype"] == yoy["a_next"]).mean())
    # chance baselines (a random archetype would agree ~ sum p_k^2)
    p = d.group_by("archetype").len().with_columns(f=pl.col("len") / d.height)["f"].to_numpy()
    chance = float((p ** 2).sum())
    return {"n_forward_seasons": d.height, "k": K, "split_half_assignment_agreement": split_agree,
            "yoy_assignment_agreement": yoy_agree, "chance_agreement": chance,
            "split_half_vs_chance": split_agree / chance, "yoy_vs_chance": yoy_agree / chance}


def run() -> dict:
    d, km, names = fit_vocabulary()
    st = stability(d, km)
    sizes = d.group_by("archetype").len().sort("archetype").to_dicts()
    ARCH_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    d.select("pid", "season_label", "archetype", *[f"z_{a}" for a in AXES]).write_parquet(ARCH_PARQUET)
    res = {"seed": config.SEED_TAG, "k": K, "axes": AXES, "min_toi_min": MIN_TOI // 60,
           "archetype_names": names, "archetype_sizes": sizes, "stability": st}
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "styles_analysis.json", "w") as f:
        json.dump(res, f, indent=2)
    return res


if __name__ == "__main__":
    r = run()
    print(f"K={r['k']} forward-seasons={r['stability']['n_forward_seasons']}")
    print(f"split-half assignment agreement={r['stability']['split_half_assignment_agreement']:.3f} "
          f"(chance {r['stability']['chance_agreement']:.3f}, x{r['stability']['split_half_vs_chance']:.1f})")
    print(f"YoY assignment agreement={r['stability']['yoy_assignment_agreement']:.3f} "
          f"(x{r['stability']['yoy_vs_chance']:.1f} chance)")
    for k, nm in r["archetype_names"].items():
        n = next(s["len"] for s in r["archetype_sizes"] if s["archetype"] == int(k))
        print(f"  A{k:>2} (n={n:>4}): {nm}")
