"""Stage 1.3 — reliability gate (pre-stated) + descriptive year-over-year stability.

For goalies with >= 60 GA pooled, split their goals-against odd/even by game-date order and correlate the
per-goalie mechanism-share vectors across halves, per mechanism, against a placebo that shuffles goalie
identity (2000 perms). PASS bar: a majority of mechanisms have split-half r >= 0.30 AND beat placebo
p < 0.05. On PASS the per-season profiles are publishable (subject to the 1.2 gates); on FAIL only the
pooled three-season tables ship, labeled "profile is a three-season aggregate; single seasons are noise."
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config, fuse, mechanisms as M, profiles as P

GA_GATE = 60
N_PERM = 2000
R_BAR = 0.30
MECHS = P.BINARY + [f"LOC_{c}" for c in P.LOC_CATS]


def _with_dates() -> pl.DataFrame:
    m = pl.read_parquet(M.MECH_FLAGS).filter(pl.col("goalie_id").is_not_null())
    dates = pl.read_parquet(fuse.FUSED).select("game_id", "event_id", "game_date")
    return m.join(dates, on=["game_id", "event_id"], how="left")


def _share(sub: pl.DataFrame, mech: str) -> tuple[float | None, int]:
    """Per-goalie share of a mechanism within its universe on a subset (half); (share, usable_n)."""
    if mech.startswith("LOC_"):
        u = sub.filter(sub["tracked"]); loc = u["LOCATION"].drop_nulls(); n = loc.len()
        cat = mech[4:]
        return (float((loc == cat).sum()) / n if n else None), n
    u = sub.filter(P._universe_mask(sub, P.UNIVERSE[mech]))
    n = u.height; vals = u[mech].drop_nulls()
    return (float(vals.mean()) if vals.len() else None), n


def split_half(m: pl.DataFrame) -> pl.DataFrame:
    """One row per (goalie, mechanism): odd/even shares for goalies with >= 60 GA pooled."""
    keep = (m.group_by("goalie_id").len().filter(pl.col("len") >= GA_GATE))["goalie_id"].to_list()
    rows = []
    for gid in keep:
        sub = (m.filter(pl.col("goalie_id") == gid)
               .sort(["game_date", "abs_game_seconds", "game_id", "event_id"])
               .with_row_index("i").with_columns(half=pl.col("i") % 2))
        odd, even = sub.filter(pl.col("half") == 1), sub.filter(pl.col("half") == 0)
        for mech in MECHS:
            so, no = _share(odd, mech); se, ne = _share(even, mech)
            rows.append({"goalie_id": gid, "mechanism": mech, "share_odd": so, "share_even": se,
                         "n_odd": no, "n_even": ne})
    return pl.DataFrame(rows)


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def run() -> dict:
    m = _with_dates()
    sh = split_half(m)
    rng = np.random.default_rng(config.SEED)
    results = []
    for mech in MECHS:
        d = sh.filter((pl.col("mechanism") == mech) & pl.col("share_odd").is_not_null()
                      & pl.col("share_even").is_not_null())
        a = d["share_odd"].to_numpy(); b = d["share_even"].to_numpy()
        r = _pearson(a, b)
        # placebo: shuffle goalie identity (permute b against a)
        if len(a) >= 3 and np.isfinite(r):
            perm = np.array([_pearson(a, rng.permutation(b)) for _ in range(N_PERM)])
            p = float(np.mean(perm >= r))
        else:
            p = float("nan")
        results.append({"mechanism": mech, "n_goalies": len(a), "split_half_r": r, "placebo_p": p,
                        "passes": bool(np.isfinite(r) and r >= R_BAR and np.isfinite(p) and p < 0.05)})
    res = pl.DataFrame(results)
    n_pass = int(res["passes"].sum()); n_tot = res.height
    gate_pass = n_pass > n_tot / 2
    return {"per_mechanism": res, "n_pass": n_pass, "n_mech": n_tot, "GATE_PASS": gate_pass,
            "n_goalies_ge60": len(sh["goalie_id"].unique()), "yoy": yoy_stability(m)}


def yoy_stability(m: pl.DataFrame) -> list[dict]:
    """Descriptive: same-goalie correlation of per-season mechanism shares across consecutive seasons."""
    per = []
    for (gid, season), sub in m.partition_by("goalie_id", "season", as_dict=True, include_key=True).items():
        if sub.height < GA_GATE:
            continue
        rec = {"goalie_id": sub["goalie_id"][0], "season": sub["season"][0]}
        for mech in MECHS:
            rec[mech] = _share(sub, mech)[0]
        per.append(rec)
    if not per:
        return []
    pf = pl.DataFrame(per)
    order = {s: i for i, s in enumerate(config.SEASONS)}
    out = []
    for mech in MECHS:
        pairs_a, pairs_b = [], []
        for gid, g in pf.partition_by("goalie_id", as_dict=True, include_key=True).items():
            g = g.with_columns(o=pl.col("season").replace_strict(order, default=None)).sort("o")
            vals = g[mech].to_list();
            for x, y in zip(vals, vals[1:]):
                if x is not None and y is not None:
                    pairs_a.append(x); pairs_b.append(y)
        out.append({"mechanism": mech, "n_pairs": len(pairs_a),
                    "yoy_r": _pearson(np.array(pairs_a), np.array(pairs_b)) if len(pairs_a) >= 3 else None})
    return out


if __name__ == "__main__":
    r = run()
    print(f"reliability: {r['n_goalies_ge60']} goalies >=60 GA | {r['n_pass']}/{r['n_mech']} mechanisms pass "
          f"-> GATE {'PASS' if r['GATE_PASS'] else 'FAIL'}")
    print(r["per_mechanism"].sort("split_half_r", descending=True))
