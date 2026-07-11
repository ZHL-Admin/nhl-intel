"""Phase 5 — pre-registered mover validation: does context correction travel?

Cohorts, metrics, and the decision rule are fixed in advance (see reports/phase5.md).
Predictors: (a) raw season-S on-ice xG share; (b) production RAPM; (b2) Atlas
variant RAPM; (c) best-adjusted + destination context. Leave-one-season-pair-out:
fit on STAYERS of all other pairs, evaluate on MOVERS of the held-out pair.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from . import config, sources, stints as stints_mod

# Scheduled-games fraction (vs 82) for shortened seasons — prorates the 400-min bar.
GAMES_FRAC = {"2012-13": 48 / 82, "2019-20": 70 / 82, "2020-21": 56 / 82}
MIN_5V5_MIN = 400.0

PLAYER_SEASON_TEAM = config.PARQUET_DIR / "player_season_team_onice.parquet"


def _is5(df: pl.DataFrame) -> pl.Expr:
    return ((df["home_skater_ids"].list.len() == 5) & (df["away_skater_ids"].list.len() == 5)
            & df["home_goalie_id"].is_not_null() & df["away_goalie_id"].is_not_null())


def build_onice(force: bool = False) -> pl.DataFrame:
    """Per (player, season, team): 5v5 TOI + on-ice xGF/xGA/GF/GA/CF/CA."""
    if not force and PLAYER_SEASON_TEAM.exists():
        return pl.read_parquet(PLAYER_SEASON_TEAM)
    st = pl.read_parquet(stints_mod.STINTS_PARQUET).filter(_is5(pl.read_parquet(stints_mod.STINTS_PARQUET))
                                                           & ~pl.col("is_quarantined"))
    games = pl.read_parquet(sources.GAMES_PARQUET).select("game_id", "home_team_id", "away_team_id")
    st = st.join(games, on="game_id", how="left")
    base = ["season_label", "duration_seconds"]

    def side(ids, tcol, xgf, xga, cf, ca, gf, ga):
        return st.select(*base, pl.col(tcol).alias("team_id"), pl.col(ids).alias("pid"),
                         pl.col(xgf).alias("xgf"), pl.col(xga).alias("xga"),
                         pl.col(cf).alias("cf"), pl.col(ca).alias("ca"),
                         pl.col(gf).alias("gf"), pl.col(ga).alias("ga")).explode("pid").rename({"pid": "player_id"})
    h = side("home_skater_ids", "home_team_id", "home_xg", "away_xg", "home_corsi", "away_corsi", "home_goals", "away_goals")
    a = side("away_skater_ids", "away_team_id", "away_xg", "home_xg", "away_corsi", "home_corsi", "away_goals", "home_goals")
    both = pl.concat([h, a]).drop_nulls("player_id")
    agg = both.group_by("player_id", "season_label", "team_id").agg(
        toi_s=pl.col("duration_seconds").sum(),
        xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
        cf=pl.col("cf").sum(), ca=pl.col("ca").sum(),
        gf=pl.col("gf").sum(), ga=pl.col("ga").sum())
    agg.write_parquet(PLAYER_SEASON_TEAM)
    return agg


def player_season() -> pl.DataFrame:
    """Per (player, season): totals across teams + primary team + shares."""
    t = build_onice()
    tot = t.group_by("player_id", "season_label").agg(
        toi_s=pl.col("toi_s").sum(), xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
        gf=pl.col("gf").sum(), ga=pl.col("ga").sum())
    prim = t.sort("toi_s", descending=True).unique(["player_id", "season_label"], keep="first").select(
        "player_id", "season_label", pl.col("team_id").alias("primary_team"))
    out = tot.join(prim, on=["player_id", "season_label"]).with_columns(
        toi_min=pl.col("toi_s") / 60.0,
        xg_share=pl.col("xgf") / (pl.col("xgf") + pl.col("xga")),
        gf_share=pl.col("gf") / (pl.col("gf") + pl.col("ga")))
    return out


def _bar(season: str) -> float:
    return MIN_5V5_MIN * GAMES_FRAC.get(season, 1.0)


def cohorts(ps: pl.DataFrame, s: str, s1: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Movers (primary team changed) and stayers for pair (s, s1)."""
    A = ps.filter((pl.col("season_label") == s) & (pl.col("toi_min") >= _bar(s)))
    B = ps.filter((pl.col("season_label") == s1) & (pl.col("toi_min") >= _bar(s1)))
    m = A.join(B, on="player_id", suffix="_next")
    movers = m.filter(pl.col("primary_team") != pl.col("primary_team_next"))
    stayers = m.filter(pl.col("primary_team") == pl.col("primary_team_next"))
    return movers, stayers


def all_pairs(start=2010, end=2025) -> list[tuple[str, str]]:
    labels = [f"{y}-{str(y+1)[2:]}" for y in range(start, end + 1)]
    return list(zip(labels, labels[1:]))


