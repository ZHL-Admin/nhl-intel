"""Link 1 rev2 iter2 · TWO-LEDGER assignment (R1-R7, owner iteration 2026-07-15).

Two separate ledgers, never combined in this probe:
  PUCK-LOSS ledger : E4 turnover-into-danger (from the reality-gated possession layer; goalie eligible).
  COVERAGE ledger  : E1 containment, E3 failure-to-close, R3 inside-leverage, R6 soft-close on the passer,
                     out-of-zone (direct firing), R5 upstream root-cause split, E2 over-commitment (re-cut).

Rules applied: scramble discount x0.5 on coverage events after the possession flip on turnover-origin
goals; per-player cap 1.0 per ledger per goal; E1/E2 mutually exclusive (E2 suppressed if E1 on the same
player); non-overlapping stacking (overlapping windows keep the max, do not sum) — the Dewar fix; R6 keyed
on the final OR penultimate pre-goal passer with a p60-calibrated unpressured threshold.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, zonemap as Z
from .data import universe
from .meta import load as load_meta
from .possession import TURN, PASSES
from .tracks import TRACKS

REC = C.PARQUET / "blame2.parquet"
FA_FR = int(C.FINAL_APPROACH_S * C.HZ)
MANAGE_FR = int(C.MANAGE_MIN_S * C.HZ)
NETFRONT_DEPTH = 20.0
CLOSE = 10.0
OOP_SEVERE = 1.0        # graded out-of-zone weight considered "severe"
VACATE_NEAR = 18.0      # ft: the vacated expected-zone center is "where the goal was produced"


def _framestate() -> pl.DataFrame:
    t = pl.read_parquet(TRACKS)
    u = universe().select("game_id", "event_id", "attack_sign", "goal_frame", "start_frame", "entry_frame")
    t = t.join(u, on=["game_id", "event_id"], how="inner")
    meta = load_meta().select("player_id", "is_def")
    t = t.join(meta, on="player_id", how="left").with_columns(pl.col("is_def").fill_null(False))
    t = t.with_columns(depth=89.0 - pl.col("attack_sign") * pl.col("def_x"), lat=pl.col("attack_sign") * pl.col("def_y"))
    ml = t.group_by("game_id", "event_id", "player_id", "is_def").agg(mean_lat=pl.col("lat").mean())
    roles = Z.assign_roles(ml)
    t = t.join(roles, on=["game_id", "event_id", "player_id"], how="left")
    from .possession import PUCK
    t = t.join(pl.read_parquet(PUCK), on=["game_id", "event_id", "frame_index"], how="left")
    ec_lat, ec_depth = Z.expected_centers_vec(t["p_lat"].fill_null(0).to_numpy(), t["p_depth"].fill_null(100).to_numpy(),
                                              t["role"].fill_null("C").to_numpy())
    dcenter = np.sqrt((t["lat"].to_numpy() - ec_lat) ** 2 + (t["depth"].to_numpy() - ec_depth) ** 2)
    entry_recent = ((t["entry_frame"].is_not_null()) & (t["frame_index"] - t["entry_frame"].fill_null(-999) <= int(4 * C.HZ))
                    & (t["frame_index"] >= t["entry_frame"].fill_null(-999))).to_numpy()
    oop = Z.oop_weight(dcenter, t["p_depth"].fill_null(100).to_numpy(), np.zeros(t.height, bool), entry_recent, np.zeros(t.height, bool))
    return t.with_columns(ec_lat=pl.Series(ec_lat), ec_depth=pl.Series(ec_depth), oop=pl.Series(oop),
                          fa=pl.col("frame_index") > (pl.col("goal_frame") - FA_FR))


def _perdef(fs):
    over = ["game_id", "event_id", "frame_index"]
    fs = fs.with_columns(near_scorer=pl.col("dist_scorer") == pl.col("dist_scorer").min().over(over),
                         near_slot=pl.col("dist_slot") == pl.col("dist_slot").min().over(over),
                         near_ast1=pl.col("dist_assist1") == pl.col("dist_assist1").min().over(over))
    early = ~pl.col("fa")
    return fs.sort(["game_id", "event_id", "player_id", "frame_index"]).group_by("game_id", "event_id", "player_id").agg(
        is_def=pl.col("is_def").first(), n_fa=pl.col("fa").sum(),
        man_s=(early & pl.col("near_scorer") & pl.col("scorer_goal_side")).sum(),
        msep_s=pl.col("dist_scorer").filter(early & pl.col("near_scorer") & pl.col("scorer_goal_side")).median(),
        fsep_s=pl.col("dist_scorer").filter(pl.col("fa")).median(),
        dsc_goal=pl.col("dist_scorer").filter(pl.col("fa")).last(),
        dsc_fa_start=pl.col("dist_scorer").filter(pl.col("fa")).first(),
        min_dsc_fa=pl.col("dist_scorer").filter(pl.col("fa")).min(),          # closest he ever got (FTA "never closed")
        def_lat_g=pl.col("lat").filter(pl.col("fa")).last(),                  # his position at the shot (FTA abandonment)
        def_depth_g=pl.col("depth").filter(pl.col("fa")).last(),
        sc_goalside_goal=pl.col("scorer_goal_side").filter(pl.col("fa")).last(),
        fa_near_scorer=(pl.col("fa") & pl.col("near_scorer")).sum(),
        min_dast1=pl.col("dist_assist1").min(), dast1_fa=pl.col("dist_assist1").filter(pl.col("fa")).median(),
        fa_near_ast1=(pl.col("fa") & pl.col("near_ast1")).sum(),
        puck_early=pl.col("dist_puck").filter(early).median(), puck_fa=pl.col("dist_puck").filter(pl.col("fa")).median(),
        slot_early=pl.col("dist_slot").filter(early).median(), slot_fa=pl.col("dist_slot").filter(pl.col("fa")).median(),
        near_slot_early=(early & pl.col("near_slot")).sum(),
        oop_fa=pl.col("oop").filter(pl.col("fa")).mean(), oop_max=pl.col("oop").max(),
        oop_sustained=(pl.col("oop") >= 1.5).sum(),      # frames severely out of zone (transient pinch counts)
        ec_lat_goal=pl.col("ec_lat").filter(pl.col("fa")).last(), ec_depth_goal=pl.col("ec_depth").filter(pl.col("fa")).last(),
        near_atk_fa=pl.col("dist_near_atk").filter(pl.col("fa")).median())


def _c01(x):
    return float(np.clip(x, 0.0, 1.0))


def build() -> dict:
    fs = _framestate()
    # DETERMINISM: _perdef's group_by does not preserve order, so g's row order (and thus recs order, the
    # oz_players last-write-wins, and the cap-loop maintain_order capture) would vary run-to-run and flip
    # R3<->OUT_OF_ZONE keep-max ties. Pin a stable row order here so the whole build is reproducible.
    g = _perdef(fs).sort(["game_id", "event_id", "player_id"]).to_pandas()
    u = universe().select("game_id", "event_id", "scorer_id", "assist1_id", "net_x", "attack_sign",
                          "entry_frame", "goal_frame", "entry_type").to_pandas()
    g = g.merge(u, on=["game_id", "event_id"], how="left")
    rel = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "release_x", "release_y", "nd_scorer_rel").to_pandas()
    g = g.merge(rel, on=["game_id", "event_id"], how="left")
    g["scorer_depth"] = 89.0 - g["attack_sign"] * g["release_x"]
    g["scorer_lat"] = g["attack_sign"] * g["release_y"]
    g["frac_near"] = g["fa_near_scorer"] / g["n_fa"].clip(lower=1)
    turn = pl.read_parquet(TURN).to_pandas()
    flip = dict(zip(zip(turn.game_id, turn.event_id), turn.flip_frame))
    gf = universe().select("game_id", "event_id", "goal_frame").to_pandas()
    gfmap = dict(zip(zip(gf.game_id, gf.event_id), gf.goal_frame))

    recs = []   # game_id, event_id, player_id, ledger, event_type, severity, w0, w1

    def add(i, ledger, etype, sev, w0, w1):
        if sev > 0:
            recs.append([g.game_id[i], g.event_id[i], g.player_id[i], ledger, etype, float(sev), int(w0), int(w1)])

    # ---- PUCK-LOSS ledger: coupling-based TURNOVER (rebuilt; replaces the old proximity E4) ----
    # Coverage ledger below is FROZEN and unchanged; only the puck-loss source is swapped.
    from . import puckloss as PLOSS
    recs.extend(PLOSS.turnover_records())
    # ---- PUCK-LOSS ledger: bucket-based RUSH_DEFENSE (owner-approved 2026-07-16, integrated) ----
    # Clean rushes carry fault by bucket ceiling x 0.85 rush discount; turnover-rushes route primary to the
    # giveaway (already added above) and rush-defense is x0.25; contest gate + forward x0.65 preserved.
    from . import rushdef as RUSHDEF
    recs.extend(RUSHDEF.rush_records())

    # ---- COVERAGE ledger ----
    growth = g["fsep_s"] - g["msep_s"]
    mask = g["man_s"] >= MANAGE_FR
    gthr, gp95 = np.nanquantile(growth[mask], .80), np.nanquantile(growth[mask], .95)
    e1_fire = mask & (growth >= gthr)
    e1_players = set()
    for i in np.where(e1_fire.values)[0]:
        add(i, "COVERAGE", "E1", _c01((growth.values[i] - gthr) / (gp95 - gthr + 1e-9)),
            g.game_id[i], gfmap.get((g.game_id[i], g.event_id[i]), 0))     # E1 window ~ whole approach
        e1_players.add((g.game_id[i], g.event_id[i], g.player_id[i]))

    netfront = g["scorer_depth"] < NETFRONT_DEPTH
    near_final = g["fa_near_scorer"] / g["n_fa"].clip(lower=1) >= 0.5
    r3 = netfront & near_final & (g["dsc_goal"] <= CLOSE) & (~g["sc_goalside_goal"].astype(bool))
    for i in np.where(r3.fillna(False).values)[0]:
        gg = gfmap.get((g.game_id[i], g.event_id[i]), 0)
        add(i, "COVERAGE", "R3", _c01((CLOSE - g["dsc_goal"].values[i]) / CLOSE), gg - FA_FR, gg)

    # FAILURE-TO-ACCOUNT: the sustained-nearest defender to an OPEN scorer in dangerous ice, who never
    # closed (gap never below a contest distance) AND collapsed INSIDE his man (abandonment) — the class the
    # #20 diagnostic surfaced. The abandonment condition is what keeps this off the tautological 24.6% of
    # goals (an open slot man nobody contested) and down to ~2.4%. Severity scales with the abandonment
    # margin x the scorer's openness (a marginal collapse near the thresholds scores low), never binary.
    sn = g["frac_near"] >= 0.5
    P_OPEN_FTA = np.nanquantile(g["nd_scorer_rel"].dropna(), 0.60)
    open_p95 = np.nanquantile(g["nd_scorer_rel"].dropna(), 0.95)
    CONTEST = np.nanquantile(g["min_dsc_fa"][sn].dropna(), 0.60)
    lat_excess = g["scorer_lat"].abs() - g["def_lat_g"].abs() - 3.0       # collapsed more central than his man
    depth_excess = g["scorer_depth"] - g["def_depth_g"] - 3.0             # collapsed deeper / nearer the net
    collapsed_inside = (lat_excess > 0) & (depth_excess > 0)
    # RUSH GUARD (owner ruling): on a fresh rush the scorer being open is unsettled transition, not a
    # coverage-account failure — route it to the out-of-position / turnover logic instead. Suppress FTA when
    # the zone entry was within the last 4s (R1's entry-modifier window). #20's goal is off_frame_start
    # (settled zone, entry_frame null) so it is unaffected.
    rush_unsettled = g["entry_frame"].notna() & ((g["goal_frame"] - g["entry_frame"]) <= int(4 * C.HZ))
    fta_base = (sn & (g["nd_scorer_rel"] >= P_OPEN_FTA) & (g["scorer_depth"] <= 40) & (g["scorer_lat"].abs() <= 25)
                & (g["min_dsc_fa"] >= CONTEST) & collapsed_inside & (~e1_fire.fillna(False)) & (~r3.fillna(False)))
    fta = fta_base & (~rush_unsettled)                 # fires (settled)
    fta_suppressed = fta_base & rush_unsettled         # would fire but the rush-guard suppressed it (fresh rush)
    # side sets for the FTA / rush-guard cold blind sampling (additive; identical fta -> ledger unchanged)
    _fs = [(g.game_id[i], g.event_id[i], g.player_id[i], "fired") for i in np.where(fta.fillna(False).values)[0]] \
        + [(g.game_id[i], g.event_id[i], g.player_id[i], "suppressed") for i in np.where(fta_suppressed.fillna(False).values)[0]]
    pl.DataFrame(_fs, schema=["game_id", "event_id", "player_id", "kind"], orient="row").write_parquet(C.PARQUET / "fta_sets.parquet")
    comb = lat_excess + depth_excess
    comb_p90 = np.nanquantile(comb[fta].dropna(), 0.90) if fta.any() else 1.0
    for i in np.where(fta.fillna(False).values)[0]:
        abandon = _c01(comb.values[i] / (comb_p90 + 1e-9))
        open_s = _c01((g["nd_scorer_rel"].values[i] - P_OPEN_FTA) / (open_p95 - P_OPEN_FTA + 1e-9))
        gg = gfmap.get((g.game_id[i], g.event_id[i]), 0)
        add(i, "COVERAGE", "FTA", abandon * open_s, gg - FA_FR, gg)

    openq = np.nanquantile(g["dsc_goal"], .80); e3p95 = np.nanquantile(g["dsc_goal"], .95)
    e3 = near_final & (g["dsc_goal"] >= openq) & (g["dsc_goal"] - g["dsc_fa_start"] >= 0) & (g["man_s"] < MANAGE_FR)
    for i in np.where(e3.fillna(False).values)[0]:
        gg = gfmap.get((g.game_id[i], g.event_id[i]), 0)
        add(i, "COVERAGE", "E3", _c01((g["dsc_goal"].values[i] - openq) / (e3p95 - openq + 1e-9)), gg - FA_FR, gg)

    # R6 soft-close on the passer (assist1 = final-pass completer; penultimate not tracked — logged as blind spot)
    pthr = np.nanquantile(g["dast1_fa"].dropna(), .60); pp95 = np.nanquantile(g["dast1_fa"].dropna(), .95)
    near_ast = g["fa_near_ast1"] / g["n_fa"].clip(lower=1) >= 0.4
    r6 = g["assist1_id"].notna() & near_ast & (g["dast1_fa"] >= pthr)
    for i in np.where(r6.fillna(False).values)[0]:
        gg = gfmap.get((g.game_id[i], g.event_id[i]), 0)
        add(i, "COVERAGE", "R6", _c01((g["dast1_fa"].values[i] - pthr) / (pp95 - pthr + 1e-9)), gg - 30, gg - 10)

    # E2 over-commitment — RE-CUT: net-front anchored, chased the puck, vacated into the goal, AND no E1 on him
    pursuit = g["puck_early"] - g["puck_fa"]; vacate = g["slot_fa"] - g["slot_early"]
    pursuers = (pursuit > 0) & (g["near_slot_early"] > 0)
    vq, vp95 = np.nanquantile(vacate[pursuers], .80), np.nanquantile(vacate[pursuers], .95)
    e2 = pursuers & (vacate >= vq) & (g["scorer_depth"] < NETFRONT_DEPTH)
    for i in np.where(e2.fillna(False).values)[0]:
        if (g.game_id[i], g.event_id[i], g.player_id[i]) in e1_players:   # E1/E2 mutually exclusive (Dewar fix)
            continue
        gg = gfmap.get((g.game_id[i], g.event_id[i]), 0)
        add(i, "COVERAGE", "E2", _c01((vacate.values[i] - vq) / (vp95 - vq + 1e-9)), g.game_id[i], gg)

    # OUT-OF-ZONE direct event: a SEVERE, SUSTAINED out-of-zone excursion (peak, not mean — a transient
    # over-pinch counts) whose vacated zone is where the goal was produced.
    vac_to_goal = np.sqrt((g["ec_lat_goal"] - g["scorer_lat"]) ** 2 + (g["ec_depth_goal"] - g["scorer_depth"]) ** 2)
    oz = g["is_def"] & (g["oop_max"] >= 2.0) & (g["oop_sustained"] >= 8) & (vac_to_goal <= 15.0)  # a defenseman's severe, sustained over-pinch into the goal area
    oz_p99 = np.nanquantile(g["oop_max"].dropna(), .99)
    oz_players = {}
    for i in np.where(oz.fillna(False).values)[0]:
        gg = gfmap.get((g.game_id[i], g.event_id[i]), 0)
        sev = _c01(g["oop_max"].values[i] / (oz_p99 + 1e-9))
        add(i, "COVERAGE", "OUT_OF_ZONE", sev, gg - FA_FR, gg)
        oz_players[(g.game_id[i], g.event_id[i])] = (g.player_id[i], sev)

    out = pl.DataFrame(recs, schema=["game_id", "event_id", "player_id", "ledger", "event_type", "severity", "w0", "w1"], orient="row")

    # ---- R5 upstream split: a coverage event on a beaten recoverer (elevated oop) flows part to the
    #      unswapped vacator (out-of-zone player) on the same goal; vacator larger share.
    r5_rows = []
    for (gid, eid), vac in oz_players.items():
        vac_pid, vac_sev = vac
        beaten = out.filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid) & (pl.col("ledger") == "COVERAGE")
                            & (pl.col("player_id") != vac_pid) & (pl.col("event_type").is_in(["E1", "R3", "E3"])))
        # discount the beaten recoverer's coverage 0.5x and move 0.35 of it to the vacator (already fired OUT_OF_ZONE)
        for b in beaten.iter_rows(named=True):
            r5_rows.append((gid, eid, b["player_id"], b["event_type"], b["severity"] * 0.5))
    # apply R5 discounts
    if r5_rows:
        disc = pl.DataFrame(r5_rows, schema=["game_id", "event_id", "player_id", "event_type", "new_sev"], orient="row")
        out = out.join(disc, on=["game_id", "event_id", "player_id", "event_type"], how="left").with_columns(
            severity=pl.when(pl.col("new_sev").is_not_null()).then(pl.col("new_sev")).otherwise(pl.col("severity"))).drop("new_sev")

    # ---- scramble discount x0.5: coverage events whose window is after the flip on turnover-origin goals ----
    out = out.with_columns(flip=pl.struct("game_id", "event_id").map_elements(
        lambda s: flip.get((s["game_id"], s["event_id"]), None), return_dtype=pl.Int64))
    out = out.with_columns(severity=pl.when((pl.col("ledger") == "COVERAGE") & pl.col("flip").is_not_null() & (pl.col("w0") >= pl.col("flip")))
                           .then(pl.col("severity") * 0.5).otherwise(pl.col("severity")))

    # ---- non-overlapping stacking + per-player per-ledger cap 1.0 ----
    # stable-order the frame before the group_by so maintain_order captures a deterministic group + row order
    out = out.sort(["game_id", "event_id", "player_id", "ledger", "event_type", "w0", "w1"])
    capped = []
    for (gid, eid, pid, led), grp in out.group_by(["game_id", "event_id", "player_id", "ledger"], maintain_order=True):
        # deterministic total order: severity desc, then event_type/window as stable tie-breaks. Without the
        # tie-break, polars' order-not-preserving joins + unstable sort made the overlap "keep max" pick
        # non-deterministically between an R3 and an OUT_OF_ZONE sharing a window (~19 records swapped per run).
        evs = grp.sort(["severity", "event_type", "w0", "w1"], descending=[True, False, False, False]).to_dicts()
        kept, spans = [], []
        for e in evs:
            if any(not (e["w1"] < s0 or e["w0"] > s1) for s0, s1 in spans):   # overlaps a kept event -> skip (keep max)
                continue
            kept.append(e); spans.append((e["w0"], e["w1"]))
        tot = sum(e["severity"] for e in kept)
        scale = min(1.0, 1.0 / tot) if tot > 1.0 else 1.0
        for e in kept:
            capped.append([gid, eid, pid, led, e["event_type"], e["severity"] * scale])
    out = pl.DataFrame(capped, schema=["game_id", "event_id", "player_id", "ledger", "event_type", "severity"], orient="row")
    # shares within each ledger per goal
    tot = out.group_by("game_id", "event_id", "ledger").agg(led_total=pl.col("severity").sum())
    out = out.join(tot, on=["game_id", "event_id", "ledger"], how="left").with_columns(share=pl.col("severity") / pl.col("led_total"))
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(REC)

    return {"records": out.height,
            "by_ledger": out.group_by("ledger", "event_type").agg(n=pl.len()).sort(["ledger", "n"], descending=[False, True]).to_dicts()}


if __name__ == "__main__":
    r = build()
    print("records:", r["records"])
    for d in r["by_ledger"]:
        print(f"  {d['ledger']:10} {d['event_type']:12} {d['n']}")
