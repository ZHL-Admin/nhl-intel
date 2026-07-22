"""Statistical-estimation pass for the D-only defensive-blame rating (evaluation; nothing promoted).

The prior work only tested the NAIVE per-player rate (isolated blame / goals), which plateaued at pooled
split-half ~0.28. Here we apply estimators that borrow strength across players/events and test each the RIGHT
way (split-half the ESTIMATOR, not the raw rate; YoY; placebo; and out-of-sample predict-next-xGA lift):
  A1 Empirical-Bayes / hierarchical shrinkage toward TOI-tier priors (exposure-weighted).
  A2 RAPM-style ridge: joint per-player defensive-blame effects controlling for on-ice teammates + opponents.
  A3 predict next-season on-ice xGA/60 out of sample, incremental over the xGA-autoregressive baseline.
  A4 coverage-ONLY under A1 and A2 (the durable component).
Design unit = each tracked 5v5 goal-against: total (and coverage) defensive blame + on-ice defenders/attackers.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, events2 as E2, leaderboard as LB
from .meta import load as load_meta
from .tracks import TRACKS

DESIGN = C.PARQUET / "estim_design.parquet"
SEASONS = ["2023-24", "2024-25", "2025-26"]
LEDMAP = {"E1": "cov", "E2": "cov", "E3": "cov", "R3": "cov", "R6": "cov", "FTA": "cov", "OUT_OF_ZONE": "cov",
          "TURNOVER": "turn", "RUSH_DEFENSE": "rush"}   # turn/rush must NOT fall through default to 'cov'


def design() -> pl.DataFrame:
    """Per tracked 5v5 goal: total blame, coverage blame, on-ice defender ids (D-only), on-ice attacker ids."""
    if DESIGN.exists():
        return pl.read_parquet(DESIGN)
    from google.cloud import bigquery
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    rows = bq.query(f"""select game_id, event_id, on_ice_for, on_ice_against
                        from `{C.BQ_PROJECT}.nhl_staging.int_on_ice_events`
                        where type_desc_key='goal' and game_id >= 2023020000""").result()
    oi = pl.DataFrame([{"game_id": r.game_id, "event_id": r.event_id,
                        "att": list(r.on_ice_for), "dfn": list(r.on_ice_against)} for r in rows])
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "season", "home_goalie_id", "away_goalie_id")
    tracked = pl.read_parquet(TRACKS).select("game_id", "event_id", "season").unique()
    isdef = set(load_meta().filter(pl.col("is_def"))["player_id"].to_list())
    rec = pl.read_parquet(E2.REC).with_columns(lk=pl.col("event_type").replace_strict(LEDMAP, default="cov"))
    blame = rec.group_by("game_id", "event_id").agg(
        total=pl.col("severity").sum(), cov=pl.col("severity").filter(pl.col("lk") == "cov").sum())
    g = (tracked.join(oi, on=["game_id", "event_id"], how="inner")
         .join(fused, on=["game_id", "event_id"], how="left")
         .join(blame, on=["game_id", "event_id"], how="left")
         .with_columns(total=pl.col("total").fill_null(0.0), cov=pl.col("cov").fill_null(0.0)))
    go = {(r["game_id"], r["event_id"]): {r["home_goalie_id"], r["away_goalie_id"]} for r in g.iter_rows(named=True)}
    recs = []
    for r in g.iter_rows(named=True):
        gs = go[(r["game_id"], r["event_id"])]
        d = [p for p in r["dfn"] if p in isdef and p not in gs]
        a = [p for p in r["att"] if p not in gs]
        recs.append({"game_id": r["game_id"], "event_id": r["event_id"], "season": r["season"],
                     "total": r["total"], "cov": r["cov"], "dfn": d, "att": a})
    out = pl.DataFrame(recs)
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(DESIGN)
    return out


# ---------- long form: one (defender, goal) row ----------
def _long(g: pl.DataFrame, value: str) -> pl.DataFrame:
    return g.select("game_id", "season", "dfn", v=value).explode("dfn").rename({"dfn": "player_id"})


# ---------- A1: Empirical-Bayes shrinkage ----------
def eb(long: pl.DataFrame, tier: dict) -> pl.DataFrame:
    """Shrink each D's mean per-goal blame toward his TOI-tier prior; weight = exposure vs within-var."""
    s2 = float(long["v"].var())                                   # within (goal-level) variance
    pl_stats = long.group_by("player_id").agg(raw=pl.col("v").mean(), n=pl.len())
    pl_stats = pl_stats.with_columns(tier=pl.col("player_id").replace_strict(tier, default="T2", return_dtype=pl.Utf8))
    grp = pl_stats.group_by("tier").agg(m_g=(pl.col("raw") * pl.col("n")).sum() / pl.col("n").sum())
    pl_stats = pl_stats.join(grp, on="tier", how="left")
    # between-var within tier (method of moments), floored at 0
    tau2 = max(float((pl_stats["raw"] - pl_stats["m_g"]).pow(2).mean()) - s2 / float(pl_stats["n"].mean()), 1e-6)
    return pl_stats.with_columns(
        B=tau2 / (tau2 + s2 / pl.col("n")),
        eb=pl.col("m_g") + (tau2 / (tau2 + s2 / pl.col("n"))) * (pl.col("raw") - pl.col("m_g"))).select("player_id", "raw", "eb", "n")


