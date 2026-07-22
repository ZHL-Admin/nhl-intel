"""Phase 1 — the coverage-signature scheme-norm, with goals-only bias mitigation.

1.1 Per team-season, the typical five-defender SHAPE as a function of PUCK situation, represented as
    distributions (mean + spread) of interpretable geometry, not single points.
1.2 Goals-only bias mitigation (Law 1): (a) league baseline per situation -> each team read as a
    DEVIATION from league structure; (b) split-half + offensive-goals cross-view agreement + the
    residual irreducible bias, stated honestly.
1.3 Per-situation sample counts + resolvable granularity: how many goals-against populate each bucket;
    coarse vs fine; min-sample gate (thin buckets get NO norm, not a guess).

Situation grid = the PUCK's location. "side" (strong/weak) is symmetric left/right and not a distinct
scheme situation, so it is operationalized as the puck's LATERAL BAND (middle/slot vs wide/boards) after
folding out left-right symmetry -- documented, flagged for owner review. Universe: 5v5 (n_def=5), real
NHL team-seasons (>=20 GA; exhibition rosters excluded).
"""
from __future__ import annotations

import glob

import numpy as np
import polars as pl

from . import config as C

SIGNATURES = C.PARQUET / "coverage_signatures.parquet"
COUNTS = C.PARQUET / "situation_counts.parquet"

NETFRONT_FT = 15.0
SLOT_HALF_Y = 7.0          # |puck_y| < this = middle/slot ; else wide/boards
MIN_FRAMES_IN_SITU = 5     # a goal "populates" a situation with >= this many frames (0.5 s)
MIN_CELL_GOALS = 15        # min goals-against to characterize a (team-season, situation) cell
EXHIBITION_TEAMS = [60, 62, 66, 67, 68, 7801, 7802, 7803, 7804, 7805, 7806]
FEATURES = ["depth", "spread", "netfront", "marking", "highest", "strong_frac"]


def _frames() -> pl.DataFrame:
    p = pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(str(C.PARQUET / "def_prim_*.parquet")))])
    p = p.filter((pl.col("n_def") == 5) & ~pl.col("defending_team_id").is_in(EXHIBITION_TEAMS))
    # per-frame five-defender shape + recovered puck position
    fr = p.group_by("defending_team_id", "season", "game_id", "event_id", "frame_index").agg(
        depth=pl.col("dist_net").mean(),
        spread=pl.col("team_spread").first(),
        netfront=(pl.col("dist_net") < NETFRONT_FT).sum(),
        marking=pl.col("dist_nearest_atk").mean(),
        highest=pl.col("dist_net").max(),
        strong_frac=(pl.col("puck_side") == "strong").mean(),
        puck_x=(pl.col("x_norm") - pl.col("dx_puck")).first(),
        puck_y=(pl.col("y_norm") - pl.col("dy_puck")).first())
    # PUCK situation grid (folded lateral)
    fr = fr.with_columns(
        pz=pl.when(pl.col("puck_x") >= C.BLUE_LINE).then(pl.lit("dzone"))
        .when(pl.col("puck_x") <= -C.BLUE_LINE).then(pl.lit("ozone")).otherwise(pl.lit("neutral")),
        pdepth=pl.when(pl.col("puck_x") >= C.LOWHIGH_X).then(pl.lit("low"))
        .when(pl.col("puck_x") >= C.BLUE_LINE).then(pl.lit("high")).otherwise(pl.lit("na")),
        plat=pl.when(pl.col("puck_y").abs() < SLOT_HALF_Y).then(pl.lit("mid")).otherwise(pl.lit("wide")))
    fr = fr.with_columns(
        situ_coarse=pl.when(pl.col("pz") == "dzone").then(pl.lit("dzone_") + pl.col("pdepth")).otherwise(pl.col("pz")),
        situ_fine=pl.when(pl.col("pz") == "dzone").then(pl.lit("dzone_") + pl.col("pdepth") + pl.lit("_") + pl.col("plat")).otherwise(pl.col("pz")))
    return fr


def _signature(fr: pl.DataFrame, situ: str, keys: list[str]) -> pl.DataFrame:
    # per (team-season, situation): feature means + spreads + sample counts
    agg = fr.group_by(keys + [situ]).agg(
        n_frames=pl.len(), n_goals=pl.struct("game_id", "event_id").n_unique(),
        **{f: pl.col(f).mean() for f in FEATURES},
        **{f + "_sd": pl.col(f).std() for f in ["depth", "spread", "netfront", "marking"]})
    return agg.rename({situ: "situation"})