def attach_predictors(cohort: pl.DataFrame, s: str,
                      prod: pl.DataFrame, var: pl.DataFrame) -> pl.DataFrame:
    """Add predictor features measured at season S: raw xG share, production RAPM
    off/def, variant RAPM off/def. Target = S+1 xg_share (col xg_share_next)."""
    out = cohort.with_columns(raw_xgshare=pl.col("xg_share"))
    p = prod.filter(pl.col("season") == s).select(
        "player_id", pl.col("off_impact").alias("prod_off"), pl.col("def_impact").alias("prod_def"))
    v = var.filter(pl.col("season") == s).select(
        "player_id", pl.col("off_impact").alias("var_off"), pl.col("def_impact").alias("var_def"))
    return out.join(p, on="player_id", how="left").join(v, on="player_id", how="left")


# ---- LOSO regression + metrics ----
def _fit_predict(train: pl.DataFrame, test: pl.DataFrame, feats: list[str], target="xg_share_next"):
    tr = train.drop_nulls(feats + [target]); te = test.drop_nulls(feats + [target])
    if tr.height < 30 or te.height == 0:
        return None
    Xtr = np.c_[np.ones(tr.height), tr.select(feats).to_numpy()]
    ytr = tr[target].to_numpy()
    beta, *_ = np.linalg.lstsq(Xtr, ytr, rcond=None)
    Xte = np.c_[np.ones(te.height), te.select(feats).to_numpy()]
    pred = Xte @ beta
    return te["player_id"].to_numpy(), te[target].to_numpy(), pred


def loso(pairs_data: dict[str, dict], feats: list[str], target: str = "xg_share_next",
         eval_on: str = "movers") -> dict[str, Any]:
    """pairs_data[pairkey] = {'movers':df,'stayers':df}. Fit on stayers of all OTHER
    pairs; predict `eval_on` (movers|stayers) of the held-out pair. Pool + per-pair
    MAE/Spearman. (Held-out stayers are out-of-fold, so stayers eval is valid.)"""
    from scipy.stats import spearmanr
    per_pair = {}
    pooled_pid, pooled_y, pooled_p, pooled_pair = [], [], [], []
    for held in pairs_data:
        train = pl.concat([pairs_data[k]["stayers"] for k in pairs_data if k != held])
        r = _fit_predict(train, pairs_data[held][eval_on], feats, target=target)
        if r is None:
            continue
        pid, y, p = r
        mae = float(np.mean(np.abs(p - y)))
        sp = spearmanr(p, y).statistic if len(y) > 2 else np.nan
        per_pair[held] = {"n": len(y), "mae": mae, "spearman": float(sp)}
        pooled_pid.extend(pid); pooled_y.extend(y); pooled_p.extend(p); pooled_pair.extend([held] * len(y))
    y = np.array(pooled_y); p = np.array(pooled_p)
    return {"per_pair": per_pair, "pooled_mae": float(np.mean(np.abs(p - y))),
            "pooled_spearman": float(spearmanr(p, y).statistic),
            "pid": np.array(pooled_pid), "y": y, "pred": p, "pair": np.array(pooled_pair)}


def _key(res):
    return {(int(pid), pr): (yy, pp) for pid, pr, yy, pp in
            zip(res["pid"], res["pair"], res["y"], res["pred"])}


def bootstrap_mae_diff(res_adj, res_base, B: int = 1000, seed: int = 20260710):
    """Paired bootstrap of MAE(adjusted) - MAE(base) over the COMMON movers (same
    held-out (player, pair)). Negative = adjusted better. Returns pct improvement +
    95% CI of the improvement fraction."""
    ka, kb = _key(res_adj), _key(res_base)
    common = sorted(set(ka) & set(kb))
    ea = np.array([abs(ka[k][1] - ka[k][0]) for k in common])
    eb = np.array([abs(kb[k][1] - kb[k][0]) for k in common])
    base_mae = eb.mean(); adj_mae = ea.mean()
    obs_impr = (base_mae - adj_mae) / base_mae  # fraction improvement over base
    rng = np.random.default_rng(seed); n = len(common); imprs = []
    for _ in range(B):
        idx = rng.integers(0, n, n)
        b = eb[idx].mean(); a = ea[idx].mean()
        imprs.append((b - a) / b)
    lo, hi = np.percentile(imprs, [2.5, 97.5])
    return {"n_common": n, "base_mae": float(base_mae), "adj_mae": float(adj_mae),
            "pct_improvement": float(obs_impr), "ci_lo": float(lo), "ci_hi": float(hi),
            "ci_excludes_zero": bool(lo > 0 or hi < 0)}


def decision(impr_pct: float, ci_excludes_zero: bool) -> str:
    if impr_pct >= 0.05 and ci_excludes_zero:
        return "SHIP"
    if impr_pct <= 0:
        return "KILL"
    return "INVESTIGATE"