# ---------- A2: RAPM ridge (joint) ----------
def rapm(g: pl.DataFrame, value: str, lam: float = 50.0) -> pl.DataFrame:
    """Ridge: y(goal)=total blame ~ on-ice defenders(+1) + on-ice attackers(+1, separate). Return D effects."""
    dfn_ids = sorted({p for r in g["dfn"].to_list() for p in r})
    att_ids = sorted({p for r in g["att"].to_list() for p in r})
    di = {p: i for i, p in enumerate(dfn_ids)}
    ai = {p: i + len(di) for i, p in enumerate(att_ids)}
    ncol = len(di) + len(ai)
    rowsd = g.to_dicts()
    nrow = len(rowsd)
    # build sparse-ish design via normal equations accumulation
    XtX = np.zeros((ncol, ncol)); Xty = np.zeros(ncol)
    y = g[value].to_numpy()
    for k, r in enumerate(rowsd):
        idx = [di[p] for p in r["dfn"]] + [ai[p] for p in r["att"] if p in ai]
        for i in idx:
            Xty[i] += y[k]
            for j in idx:
                XtX[i, j] += 1.0
    beta = np.linalg.solve(XtX + lam * np.eye(ncol), Xty)
    return pl.DataFrame({"player_id": dfn_ids, "rapm": beta[:len(di)].tolist()})


# ---------- reliability: split-half (fit on each half) + placebo ----------
def _corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")


def _placebo(a, b, real, n=2000):
    rng = np.random.RandomState(20260716)
    null = np.array([np.corrcoef(a, rng.permutation(b))[0, 1] for _ in range(n)])
    return {"null": round(float(null.mean()), 3), "p_ge": round(float((null >= real).mean()), 4)}


def _tier() -> dict:
    lb = LB.aggregate().filter(pl.col("pos") == "D")
    t = lb.group_by("player_id").agg(toi=pl.col("toi_min").sum())
    t = t.with_columns(tier=("T" + (pl.col("toi").rank(descending=True) / pl.len() * 4).ceil().clip(1, 4).cast(pl.Int64).cast(pl.Utf8)))
    return dict(zip(t["player_id"], t["tier"]))


def evaluate(value: str, min_ga: int = 60) -> dict:
    g = design().with_columns(gi=pl.int_range(pl.len()).over("game_id") * 0)  # placeholder
    g = design().sort("game_id", "event_id").with_columns(half=pl.int_range(pl.len()) % 2)
    tier = _tier()
    exposure = _long(g, value).group_by("player_id").agg(n=pl.len())
    keep = set(exposure.filter(pl.col("n") >= min_ga)["player_id"].to_list())
    out = {}
    for est in ["naive", "eb", "rapm"]:
        halves = []
        for h in [0, 1]:
            gh = g.filter(pl.col("half") == h)
            lh = _long(gh, value)
            if est == "naive":
                e = lh.group_by("player_id").agg(val=pl.col("v").mean())
            elif est == "eb":
                e = eb(lh, tier).select("player_id", val="eb")
            else:
                e = rapm(gh, value).rename({"rapm": "val"})
            halves.append(e)
        w = halves[0].join(halves[1], on="player_id", how="inner", suffix="_2").filter(pl.col("player_id").is_in(keep)).drop_nulls()
        a, b = w["val"].to_numpy(), w["val_2"].to_numpy()
        r = _corr(a, b)
        out[est] = {"n": len(a), "split_half": round(r, 3), **_placebo(a, b, r)}
    return out


# ---------- A3: predict next-season xGA/60 ----------
def _season_estimates(value: str) -> pl.DataFrame:
    """Per (player, season): naive rate, EB estimate, RAPM effect."""
    g = design(); tier = _tier()
    parts = []
    for s in SEASONS:
        gs = g.filter(pl.col("season") == s)
        lh = _long(gs, value)
        naive = lh.group_by("player_id").agg(naive=pl.col("v").mean(), n=pl.len())
        ebs = eb(lh, tier).select("player_id", eb="eb")
        rp = rapm(gs, value).rename({"rapm": "rapm"})
        m = naive.join(ebs, on="player_id", how="left").join(rp, on="player_id", how="left").with_columns(season=pl.lit(s))
        parts.append(m)
    return pl.concat(parts)


