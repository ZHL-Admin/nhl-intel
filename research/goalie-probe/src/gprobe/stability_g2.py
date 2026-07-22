"""G2.2 — stability gate for the behavior axes (pre-stated, same machinery as G1.4).

Per axis: split-half (odd/even games) and YoY (season t vs t+1) correlation of the goalie's axis rate,
vs a placebo shuffling goalie identity (N_PERM perms). PASS iff split-half r >= 0.30 AND YoY placebo
p < 0.05. Every axis rate is num/den (rate axes: flag/count; mean axes: sum/count). Rebound-control is
reported first (denominator-backed); the goals-only axes carry the caveat that they are measured on
goals-against, not over a save denominator.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import behavior as B, config

# axis -> (parquet, num_col, den_col, min_den, denominator_backed, source)
AXES = {
    "rebound_control": (B.REB, "num", "den", config.REBOUND_MIN_SAVES, True, "pbp spine / SAVES"),
    "depth": (B.TRK, "depth_num", "depth_den", config.GOALS_AXIS_MIN, False, "tracking / goals-only"),
    "lateral_recovery": (B.TRK, "lat_num", "lat_den", config.GOALS_AXIS_MIN, False, "tracking / goals-only"),
    "unset_rate": (B.TRK, "unset_num", "unset_den", config.GOALS_AXIS_MIN, False, "tracking / goals-only"),
    "ew_coverage": (B.TRK, "ew_num", "ew_den", config.EW_AXIS_MIN, False, "tracking / goals-only"),
}


def _pearson(a, b):
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _placebo_p(a, b, r_obs, rng):
    if len(a) < 3 or not np.isfinite(r_obs):
        return float("nan")
    perm = np.array([_pearson(a, rng.permutation(b)) for _ in range(config.N_PERM)])
    return float(np.mean(perm >= r_obs))


def _axis(path, num, den, min_den, rng) -> dict:
    df = pl.read_parquet(path)
    games = (df.select("goalie_id", "game_id", "game_date").unique()
             .sort(["goalie_id", "game_date", "game_id"])
             .with_columns(half=pl.int_range(pl.len()).over("goalie_id") % 2))
    d = df.join(games.select("goalie_id", "game_id", "half"), on=["goalie_id", "game_id"], how="left")
    keep = (d.group_by("goalie_id").agg(td=pl.col(den).sum()).filter(pl.col("td") >= min_den))["goalie_id"]
    d = d.filter(pl.col("goalie_id").is_in(keep.to_list()))
    # split-half
    h = (d.group_by("goalie_id", "half").agg(n=pl.col(num).sum(), de=pl.col(den).sum())
         .with_columns(rate=pl.col("n") / pl.col("de")))
    odd = h.filter(pl.col("half") == 1).select("goalie_id", rate_odd="rate")
    even = h.filter(pl.col("half") == 0).select("goalie_id", rate_even="rate")
    piv = odd.join(even, on="goalie_id", how="inner").drop_nulls().sort("goalie_id")   # deterministic order
    a, b = piv["rate_odd"].to_numpy(), piv["rate_even"].to_numpy()
    sh_r = _pearson(a, b); sh_p = _placebo_p(a, b, sh_r, rng)
    # YoY
    order = {s: i for i, s in enumerate(config.TRACKING_SEASONS)}
    ys = (d.group_by("goalie_id", "season").agg(n=pl.col(num).sum(), de=pl.col(den).sum())
          .with_columns(rate=pl.col("n") / pl.col("de"), o=pl.col("season").replace_strict(order, default=None)))
    bygoalie = {}
    for r in ys.iter_rows(named=True):
        bygoalie.setdefault(r["goalie_id"], {})[r["o"]] = r["rate"]
    pa, pb = [], []
    for gid in sorted(bygoalie):                          # deterministic order
        seasons = bygoalie[gid]
        for o in sorted(seasons):
            if o + 1 in seasons:
                pa.append(seasons[o]); pb.append(seasons[o + 1])
    ya, yb = np.array(pa), np.array(pb)
    yoy_r = _pearson(ya, yb); yoy_p = _placebo_p(ya, yb, yoy_r, rng)
    return {"n_goalies": len(a), "split_half_r": sh_r, "split_half_p": sh_p,
            "n_pairs": len(pa), "yoy_r": yoy_r, "yoy_p": yoy_p,
            "PASS": bool(np.isfinite(sh_r) and sh_r >= config.SPLIT_HALF_BAR and np.isfinite(yoy_p) and yoy_p < 0.05)}


def run() -> pl.DataFrame:
    rng = np.random.default_rng(config.SEED_INT)
    rows = []
    for axis, (path, num, den, mind, denom_backed, src) in AXES.items():
        r = _axis(path, num, den, mind, rng)
        rows.append({"axis": axis, "denominator_backed": denom_backed, "source": src, **r})
    # order: rebound first, then by split-half r
    res = pl.DataFrame(rows)
    return res.sort(["denominator_backed", "split_half_r"], descending=[True, True])


if __name__ == "__main__":
    r = run()
    print(r.select("axis", "source", "n_goalies", "split_half_r", "yoy_r", "yoy_p", "PASS"))
