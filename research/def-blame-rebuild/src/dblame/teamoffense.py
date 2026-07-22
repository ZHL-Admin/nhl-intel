"""TEAM OFFENSIVE style from the Phase-3 (defensive-blame) event vocabulary — the symmetric mirror pointed at
the SCORING team (Stage-4 extension; feeds the gtrack F4 team-style visual). Reuses the validated detection
(events2 ledger, rushdef buckets, puckloss turnover location) read-only; does NOT rebuild it.

GOALS-ONLY (LAW 1): describes how a team's goals were built, never what causes goals. Descriptive only.

Offensive-mirror metrics per team-season (over the team's goals-FOR):
  turnover-created (share off a forced turnover the team gained; forecheck deep vs neutral-zone),
  rush-by-TYPE (odd-man share + breakaway/even bucket mix, finer than Stage-4's coarse rush_share),
  transition vs sustained (rush origin share), coverage-EXPLOITED (which defensive failure the goal beat:
  inside-leverage / blown-switch / containment-break).
Same two-bar gate as Stage 4 / F30-F31: STABILITY (split-half odd/even games vs placebo, bar 0.40) AND
DISTINCTIVENESS (between-team spread vs sampling noise, excess ≥1.5). A metric matters only if BOTH.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, events2 as E2, puckloss as PL, rushdef as RD
from .data import universe
from .tracks import TRACKS

COVMAP = {"E1": "containment", "E2": "over_commit", "R3": "inside_lev", "E3": "fail_close", "R6": "fail_close",
          "FTA": "blown_switch", "OUT_OF_ZONE": "blown_switch"}
FORECHECK_DEPTH = 50.0   # a turnover within 50 ft of the defended net = deep o-zone forecheck steal


def goal_labels() -> pl.DataFrame:
    tracked = pl.read_parquet(TRACKS).select("game_id", "event_id", "season").unique()
    u = universe().select("game_id", "event_id", "scoring_team_id", "entry_frame", "goal_frame")
    base = tracked.join(u, on=["game_id", "event_id"], how="inner").with_columns(
        rush=pl.col("entry_frame").is_not_null() & ((pl.col("goal_frame") - pl.col("entry_frame")) <= int(4 * C.HZ)))
    turn = PL._turnovers().select("game_id", "event_id", "turn_depth").with_columns(
        turnover=pl.lit(True), forecheck=pl.col("turn_depth") < FORECHECK_DEPTH)
    bucket = RD._threat_count(RD.rush_universe().select("game_id", "event_id")).select("game_id", "event_id", "bucket")
    rec = pl.read_parquet(E2.REC).filter(pl.col("event_type").is_in(list(COVMAP.keys())))
    covprim = rec.sort("severity", descending=True).group_by("game_id", "event_id").first().select(
        "game_id", "event_id", pl.col("event_type").alias("cov_type"))
    g = (base.join(turn, on=["game_id", "event_id"], how="left")
         .join(bucket, on=["game_id", "event_id"], how="left")
         .join(covprim, on=["game_id", "event_id"], how="left")
         .with_columns(turnover=pl.col("turnover").fill_null(False), forecheck=pl.col("forecheck").fill_null(False),
                       cov_cat=pl.col("cov_type").replace_strict(COVMAP, default=None)))
    return g.with_columns(**{k: e for k, e in _metric_exprs().items()})


def _metric_exprs() -> dict:
    return {
        "_turnover":        pl.col("turnover").cast(pl.Float64),
        "_forecheck_turn":  pl.col("forecheck").cast(pl.Float64),
        "_nz_turn":         (pl.col("turnover") & ~pl.col("forecheck")).cast(pl.Float64),
        "_oddman_rush":     (pl.col("rush") & pl.col("bucket").is_in(["SLIGHTLY", "BADLY"])).cast(pl.Float64),
        "_breakaway":       (pl.col("rush") & (pl.col("bucket") == "BADLY")).cast(pl.Float64),
        "_even_rush":       (pl.col("rush") & (pl.col("bucket") == "EVEN")).cast(pl.Float64),
        "_transition":      pl.col("rush").cast(pl.Float64),
        "_inside_lev_exploit":  (pl.col("cov_cat") == "inside_lev").cast(pl.Float64),
        "_blown_switch_exploit": (pl.col("cov_cat") == "blown_switch").cast(pl.Float64),
        "_containment_break":   (pl.col("cov_cat") == "containment").cast(pl.Float64),
    }


METRICS = [k[1:] for k in _metric_exprs()]   # names without the leading underscore


def profiles(min_n: int = 60) -> pl.DataFrame:
    g = goal_labels()
    return g.group_by(pl.col("scoring_team_id").alias("team"), "season").agg(
        gf=pl.len(), **{m: pl.col(f"_{m}").mean() for m in METRICS}).filter(pl.col("gf") >= min_n)


def _corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")


def gate(min_n: int = 60) -> dict:
    g = goal_labels().sort("scoring_team_id", "season", "game_id").with_columns(
        half=pl.int_range(pl.len()).over("scoring_team_id", "season") % 2)
    tot = g.group_by(pl.col("scoring_team_id").alias("team"), "season").agg(n=pl.len())
    prof = profiles(min_n)
    rng = np.random.RandomState(20260714)   # deterministic placebo
    R = {}
    for m in METRICS:
        half = g.group_by(pl.col("scoring_team_id").alias("team"), "season", "half").agg(v=pl.col(f"_{m}").mean())
        w = half.pivot(values="v", index=["team", "season"], on="half").join(tot, on=["team", "season"]).filter(pl.col("n") >= min_n)
        c0 = [c for c in w.columns if c not in ("team", "season", "n")][0]
        c1 = [c for c in w.columns if c not in ("team", "season", "n")][1]
        s = w.drop_nulls([c0, c1]); a, b = s[c0].to_numpy(), s[c1].to_numpy()
        r = _corr(a, b)
        null = np.array([_corr(a, rng.permutation(b)) for _ in range(2000)])
        p = prof.join(tot, on=["team", "season"], how="left").filter(pl.col("n") >= min_n)
        vals, ns = p[m].to_numpy(), p["n"].to_numpy()
        obs = float(np.var(vals)); samp = float(np.mean(vals * (1 - vals) / ns))
        R[m] = {"n_ts": len(a), "split_half": round(r, 3), "placebo_p": round(float((null >= r).mean()), 4),
                "excess": round(obs / (samp + 1e-12), 2), "league_mean": round(float(np.mean(vals)), 3),
                "both": bool(r >= 0.40 and obs / (samp + 1e-12) >= 1.5)}
    return R


TEAM_ABBR = {1: "NJD", 2: "NYI", 3: "NYR", 4: "PHI", 5: "PIT", 6: "BOS", 7: "BUF", 8: "MTL", 9: "OTT", 10: "TOR",
             12: "CAR", 13: "FLA", 14: "TBL", 15: "WSH", 16: "CHI", 17: "DET", 18: "NSH", 19: "STL", 20: "CGY",
             21: "COL", 22: "EDM", 23: "VAN", 24: "ANA", 25: "DAL", 26: "LAK", 28: "SJS", 29: "CBJ", 30: "MIN",
             52: "WPG", 53: "ARI", 54: "VGK", 55: "SEA", 59: "UTA", 68: "UTA"}


def write() -> dict:
    R = gate()
    prof = profiles()
    L = []; W = L.append
    W("# Team OFFENSIVE style via the Phase-3 defensive-blame vocabulary (mirror; descriptive; nothing promoted)\n")
    W("**LAW 1 · GOALS-ONLY** — describes how a team's goals were built, never what causes goals. The Phase-3 "
      "detection (turnover coupling, rush buckets, coverage ledger) is reused read-only, pointed at the SCORING "
      "team. Two-bar gate (F30/F31 discipline): **STABILITY split-half ≥0.40 AND DISTINCTIVENESS excess ≥1.5.**\n")
    W("**Caution:** these richer events are rarer per team than total goals, so distinctiveness may rise while "
      "stability falls from thinner samples — reported per metric.\n")
    W("## Gate — offensive-mirror metrics (scoring team, ≥60 GF/team-season)\n")
    W("| metric | league mean | n team-seasons | split-half r | placebo p | excess | STABLE | DISTINCT | BOTH |")
    W("|---|---|---|---|---|---|---|---|---|")
    for m in METRICS:
        v = R[m]
        W(f"| {m} | {v['league_mean']} | {v['n_ts']} | **{v['split_half']}** | {v['placebo_p']} | **{v['excess']}** | "
          f"{'Y' if v['split_half'] >= 0.40 else 'n'} | {'Y' if v['excess'] >= 1.5 else 'n'} | {'**YES**' if v['both'] else '—'} |")
    W("\n## Does finer rush-by-TYPE separate teams where Stage-4 coarse rush_share (excess 1.28) did NOT?\n")
    W(f"- coarse transition/rush_share: excess {R['transition']['excess']}, split-half {R['transition']['split_half']}")
    W(f"- finer oddman_rush_share: excess {R['oddman_rush']['excess']}, split-half {R['oddman_rush']['split_half']}")
    W(f"- breakaway_share: excess {R['breakaway']['excess']}, split-half {R['breakaway']['split_half']}")
    W("## Does a transition/turnover vs cycle AXIS emerge stable+distinctive?\n")
    both = [m for m in METRICS if R[m]['both']]
    W(f"- metrics clearing BOTH bars: {both or 'none'}")
    W("\n## Three worked team profiles (FOR, 2025-26)\n")
    lm = prof.filter(pl.col("season") == "2025-26").with_columns(ab=pl.col("team").replace_strict(TEAM_ABBR, default=pl.col("team").cast(pl.Utf8)))
    show = both[:1] + ["turnover", "oddman_rush"] if both else ["turnover", "oddman_rush", "inside_lev_exploit"]
    for pk in [lm.sort("turnover", descending=True).head(1), lm.sort("oddman_rush", descending=True).head(1), lm.sort("inside_lev_exploit", descending=True).head(1)]:
        r = pk.to_dicts()[0]
        W(f"- **{r['ab']}** ({int(r['gf'])} GF): " + ", ".join(f"{m} {r[m]:.2f}" for m in ["turnover", "forecheck_turn", "oddman_rush", "breakaway", "transition", "inside_lev_exploit", "blown_switch_exploit"]))
    W("\n## STOP — owner review. Feeds gtrack F4 team-style visual. Nothing promoted.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "teamoffense_style.md").write_text("\n".join(L))
    return {"gate": R, "both": both}


if __name__ == "__main__":
    import json
    r = write()
    for m in METRICS:
        v = r["gate"][m]
        print(f"  {m:22} split_half {v['split_half']:+.3f} excess {v['excess']:.2f} mean {v['league_mean']:.3f}  {'BOTH' if v['both'] else ''}")
    print("BOTH-bar metrics:", r["both"])
