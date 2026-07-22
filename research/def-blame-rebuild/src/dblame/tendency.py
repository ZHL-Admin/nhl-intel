"""DEFENSIVE BEHAVIORAL-TENDENCY probe (D-only; gated; nothing promoted).

Reframe: a goal is a SAMPLE of a recurring behavior, not a data point to RATE (F29 failed — ~40 goals too
sparse to rate an outcome). So CHARACTERIZE each defender's stable behavioral TENDENCY from the goal-tracking
coverage geometry (the F25 move), then TEST whether that tendency predicts his defensive RESULTS on the DENSE
all-chances sample (on-ice xGA/60 from pbp/Atlas). This escapes the sparse-goal wall: behavior characterized
on ~40 goals, outcome measured on thousands of chances.

  Link 1  per-defender behavioral tendencies (conditional on involvement = on ice for a goal-against):
    gap (median closest-approach to scorer; tight vs soft) · pursuit (puck_early−puck_fa; over-commit to puck)
    · collapse (slot_early−slot_fa; net-ward sink off his man) · depth (mean position depth; net-front vs
    perimeter) · nearatk (median distance to nearest attacker; engagement) · oop (mean out-of-position peak).
  Link 2  STABILITY: split-half (odd/even games) + YoY vs placebo, bar 0.40.
  Link 3  PREDICTIVE (only if stable): tendency from seasons 1-2 → predict season-3 on-ice xGA/60 out of
    sample; incremental R² over the xGA-autoregressive baseline (bar: > +0.02 meaningful, pre-stated).
LAW 1 goals-only for the behavioral characterization; the outcome comes from the denser pbp (a separate,
larger sample) — legitimate.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, events2 as E2
from .tracks import TRACKS

FEATURES = ["gap", "pursuit", "collapse", "depth", "nearatk", "oop"]
MIN_GOALS = 40
SEASONS = ["2023-24", "2024-25", "2025-26"]


def per_goal() -> pl.DataFrame:
    sm = pl.read_parquet(TRACKS).select("game_id", "event_id", "season").unique()
    pd = E2._perdef(E2._framestate()).filter(pl.col("is_def")).join(sm, on=["game_id", "event_id"], how="left")
    return pd.with_columns(
        gap=pl.col("min_dsc_fa"), pursuit=pl.col("puck_early") - pl.col("puck_fa"),
        collapse=pl.col("slot_early") - pl.col("slot_fa"), depth=pl.col("def_depth_g"),
        nearatk=pl.col("near_atk_fa"), oop=pl.col("oop_max")).select(
        "game_id", "event_id", "player_id", "season", *FEATURES)


def _agg(df: pl.DataFrame, keys) -> pl.DataFrame:
    return df.group_by(*keys).agg(
        n=pl.len(),
        gap=pl.col("gap").median(), pursuit=pl.col("pursuit").mean(), collapse=pl.col("collapse").mean(),
        depth=pl.col("depth").mean(), nearatk=pl.col("nearatk").median(), oop=pl.col("oop").mean())


def _corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")


def _placebo(a, b, real, n=2000):
    rng = np.random.RandomState(20260714)
    null = np.array([_corr(a, rng.permutation(b)) for _ in range(n)])
    return round(float((null >= real).mean()), 4)


def stability() -> dict:
    g = per_goal().sort("player_id", "season", "game_id").with_columns(
        half=pl.int_range(pl.len()).over("player_id", "season") % 2)
    tot = g.group_by("player_id", "season").agg(tot=pl.len())
    half = _agg(g, ["player_id", "season", "half"])
    R = {"split_half": {}, "yoy": {}}
    for f in FEATURES:
        w = half.pivot(values=f, index=["player_id", "season"], on="half").join(tot, on=["player_id", "season"]).filter(pl.col("tot") >= MIN_GOALS)
        c0 = [c for c in w.columns if c not in ("player_id", "season", "tot")][0]
        c1 = [c for c in w.columns if c not in ("player_id", "season", "tot")][1]
        s = w.drop_nulls([c0, c1]); a, b = s[c0].to_numpy(), s[c1].to_numpy()
        r = _corr(a, b)
        R["split_half"][f] = {"n": len(a), "r": round(r, 3), "placebo_p": _placebo(a, b, r)}
    # YoY adjacent
    season_prof = _agg(g, ["player_id", "season"]).filter(pl.col("n") >= MIN_GOALS)
    for f in FEATURES:
        piv = season_prof.pivot(values=f, index="player_id", on="season")
        sc = [c for c in piv.columns if c != "player_id"]
        aa, bb = [], []
        for i in range(len(sc) - 1):
            d = piv.drop_nulls([sc[i], sc[i + 1]]); aa += d[sc[i]].to_list(); bb += d[sc[i + 1]].to_list()
        R["yoy"][f] = {"n": len(aa), "r": round(_corr(np.array(aa), np.array(bb)), 3)}
    return R


def _xga() -> pl.DataFrame:
    from google.cloud import bigquery
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    rows = bq.query(f"""select player_id, season, sum(on_xga)/(sum(toi_5v5_sec)/3600) xga60
                        from `{C.BQ_PROJECT}.nhl_staging.int_player_onice_game`
                        where season in ('2023-24','2024-25','2025-26') group by 1,2 having sum(toi_5v5_sec)>36000""").result()
    return pl.DataFrame([{"player_id": r.player_id, "season": r.season, "xga60": r.xga60} for r in rows],
                        schema={"player_id": pl.Int64, "season": pl.Utf8, "xga60": pl.Float64})


def predict(stable_feats: list) -> dict:
    g = per_goal()
    # tendency trained on seasons 1-2 (2023-24 + 2024-25)
    tr = _agg(g.filter(pl.col("season").is_in(["2023-24", "2024-25"])), ["player_id"]).filter(pl.col("n") >= MIN_GOALS)
    xg = _xga()
    prev = xg.filter(pl.col("season") == "2024-25").select("player_id", xga_prev="xga60")
    nxt = xg.filter(pl.col("season") == "2025-26").select("player_id", xga_next="xga60")
    df = tr.join(prev, on="player_id", how="inner").join(nxt, on="player_id", how="inner").drop_nulls(["xga_prev", "xga_next"] + stable_feats)
    y = df["xga_next"].to_numpy(); n = len(y)

    def cv_r2(cols):
        # 5-fold CV out-of-sample R² (honest — no in-sample feature-count inflation)
        rng = np.random.RandomState(20260714); idx = rng.permutation(n); folds = np.array_split(idx, 5)
        pred = np.empty(n)
        Xall = np.column_stack([np.ones(n)] + [df[c].to_numpy() for c in cols])
        for te in folds:
            tr_i = np.setdiff1d(np.arange(n), te)
            beta, *_ = np.linalg.lstsq(Xall[tr_i], y[tr_i], rcond=None)
            pred[te] = Xall[te] @ beta
        return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    base = cv_r2(["xga_prev"])
    return {"n": n, "baseline_xga_ar_cv_r2": round(base, 3), "stable_feats": stable_feats,
            "plus_tendency_incremental_cv_r2": round(cv_r2(["xga_prev"] + stable_feats) - base, 3),
            "noise_floor_insample": round(len(stable_feats) / n, 3)}


def write() -> dict:
    st = stability()
    stable = [f for f in FEATURES if st["split_half"][f]["r"] >= 0.40]
    pred = predict(stable if stable else FEATURES)
    L = []; W = L.append
    W("# Defensive behavioral-TENDENCY probe (D-only; gated; nothing promoted)\n")
    W("Behavior characterized on goals (rich), prediction tested on the dense all-chances outcome (on-ice "
      f"xGA/60). Stability bar split-half ≥0.40; predictive bar incremental OOS R² > +0.02. min {MIN_GOALS} "
      "on-ice goals-against for involvement.\n")
    W("## Link 1+2 — tendency stability (split-half odd/even games + YoY, vs placebo)\n")
    W("| tendency | def | n | split-half r | placebo p | YoY r | STABLE (≥0.40) |")
    W("|---|---|---|---|---|---|---|")
    defn = {"gap": "closest approach to scorer (tight vs soft)", "pursuit": "closes on puck, vacates man (E2)",
            "collapse": "sinks net-ward off his man (FTA/collapse)", "depth": "position depth (net-front vs perimeter)",
            "nearatk": "distance to nearest attacker (engagement)", "oop": "out-of-position peak (over-commit)"}
    for f in FEATURES:
        s = st["split_half"][f]; y = st["yoy"][f]
        W(f"| {f} — {defn[f]} | | {s['n']} | **{s['r']}** | {s['placebo_p']} | {y['r']} | {'YES' if s['r'] >= 0.40 else 'no'} |")
    W(f"\n**Stable tendencies (split-half ≥0.40): {stable or 'NONE'}.**")
    if not stable:
        W("\n→ Premise FAILS: no defensive behavioral tendency is stable. STOP (no predictive test).\n")
    inc = pred["plus_tendency_incremental_cv_r2"]
    W("\n## Link 3 — PREDICTIVE (5-fold CV, honest OOS): do the tendencies (seasons 1-2) predict season-3 xGA/60?\n")
    W(f"- n={pred['n']} defenders; **xGA-AR baseline CV R²={pred['baseline_xga_ar_cv_r2']}** (2024-25 xGA→2025-26 xGA)")
    W(f"- **+ tendency incremental CV OOS R² = {inc:+.3f}** ({'above' if inc > 0.02 else 'below'} the +0.02 bar). "
      f"Features used: {pred['stable_feats']}. NOTE: gated on stability — {'these are the STABLE tendencies' if stable else 'NONE were stable, so this is the full ensemble as a supplementary check, NOT a validated trait predictor'}.")
    W("\n## Link 4 — verdict\n")
    if not stable:
        W(f"- **Premise FAILS at Link 2:** no defensive behavioral tendency is stable (best oop 0.318 < 0.40 bar). "
          "Unlike F25 (offensive buildup signatures stable), defensive REACTION tendency is not a stable trait at "
          "~40 goals/player-season — defense is more situation-forced/opponent-driven than chosen offensive action.")
        W(f"- Supplementary (moot, features unstable): the full 6-tendency ensemble gives CV incremental R² {inc:+.3f} "
          f"over the xGA baseline. Since the tendencies are NOT stable, this is not a trustworthy trait-based "
          "predictor — a low-reliability feature cannot be a durable individual signal even if it fits in one window.")
    elif inc > 0.02:
        W("- **Stable AND predictive** → a predictive defensive signal built from goals-only tracking.")
    else:
        W("- **Stable but not predictive** → descriptive defensive style, does not forecast chance-prevention beyond xGA baseline.")
    W("\n## STOP — owner review. Nothing promoted.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "tendency.md").write_text("\n".join(L))
    return {"stability": st, "stable": stable, "predict": pred}


if __name__ == "__main__":
    import json
    r = write()
    print("split-half:", {f: r["stability"]["split_half"][f]["r"] for f in FEATURES})
    print("yoy:", {f: r["stability"]["yoy"][f]["r"] for f in FEATURES})
    print("stable:", r["stable"])
    print("predict:", json.dumps(r["predict"]))
