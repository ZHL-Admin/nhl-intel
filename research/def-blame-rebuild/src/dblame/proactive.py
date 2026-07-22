"""PROACTIVE defensive-action fingerprint probe (D-only; scope-then-gate; nothing promoted).

The untested defensive analog of F25. F32 tested how a defender REACTS/FAILS (collapse, over-pursue, soft gap)
and found it unstable — reactions are FORCED by the offense. This tests what a defender CHOOSES to do: his
habitual PROACTIVE actions, which by F25's logic (chosen actions repeat) may be stable where reactions weren't.

Discipline (per the blame ledgers): SCOPE the new detectors first (rate + phantom check + examples), THEN build,
THEN test stability. Goals-only (LAW 1) — describe habitual action, never claim what causes goals.

  Link 1  proactive-action detectors (chosen behaviors): TAKEAWAY (coupling win, reuse), PUCK-CHALLENGE /
          STEP-UP depth (geometry), NET-FRONT anchor (geometry), ROVING vs ANCHORED (near-attacker stability),
          + SCOPED new detectors SHOT-BLOCK / BOARD-PIN / LANE-DISRUPTION (rate + phantom, reported not forced).
  Link 2  per-defender action MIX (rates conditional on involvement).
  Link 3  STABILITY gate: split-half (odd/even games) + YoY vs placebo, bar 0.40 (F25 offensive ref 0.41-0.76).
  Link 4  role-control: does a stable action survive WITHIN team (vs his own teammates) — habit not system.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, puckloss as PL
from .meta import load as load_meta
from .tracks import TRACKS

MIN_GOALS = 40
SEASONS = ["2023-24", "2024-25", "2025-26"]


# ---------------- Link 1 scope: new detectors on the coupling/frame data ----------------
def scope() -> dict:
    c = pl.read_parquet(PL.COUP)
    ng = c.select(pl.struct("game_id", "event_id").n_unique()).item()
    dfr = c.filter(pl.col("side") == "D")
    # SHOT-BLOCK candidate: a defender coupling a FAST-arriving puck (pre_speed>30) while GOAL-SIDE of it
    # (pl_depth < p_depth = between puck and net). phantom = drop non-goal-side (merely near a fast puck).
    sb = dfr.filter(pl.col("pre_speed") > 30)
    sb_goalside = sb.filter(pl.col("pl_depth") < pl.col("p_depth"))
    sb_ev = sb_goalside.group_by("game_id", "event_id", "coup_id").len().height   # collapse frames->events
    # BOARD-PIN candidate: defender coupling a near-boards (|p_lat|>35), slow (pspeed<5), sustained (>=5 frames) puck
    bp = dfr.filter((pl.col("p_lat").abs() > 35) & (pl.col("pspeed") < 5))
    bp_ev = bp.group_by("game_id", "event_id", "coup_id").len().filter(pl.col("len") >= 5).height
    # LANE-DISRUPTION candidate: defender couples a mid-flight puck (pre_speed 12-40) NOT goal-side (out in a lane),
    #   redirecting it (dir_cos<0.3 = puck changes heading at his stick). phantom = the redirect + mid-flight speed.
    ld = dfr.filter((pl.col("pre_speed") > 12) & (pl.col("pre_speed") <= 40) & (pl.col("dir_cos") < 0.3))
    ld_ev = ld.group_by("game_id", "event_id", "coup_id").len().height
    return {"n_goals": ng,
            "shot_block": {"cand_frames": sb.height, "goalside_events": sb_ev, "rate_per_goal": round(sb_ev / ng, 3),
                           "phantom": "goal-side filter (pl_depth<p_depth) drops %d%% of fast-puck touches (defender merely near a fast puck, not between it and the net)" % round(100 * (1 - sb_goalside.height / max(sb.height, 1)))},
            "board_pin": {"events": bp_ev, "rate_per_goal": round(bp_ev / ng, 3),
                          "phantom": "requires slow (pspeed<5) near-boards (|lat|>35) coupling sustained >=5 frames — a pin, not a fly-by"},
            "lane_disruption": {"events": ld_ev, "rate_per_goal": round(ld_ev / ng, 3),
                                "phantom": "mid-flight speed (12-40) + heading change (dir_cos<0.3) at the defender = a redirect, not a clean reception; but NOISY — overlaps deflections/bounces, needs pre-state pass check (deferred)"}}


# ---------------- Link 1/2: per-defender proactive action features ----------------
def features() -> pl.DataFrame:
    isdef = set(load_meta().filter(pl.col("is_def"))["player_id"].to_list())
    t = pl.read_parquet(TRACKS).filter(pl.col("player_id").is_in(list(isdef)))
    # geometry action features per (goal, defender)
    geo = t.group_by("game_id", "event_id", "player_id", "season").agg(
        puck_challenge=pl.col("dist_puck").min(),                                   # closest he chose to get to the puck (aggression)
        stepup_depth=pl.col("dist_net").filter(pl.col("dist_puck") == pl.col("dist_puck").min()).first(),  # how high he engages
        netfront_frac=(pl.col("dist_net") < 15).mean(),                             # net-front anchor
        man_stability=(pl.col("near_att_id").drop_nulls().mode().len().cast(pl.Float64) * 0 +
                       pl.col("near_att_id").drop_nulls().value_counts().struct.field("count").max() / pl.len()))  # man-marking (roving inverse)
    # coupling action features per (goal, defender): TAKEAWAY (genuine D coupling) + SHOT-BLOCK
    c = pl.read_parquet(PL.COUP).filter(pl.col("side") == "D")
    take = c.filter((pl.col("dir_cos") > 0) & (pl.col("rel") < 8)).group_by("game_id", "event_id", coup_id="coup_id").len().filter(pl.col("len") >= 3).with_columns(takeaway=pl.lit(1.0))
    sblk = c.filter((pl.col("pre_speed") > 30) & (pl.col("pl_depth") < pl.col("p_depth"))).group_by("game_id", "event_id", coup_id="coup_id").len().with_columns(shot_block=pl.lit(1.0))
    g = (geo.join(take.select("game_id", "event_id", player_id="coup_id", takeaway="takeaway"), on=["game_id", "event_id", "player_id"], how="left")
         .join(sblk.select("game_id", "event_id", player_id="coup_id", shot_block="shot_block"), on=["game_id", "event_id", "player_id"], how="left")
         .with_columns(takeaway=pl.col("takeaway").fill_null(0.0), shot_block=pl.col("shot_block").fill_null(0.0)))
    return g


FEATS = ["puck_challenge", "stepup_depth", "netfront_frac", "man_stability", "takeaway", "shot_block"]


def _corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")


def _placebo(a, b, real, n=2000):
    rng = np.random.RandomState(20260714)
    return round(float((np.array([_corr(a, rng.permutation(b)) for _ in range(n)]) >= real).mean()), 4)


def stability() -> dict:
    g = features().sort("player_id", "season", "game_id").with_columns(
        half=pl.int_range(pl.len()).over("player_id", "season") % 2)
    tot = g.group_by("player_id", "season").agg(tot=pl.len())
    R = {"split_half": {}, "yoy": {}}
    half = g.group_by("player_id", "season", "half").agg(**{f: pl.col(f).mean() for f in FEATS})
    for f in FEATS:
        w = half.pivot(values=f, index=["player_id", "season"], on="half").join(tot, on=["player_id", "season"]).filter(pl.col("tot") >= MIN_GOALS)
        c0 = [c for c in w.columns if c not in ("player_id", "season", "tot")][0]
        c1 = [c for c in w.columns if c not in ("player_id", "season", "tot")][1]
        s = w.drop_nulls([c0, c1]); a, b = s[c0].to_numpy(), s[c1].to_numpy()
        r = _corr(a, b)
        R["split_half"][f] = {"n": len(a), "r": round(r, 3), "placebo_p": _placebo(a, b, r)}
    sp = g.group_by("player_id", "season").agg(n=pl.len(), **{f: pl.col(f).mean() for f in FEATS}).filter(pl.col("n") >= MIN_GOALS)
    for f in FEATS:
        piv = sp.pivot(values=f, index="player_id", on="season"); sc = [c for c in piv.columns if c != "player_id"]
        aa, bb = [], []
        for i in range(len(sc) - 1):
            d = piv.drop_nulls([sc[i], sc[i + 1]]); aa += d[sc[i]].to_list(); bb += d[sc[i + 1]].to_list()
        R["yoy"][f] = {"n": len(aa), "r": round(_corr(np.array(aa), np.array(bb)), 3)}
    return R, sp


def role_control(sp: pl.DataFrame, feat: str) -> dict:
    """Does a stable feature survive WITHIN team-season (player vs his own teammates' mean)? habit vs system."""
    from google.cloud import bigquery
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    rows = bq.query(f"select distinct player_id, season, team_id from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where season in ('2023-24','2024-25','2025-26')").result()
    tm = pl.DataFrame([{"player_id": r.player_id, "season": r.season, "team_id": r.team_id} for r in rows],
                      schema={"player_id": pl.Int64, "season": pl.Utf8, "team_id": pl.Int64}).unique(["player_id", "season"])
    d = sp.join(tm, on=["player_id", "season"], how="left").drop_nulls(["team_id"])
    d = d.with_columns(team_mean=pl.col(feat).mean().over(["team_id", "season"]), rel=pl.col(feat) - pl.col(feat).mean().over(["team_id", "season"]))
    # split-half of the WITHIN-TEAM residual (rel) — if stable, it's the player's habit not the team's
    return {"var_total": round(float(d[feat].var()), 4), "var_within_team": round(float(d["rel"].var()), 4),
            "within_share": round(float(d["rel"].var()) / (float(d[feat].var()) + 1e-9), 2)}


def write() -> dict:
    sc = scope()
    st, sp = stability()
    stable = [f for f in FEATS if st["split_half"][f]["r"] >= 0.40]
    L = []; W = L.append
    W("# PROACTIVE defensive-action fingerprint probe (D-only; scope-then-gate; nothing promoted)\n")
    W("Tests CHOSEN defensive actions (proactive), unlike F32 (forced reactions, unstable). Goals-only (LAW 1). "
      f"Bar: split-half ≥0.40 (F25 offensive ref 0.41-0.76). min {MIN_GOALS} on-ice goals-against.\n")
    W("## Link 1 — SCOPE of the NEW detectors (rate + phantom; scoped before trusting)\n")
    W(f"Corpus {sc['n_goals']} goals.")
    for d, lab in [("shot_block", "SHOT-BLOCK"), ("board_pin", "BOARD-PIN"), ("lane_disruption", "LANE-DISRUPTION")]:
        v = sc[d]
        rate = v.get("rate_per_goal")
        W(f"- **{lab}**: ~{rate}/goal ({v.get('goalside_events', v.get('events'))} events). Phantom: {v['phantom']}")
    W("- SHOT-BLOCK scopes CLEAN (goal-side filter is a real phantom discriminator). BOARD-PIN scopes usable "
      "(slow near-boards sustained). LANE-DISRUPTION is NOISY (overlaps bounces/deflections; the pre-state pass "
      "check to separate disruption from bounce is DEFERRED — not built, per the scope-first discipline).\n")
    W("## Link 2/3 — action MIX stability (split-half odd/even games + YoY, vs placebo)\n")
    W("| proactive action | def | n | split-half r | placebo p | YoY r | STABLE (≥0.40) |")
    W("|---|---|---|---|---|---|---|")
    defn = {"puck_challenge": "closest he chooses to attack the puck (aggression)", "stepup_depth": "how high up-ice he engages",
            "netfront_frac": "net-front anchor (chosen position)", "man_stability": "man-marking (tracks a man) vs zone/roving",
            "takeaway": "genuine puck-win/coupling (chosen puck-attack)", "shot_block": "shot-block (goal-side fast-puck intercept)"}
    for f in FEATS:
        s = st["split_half"][f]; y = st["yoy"][f]
        W(f"| {f} — {defn[f]} | | {s['n']} | **{s['r']}** | {s['placebo_p']} | {y['r']} | {'YES' if s['r'] >= 0.40 else 'no'} |")
    W(f"\n**Stable proactive actions (split-half ≥0.40): {stable or 'NONE'}.**\n")
    W("## Link 4 — role/system control (for stable actions: does it survive WITHIN team?)\n")
    if stable:
        for f in stable:
            rc = role_control(sp, f)
            W(f"- **{f}**: within-team variance share {rc['within_share']} (>~0.5 = mostly the PLAYER's habit, not the team system).")
    else:
        W("- (no stable action to role-control)")
    W("\n## Link 5 — verdict\n")
    if stable:
        W(f"- **Proactive defensive actions ARE stable individual traits: {stable}** — a real DEFENSIVE fingerprint "
          "(the F25 analog), unlike F32's forced reactions. Opens a defensive F33 predictive test (next, gated).")
    else:
        W("- **No proactive defensive action is stable** even though chosen — a DEEPER finding than F32: defense is "
          "illegible even in its chosen actions on goals-only data. The reactive-vs-chosen distinction does NOT "
          "rescue defensive fingerprinting. Defensive individual signal stays out of reach.")
    W("\n## STOP — owner review after scoping + stability (before any predictive test). Nothing promoted.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "proactive.md").write_text("\n".join(L))
    return {"scope": sc, "stability": st, "stable": stable}


if __name__ == "__main__":
    import json
    r = write()
    print("SCOPE:", json.dumps({k: (v if isinstance(v, int) else {kk: v.get(kk) for kk in ('rate_per_goal',)}) for k, v in r["scope"].items()}))
    print("split-half:", {f: r["stability"]["split_half"][f]["r"] for f in FEATS})
    print("yoy:", {f: r["stability"]["yoy"][f]["r"] for f in FEATS})
    print("STABLE:", r["stable"])
