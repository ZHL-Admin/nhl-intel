"""Stage 1.2 — goalie mechanism profiles with empirical-Bayes shrinkage and publication gates.

Per goalie-season and pooled 2023-26, each mechanism's mix is a count + share. Shares are shrunk toward
the league via a Dirichlet-multinomial empirical-Bayes prior of strength k=20 goals-against (for a binary
present/absent mechanism this is the Beta-Binomial special case); 90% CIs come from 1000 posterior draws
(seed = config.SEED). Publication gates: no goalie row below 40 GA in the relevant sample; no
mechanism-level claim where that mechanism's raw count < 10.

Universes differ by mechanism (AMENDMENT): EAST_WEST/SCREENED/UNSET/LOCATION over TRACKED GA;
CLEAN_LOOK over flight-fired GA; RUSH/IN_ZONE/SECOND_CHANCE over all GA. Every usable-n is reported so
no profile silently thins.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config, mechanisms as M

PROFILES = config.PARQUET / "goalie_profiles.parquet"
K = 20                       # EB prior strength (goals-against), fixed
N_DRAWS = 1000
GA_ROW_GATE = 40             # no goalie row below this many GA in the relevant sample
MECH_CLAIM_GATE = 10         # no mechanism claim with raw count below this

BINARY = ["EAST_WEST", "SCREENED", "CLEAN_LOOK", "UNSET", "RUSH", "IN_ZONE", "SECOND_CHANCE"]
LOC_CATS = ["glove", "center", "blocker"]
# usable universe per binary mechanism
UNIVERSE = {"EAST_WEST": "tracked", "SCREENED": "tracked", "UNSET": "tracked",
            "CLEAN_LOOK": "flight", "RUSH": "all", "IN_ZONE": "all", "SECOND_CHANCE": "all"}


def _universe_mask(df: pl.DataFrame, kind: str) -> pl.Series:
    if kind == "tracked":
        return df["tracked"]
    if kind == "flight":
        return df["flight_detected"]
    return pl.Series([True] * df.height)


def league_rates(m: pl.DataFrame) -> dict:
    """Pooled league rate per binary mechanism + Dirichlet mean for LOCATION."""
    out = {}
    for mech in BINARY:
        u = m.filter(_universe_mask(m, UNIVERSE[mech]))
        vals = u[mech].drop_nulls()
        out[mech] = float(vals.mean()) if vals.len() else 0.0
    loc = m.filter(m["tracked"])["LOCATION"].drop_nulls()
    tot = loc.len()
    out["LOCATION"] = {c: (float((loc == c).sum()) / tot if tot else 1 / 3) for c in LOC_CATS}
    return out


def _beta_ci(rng, alpha, beta, n_draws=N_DRAWS):
    d = rng.beta(alpha, beta, n_draws)
    return float(np.quantile(d, 0.05)), float(np.quantile(d, 0.95))


def _dir_ci(rng, alphas, n_draws=N_DRAWS):
    d = rng.dirichlet(alphas, n_draws)   # (n_draws, k)
    return {LOC_CATS[i]: (float(np.quantile(d[:, i], 0.05)), float(np.quantile(d[:, i], 0.95)))
            for i in range(len(LOC_CATS))}


def build(from_cache: bool = True) -> pl.DataFrame:
    m = pl.read_parquet(M.MECH_FLAGS).filter(pl.col("goalie_id").is_not_null())
    lg = league_rates(m)
    rng = np.random.default_rng(config.SEED)

    def profile_rows(sub: pl.DataFrame, goalie: int, scope: str) -> list[dict]:
        ga_all = sub.height
        ga_tracked = int(sub["tracked"].sum())
        ga_flight = int(sub["flight_detected"].sum())
        rows = []
        for mech in BINARY:
            u = sub.filter(_universe_mask(sub, UNIVERSE[mech]))
            n = u.height
            c = int(u[mech].fill_null(False).sum())
            p_l = lg[mech]
            a, b = K * p_l + c, K * (1 - p_l) + (n - c)
            eb = a / (a + b)
            lo, hi = _beta_ci(rng, a, b)
            rows.append({"goalie_id": goalie, "scope": scope, "ga_all": ga_all, "ga_tracked": ga_tracked,
                         "ga_flight": ga_flight, "mechanism": mech, "category": None, "count": c,
                         "usable_n": n, "raw_share": (c / n if n else None), "eb_share": eb,
                         "ci_lo": lo, "ci_hi": hi, "claim_ok": c >= MECH_CLAIM_GATE})
        # LOCATION 3-way Dirichlet
        u = sub.filter(sub["tracked"])
        loc = u["LOCATION"].drop_nulls()
        n = loc.len()
        counts = {cat: int((loc == cat).sum()) for cat in LOC_CATS}
        alphas = np.array([K * lg["LOCATION"][cat] + counts[cat] for cat in LOC_CATS])
        cis = _dir_ci(rng, alphas)
        for cat in LOC_CATS:
            eb = alphas[LOC_CATS.index(cat)] / alphas.sum()
            rows.append({"goalie_id": goalie, "scope": scope, "ga_all": ga_all, "ga_tracked": ga_tracked,
                         "ga_flight": ga_flight, "mechanism": "LOCATION", "category": cat,
                         "count": counts[cat], "usable_n": n, "raw_share": (counts[cat] / n if n else None),
                         "eb_share": float(eb), "ci_lo": cis[cat][0], "ci_hi": cis[cat][1],
                         "claim_ok": counts[cat] >= MECH_CLAIM_GATE})
        return rows

    out = []
    for goalie, sub in m.partition_by("goalie_id", as_dict=True, include_key=True).items():
        gid = goalie[0] if isinstance(goalie, tuple) else goalie
        out += profile_rows(sub, gid, "pooled")
        for season, ssub in sub.partition_by("season", as_dict=True, include_key=True).items():
            sname = season[0] if isinstance(season, tuple) else season
            out += profile_rows(ssub, gid, sname)
    prof = pl.DataFrame(out).with_columns(
        row_ga=pl.when(pl.col("scope") == "pooled").then(pl.col("ga_all")).otherwise(pl.col("ga_all")),
        row_gate_ok=pl.col("ga_all") >= GA_ROW_GATE)
    prof.write_parquet(PROFILES)
    return prof


if __name__ == "__main__":
    p = build()
    pooled = p.filter((pl.col("scope") == "pooled"))
    goalies = pooled["goalie_id"].n_unique()
    gated = pooled.filter(pl.col("row_gate_ok"))["goalie_id"].n_unique()
    print(f"profiles: {goalies} goalies (pooled), {gated} pass the >=40 GA row gate")
    print("league rates:", {k: (round(v, 3) if isinstance(v, float) else {c: round(x, 3) for c, x in v.items()})
                             for k, v in league_rates(pl.read_parquet(M.MECH_FLAGS)).items()})
