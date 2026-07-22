"""Link 1 — the four context-adjusted culprit rates (+ combined), for D and F.

RAW = mean per-goal culprit share over on-ice GA (the F27 metric). Adjustments, each isolating one
confound:
  ADJ-1 within-team : his rate vs his on-ice teammates' shares in the same goals. (NOTE: on this metric
      the per-goal unit is already distributed entirely within his own on-ice team, so this is a
      monotone rescaling of RAW -- team quality was never a rate-inflating confound. Reported honestly.)
  ADJ-2 usage       : RAW residualized on deployment (OZ-start share, PK share, trailing share, 5v5 TOI).
  ADJ-3 opponent    : per-goal share downweighted by the scorer's offensive RAPM (being the culprit vs an
      elite attacker counts less); weighted mean.
  ADJ-4 xGA-relative: RAW residualized on his on-ice xGA/60 (does breakdown cluster on him beyond his
      unit's results).
  ADJ-COMBINED      : ADJ-3 (opponent-weighted) then residualized on usage.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, context as CX, link2 as L, signals as S

RATES = C.PARQUET / "adj_rates.parquet"
POS = {"D": ["D"], "F": ["C", "L", "R"]}
USAGE_COVS = ["oz_start_share", "pk_share", "trail_share", "toi_5v5_min"]


def _residual(df: pl.DataFrame, y: str, covs: list[str]) -> np.ndarray:
    d = df.select([y] + covs).drop_nulls()
    X = np.column_stack([np.ones(d.height)] + [d[c].to_numpy() for c in covs])
    yv = d[y].to_numpy()
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    pred = X @ beta
    return yv - pred, beta


def _per_goal(positions) -> pl.DataFrame:
    d = pl.read_parquet(S.SHARES).select("game_id", "event_id", "season", "player_id", "breakdown_share")
    gd = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "game_date")
    pos = L._position()
    w = CX.scorer_quality().with_columns(w_opp=1.0 - pl.col("scorer_off"))
    return (d.join(gd, on=["game_id", "event_id"], how="left").join(pos, on="player_id", how="left")
            .join(w, on=["game_id", "event_id"], how="left")
            .filter(pl.col("position").is_in(positions))
            .with_columns(half=pl.int_range(pl.len()).over("player_id")))   # placeholder; real half set later


def build() -> dict:
    usage = pl.read_parquet(CX.USAGE)
    p5 = pl.read_parquet(CX.ATLAS / "player_5v5.parquet").select("player_id", season="season_label",
                                                                 xga_per60="xga_per60", toi_min="toi_min")
    out = []
    betas = {}
    for posname, plist in POS.items():
        g = _per_goal(plist)
        base = g.group_by("player_id", "season").agg(
            ga=pl.len(), raw=pl.col("breakdown_share").mean(),
            adj3=(pl.col("breakdown_share") * pl.col("w_opp")).sum() / pl.col("w_opp").sum())
        base = (base.join(usage.select("player_id", "season", *USAGE_COVS), on=["player_id", "season"], how="left")
                .join(p5, on=["player_id", "season"], how="left")
                .filter(pl.col("ga") >= L.MIN_RATE_GA))
        base = base.with_columns(position=pl.lit(posname), adj1=pl.col("raw"))   # ADJ-1 == RAW (see note)
        # ADJ-2 usage residual, ADJ-4 xGA residual, ADJ-COMBINED (adj3 resid on usage)
        elig = base.drop_nulls(USAGE_COVS + ["xga_per60"])
        r2, b2 = _residual(elig, "raw", USAGE_COVS)
        r4, b4 = _residual(elig, "raw", ["xga_per60"])
        rc, bc = _residual(elig, "adj3", USAGE_COVS)
        elig = elig.with_columns(adj2=pl.Series(r2), adj4=pl.Series(r4), adjc=pl.Series(rc))
        betas[posname] = {"usage": dict(zip(["intercept"] + USAGE_COVS, b2.tolist())),
                          "xga": dict(zip(["intercept", "xga_per60"], b4.tolist()))}
        # tier
        elig = elig.with_columns(tier=pl.when(pl.col("toi_min") >= pl.col("toi_min").quantile(0.67).over("season")).then(pl.lit("hi"))
                                 .when(pl.col("toi_min") >= pl.col("toi_min").quantile(0.33).over("season")).then(pl.lit("mid")).otherwise(pl.lit("lo")))
        out.append(elig)
    rates = pl.concat(out)
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    rates.write_parquet(RATES)
    # spread of each version vs raw's band
    spreads = {}
    for v in ["raw", "adj1", "adj2", "adj3", "adj4", "adjc"]:
        s = rates.filter(pl.col("season") == "2025-26")
        spreads[v] = float(s[v].max() - s[v].min())
    # correlations among versions (pooled eligible)
    return {"n": rates.height, "betas": betas, "spreads": spreads,
            "by_pos": rates.group_by("position").agg(n=pl.len(), n2526=(pl.col("season") == "2025-26").sum()).to_dicts()}


if __name__ == "__main__":
    r = build()
    print(f"adjusted rates: {r['n']:,} player-seasons | by position {r['by_pos']}")
    print("2025-26 spread by version (raw band ~0.034 D):", {k: round(v, 3) for k, v in r["spreads"].items()})
    print("ADJ-2 usage betas (D):", {k: round(v, 4) for k, v in r["betas"]["D"]["usage"].items()})