def predict_xga(value: str = "total", min_ga: int = 40) -> dict:
    from google.cloud import bigquery
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    xg = pl.DataFrame([{"player_id": r.player_id, "season": r.season, "xga60": r.xga60}
                       for r in bq.query(f"""select player_id, season, sum(on_xga)/(sum(toi_5v5_sec)/3600) xga60
                       from `{C.BQ_PROJECT}.nhl_staging.int_player_onice_game` where season in ('2023-24','2024-25','2025-26')
                       group by 1,2 having sum(toi_5v5_sec) > 60000""").result()],
                      schema={"player_id": pl.Int64, "season": pl.Utf8, "xga60": pl.Float64})
    est = _season_estimates(value).filter(pl.col("n") >= min_ga)
    nxt = {"2023-24": "2024-25", "2024-25": "2025-26"}
    est = est.with_columns(nseason=pl.col("season").replace_strict(nxt, default=None, return_dtype=pl.Utf8))
    df = (est.join(xg, on=["player_id", "season"], how="inner")
          .join(xg.rename({"season": "nseason", "xga60": "xga60_next"}), on=["player_id", "nseason"], how="inner")
          .drop_nulls(["xga60", "xga60_next", "naive", "eb", "rapm"]))
    y = df["xga60_next"].to_numpy()

    def r2(Xcols):
        X = np.column_stack([np.ones(len(y))] + [df[c].to_numpy() for c in Xcols])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        yh = X @ beta
        return 1 - ((y - yh) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    base = r2(["xga60"])
    return {"n": len(y), "baseline_xga_ar_r2": round(base, 3),
            "plus_naive": round(r2(["xga60", "naive"]) - base, 3),
            "plus_eb": round(r2(["xga60", "eb"]) - base, 3),
            "plus_rapm": round(r2(["xga60", "rapm"]) - base, 3)}


def write() -> dict:
    R = {"reliability": {}, "predict": {}}
    for label, value in [("blend", "total"), ("coverage", "cov")]:
        R["reliability"][label] = {f"min{m}": evaluate(value, m) for m in [60, 100]}
        R["predict"][label] = predict_xga(value, 40)
    L = []; W = L.append
    W("# D-only defensive blame — statistical-estimation pass (evaluation; nothing promoted)\n")
    W("Estimators that borrow strength, each split-half tested on the ESTIMATE (not the raw rate), + placebo, "
      "+ out-of-sample predict-next-xGA lift. 0.30 reliability bar; F25 offensive reference 0.41-0.76.\n")
    for label in ["blend", "coverage"]:
        W(f"\n## {label.upper()} — split-half reliability of each estimator (pooled 3-season)\n")
        W("| pool | estimator | n | split-half r | placebo p(null≥r) | vs 0.30 |")
        W("|---|---|---|---|---|---|")
        for m in [60, 100]:
            for est in ["naive", "eb", "rapm"]:
                v = R["reliability"][label][f"min{m}"][est]
                W(f"| min-{m} | {est} | {v['n']} | **{v['split_half']}** | {v['p_ge']} | {'PASS' if v['split_half'] >= 0.30 else 'FAIL'} |")
        p = R["predict"][label]
        W(f"\n**{label} — predict next-season xGA/60 (n={p['n']}):** xGA-AR baseline R²={p['baseline_xga_ar_r2']}; "
          f"incremental over baseline → +naive {p['plus_naive']:+.3f}, +EB {p['plus_eb']:+.3f}, +RAPM {p['plus_rapm']:+.3f}.")
    W("\n## A5 feasibility — expand numerator to chances\n")
    W("The tracking corpus (`fused_goals`, 25,946 events / 4,250 games) is **GOALS-ONLY** — non-goal shots have "
      "no tracking frames. Extending the coverage blame-geometry to high-danger chances would multiply events "
      "~5-10x (shots) / ~3-4x (high-danger), but is NOT computable on the current data (no frames on non-goal "
      "shots). It requires new tracking ingestion on shot events — a data-acquisition lever, not an analysis one.\n")
    W("\n## STOP — owner reads which estimator (if any) graduates.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "estimators.md").write_text("\n".join(L))
    return R


if __name__ == "__main__":
    import json
    print(json.dumps(write(), indent=1))
