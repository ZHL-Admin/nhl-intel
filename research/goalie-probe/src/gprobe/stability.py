"""G1.4 — THE STABILITY GATE (pre-stated).

For each bucket, among goalies with >= STABILITY_MIN_SHOTS shots faced in that bucket, test whether the
league-centered GSAx-per-100 residual is a persistent goalie trait:
  split-half : split the goalie's games odd/even; Pearson r across goalies of (dev_odd, dev_even).
  YoY        : same goalie, season t vs t+1; Pearson r across goalie-season pairs.
Both vs a placebo that shuffles goalie identity (N_PERM perms). PASS a bucket iff split-half r >= 0.30
AND YoY beats placebo p < 0.05. Overall (all-shot) GSAx is the benchmark: a bucket is a real shot-type
specialty only if it is at least as reliable as the goalie's own overall stopping.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config, spine as S

DIMS = {"shot_bucket": ["wrist", "snap", "slap", "backhand", "deflection"],
        "danger": ["low", "mid", "high"], "region": ["inner_slot", "outer_slot", "point"],
        "rebound": ["rebound", "non_rebound"], "overall": ["all"]}


def _prep() -> tuple[pl.DataFrame, dict]:
    s = pl.read_parquet(S.SPINE).filter(pl.col("goalie_id").is_not_null() & pl.col("xg").is_not_null())
    s = s.with_columns(rebound=pl.when(pl.col("rebound")).then(pl.lit("rebound")).otherwise(pl.lit("non_rebound")),
                       overall=pl.lit("all"))
    # league per-100 baseline per (dimension,bucket)
    league = {}
    for dim in DIMS:
        agg = s.group_by(dim).agg(xg=pl.col("xg").sum(), goal=pl.col("is_goal").sum(), n=pl.len())
        for row in agg.iter_rows(named=True):
            league[(dim, row[dim])] = 100 * (row["xg"] - row["goal"]) / row["n"]
    # game parity per goalie (odd/even by game-date order)
    games = (s.select("goalie_id", "game_id", "game_date").unique()
             .sort(["goalie_id", "game_date", "game_id"])
             .with_columns(half=pl.int_range(pl.len()).over("goalie_id") % 2))
    s = s.join(games.select("goalie_id", "game_id", "half"), on=["goalie_id", "game_id"], how="left")
    return s, league


def _dev(sub: pl.DataFrame, lg: float) -> float:
    return 100 * (sub["xg"].sum() - sub["is_goal"].sum()) / sub.height - lg


def _pearson(a, b):
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _placebo_p(a, b, r_obs, rng):
    if len(a) < 3 or not np.isfinite(r_obs):
        return float("nan")
    perm = np.array([_pearson(a, rng.permutation(b)) for _ in range(config.N_PERM)])
    return float(np.mean(perm >= r_obs))


def run() -> dict:
    s, league = _prep()
    rng = np.random.default_rng(config.SEED_INT)
    order = {sea: i for i, sea in enumerate(config.TRACKING_SEASONS)}
    rows = []
    for dim, buckets in DIMS.items():
        for bv in buckets:
            lg = league.get((dim, bv))
            sub = s.filter(pl.col(dim) == bv)
            # goalies with >= STABILITY_MIN_SHOTS in the bucket (over all seasons)
            tot = sub.group_by("goalie_id").len().filter(pl.col("len") >= config.STABILITY_MIN_SHOTS)
            keep = set(tot["goalie_id"].to_list())
            gk = sub.filter(pl.col("goalie_id").is_in(list(keep)))
            # split-half
            pairs = []
            for gid, g in gk.partition_by("goalie_id", as_dict=True, include_key=True).items():
                gi = gid[0] if isinstance(gid, tuple) else gid
                o = g.filter(pl.col("half") == 1); e = g.filter(pl.col("half") == 0)
                if o.height >= 20 and e.height >= 20:
                    pairs.append((gi, _dev(o, lg), _dev(e, lg)))
            pairs.sort()                                              # deterministic order
            a = np.array([p[1] for p in pairs]); b = np.array([p[2] for p in pairs])
            sh_r = _pearson(a, b); sh_p = _placebo_p(a, b, sh_r, rng)
            # YoY: consecutive-season pairs
            per = []
            for (gid, sea), g in gk.partition_by("goalie_id", "season", as_dict=True, include_key=True).items():
                if g.height >= 50:
                    per.append((g["goalie_id"][0], order[g["season"][0]], _dev(g, lg)))
            pa, pb = [], []
            bygoalie = {}
            for gi, o, d in per:
                bygoalie.setdefault(gi, {})[o] = d
            for gi in sorted(bygoalie):                              # deterministic order
                seasons = bygoalie[gi]
                for o in sorted(seasons):
                    if o + 1 in seasons:
                        pa.append(seasons[o]); pb.append(seasons[o + 1])
            ya, yb = np.array(pa), np.array(pb)
            yoy_r = _pearson(ya, yb); yoy_p = _placebo_p(ya, yb, yoy_r, rng)
            rows.append({"dimension": dim, "bucket": bv, "n_goalies_splithalf": len(a),
                         "split_half_r": sh_r, "split_half_p": sh_p, "n_pairs_yoy": len(pa),
                         "yoy_r": yoy_r, "yoy_p": yoy_p,
                         "PASS": bool(np.isfinite(sh_r) and sh_r >= config.SPLIT_HALF_BAR
                                      and np.isfinite(yoy_p) and yoy_p < 0.05)})
    res = pl.DataFrame(rows)
    overall = res.filter((pl.col("dimension") == "overall"))
    return {"table": res, "overall": overall.to_dicts()[0] if overall.height else None,
            "n_pass": int(res.filter(pl.col("dimension") != "overall")["PASS"].sum())}


if __name__ == "__main__":
    r = run()
    o = r["overall"]
    print(f"OVERALL benchmark: split-half r={o['split_half_r']:.2f} (p={o['split_half_p']:.3f}) | "
          f"YoY r={o['yoy_r']:.2f} (p={o['yoy_p']:.3f})")
    print(f"\nbucket stability ({r['n_pass']} pass):")
    print(r["table"].filter(pl.col("dimension") != "overall").sort("split_half_r", descending=True))
