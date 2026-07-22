"""TEAM defensive failure-type profiles — stable? predictive? (gated probe; nothing promoted).

Reuses the five VALIDATED ledgers as the failure-type vocabulary (does NOT rebuild them). Each tracked
goal-against is labelled by its PRIMARY mechanism (the max-severity charged event), plus origin (rush vs
settled). A team-season profile = the distribution of its goals-against across those failure types. Then:
  Link 1  build profiles + league baseline + how much teams actually differ (vs sampling noise)
  Link 2  STABILITY gate: split-half (odd/even games) of each type share vs placebo (bar 0.40 team-level), YoY
Failure-type vocabulary (event_type -> category):
  E1 containment · E2 over-commit · R3 inside-leverage · E3/R6 failure-to-close · OUT_OF_ZONE/FTA
  out-of-zone/blown-switch · TURNOVER turnover-into-danger · RUSH_DEFENSE rush-beaten · (none = no mechanism)
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, events2 as E2
from .data import universe

CATMAP = {"E1": "containment", "E2": "over_commit", "R3": "inside_lev", "E3": "fail_close", "R6": "fail_close",
          "FTA": "out_of_zone", "OUT_OF_ZONE": "out_of_zone", "TURNOVER": "turnover", "RUSH_DEFENSE": "rush_beaten"}
CATS = ["containment", "over_commit", "inside_lev", "fail_close", "out_of_zone", "turnover", "rush_beaten", "none"]


def goal_labels() -> pl.DataFrame:
    """Per tracked goal: defending_team, season, game_id, primary failure category, rush/settled origin."""
    rec = pl.read_parquet(E2.REC)
    prim = (rec.sort("severity", descending=True).group_by("game_id", "event_id").first()
            .select("game_id", "event_id", "event_type", top_sev="severity"))
    u = universe().select("game_id", "event_id", "season", "defending_team_id", "entry_frame", "goal_frame")
    g = (u.join(prim, on=["game_id", "event_id"], how="left")
         .with_columns(cat=pl.when(pl.col("top_sev").fill_null(0) < 1e-6).then(pl.lit("none"))
                       .otherwise(pl.col("event_type").replace_strict(CATMAP, default="none")),
                       rush=pl.col("entry_frame").is_not_null() & ((pl.col("goal_frame") - pl.col("entry_frame")) <= int(4 * C.HZ))))
    return g.select("game_id", "event_id", "season", pl.col("defending_team_id").alias("team"), "cat", "rush")


def profiles(min_ga: int = 40) -> pl.DataFrame:
    g = goal_labels()
    prof = (g.group_by("team", "season").agg(
        ga=pl.len(), rush_share=pl.col("rush").mean(),
        **{c: (pl.col("cat") == c).mean() for c in CATS}))
    return prof.filter(pl.col("ga") >= min_ga)


def _spread() -> pl.DataFrame:
    """How much do teams differ per category vs sampling noise? observed SD vs binomial SD at team GA."""
    p = profiles(60)
    rows = []
    for c in CATS + ["rush_share"]:
        obs = float(p[c].std())
        pbar = float(p[c].mean()); nbar = float(p["ga"].mean())
        samp = float(np.sqrt(pbar * (1 - pbar) / nbar))
        rows.append({"type": c, "league_mean": round(pbar, 3), "team_sd": round(obs, 3),
                     "sampling_sd": round(samp, 3), "excess_ratio": round(obs / (samp + 1e-9), 2)})
    return pl.DataFrame(rows)


def _corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")


def _placebo(a, b, real, n=2000):
    rng = np.random.RandomState(20260716)
    null = np.array([np.corrcoef(a, rng.permutation(b))[0, 1] for _ in range(n)])
    return {"null": round(float(null.mean()), 3), "p_ge": round(float((null >= real).mean()), 4)}


def stability(min_ga: int = 60) -> dict:
    g = goal_labels().sort("team", "season", "game_id").with_columns(
        half=pl.int_range(pl.len()).over("team", "season") % 2)
    half = g.group_by("team", "season", "half").agg(
        ga=pl.len(), rush_share=pl.col("rush").mean(), **{c: (pl.col("cat") == c).mean() for c in CATS})
    tot = g.group_by("team", "season").agg(tot=pl.len())
    R = {}
    for metric in CATS + ["rush_share"]:
        w = half.pivot(values=metric, index=["team", "season"], on="half").join(tot, on=["team", "season"]).filter(pl.col("tot") >= min_ga)
        c0 = [c for c in w.columns if c not in ("team", "season", "tot")][0]
        c1 = [c for c in w.columns if c not in ("team", "season", "tot")][1]
        s = w.drop_nulls([c0, c1]); a, b = s[c0].to_numpy(), s[c1].to_numpy()
        r = _corr(a, b)
        R[metric] = {"n": len(a), "split_half": round(r, 3), **_placebo(a, b, r)}
    # YoY: same team adjacent seasons
    pr = profiles(60)
    yoy = {}
    for metric in CATS + ["rush_share"]:
        piv = pr.pivot(values=metric, index="team", on="season")
        scols = [c for c in piv.columns if c != "team"]
        pairs = []
        for i in range(len(scols) - 1):
            d = piv.drop_nulls([scols[i], scols[i + 1]])
            pairs.append((d[scols[i]].to_numpy(), d[scols[i + 1]].to_numpy()))
        aa = np.concatenate([p[0] for p in pairs]); bb = np.concatenate([p[1] for p in pairs])
        yoy[metric] = {"n": len(aa), "yoy": round(_corr(aa, bb), 3)}
    return {"split_half": R, "yoy": yoy}


def predictive(cats, min_ga: int = 60) -> dict:
    """Link 3 — out-of-sample: chronological first-half predicts second-half; and does the team's train-half
    rate beat the league base rate at predicting whether a held-out goal is that type (Brier skill)?"""
    g = goal_labels().sort("team", "season", "game_id").with_columns(
        gi=pl.int_range(pl.len()).over("team", "season"), n=pl.len().over("team", "season"))
    g = g.with_columns(part=pl.when(pl.col("gi") < (pl.col("n") / 2)).then(0).otherwise(1))
    tot = g.group_by("team", "season").agg(tot=pl.len())
    out = {}
    for cat in cats:
        gc = g.with_columns(y=(pl.col("cat") == cat).cast(pl.Float64))
        tr = gc.filter(pl.col("part") == 0).group_by("team", "season").agg(train=pl.col("y").mean())
        te = gc.filter(pl.col("part") == 1).group_by("team", "season").agg(test=pl.col("y").mean())
        m = tr.join(te, on=["team", "season"], how="inner").join(tot, on=["team", "season"]).filter(pl.col("tot") >= min_ga).drop_nulls()
        oos_r = _corr(m["train"].to_numpy(), m["test"].to_numpy())
        # Brier skill on held-out (part==1) goals: team train-rate vs league train base rate
        league = float(gc.filter(pl.col("part") == 0)["y"].mean())
        test_goals = gc.filter(pl.col("part") == 1).join(tr, on=["team", "season"], how="inner").join(tot, on=["team", "season"]).filter(pl.col("tot") >= min_ga)
        y = test_goals["y"].to_numpy(); pt = test_goals["train"].to_numpy()
        br_team = float(((y - pt) ** 2).mean()); br_league = float(((y - league) ** 2).mean())
        out[cat] = {"n_ts": m.height, "oos_first_predicts_second_r": round(oos_r, 3),
                    "brier_skill_vs_league": round(1 - br_team / br_league, 4)}
    return out


def player_situation(cat: str, min_ga: int = 60) -> dict:
    """Link 4 (lower expectation) — per-player RATE: of the on-ice tracked goals a D was on for, the share where
    HE was the culprit of this failure type. Split-half odd/even goals (exposure-neutral, unlike raw counts)."""
    from .tracks import TRACKS
    from .meta import load as load_meta
    isdef = load_meta().filter(pl.col("is_def")).select("player_id")
    keys = {k for k, v in CATMAP.items() if v == cat}
    culprit = pl.read_parquet(E2.REC).filter(pl.col("event_type").is_in(list(keys))).select("game_id", "event_id", "player_id").unique().with_columns(hit=pl.lit(1.0))
    onice = pl.read_parquet(TRACKS).select("game_id", "event_id", "player_id").unique().join(isdef, on="player_id", how="inner")
    j = onice.join(culprit, on=["game_id", "event_id", "player_id"], how="left").with_columns(hit=pl.col("hit").fill_null(0.0)).sort("player_id", "game_id").with_columns(half=pl.int_range(pl.len()).over("player_id") % 2)
    h = j.group_by("player_id", "half").agg(rate=pl.col("hit").mean(), n=pl.len())
    tot = j.group_by("player_id").agg(t=pl.len())
    w = h.pivot(values="rate", index="player_id", on="half").join(tot, on="player_id").filter(pl.col("t") >= min_ga).drop_nulls()
    c0 = [c for c in w.columns if c not in ("player_id", "t")][0]; c1 = [c for c in w.columns if c not in ("player_id", "t")][1]
    a, b = w[c0].to_numpy(), w[c1].to_numpy()
    return {"cat": cat, "n_players": w.height, "split_half_rate_r": round(_corr(a, b), 3)}


def write() -> dict:
    sp = _spread()
    st = stability(60)
    pr = profiles(60)
    top = ["out_of_zone", "turnover", "inside_lev"]
    pred = predictive(top, 60)
    psit = {c: player_situation(c) for c in ["out_of_zone", "inside_lev"]}
    L = []; W = L.append
    W("# TEAM defensive failure-type profiles — stability probe (gated; nothing promoted)\n")
    W("Each tracked goal-against labelled by PRIMARY mechanism (max-severity charged event) + rush/settled "
      "origin; team-season profile = distribution over failure types. **Bar: team-level split-half ≥ 0.40 "
      "beating placebo.**\n")
    W("## Link 1 — do teams actually differ? (observed team SD vs binomial sampling SD)\n")
    W("| failure type | league mean | team SD | sampling SD | excess (SD/noise) |")
    W("|---|---|---|---|---|")
    for r in sp.sort("excess_ratio", descending=True).iter_rows(named=True):
        W(f"| {r['type']} | {r['league_mean']} | {r['team_sd']} | {r['sampling_sd']} | **{r['excess_ratio']}** |")
    W("\n(excess ≈1 = teams differ no more than chance; >1.5 = real between-team structure.)\n")
    W("## Link 2 — STABILITY: split-half (odd/even games) vs placebo, + YoY. Bar 0.40.\n")
    W("| failure type | n | split-half r | placebo p | YoY r | vs 0.40 |")
    W("|---|---|---|---|---|---|")
    for m in CATS + ["rush_share"]:
        v = st["split_half"][m]; y = st["yoy"][m]
        W(f"| {m} | {v['n']} | **{v['split_half']}** | {v['p_ge']} | {y['yoy']} | {'PASS' if v['split_half'] >= 0.40 else 'fail'} |")
    W("\n## Link 3 — PREDICTIVE (top-differentiated types): chronological first-half → second-half, out of sample\n")
    W("| failure type | n team-seasons | OOS r (1st→2nd half) | Brier skill vs league base rate |")
    W("|---|---|---|---|")
    for c in top:
        p = pred[c]; W(f"| {c} | {p['n_ts']} | **{p['oos_first_predicts_second_r']}** | {p['brier_skill_vs_league']:+.4f} |")
    W("\n(Brier skill >0 = the team's own first-half rate predicts held-out goal types BETTER than the league "
      "base rate; ≤0 = no team-specific predictive value beyond the league average.)\n")
    W("## Link 4 — player-in-situation (lower-sample, coin-flip caveat): does a D repeatedly get beaten the same way?\n")
    for c, v in psit.items():
        W(f"- **{c}:** per-player split-half of culprit-RATE = {v['split_half_rate_r']} (n={v['n_players']} D, ≥60 on-ice GA; exposure-neutral)")
    W("\n## STOP — owner reads the verdict.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "team_failure_profiles.md").write_text("\n".join(L))
    return {"spread": sp.to_dicts(), "stability": st, "predictive": pred, "player": psit, "n_team_seasons": pr.height}


if __name__ == "__main__":
    import json
    r = write()
    print("team-seasons (min60):", r["n_team_seasons"])
    print(json.dumps(r["stability"], indent=1))
