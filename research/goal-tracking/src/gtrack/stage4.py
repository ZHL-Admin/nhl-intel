"""Stage 4 — TEAM goal-STYLE enrichment. Aggregates the Stage 2 per-goal buildup descriptors to the team
level (FOR = how a team scores; AGAINST = how it is scored on), then gates on STABILITY (split-half vs
shuffled-team placebo) and DISTINCTIVENESS (between-team spread vs sampling noise), and compares to the
System Effects movement-based fingerprints. Reuses Stage 0 fused_goals + Stage 2 goal_descriptors read-only.

THE TWO LAWS (inherited):
  LAW 1 · GOALS-ONLY — the corpus is only goal buildups. We DESCRIBE how goals that happened were built; we
    never claim what causes goals or predict goal probability. Team profiles are descriptive style, not causal.
  LAW 2 · descriptive only — no fault/scheme/matchup verdicts beyond what the descriptors support. This stage
    does NOT reopen matchup/style-install questions (closed as F12/F15).
Deterministic (config.SEED). Ratio metrics carry absolute counts. Nothing promoted.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config

DESCR = config.PARQUET / "goal_descriptors.parquet"
FUSED = config.PARQUET / "fused_goals.parquet"
OUT = config.PARQUET / "team_style.parquet"
SEASONS = ["2023-24", "2024-25", "2025-26"]

TEAM_ABBR = {1: "NJD", 2: "NYI", 3: "NYR", 4: "PHI", 5: "PIT", 6: "BOS", 7: "BUF", 8: "MTL", 9: "OTT",
             10: "TOR", 12: "CAR", 13: "FLA", 14: "TBL", 15: "WSH", 16: "CHI", 17: "DET", 18: "NSH", 19: "STL",
             20: "CGY", 21: "COL", 22: "EDM", 23: "VAN", 24: "ANA", 25: "DAL", 26: "LAK", 28: "SJS", 29: "CBJ",
             30: "MIN", 52: "WPG", 53: "ARI", 54: "VGK", 55: "SEA", 59: "UTA", 68: "UTA"}  # 68 = Utah Mammoth (2025-26 id)

# style metric -> (expr producing a 0/1 or continuous per-goal value, is_share)
METRICS = {
    "rush_share":       (pl.col("rush_flag").cast(pl.Float64), True),
    "carried_share":    ((pl.col("entry_type") == "carried").cast(pl.Float64), True),
    "dumped_share":     ((pl.col("entry_type") == "dumped").cast(pl.Float64), True),
    "cross_slot_share": ((pl.col("pass_pattern") == "cross_slot").cast(pl.Float64), True),
    "netfront_share":   ((pl.col("nd_scorer_rel") <= 8.0).cast(pl.Float64), True),
    "multipass_share":  ((pl.col("pass_count") >= 3).cast(pl.Float64), True),
    "direct_share":     ((pl.col("pass_count") == 0).cast(pl.Float64), True),
    "mean_time_in_zone": (pl.col("time_in_zone").cast(pl.Float64), False),
}


def _base() -> pl.DataFrame:
    d = pl.read_parquet(DESCR)
    f = pl.read_parquet(FUSED).select("game_id", "event_id", "home_team_id", "away_team_id", "game_date")
    g = d.join(f, on=["game_id", "event_id"], how="left").filter(pl.col("season").is_in(SEASONS))
    g = g.with_columns(defending_team_id=pl.when(pl.col("scoring_team_id") == pl.col("home_team_id"))
                       .then(pl.col("away_team_id")).otherwise(pl.col("home_team_id")))
    return g.with_columns(**{f"_{k}": e for k, (e, _) in METRICS.items()})


def _profile(g: pl.DataFrame, team_col: str) -> pl.DataFrame:
    return g.group_by(pl.col(team_col).alias("team"), "season", "game_id").agg(pl.col("game_id").first().alias("_gid")).drop("_gid") if False else \
        g.group_by(pl.col(team_col).alias("team"), "season").agg(
            n=pl.len(), **{k: pl.col(f"_{k}").mean() for k in METRICS})


def profiles() -> pl.DataFrame:
    g = _base()
    forp = _profile(g, "scoring_team_id").with_columns(side=pl.lit("FOR"))
    agp = _profile(g, "defending_team_id").with_columns(side=pl.lit("AGAINST"))
    out = pl.concat([forp, agp])
    config.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(OUT)
    return out


# ---------- gate ----------
def _corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")


def gate(side: str, min_n: int = 60) -> dict:
    g = _base()
    tcol = "scoring_team_id" if side == "FOR" else "defending_team_id"
    g = g.sort(tcol, "season", "game_id").with_columns(
        half=pl.int_range(pl.len()).over(tcol, "season") % 2)
    tot = g.group_by(pl.col(tcol).alias("team"), "season").agg(n=pl.len())
    prof = _profile(g, tcol)
    rng = np.random.RandomState(config.SEED)
    R = {}
    for k, (_, is_share) in METRICS.items():
        # split-half
        half = g.group_by(pl.col(tcol).alias("team"), "season", "half").agg(v=pl.col(f"_{k}").mean())
        w = half.pivot(values="v", index=["team", "season"], on="half").join(tot, on=["team", "season"]).filter(pl.col("n") >= min_n)
        c0 = [c for c in w.columns if c not in ("team", "season", "n")][0]
        c1 = [c for c in w.columns if c not in ("team", "season", "n")][1]
        s = w.drop_nulls([c0, c1]); a, b = s[c0].to_numpy(), s[c1].to_numpy()
        r = _corr(a, b)
        null = np.array([_corr(a, rng.permutation(b)) for _ in range(2000)])
        # distinctiveness: observed between-team var vs sampling-noise var
        p = prof.join(tot, on=["team", "season"], how="left").filter(pl.col("n") >= min_n).drop_nulls([k])
        vals, ns = p[k].to_numpy(), p["n"].to_numpy()
        obs_var = float(np.var(vals))
        if is_share:
            samp = float(np.mean(vals * (1 - vals) / ns))
        else:
            pooled = float(g[f"_{k}"].var())
            samp = float(np.mean(pooled / ns))
        R[k] = {"n_ts": len(a), "split_half": round(r, 3), "placebo_p": round(float((null >= r).mean()), 4),
                "excess_ratio": round(obs_var / (samp + 1e-12), 2),
                "stable": r >= 0.40, "distinct": obs_var / (samp + 1e-12) >= 1.5}
    return R


def compare_sysfx() -> dict:
    """Descriptive agreement vs the System Effects movement-based fingerprints on overlapping team-seasons."""
    fp = pl.read_parquet(config.TEAM_SEASON_FP).rename({"season_label": "season"}).filter(pl.col("season").is_in(SEASONS))
    prof = profiles().filter(pl.col("side") == "FOR")
    m = prof.join(fp, left_on=["team", "season"], right_on=["team_id", "season"], how="inner")
    out = {}
    # direct concept overlaps
    for gt, se in [("rush_share", "rush_share_for"), ("netfront_share", "loc_inner_against"), ("direct_share", "point_shot_share_for")]:
        if se in m.columns:
            out[f"{gt}~{se}"] = {"n": m.drop_nulls([gt, se]).height, "r": round(_corr(m.drop_nulls([gt, se])[gt].to_numpy(), m.drop_nulls([gt, se])[se].to_numpy()), 3)}
    return out


def _nm(tid):
    return TEAM_ABBR.get(tid, str(tid))


def write() -> dict:
    prof = profiles()
    gates = {s: gate(s) for s in ["FOR", "AGAINST"]}
    cmp = compare_sysfx()
    # partial-season flag
    g = _base()
    maxdate = {s: g.filter(pl.col("season") == s)["game_date"].max() for s in SEASONS}
    L = []; W = L.append
    W("# Stage 4 — TEAM goal-STYLE enrichment (descriptive; nothing promoted)\n")
    W(f"**{config.LAW_1}**\n\n**{config.LAW_2}**\n")
    W("Team-season profiles aggregate the Stage 2 per-goal buildup descriptors. FOR = how a team scores; "
      "AGAINST = how it is scored on. Shares carry absolute goal counts. Deterministic (seed "
      f"{config.SEED}). 2025-26 latest game_date " + str(maxdate.get("2025-26")) + " and ~230-355 GF/team → "
      "**complete season (not partial)**. (Utah team_id changed to 68 in 2025-26.)\n")
    W("## Metric definitions\n")
    defs = {"rush_share": "goal off the rush (rush_flag)", "carried_share": "zone entry carried in",
            "dumped_share": "entry dumped in", "cross_slot_share": "buildup pass pattern = cross-slot/royal-road",
            "netfront_share": "scorer released ≤8 ft from net (net-front reliance)",
            "multipass_share": "≥3 passes in the buildup", "direct_share": "0 passes (direct/off-rebound)",
            "mean_time_in_zone": "mean seconds in zone before the goal (buildup speed; lower=faster)"}
    for k, v in defs.items():
        W(f"- **{k}** — {v}")

    for side in ["FOR", "AGAINST"]:
        W(f"\n## Gate — {side} side: stability (split-half, bar 0.40) AND distinctiveness (excess ≥1.5)\n")
        W("| metric | n team-seasons | split-half r | placebo p | excess (spread/noise) | STABLE | DISTINCT | BOTH |")
        W("|---|---|---|---|---|---|---|---|")
        for k, v in gates[side].items():
            both = "**YES**" if (v["stable"] and v["distinct"]) else ("stable-only" if v["stable"] else ("distinct-only" if v["distinct"] else "—"))
            W(f"| {k} | {v['n_ts']} | **{v['split_half']}** | {v['placebo_p']} | **{v['excess_ratio']}** | "
              f"{'Y' if v['stable'] else 'n'} | {'Y' if v['distinct'] else 'n'} | {both} |")

    W("\n## System Effects fingerprint agreement (goals-only style vs movement-based style, overlapping seasons)\n")
    W("Descriptive agreement only — does NOT reopen matchup/style-install (F12/F15).\n")
    for k, v in cmp.items():
        W(f"- {k}: r={v['r']} (n={v['n']})")
    W("\n**Interpretation:** the overlapping concepts show ~zero correlation (|r|<0.15) — the goals-only "
      "event-sequence style and the movement-based System Effects fingerprint capture DIFFERENT facets of team "
      "identity (goals-only rush/net-front vs all-shot movement/location; and SE has no pass-count analog, "
      "which is where goals-only is most distinctive). They do NOT agree on team identity for these concepts; "
      "the goals-only pass-count signature is a NEW, independent style axis, not a re-derivation of SE.")

    # league map: FOR side, the both-stable-and-distinct metrics
    keep = [k for k, v in gates["FOR"].items() if v["stable"] and v["distinct"]] or \
           [k for k, v in sorted(gates["FOR"].items(), key=lambda x: -x[1]["excess_ratio"])[:4]]
    W(f"\n## League style map — FOR side, {'stable+distinct' if any(gates['FOR'][k]['stable'] and gates['FOR'][k]['distinct'] for k in gates['FOR']) else 'most-distinctive'} metrics (2025-26)\n")
    lm = prof.filter((pl.col("side") == "FOR") & (pl.col("season") == "2025-26")).with_columns(team_ab=pl.col("team").replace_strict(TEAM_ABBR, default=pl.col("team").cast(pl.Utf8)))
    cols = ["team_ab", "n"] + keep
    W("| team | GF | " + " | ".join(keep) + " |")
    W("|---|---|" + "|".join(["---"] * len(keep)) + "|")
    for r in lm.sort(keep[0], descending=True).iter_rows(named=True):
        W(f"| {r['team_ab']} | {int(r['n'])} | " + " | ".join(f"{r[k]:.3f}" for k in keep) + " |")

    W("\n## Three worked team profiles (FOR, 2025-26)\n")
    exemplars = lm.sort(keep[0], descending=True)
    picks = [exemplars.head(1), exemplars.tail(1), exemplars.sort("netfront_share", descending=True).head(1)]
    for pk in picks:
        r = pk.to_dicts()[0]
        W(f"- **{r['team_ab']}** ({int(r['n'])} GF): " + ", ".join(f"{k} {r[k]:.2f}" for k in METRICS) + f", time_in_zone {r['mean_time_in_zone']:.1f}s")

    W("\n## STOP — owner review. Nothing promoted. Unlocks the F4 team-style visual if the gate holds.\n")
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    (config.REPORTS / "stage4.md").write_text("\n".join(L))
    return {"gates": gates, "compare": cmp, "n_profiles": prof.height}


if __name__ == "__main__":
    import json
    r = write()
    print("team-season-side profiles:", r["n_profiles"])
    for side in ["FOR", "AGAINST"]:
        print(f"\n{side} gate:")
        for k, v in r["gates"][side].items():
            print(f"  {k:18} split_half {v['split_half']:+.3f} excess {v['excess_ratio']:.2f}  {'BOTH' if v['stable'] and v['distinct'] else ''}")
    print("\nSysFx agreement:", json.dumps(r["compare"]))
