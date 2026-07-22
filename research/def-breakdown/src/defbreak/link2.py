"""Link 2 — culprit-rate tally + the stability gate (pre-registered).

CULPRIT_RATE (per defenseman-season) = summed per-goal breakdown share / on-ice goals-against. Reported
continuous-share and hard-flag versions. Denominator = his goals-against in the qualifying tracked-5v5
universe (the consistent share universe); min 25 GA to report a rate, min 40 for the stability gate.
Analysis population = defensemen (rosters position_code='D'); the share itself is distributed among all
five defending skaters. FRAMING: comparative culprit rate over goals-against, never a single-goal verdict.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, signals as S

RATES = C.PARQUET / "culprit_rates.parquet"
MIN_RATE_GA = 25
MIN_STAB_GA = 40
N_PERM = 2000
BAR = 0.30
OFF_REF = 0.40           # the offensive-signature (Stage 2) split-half, as a reference point
SEASON_ORD = {s: i for i, s in enumerate(C.SEASONS)}


def _position() -> pl.DataFrame:
    ros = pl.read_parquet(C.ROSTERS, columns=["player_id", "position_code"])
    return (ros.group_by("player_id", "position_code").len()
            .sort("len", descending=True).group_by("player_id").first()
            .select("player_id", position="position_code"))


def _per_goal_def() -> pl.DataFrame:
    d = pl.read_parquet(S.SHARES)
    gd = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "game_date")
    pos = _position()
    return (d.join(gd, on=["game_id", "event_id"], how="left").join(pos, on="player_id", how="left")
            .filter(pl.col("position") == "D"))


def tally() -> pl.DataFrame:
    x = _per_goal_def()
    p5 = pl.read_parquet(C.NIR / "research/deployment-atlas/data/parquet/player_5v5.parquet") \
        .select("player_id", season="season_label", toi_min="toi_min", xga_per60="xga_per60", ga5v5="ga")

    per_season = x.group_by("player_id", "season").agg(
        ga=pl.len(), cont=pl.col("breakdown_share").mean(), hard=pl.col("hard_culprit").mean(),
        b_alone=pl.col("B_norm").mean(), a_alone=pl.col("A_norm").mean())
    pooled = x.group_by("player_id").agg(
        ga=pl.len(), cont=pl.col("breakdown_share").mean(), hard=pl.col("hard_culprit").mean(),
        b_alone=pl.col("B_norm").mean(), a_alone=pl.col("A_norm").mean()).with_columns(season=pl.lit("pooled"))
    rates = pl.concat([per_season, pooled], how="diagonal")
    rates = rates.join(p5, on=["player_id", "season"], how="left").with_columns(rate_ok=pl.col("ga") >= MIN_RATE_GA)
    # TOI tier baseline (top-pair / middle / depth) within season, on rate-eligible D
    elig = rates.filter(pl.col("rate_ok") & (pl.col("season") != "pooled") & pl.col("toi_min").is_not_null())
    tiers = (elig.with_columns(tier=pl.when(pl.col("toi_min") >= pl.col("toi_min").quantile(0.67).over("season")).then(pl.lit("top-pair"))
                               .when(pl.col("toi_min") >= pl.col("toi_min").quantile(0.33).over("season")).then(pl.lit("middle")).otherwise(pl.lit("depth")))
             .select("player_id", "season", "tier"))
    rates = rates.join(tiers, on=["player_id", "season"], how="left")
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    rates.write_parquet(RATES)
    return rates


# ---------------- stability ----------------
def _pearson(a, b):
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _placebo_p(a, b, r, rng):
    if len(a) < 3 or not np.isfinite(r):
        return float("nan")
    return float(np.mean(np.array([_pearson(a, rng.permutation(b)) for _ in range(N_PERM)]) >= r))


def _splithalf(x, metric, rng, subset=None):
    """Split each defender's GA odd/even by date; correlate the metric across halves for D with >=40 GA."""
    df = x.filter(subset) if subset is not None else x
    games = (df.select("player_id", "game_id", "game_date").unique().sort(["player_id", "game_date", "game_id"])
             .with_columns(half=pl.int_range(pl.len()).over("player_id") % 2))
    df = df.join(games.select("player_id", "game_id", "half"), on=["player_id", "game_id"], how="left")
    keep = (df.group_by("player_id").len().filter(pl.col("len") >= MIN_STAB_GA))["player_id"]
    df = df.filter(pl.col("player_id").is_in(keep.to_list()))
    h = df.group_by("player_id", "half").agg(v=pl.col(metric).mean())
    o = h.filter(pl.col("half") == 1).select("player_id", vo="v")
    e = h.filter(pl.col("half") == 0).select("player_id", ve="v")
    m = o.join(e, on="player_id", how="inner").drop_nulls().sort("player_id")
    a, b = m["vo"].to_numpy(), m["ve"].to_numpy()
    r = _pearson(a, b)
    return {"n": len(a), "r": r, "p": _placebo_p(a, b, r, rng)}


