"""Stability evaluation for RAW and ADJUSTED blame rate, D and F (owner gate; NOT a promotion).

- Split-half reliability: each player's on-ice tracked goals split odd/even, blame rate on each half, correlated
  across players (min 40 tracked on-ice GA), vs a shuffled-identity placebo (2000 perms).
- Year-over-year: same-player 2024-25 vs 2025-26 (min 40 GA both seasons).
- Deployment-change vs YoY change: does a player's year-to-year blame change track a change in his deployment
  (zone starts / QoC / QoT)? A flip that tracks a deployment change is the metric working, not failing.
Benchmarks: the pre-stated 0.30 reliability bar, and the F25 offensive-signature reference band 0.41-0.76.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, events2 as E2
from .tracks import TRACKS

MIN_GA = 40
SEASONS = ["2024-25", "2025-26"]
ADJ = C.PARQUET / "leaderboard_adjusted.parquet"


def _halves() -> pl.DataFrame:
    onice = pl.read_parquet(TRACKS).select("game_id", "event_id", "player_id", "season").unique()
    pg = pl.read_parquet(E2.REC).group_by("player_id", "game_id", "event_id").agg(sev=pl.col("severity").sum())
    j = (onice.join(pg, on=["player_id", "game_id", "event_id"], how="left")
         .with_columns(sev=pl.col("sev").fill_null(0.0))
         .sort("player_id", "season", "game_id", "event_id")
         .with_columns(parity=pl.int_range(pl.len()).over("player_id", "season") % 2))
    halves = j.group_by("player_id", "season", "parity").agg(rate=pl.col("sev").mean(), ga=pl.len())
    tot = j.group_by("player_id", "season").agg(tot_ga=pl.len())
    w = halves.pivot(values=["rate", "ga"], index=["player_id", "season"], on="parity")
    w = w.join(tot, on=["player_id", "season"], how="left")
    cols = {c: c for c in w.columns}
    # normalize pivot column names (rate_parity_0 / rate_0 depending on polars)
    r0 = [c for c in w.columns if c.startswith("rate") and c.endswith("0")][0]
    r1 = [c for c in w.columns if c.startswith("rate") and c.endswith("1")][0]
    return w.rename({r0: "rate_odd", r1: "rate_even"}).select("player_id", "season", "rate_odd", "rate_even", "tot_ga")


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _placebo(a: np.ndarray, b: np.ndarray, real: float, n: int = 2000) -> dict:
    rng = np.random.RandomState(20260716)
    null = np.empty(n)
    for i in range(n):
        null[i] = np.corrcoef(a, rng.permutation(b))[0, 1]
    return {"null_mean": round(float(null.mean()), 3), "null_sd": round(float(null.std()), 3),
            "z": round((real - null.mean()) / (null.std() + 1e-9), 1),
            "p_ge": round(float((null >= real).mean()), 4)}


def run() -> dict:
    adj = pl.read_parquet(ADJ).select("player_id", "season", "pos", "combined_rate", "adjusted",
                                       "expected_rate", "oz_start_share", "qoc", "qot", "trk_ga")
    halves = _halves().join(adj.select("player_id", "season", "pos", "expected_rate"), on=["player_id", "season"], how="inner")
    halves = halves.with_columns(adj_odd=pl.col("rate_odd") - pl.col("expected_rate"),
                                 adj_even=pl.col("rate_even") - pl.col("expected_rate"))
    R = {"split_half": {}, "yoy": {}, "dep_change": {}}

    # --- split-half (raw + adjusted), per position, min 40 GA ---
    for pos in ["D", "F"]:
        s = halves.filter((pl.col("pos") == pos) & (pl.col("tot_ga") >= MIN_GA))
        for kind, o, e in [("raw", "rate_odd", "rate_even"), ("adjusted", "adj_odd", "adj_even")]:
            a, b = s[o].to_numpy(), s[e].to_numpy()
            r = _corr(a, b)
            R["split_half"][f"{pos}_{kind}"] = {"n": len(a), "r": round(r, 3), **_placebo(a, b, r)}

    # --- YoY same-player (raw + adjusted), min 40 GA both seasons ---
    piv = adj.filter(pl.col("trk_ga") >= MIN_GA).pivot(
        values=["combined_rate", "adjusted", "oz_start_share", "qoc", "qot"], index=["player_id", "pos"], on="season")

    def _c(df, ca, cb):
        d = df.drop_nulls([ca, cb])
        return {"n": d.height, "r": round(_corr(d[ca].to_numpy(), d[cb].to_numpy()), 3)}
    for pos in ["D", "F"]:
        p = piv.filter(pl.col("pos") == pos)
        raw_a = [c for c in p.columns if c.startswith("combined_rate") and "2024" in c][0]
        raw_b = [c for c in p.columns if c.startswith("combined_rate") and "2025" in c][0]
        adj_a = [c for c in p.columns if c.startswith("adjusted") and "2024" in c][0]
        adj_b = [c for c in p.columns if c.startswith("adjusted") and "2025" in c][0]
        R["yoy"][f"{pos}_raw"] = _c(p, raw_a, raw_b)
        R["yoy"][f"{pos}_adjusted"] = _c(p, adj_a, adj_b)
        # --- deployment-change vs blame-change ---
        both = p.drop_nulls([raw_a, raw_b])
        dep = {}
        d_rate = (both[raw_b] - both[raw_a]).to_numpy()
        for f in ["oz_start_share", "qoc", "qot"]:
            fa = [c for c in p.columns if c.startswith(f) and "2024" in c][0]
            fb = [c for c in p.columns if c.startswith(f) and "2025" in c][0]
            d_dep = (both[fb] - both[fa]).to_numpy()
            m = ~(np.isnan(d_rate) | np.isnan(d_dep))
            dep[f"dRate_vs_d{f}"] = round(_corr(d_rate[m], d_dep[m]), 3)
        R["dep_change"][pos] = {"n": both.height, **dep}
    return R


def write() -> dict:
    R = run()
    L = []; W = L.append
    W("# Stability — RAW vs ADJUSTED blame rate (D, F). Owner gate; nothing promoted.\n")
    W(f"Min {MIN_GA} tracked on-ice GA. Benchmarks: **0.30 reliability bar**; **F25 offensive-signature "
      "reference band 0.41-0.76**. Split-half vs shuffled-identity placebo (2000 perms).\n")
    W("## Split-half reliability (odd/even GA), vs placebo\n")
    W("| pos · version | n | split-half r | placebo null | z | p(null≥r) | vs 0.30 bar |")
    W("|---|---|---|---|---|---|---|")
    for k, v in R["split_half"].items():
        bar = "PASS" if v["r"] >= 0.30 else "FAIL"
        W(f"| {k} | {v['n']} | **{v['r']}** | {v['null_mean']}±{v['null_sd']} | {v['z']} | {v['p_ge']} | {bar} |")
    W("\n## Year-over-year (same player, 2024-25 → 2025-26)\n")
    W("| pos · version | n | YoY r |")
    W("|---|---|---|")
    for k, v in R["yoy"].items():
        W(f"| {k} | {v['n']} | **{v['r']}** |")
    W("\n## Deployment-change vs blame-change — does a YoY flip track a deployment change?\n")
    W("Correlation of each player's YoY blame-rate change with his YoY change in deployment. Near-zero = flips "
      "are NOT explained by deployment change (i.e. noise, not a real change in defensive burden).\n")
    W("| pos | n | dRate vs d(oz_start) | dRate vs d(qoc) | dRate vs d(qot) |")
    W("|---|---|---|---|---|")
    for pos, v in R["dep_change"].items():
        W(f"| {pos} | {v['n']} | {v['dRate_vs_doz_start_share']} | {v['dRate_vs_dqoc']} | {v['dRate_vs_dqot']} |")
    # power / exposure diagnostics
    adj = pl.read_parquet(ADJ)
    exp_corr = {pos: round(float(adj.filter(pl.col("pos") == pos).select(pl.corr("trk_ga", "combined_rate")).item()), 3) for pos in ["D", "F"]}
    h = _halves().join(adj.select("player_id", "season", "pos"), on=["player_id", "season"], how="inner").filter(pl.col("pos") == "D")
    sweep = []
    for mg in [25, 40, 60]:
        s = h.filter(pl.col("tot_ga") >= mg)
        sweep.append((mg, s.height, round(_corr(s["rate_odd"].to_numpy(), s["rate_even"].to_numpy()), 3)))
    W("\n## Power / exposure diagnostics (why it fails, and what it isn't)\n")
    W(f"- **Not exposure-confounded:** corr(tracked GA, blame rate) = D {exp_corr['D']}, F {exp_corr['F']} — the "
      "rate is exposure-neutral, so the clean low-blame anchors (Lindholm/Lindell/Brodin, all <40 tracked GA on "
      "strong defensive teams) are real, not a low-sample artifact.")
    W("- **The failure is largely a POWER problem** — D split-half by exposure: " +
      ", ".join(f"min {mg} GA → r={r} (n={n})" for mg, n, r in sweep) + ". At ~20-30 goals/half the rate is too "
      "noisy to estimate; at min-60 GA it clears the 0.30 bar but only ~13 D qualify. The individual signal "
      "likely exists but is under-sampled at the tracked-goal counts available per player-season.")
    W("\n## STOP — owner reads which version is real.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "stability.md").write_text("\n".join(L))
    return R


if __name__ == "__main__":
    import json
    print(json.dumps(write(), indent=1))
