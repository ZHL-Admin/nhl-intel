"""Stage 4 sweep — the FULL offensive-style axis space across all 5 dimensions, each through the same two-bar
gate (F30/F31 discipline). Descriptor-based axes use the full goal corpus (Stage 0 fused + Stage 2
descriptors + Stage 1 mechanism_flags, read-only). Phase-3 (defensive-blame) axes (turnover-created,
rush-by-odd-man-bucket, coverage-exploited) are computed in the def-blame `teamoffense` extension on the
tracked-5v5 subset and are CARRIED here for the synthesis (different, thinner sample — flagged).

LAW 1 · GOALS-ONLY: describes how a team's goals were built, never what causes goals. Descriptive only.
Gate: STABILITY split-half (odd/even games) vs shuffled-team placebo, bar 0.40; DISTINCTIVENESS excess
(between-team var / sampling-noise var), bar 1.5. An axis is a real identity ONLY if it clears BOTH.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config
from .stage4 import TEAM_ABBR

D = config.PARQUET / "goal_descriptors.parquet"
F = config.PARQUET / "fused_goals.parquet"
MF = config.PARQUET / "mechanism_flags.parquet"
SEASONS = ["2023-24", "2024-25", "2025-26"]

FACEOFF_WINDOW = 10   # a goal within this many seconds of winning an o-zone faceoff = faceoff-origin

# per-goal metric expr + is_share + dimension
AXES = {
    # DIM 1 ORIGIN (descriptor side; turnover/rush-by-type are Phase-3, carried below)
    "sustained_share":   (pl.col("rush_flag").not_().cast(pl.Float64), True, "ORIGIN"),
    "rebound_share":     (pl.col("SECOND_CHANCE").cast(pl.Float64), True, "ORIGIN"),
    "faceoff_origin":    (pl.col("faceoff_origin").cast(pl.Float64), True, "ORIGIN"),
    # DIM 2 ENTRY QUALITY
    "carried_entry":     ((pl.col("entry_type") == "carried").cast(pl.Float64), True, "ENTRY"),
    "dumped_entry":      ((pl.col("entry_type") == "dumped").cast(pl.Float64), True, "ENTRY"),
    "passed_entry":      ((pl.col("entry_type") == "passed").cast(pl.Float64), True, "ENTRY"),
    # DIM 3 ZONE-MOVEMENT SHAPE
    "multipass":         ((pl.col("pass_count") >= 3).cast(pl.Float64), True, "SHAPE"),
    "direct":            ((pl.col("pass_count") == 0).cast(pl.Float64), True, "SHAPE"),
    "point_involve":     (pl.col("pass_pattern").is_in(["point_to_net", "low_to_high_to_net"]).cast(pl.Float64), True, "SHAPE"),
    "east_west":         (pl.col("EAST_WEST").cast(pl.Float64), True, "SHAPE"),
    # DIM 4 FINISH
    "netfront_finish":   ((pl.col("nd_scorer_rel") <= 8).cast(pl.Float64), True, "FINISH"),
    "slot_finish":       (((pl.col("nd_scorer_rel") > 8) & (pl.col("nd_scorer_rel") <= 20)).cast(pl.Float64), True, "FINISH"),
    "point_finish":      ((pl.col("nd_scorer_rel") > 25).cast(pl.Float64), True, "FINISH"),
    "cross_slot":        ((pl.col("pass_pattern") == "cross_slot").cast(pl.Float64), True, "FINISH"),
    # DIM 5 TEMPO
    "buildup_speed":     (pl.col("time_in_zone").cast(pl.Float64), False, "TEMPO"),
    "shot_quickness":    (((pl.col("release_frame") - pl.col("entry_frame")) / 10.0).cast(pl.Float64), False, "TEMPO"),
}

# Phase-3 axes carried from def-blame teamoffense (tracked-5v5, ~120 GF/team-season; thinner sample)
PHASE3 = {
    "turnover_created (ORIGIN)":     {"split": 0.225, "excess": 1.88},
    "forecheck_turnover (ORIGIN)":   {"split": 0.178, "excess": 1.32},
    "nz_turnover (ORIGIN)":          {"split": 0.319, "excess": 1.76},
    "oddman_rush (ORIGIN)":          {"split": 0.086, "excess": 0.98},
    "breakaway_rush (ORIGIN)":       {"split": 0.251, "excess": 1.26},
    "inside_lev_exploit (SHAPE)":    {"split": 0.207, "excess": 2.07},
    "blown_switch_exploit (FINISH)": {"split": 0.260, "excess": 2.24},
}


def _faceoff_origin() -> pl.DataFrame:
    """Per goal: did it come within FACEOFF_WINDOW s of the scoring team WINNING an offensive-zone faceoff?
    zone_code is relative to the winner, so o-zone win = event_owner_team_id==winner & zone_code=='O'.
    Combines the goal corpus with pbp faceoffs (not in the tracking json, per owner). Cached."""
    from . import bq
    sql = ("select game_id, period_number, time_in_period, event_owner_team_id as winner "
           f"from `{config.__dict__.get('BQ_PROJECT', 'nhl-intel-498216')}.nhl_staging.stg_play_by_play` "
           "where type_desc_key='faceoff' and zone_code='O' and season in ('2023-24','2024-25','2025-26')")
    fo = bq.cached_query("ozone_faceoffs", sql).with_columns(
        fo_elapsed=pl.col("time_in_period").str.split(":").list.eval(pl.element().cast(pl.Int64)).list.eval(
            pl.element().first() * 60 + pl.element().last()).list.first()).rename({"period_number": "period"})
    f = pl.read_parquet(F).filter(pl.col("season").is_in(SEASONS)).select(
        "game_id", "event_id", "period", "game_clock_seconds", "scoring_team_id").with_columns(
        g_elapsed=1200 - pl.col("game_clock_seconds"))
    j = f.join(fo.select("game_id", "period", "winner", "fo_elapsed"), on=["game_id", "period"], how="left")
    j = j.with_columns(hit=((pl.col("winner") == pl.col("scoring_team_id")) & (pl.col("fo_elapsed") <= pl.col("g_elapsed"))
                            & ((pl.col("g_elapsed") - pl.col("fo_elapsed")) <= FACEOFF_WINDOW)).fill_null(False))
    return j.group_by("game_id", "event_id").agg(faceoff_origin=pl.col("hit").any())


def _base() -> pl.DataFrame:
    d = pl.read_parquet(D).filter(pl.col("season").is_in(SEASONS))
    f = pl.read_parquet(F).select("game_id", "event_id", "ew_disp_2s", "entry_frame", "release_frame", "scorer_id")
    mf = pl.read_parquet(MF).select("game_id", "event_id", "SECOND_CHANCE", "EAST_WEST")
    g = (d.join(f, on=["game_id", "event_id"], how="left").join(mf, on=["game_id", "event_id"], how="left")
         .join(_faceoff_origin(), on=["game_id", "event_id"], how="left")
         .with_columns(faceoff_origin=pl.col("faceoff_origin").fill_null(False)))
    return g.with_columns(**{f"_{k}": e for k, (e, _, _) in AXES.items()})


def _corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")


def gate(min_n: int = 60) -> dict:
    g = _base().sort("scoring_team_id", "season", "game_id").with_columns(
        half=pl.int_range(pl.len()).over("scoring_team_id", "season") % 2)
    tot = g.group_by(pl.col("scoring_team_id").alias("team"), "season").agg(n=pl.len())
    prof = g.group_by(pl.col("scoring_team_id").alias("team"), "season").agg(
        n=pl.len(), **{k: pl.col(f"_{k}").mean() for k in AXES}).filter(pl.col("n") >= min_n)
    rng = np.random.RandomState(config.SEED)
    R = {}
    for k, (_, is_share, dim) in AXES.items():
        half = g.group_by(pl.col("scoring_team_id").alias("team"), "season", "half").agg(v=pl.col(f"_{k}").mean())
        w = half.pivot(values="v", index=["team", "season"], on="half").join(tot, on=["team", "season"]).filter(pl.col("n") >= min_n)
        c0 = [c for c in w.columns if c not in ("team", "season", "n")][0]
        c1 = [c for c in w.columns if c not in ("team", "season", "n")][1]
        s = w.drop_nulls([c0, c1]); a, b = s[c0].to_numpy(), s[c1].to_numpy()
        r = _corr(a, b)
        null = np.array([_corr(a, rng.permutation(b)) for _ in range(2000)])
        p = prof.drop_nulls([k]); vals, ns = p[k].to_numpy(), p["n"].to_numpy()
        obs = float(np.var(vals))
        samp = float(np.mean(vals * (1 - vals) / ns)) if is_share else float(np.mean(g[f"_{k}"].var() / ns))
        R[k] = {"dim": dim, "n_ts": len(a), "split": round(r, 3), "placebo_p": round(float((null >= r).mean()), 4),
                "excess": round(obs / (samp + 1e-12), 2), "mean": round(float(np.mean(vals)), 3),
                "both": bool(r >= 0.40 and obs / (samp + 1e-12) >= 1.5)}
    # scorer concentration (HHI): separate — split-half + bootstrap sampling noise
    R["scorer_hhi"] = _hhi_gate(min_n)
    return R


def _hhi_gate(min_n: int) -> dict:
    g = _base().sort("scoring_team_id", "season", "game_id").with_columns(
        gi=pl.int_range(pl.len()).over("scoring_team_id", "season"))
    g = g.with_columns(half=pl.col("gi") % 2)

    def hhi(df, grp):
        sc = df.group_by(*grp, "scorer_id").agg(c=pl.len())
        tot = sc.group_by(*grp).agg(t=pl.col("c").sum())
        return sc.join(tot, on=grp).with_columns(sh2=(pl.col("c") / pl.col("t")) ** 2).group_by(*grp).agg(hhi=pl.col("sh2").sum(), n=pl.col("c").sum())
    full = hhi(g, ["scoring_team_id", "season"]).filter(pl.col("n") >= min_n)
    h0 = hhi(g.filter(pl.col("half") == 0), ["scoring_team_id", "season"]).rename({"hhi": "h0"}).drop("n")
    h1 = hhi(g.filter(pl.col("half") == 1), ["scoring_team_id", "season"]).rename({"hhi": "h1"}).drop("n")
    w = h0.join(h1, on=["scoring_team_id", "season"]).join(full.select("scoring_team_id", "season", "n"), on=["scoring_team_id", "season"]).filter(pl.col("n") >= min_n)
    r = _corr(w["h0"].to_numpy(), w["h1"].to_numpy())
    # bootstrap sampling noise of HHI per team
    rng = np.random.RandomState(config.SEED)
    obs = float(np.var(full["hhi"].to_numpy()))
    samps = []
    scdist = g.group_by("scoring_team_id", "season", "scorer_id").agg(c=pl.len())
    for row in full.iter_rows(named=True):
        sub = scdist.filter((pl.col("scoring_team_id") == row["scoring_team_id"]) & (pl.col("season") == row["season"]))
        probs = (sub["c"] / sub["c"].sum()).to_numpy(); n = int(row["n"]); boot = []
        for _ in range(200):
            draw = rng.multinomial(n, probs) / n
            boot.append(float((draw ** 2).sum()))
        samps.append(float(np.var(boot)))
    excess = obs / (float(np.mean(samps)) + 1e-12)
    return {"dim": "FINISH", "n_ts": w.height, "split": round(r, 3), "placebo_p": None,
            "excess": round(excess, 2), "mean": round(float(full["hhi"].mean()), 3),
            "both": bool(r >= 0.40 and excess >= 1.5)}


def write() -> dict:
    R = gate()
    prof = _base().group_by(pl.col("scoring_team_id").alias("team"), "season").agg(
        gf=pl.len(), **{k: pl.col(f"_{k}").mean() for k in AXES}).filter((pl.col("gf") >= 60) & (pl.col("season") == "2025-26"))
    L = []; W = L.append
    W("# Stage 4 sweep — FULL offensive-style axis space, two-bar gate (descriptive; nothing promoted)\n")
    W(f"**{config.LAW_1}**\n\nGate: STABILITY split-half ≥0.40 AND DISTINCTIVENESS excess ≥1.5 — an axis is a "
      f"real team-style identity ONLY if it clears BOTH. Full goal corpus (~270 GF/team-season); seed {config.SEED}.\n")
    W("**faceoff-origin now COMPUTED** by combining the goal corpus with pbp faceoffs (not in the tracking json "
      "but in stg_play_by_play, per owner): goal within 10 s of the scoring team winning an o-zone faceoff "
      f"(zone_code relative to winner). League share ~5.7% — rare, so a thin per-team sample (~16 goals/team-season).\n")
    W("## Gate by dimension (FOR side)\n")
    W("| dim | axis | mean | n_ts | split-half r | placebo p | excess | STABLE | DISTINCT | BOTH |")
    W("|---|---|---|---|---|---|---|---|---|---|")
    order = ["ORIGIN", "ENTRY", "SHAPE", "FINISH", "TEMPO"]
    for dim in order:
        for k, v in R.items():
            if v["dim"] != dim:
                continue
            W(f"| {dim} | {k} | {v['mean']} | {v['n_ts']} | **{v['split']}** | {v.get('placebo_p')} | **{v['excess']}** | "
              f"{'Y' if v['split'] >= 0.40 else 'n'} | {'Y' if v['excess'] >= 1.5 else 'n'} | {'**YES**' if v['both'] else '—'} |")
    W("\n## Phase-3 (def-blame) axes — CARRIED from teamoffense (tracked-5v5, ~120 GF/team-season; thinner, flagged)\n")
    W("| axis | split-half r | excess | BOTH |")
    W("|---|---|---|---|")
    for k, v in PHASE3.items():
        W(f"| {k} | {v['split']} | {v['excess']} | {'YES' if v['split'] >= 0.40 and v['excess'] >= 1.5 else '—'} |")

    both = [k for k, v in R.items() if v["both"]]
    W(f"\n## Synthesis — axes clearing BOTH bars = the real team-offensive-identity dimensions\n")
    W(f"- **BOTH-bar axes: {both or 'ONLY pass-count (multipass/direct)'}**")
    stable_uniform = [k for k, v in R.items() if v["split"] >= 0.40 and v["excess"] < 1.5]
    distinct_noisy = [k for k, v in R.items() if v["split"] < 0.40 and v["excess"] >= 1.5]
    W(f"- stable-but-uniform (F30-style): {stable_uniform or 'none'}")
    W(f"- distinctive-but-noisy (thin sample / game-to-game noise): {distinct_noisy or 'none'}")
    W("\n## Three worked team profiles (FOR, 2025-26)\n")
    prof = prof.with_columns(ab=pl.col("team").replace_strict(TEAM_ABBR, default=pl.col("team").cast(pl.Utf8)))
    keyaxes = (both or ["multipass"]) + ["netfront_finish", "point_involve", "rebound_share", "buildup_speed"]
    keyaxes = list(dict.fromkeys(keyaxes))
    for pk in [prof.sort("multipass", descending=True).head(1), prof.sort("direct", descending=True).head(1), prof.sort("netfront_finish", descending=True).head(1)]:
        r = pk.to_dicts()[0]
        W(f"- **{r['ab']}** ({int(r['gf'])} GF): " + ", ".join(f"{k} {r[k]:.2f}" for k in keyaxes if k in r))
    W("\n## STOP — owner review. Feeds F4 team-style visual. Nothing promoted.\n")
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    (config.REPORTS / "stage4_sweep.md").write_text("\n".join(L))
    return {"gate": R, "both": both, "stable_uniform": stable_uniform, "distinct_noisy": distinct_noisy}


if __name__ == "__main__":
    r = write()
    for dim in ["ORIGIN", "ENTRY", "SHAPE", "FINISH", "TEMPO"]:
        for k, v in r["gate"].items():
            if v["dim"] == dim:
                print(f"  {dim:7} {k:16} split {v['split']:+.3f} excess {v['excess']:.2f}  {'BOTH' if v['both'] else ''}")
    print("\nBOTH-bar axes:", r["both"])