def _yoy(x, metric, rng):
    ys = x.group_by("player_id", "season").agg(v=pl.col(metric).mean(), n=pl.len()).filter(pl.col("n") >= MIN_STAB_GA)
    ys = ys.with_columns(o=pl.col("season").replace_strict(SEASON_ORD, default=None))
    by = {}
    for r in ys.iter_rows(named=True):
        by.setdefault(r["player_id"], {})[r["o"]] = r["v"]
    pa, pb = [], []
    for pid in sorted(by):
        for o in sorted(by[pid]):
            if o + 1 in by[pid]:
                pa.append(by[pid][o]); pb.append(by[pid][o + 1])
    a, b = np.array(pa), np.array(pb)
    r = _pearson(a, b)
    return {"n": len(a), "r": r, "p": _placebo_p(a, b, r, rng)}


def stability() -> dict:
    x = _per_goal_def()
    rng = np.random.default_rng(C.SEED_INT)
    out = {}
    for name, metric in [("combined_cont", "breakdown_share"), ("combined_hard", "hard_culprit"),
                         ("B_alone", "B_norm"), ("A_alone", "A_norm")]:
        out[name] = {"split_half": _splithalf(x, metric, rng), "yoy": _yoy(x, metric, rng)}
    out["B_eastwest"] = {"split_half": _splithalf(x, "B_norm", rng, subset=pl.col("cross_slot") == True)}  # noqa: E712
    return out


def exposure(rates: pl.DataFrame) -> dict:
    # per-season eligible rows carry TOI + on-ice xGA (pooled rows do not); correlate culprit rate with
    # exposure proxies (GA volume, 5v5 TOI) and the on-ice xGA face-validity check.
    r = rates.filter((pl.col("season") != "pooled") & pl.col("rate_ok"))
    out = {}
    for col in ["ga", "toi_min", "xga_per60"]:
        d = r.select("cont", col).drop_nulls()
        out[col] = _pearson(d["cont"].to_numpy(), d[col].to_numpy()) if d.height >= 3 else float("nan")
    out["n"] = r.filter(pl.col("xga_per60").is_not_null()).height
    return out


if __name__ == "__main__":
    rates = tally()
    pooled = rates.filter((pl.col("season") == "pooled") & pl.col("rate_ok"))
    print(f"defensemen with >=25 GA (pooled): {pooled.height} | league mean culprit rate {pooled['cont'].mean():.3f}")
    st = stability()
    print("\nSTABILITY (split-half r / placebo p | YoY r):")
    for k, v in st.items():
        sh = v["split_half"]; yo = v.get("yoy", {})
        print(f"  {k}: split-half r={sh['r']:.2f} p={sh['p']:.3f} (n={sh['n']})" +
              (f" | YoY r={yo['r']:.2f} p={yo['p']:.3f} (n={yo['n']})" if yo else ""))
    print("\nEXPOSURE (culprit-rate corr): " + ", ".join(f"{k}={v:+.2f}" for k, v in exposure(rates).items()))