def build() -> dict:
    fr = _frames()
    ts_keys = ["defending_team_id", "season"]
    # 1.1 coverage signatures (coarse + fine), 1.3 counts
    sig_coarse = _signature(fr, "situ_coarse", ts_keys).with_columns(grid=pl.lit("coarse"))
    sig_fine = _signature(fr, "situ_fine", ts_keys).with_columns(grid=pl.lit("fine"))
    sig = pl.concat([sig_coarse, sig_fine]).with_columns(cell_ok=pl.col("n_goals") >= MIN_CELL_GOALS)

    # 1.2a league baseline per (grid, situation) + deviation
    league = pl.concat([
        _signature(fr, "situ_coarse", []).with_columns(grid=pl.lit("coarse")),
        _signature(fr, "situ_fine", []).with_columns(grid=pl.lit("fine"))]).select(
        ["grid", "situation"] + [pl.col(f).alias("lg_" + f) for f in FEATURES])
    sig = sig.join(league, on=["grid", "situation"], how="left")
    for f in FEATURES:
        sig = sig.with_columns((pl.col(f) - pl.col("lg_" + f)).alias("dev_" + f))
    # across-team-season standardization (z-scored deviation) for Phase 2 clustering readiness
    for f in FEATURES:
        sig = sig.with_columns(
            (pl.col("dev_" + f) / pl.col("dev_" + f).std().over("grid", "situation")).alias("z_" + f))

    C.PARQUET.mkdir(parents=True, exist_ok=True)
    sig.write_parquet(SIGNATURES)

    # 1.3 resolvable granularity: per team-season, cells meeting the gate
    def gran(grid):
        s = sig.filter((pl.col("grid") == grid) & pl.col("cell_ok"))
        per = s.group_by(ts_keys).agg(cells=pl.len())
        n_situ = sig.filter(pl.col("grid") == grid)["situation"].n_unique()
        return {"grid": grid, "n_situations": n_situ, "team_seasons_full": int((per["cells"] == n_situ).sum()),
                "median_cells_covered": float(per["cells"].median()), "n_team_seasons": per.height}

    # 1.2b split-half agreement of the coarse signature vector, per team-season
    half = fr.with_columns(
        h=pl.struct("game_id", "event_id").hash(seed=C.SEED_INT) % 2)
    sh = []
    for hv in (0, 1):
        s = _signature(half.filter(pl.col("h") == hv), "situ_coarse", ts_keys)
        sh.append(s.select(ts_keys + ["situation"] + FEATURES).with_columns(half=pl.lit(hv)))
    sh = pl.concat(sh)
    agree = _split_half_agreement(sh, ts_keys)
    # per-feature ABSOLUTE reproducibility (geometry) — high = the situation-driven shape is stable,
    # separate from the weak TEAM-DEVIATION signal measured by `agree`.
    perfeat = {}
    for f in FEATURES:
        a = sh.filter(pl.col("half") == 0).select(*ts_keys, "situation", pl.col(f).alias("v0"))
        b = sh.filter(pl.col("half") == 1).select(*ts_keys, "situation", pl.col(f).alias("v1"))
        m = a.join(b, on=ts_keys + ["situation"], how="inner").drop_nulls()
        va, vb = m["v0"].to_numpy(), m["v1"].to_numpy()
        perfeat[f] = float(np.corrcoef(va, vb)[0, 1]) if len(va) >= 3 else float("nan")

    counts = sig.select(ts_keys + ["grid", "situation", "n_goals", "n_frames", "cell_ok"])
    counts.write_parquet(COUNTS)
    # per-cell goal-count distribution across team-seasons (honest resolvability)
    percell = (counts.group_by("grid", "situation").agg(
        min_goals=pl.col("n_goals").min(), med_goals=pl.col("n_goals").median(),
        below_gate=(pl.col("n_goals") < MIN_CELL_GOALS).sum()).sort("grid", "situation"))
    return {"n_team_seasons": sig.select(ts_keys).unique().height,
            "granularity": [gran("coarse"), gran("fine")],
            "per_cell_counts": percell.to_dicts(),
            "split_half_median_r": agree, "per_feature_abs": perfeat,
            "coarse_situ": sig.filter(pl.col("grid") == "coarse")["situation"].unique().sort().to_list(),
            "fine_situ": sig.filter(pl.col("grid") == "fine")["situation"].unique().sort().to_list()}


def _split_half_agreement(sh: pl.DataFrame, ts_keys) -> float:
    """Per team-season, correlate its coarse signature vector across the two goal-halves; return median r."""
    piv = (sh.unpivot(index=ts_keys + ["situation", "half"], on=FEATURES, variable_name="feat", value_name="val")
           .with_columns(k=pl.col("situation") + "|" + pl.col("feat")))
    # Z-SCORE each feature-situation column across teams within each half (removes the cross-feature scale
    # structure that would trivially inflate r AND equal-weights every feature); correlate the resulting
    # standardized deviation vectors across halves.
    piv = piv.with_columns(
        dev=(pl.col("val") - pl.col("val").mean().over("half", "k")) / pl.col("val").std().over("half", "k"))
    rs = []
    h0 = piv.filter(pl.col("half") == 0).select(*ts_keys, "k", pl.col("dev").alias("v0"))
    h1 = piv.filter(pl.col("half") == 1).select(*ts_keys, "k", pl.col("dev").alias("v1"))
    m = h0.join(h1, on=ts_keys + ["k"], how="inner").drop_nulls()
    for (t, s), g in m.partition_by("defending_team_id", "season", as_dict=True, include_key=True).items():
        a, b = g["v0"].to_numpy(), g["v1"].to_numpy()
        if len(a) >= 5 and np.std(a) > 0 and np.std(b) > 0:
            rs.append(float(np.corrcoef(a, b)[0, 1]))
    return float(np.median(rs)) if rs else float("nan")


if __name__ == "__main__":
    import time
    t = time.time()
    r = build()
    print(f"signatures for {r['n_team_seasons']} team-seasons in {time.time()-t:.0f}s")
    print("coarse situations:", r["coarse_situ"])
    print("fine situations:", r["fine_situ"])
    for g in r["granularity"]:
        print(f"  {g['grid']}: {g['n_situations']} situations | median cells covered {g['median_cells_covered']:.0f} "
              f"| {g['team_seasons_full']}/{g['n_team_seasons']} team-seasons cover ALL cells (>= {MIN_CELL_GOALS} GA)")
    print(f"split-half signature agreement (median r): {r['split_half_median_r']:.2f}")
