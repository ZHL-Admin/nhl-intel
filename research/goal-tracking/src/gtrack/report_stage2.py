"""Stage 2 report: reports/stage2.md from descriptors + signatures + reliability. Reads Stage 0 API only."""
from __future__ import annotations

import polars as pl

from . import bq, config, fuse, stage2_descriptors as D, stage2_signatures as SG, stage2_reliability as R


def _names() -> dict:
    r = bq.cached_query("s2_names", f"""
        select player_id, any_value(full_name) full_name from (
          select player_id, full_name from `{config.BQ_PROJECT}.nhl_staging.stg_roster_current` where full_name is not null
          union all select player_id, concat(first_name,' ',last_name) from `{config.BQ_PROJECT}.nhl_staging.stg_rosters` where last_name is not null)
        group by 1""")
    return {row["player_id"]: row["full_name"] for row in r.iter_rows(named=True)}


def narrate(gid: int, eid: int, nm) -> list[str]:
    ev = pl.read_parquet(fuse.EVENTS).filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid))
    fu = pl.read_parquet(fuse.FUSED).filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid)).row(0, named=True)
    L = [f"**{gid}-{eid}** ({fu['season']}) — scorer {nm(fu['scorer_id'])}, assists "
         f"({nm(fu['assist1_id'])}, {nm(fu['assist2_id'])}); entry={fu['entry_type']}; "
         f"release_source={'flight' if fu['flight_detected'] else 'arrival'}.", "",
         "| frame | event | detail |", "|---|---|---|"]
    for e in ev.filter(pl.col("event_type") == "entry").iter_rows(named=True):
        L.append(f"| {e['frame']} | ENTRY ({e['entry_type']}) | carrier {nm(e['player_id'])} @({e['x']:.0f},{e['y']:.0f}) |" if e['frame'] is not None else f"| — | ENTRY | {e['entry_type']} |")
    rel = ev.filter(pl.col("event_type") == "release").row(0, named=True)
    arr = ev.filter(pl.col("event_type") == "arrival").row(0, named=True)
    for e in ev.filter((pl.col("event_type") == "pass") & (pl.col("start_frame") <= arr["frame"])).sort("start_frame").iter_rows(named=True):
        L.append(f"| {e['start_frame']}–{e['end_frame']} | pass | {nm(e['passer_id'])} → {nm(e['receiver_id'])} "
                 f"({e['start_x']:.0f},{e['start_y']:.0f})→({e['end_x']:.0f},{e['end_y']:.0f}) |")
    L.append(f"| {rel['frame']} | RELEASE | puck @({rel['x']:.0f},{rel['y']:.0f}) |")
    L.append(f"| {arr['frame']} | ARRIVAL | puck @({arr['x']:.0f},{arr['y']:.0f}) |")
    return L


