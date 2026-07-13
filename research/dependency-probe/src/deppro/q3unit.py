"""Link Q3 — the shoot-vs-defer decision cut by FORWARD UNIT, not just single partner.

The Round-1 survivor (shot-share) moves by single partner; Q3 asks whether a DEFENSEMAN's shot-share
ALSO organizes by the forward TRIO on ice: does a D shoot with one forward line but defer/move it with
another? Grain: (focal D, forward-trio, season). D's unit shot-share = D's attempts / (D's + the
trio's attempts) over their shared 5v5 ice. Same reliability-of-partner-deviation test (odd/even
shared games, TOI-weighted, within-player shuffle placebo).
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import config
from . import behavior as B
from . import qaxes as Q  # noqa: F401  (ensures enriched paths wired the same way)
from .linkA import _wcorr
import chem.corpus as cc

Q3DIR = config.PARQUET / "q3unit"
FLOOR = 3000        # 50 shared min at the D-trio grain (sparser than pair grain; reported)
MIN_TRIOS = 3
N_PERM = 500


def build_q3(season: str, write: bool = True) -> pl.DataFrame:
    st = B._stints(season)
    pf = cc._pos_frame()
    # per (rid, pid) shot attempts (located shooter events)
    ev = B._locate_in_stint(B._actor_events(season), st)
    att = ev.filter(pl.col("is_shot")).group_by("rid", pl.col("actor").alias("pid")).agg(
        att=pl.len())
    onice = B._onice(st).join(pf.rename({"player_id": "pid"}), on="pid", how="left").with_columns(
        pg=pl.col("pg").fill_null("F")).join(att, on=["rid", "pid"], how="left").with_columns(
        att=pl.col("att").fill_null(0))
    # per (rid, side): the sorted forward trio + trio attempts; keep only exactly-3-F sides
    fwd = (onice.filter(pl.col("pg") == "F").group_by("rid", "side")
           .agg(fwds=pl.col("pid").sort(), nf=pl.len(), trio_att=pl.col("att").sum())
           .filter(pl.col("nf") == 3)
           .with_columns(trio=pl.col("fwds").list.eval(pl.element().cast(pl.Utf8)).list.join("_")))
    # focal D on the same side
    ds = onice.filter(pl.col("pg") == "D").select("rid", "side", "game_id", D="pid", d_att="att",
                                                  dur="dur")
    dt = ds.join(fwd.select("rid", "side", "trio", "trio_att"), on=["rid", "side"], how="inner")
    dt = dt.group_by("D", "trio", "game_id").agg(
        d_att=pl.col("d_att").sum(), trio_att=pl.col("trio_att").sum(), dur=pl.col("dur").sum())
    dt = dt.with_columns(half=(pl.col("game_id").rank("dense").over("D", "trio") % 2))

    def roll(df, sfx):
        a = df.group_by("D", "trio").agg(
            d_att=pl.col("d_att").sum(), trio_att=pl.col("trio_att").sum(), dur=pl.col("dur").sum())
        return a.with_columns(**{f"share{sfx}": pl.when(pl.col("d_att") + pl.col("trio_att") > 0)
                                 .then(pl.col("d_att") / (pl.col("d_att") + pl.col("trio_att"))).otherwise(None)}
                              ).select("D", "trio", pl.col("dur").alias(f"dur{sfx}"), f"share{sfx}")
    agg = (roll(dt, "").join(roll(dt.filter(pl.col("half") == 1), "_odd"), on=["D", "trio"], how="left")
           .join(roll(dt.filter(pl.col("half") == 0), "_even"), on=["D", "trio"], how="left")
           .rename({"dur": "shared_toi"}).with_columns(season_label=pl.lit(season)))
    if write:
        Q3DIR.mkdir(parents=True, exist_ok=True)
        agg.write_parquet(Q3DIR / f"{season.replace('-', '_')}.parquet")
    return agg


def run(floor: int = FLOOR) -> dict:
    d = pl.concat([pl.read_parquet(p) for p in sorted(Q3DIR.glob("*.parquet"))],
                  how="vertical_relaxed").filter(pl.col("shared_toi") >= floor)
    keep = d.group_by("D", "season_label").len().filter(pl.col("len") >= MIN_TRIOS)
    d = d.join(keep.select("D", "season_label"), on=["D", "season_label"], how="inner")
    s = d.drop_nulls(["share_odd", "share_even"]).with_columns(
        do=pl.col("share_odd") - pl.col("share_odd").mean().over("D", "season_label"),
        de=pl.col("share_even") - pl.col("share_even").mean().over("D", "season_label"))
    x, y = s["do"].to_numpy(), s["de"].to_numpy(); w = s["shared_toi"].to_numpy().astype(float)
    r = _wcorr(x, y, w)
    cell = s.select(pl.concat_str([pl.col("D").cast(pl.Utf8), pl.lit("|"), pl.col("season_label")]))
    _, cid = np.unique(cell.to_series().to_numpy(), return_inverse=True)
    rng = np.random.default_rng(config.SEED); n = len(y); slot = np.lexsort((np.arange(n), cid))
    perms = np.empty(N_PERM)
    for k in range(N_PERM):
        src = np.lexsort((rng.random(n), cid)); p = np.empty(n, dtype=np.int64); p[slot] = src
        perms[k] = _wcorr(x, y[p], w)
    across_sd = float(d.group_by("D", "season_label").agg(sd=pl.col("share").std()).drop_nulls()["sd"].median())
    res = {"seed": config.SEED_TAG, "floor_min": floor // 60, "n_D_trio": s.height,
           "n_focal_D": s.select("D", "season_label").unique().height,
           "reliability": r, "placebo_mean": float(np.mean(perms)),
           "p": float((np.sum(perms >= r) + 1) / (N_PERM + 1)),
           "across_trio_sd_median": across_sd, "passes": (r >= 0.30 and float((np.sum(perms >= r) + 1) / (N_PERM + 1)) < 0.05)}
    with open(config.REPORTS / "linkQ3_analysis.json", "w") as f:
        json.dump(res, f, indent=2)
    return res


if __name__ == "__main__":
    import sys
    if "--build" in sys.argv:
        for sea in config.SEASONS_PRIMARY:
            print(f"{sea}: D-trio rows={build_q3(sea).height:,}", flush=True)
    else:
        r = run()
        print(f"D-trio units: {r['n_D_trio']} focal D: {r['n_focal_D']} | reliability={r['reliability']:+.3f} "
              f"placebo={r['placebo_mean']:+.3f} p={r['p']:.3f} across-trio SD~{r['across_trio_sd_median']:.3f} "
              f"pass={r['passes']}")
