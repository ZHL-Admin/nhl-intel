"""Stage 2.3 — signature reliability gate (pre-stated) + role-axis sanity matrix.

Players with >= 30 involved goals pooled (pbp universe): odd/even split-half of the signature vector vs
a shuffled-identity placebo (2000 perms). PASS bar: a majority of fields have split-half r >= 0.30 AND
beat placebo p < 0.05; on FAIL, signatures ship pooled-only with the Stage-1 caveat. Sanity exhibit (no
bar): correlation matrix of the signatures against the role-fit two-way role axes; flag face-invalid
signs.
"""
from __future__ import annotations

import glob

import numpy as np
import polars as pl

from . import config, stage2_signatures as SG

MIN_RELI = 30
N_PERM = 2000
BAR = 0.30
FIELDS = SG.FIELDS
FLAGCOL = {"finisher_share": "is_finisher", "feeder_share": "is_feeder", "carrier_share": "is_carrier",
           "rush_share": "is_rush", "royal_road_share": "is_royal", "entry_driver_share": "is_entry_driver",
           "net_front_share": "is_net_front"}
ROLE_AXES = ["xg60", "assists60", "goals60", "slot_share", "point_share", "tip_share", "cf60"]


def _pearson(a, b):
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _placebo_p(a, b, r, rng):
    if len(a) < 3 or not np.isfinite(r):
        return float("nan")
    perm = np.array([_pearson(a, rng.permutation(b)) for _ in range(N_PERM)])
    return float(np.mean(perm >= r))


def split_half() -> pl.DataFrame:
    x = SG.flags().filter(pl.col("involvement") == "pbp")
    # players with >=30 involved goals pooled
    keep = (x.group_by("player_id").len().filter(pl.col("len") >= MIN_RELI))["player_id"]
    x = x.filter(pl.col("player_id").is_in(keep.to_list()))
    # game-date parity per player
    games = (x.select("player_id", "game_id", "game_date").unique()
             .sort(["player_id", "game_date", "game_id"])
             .with_columns(half=pl.int_range(pl.len()).over("player_id") % 2))
    x = x.join(games.select("player_id", "game_id", "half"), on=["player_id", "game_id"], how="left")
    agg = x.group_by("player_id", "half").agg(
        n=pl.len(), **{f: pl.col(FLAGCOL[f]).mean() for f in FIELDS})
    return agg


def run() -> dict:
    agg = split_half()
    rng = np.random.default_rng(config.SEED if isinstance(config.SEED, int) else 20260714)
    odd = agg.filter(pl.col("half") == 1); even = agg.filter(pl.col("half") == 0)
    m = odd.join(even, on="player_id", how="inner", suffix="_e").sort("player_id")
    rows = []
    for f in FIELDS:
        a = m[f].to_numpy(); b = m[f + "_e"].to_numpy()
        r = _pearson(a, b); p = _placebo_p(a, b, r, rng)
        rows.append({"field": f, "n_players": len(a), "split_half_r": r, "placebo_p": p,
                     "passes": bool(np.isfinite(r) and r >= BAR and np.isfinite(p) and p < 0.05)})
    res = pl.DataFrame(rows)
    n_pass = int(res["passes"].sum())
    return {"per_field": res, "n_pass": n_pass, "n_fields": len(FIELDS),
            "GATE_PASS": n_pass > len(FIELDS) / 2, "n_players": m.height}


def role_axis_matrix() -> pl.DataFrame:
    """Sanity (no bar): corr of pooled pbp signatures vs role-fit two-way role axes, per season overlap."""
    sig = pl.read_parquet(SG.SIGNATURES).filter((pl.col("involvement") == "pbp") & (pl.col("season") != "pooled") & pl.col("gate_ok"))
    frames = []
    for fp in sorted(glob.glob(str(config.ROLEFIT_PROFILES / "20*_*.parquet"))):
        season = fp.split("/")[-1].replace(".parquet", "").replace("_", "-")
        r = pl.read_parquet(fp).select(["pid"] + [c for c in ROLE_AXES if c in pl.read_parquet_schema(fp)])
        frames.append(r.with_columns(season=pl.lit(season)))
    role = pl.concat(frames, how="diagonal")
    j = sig.join(role, left_on=["player_id", "season"], right_on=["pid", "season"], how="inner")
    out = []
    for f in FIELDS:
        for ax in ROLE_AXES:
            if ax in j.columns:
                d = j.select(f, ax).drop_nulls()
                out.append({"signature": f, "role_axis": ax, "r": _pearson(d[f].to_numpy(), d[ax].to_numpy()),
                            "n": d.height})
    return pl.DataFrame(out)


if __name__ == "__main__":
    r = run()
    print(f"reliability: {r['n_players']} players >=30 | {r['n_pass']}/{r['n_fields']} fields pass -> "
          f"GATE {'PASS' if r['GATE_PASS'] else 'FAIL'}")
    print(r["per_field"].sort("split_half_r", descending=True))
    print("\nrole-axis sanity (selected):")
    mtx = role_axis_matrix()
    print(mtx.filter(pl.col("signature").is_in(["finisher_share", "feeder_share", "net_front_share"])).sort("r", descending=True).head(8))