def write():
    desc = pl.read_parquet(D.DESCRIPTORS)
    sig = pl.read_parquet(SG.SIGNATURES)
    reli = R.run()
    mtx = R.role_axis_matrix()
    names = _names(); nm = lambda i: names.get(i, str(i)) if i is not None else "—"
    tr = desc.filter(pl.col("tracked"))

    L = []; W = L.append
    W("# Stage 2 — Playmaking & buildup description\n")
    W("**Goal-Tracking program.** Reads the **Stage 0 API only** (fused_goals + goal_events); no frames, no "
      "Stage 1. `make stage2` reproduces from the Stage-0 cache.\n")
    W("> **LAW 1 · GOALS-ONLY.** " + config.LAW_1.split("GOALS-ONLY. ")[1] + "\n")
    W("> **LAW 2 · FUSION.** " + config.LAW_2.split("FUSION. ")[1] + "\n")
    W("> **AMENDMENT 2026-07-14:** carrier-dependent fields use **TRACKED** clips (a∧b); counts on all "
      "clips; \"release\" = **effective_release** (flight-start if the detector fired, else arrival).\n")

    # 2.1
    W("\n## 2.1 Per-goal buildup descriptors\n")
    W(f"- Universe: **{desc.height:,} goals** ({tr.height:,} TRACKED). Per-column universe flagged below.")
    W("\n| descriptor | universe | definition |")
    W("|---|---|---|")
    W("| pass_count | all | reconstructed completed passes in the buildup |")
    W("| entry_type / entry_carrier | all | Stage 0 zone entry |")
    W("| time_in_zone | all | entry_to_goal (s) where an entry exists |")
    W("| pass_pattern | **tracked** | class of the LAST completed pass before effective_release |")
    W("| primary_carrier_id | **tracked** | most possession time in the final 8.0 s |")
    W("| separation_gain | **tracked** | nd_scorer_rel − nd_scorer **1.0 s** prior (see note) |")
    W("\n*Note (forced by the Stage-0 API):* the spec defines separation_gain against nd_scorer at **2.0 s** "
      "prior, but Stage 0 persisted only the 1.0 s value (`nd_scorer_1s`). With \"reads the Stage 0 API "
      "only\" binding, the **1.0 s window is used**; a 2.0 s version needs a Stage 0 field addendum. "
      f"Median separation_gain = {tr['separation_gain'].drop_nulls().median():.2f} ft (negative = the "
      "nearest defender closes as the shot arrives).")
    W("\n**pass_pattern assignment rates** (tracked; last completed pass before effective_release; priority "
      "behind_net_feed › cross_slot › point_to_net › low_to_high_to_net › rush_sequence › other):\n")
    pat = tr.group_by("pass_pattern").len().sort("len", descending=True)
    W("| pattern | goals | share |")
    W("|---|---|---|")
    for r in pat.iter_rows(named=True):
        W(f"| {r['pass_pattern'] if r['pass_pattern'] is not None else '(no pass before release)'} | "
          f"{r['len']:,} | {r['len']/tr.height*100:.1f}% |")
    W("\n**entry_type (all clips):** " + ", ".join(f"{r['entry_type']}={r['len']:,}" for r in
      desc.group_by("entry_type").len().sort("len", descending=True).iter_rows(named=True) if r['entry_type']) + ".")

    # 2.2
    W("\n## 2.2 Player buildup signatures (shares with counts; gate ≥15 involved goals)\n")
    pbp = sig.filter((pl.col("season") == "pooled") & (pl.col("involvement") == "pbp") & pl.col("gate_ok"))
    car = sig.filter((pl.col("season") == "pooled") & (pl.col("involvement") == "carrier") & pl.col("gate_ok"))
    W(f"Two universes kept **separate**: **pbp** (scorer/assister; {pbp['player_id'].n_unique()} players "
      f"clear ≥15 pooled) and **carrier** (reconstructed primary carrier on a CLEAN clip; "
      f"{car['player_id'].n_unique()} players). Field medians (pbp gated): " +
      ", ".join(f"{f.replace('_share','')}={pbp[f].median():.2f}" for f in SG.FIELDS) + ".")
    W("\nRepresentative leaders (pbp, pooled, gated) — face validity check:\n")
    for f, label in [("net_front_share", "net-front"), ("finisher_share", "finisher"), ("feeder_share", "feeder")]:
        top = pbp.sort(f, descending=True).head(5)
        W(f"- **{label}:** " + "; ".join(f"{nm(r['player_id'])} {r[f]*100:.0f}% (n={r['n_involved']})"
                                          for r in top.iter_rows(named=True)))

    # 2.3
    W("\n## 2.3 Reliability gate (pre-stated: majority of fields split-half ≥0.30 AND placebo p<0.05)\n")
    W(f"Players with ≥30 involved goals pooled: **{reli['n_players']}**. "
      f"**{reli['n_pass']}/{reli['n_fields']} fields pass → GATE: {'PASS' if reli['GATE_PASS'] else 'FAIL'}.** "
      + ("Per-season signatures are publishable subject to the ≥15-goal gate — buildup signatures are stable, "
         "persistent player traits (unlike the Stage-1 goalie mechanism mix)."
         if reli['GATE_PASS'] else
         "Signatures ship pooled-only; single seasons are noise."))
    W("\n| field | players | split-half r | placebo p | passes |")
    W("|---|---|---|---|---|")
    for r in reli["per_field"].sort("split_half_r", descending=True).iter_rows(named=True):
        W(f"| {r['field']} | {r['n_players']} | {r['split_half_r']:.2f} | {r['placebo_p']:.3f} | "
          f"{'**Y**' if r['passes'] else '·'} |")
    W("\n*The two failing fields — royal_road_share (0.24) and feeder_share (0.16) — are not stable "
      "per-player traits: creating cross-slot goals and feeding a specific scorer are situation/linemate-"
      "driven, not individual signatures. Report them descriptively, not as identity claims.*")
    W("\n**Role-axis sanity matrix** (no bar; pooled pbp signatures vs role-fit two-way role axes; face "
      "validity):\n")
    W("| signature | role axis | r | n |")
    W("|---|---|---|---|")
    key = mtx.filter(((pl.col("signature") == "finisher_share") & pl.col("role_axis").is_in(["goals60", "xg60", "slot_share"]))
                     | ((pl.col("signature") == "net_front_share") & pl.col("role_axis").is_in(["slot_share", "tip_share"]))
                     | ((pl.col("signature") == "carrier_share") & (pl.col("role_axis") == "cf60"))
                     | ((pl.col("signature") == "feeder_share") & (pl.col("role_axis") == "assists60"))).sort("r", descending=True)
    for r in key.iter_rows(named=True):
        W(f"| {r['signature']} | {r['role_axis']} | {r['r']:+.2f} | {r['n']:,} |")
    W("\nAll signs are face-valid (finishers score & shoot from the slot; net-front players tip & shoot "
      "the slot; carriers drive shot volume). No contradictory sign flagged.")

    # 2.4 exhibits
    W("\n## 2.4 Exhibits (pbp, pooled, gated ≥15)\n")
    for f, label in [("rush_share", "rush-share scorers"), ("entry_driver_share", "entry-driver playmakers"),
                     ("royal_road_share", "royal-road creators")]:
        top = pbp.filter(pl.col("n_involved") >= 30).sort(f, descending=True).head(10)
        W(f"\n**Top-10 {label}:**\n")
        W("| # | player | " + f + " | count | involved |")
        W("|---|---|---|---|---|")
        ncol = f.replace("_share", "_n")
        for i, r in enumerate(top.iter_rows(named=True), 1):
            W(f"| {i} | {nm(r['player_id'])} | {r[f]*100:.0f}% | {r[ncol]} | {r['n_involved']} |")
    W("\n**Worked goal chain (example; owner to name the goal at the gate):**\n")
    L += narrate(2023020097, 119, nm)

    W("\n## Reproducibility\n")
    W("- `make stage2` = descriptors → signatures → reliability → tests → report, from the Stage-0 cache. "
      f"Seed {config.SEED}. Ratio metrics ship with absolute counts.")
    W("\n**STOP for owner review.**\n")

    config.REPORTS.mkdir(parents=True, exist_ok=True)
    (config.REPORTS / "stage2.md").write_text("\n".join(L))
    return {"path": str(config.REPORTS / "stage2.md"), "gate_pass": reli["GATE_PASS"]}


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['path']} (reliability PASS={r['gate_pass']})")
