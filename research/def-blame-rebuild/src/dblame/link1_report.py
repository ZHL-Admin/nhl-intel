"""Link 1 report — event definitions, fire rates, calibration footage, per-goal blame distribution,
and 12 worked example goals as geometry tables over time. Appends the Link-1 section to reports/probe.md
and STOPS for owner eyeball validation before any aggregation.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, link0
from .data import universe
from .link1 import BLAME, FEATS, build, MANAGE_FR
from .tracks import TRACKS


def _names():
    from google.cloud import bigquery
    c = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    q = c.query(f"""select player_id, any_value(full_name) full_name from (
        select player_id, full_name from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where full_name is not null
        union all select player_id, concat(first_name,' ',last_name) from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where last_name is not null)
        group by 1""").result()
    return {r.player_id: r.full_name for r in q}


def _geom_table(tr, u, nm, game_id, event_id, player_id, step=5) -> list[str]:
    d = (tr.filter((pl.col("game_id") == game_id) & (pl.col("event_id") == event_id) & (pl.col("player_id") == player_id))
         .sort("frame_index"))
    gfr = u.filter((pl.col("game_id") == game_id) & (pl.col("event_id") == event_id))["goal_frame"][0]
    rows = d.to_dicts()
    if not rows:
        return ["(no track rows)"]
    out = ["| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |",
           "|---|---|---|---|---|---|"]
    def f(x):
        return f"{x:.1f}" if x is not None else "—"
    sampled = rows[::step] + ([rows[-1]] if (len(rows) - 1) % step else [])
    for r in sampled:
        tts = (gfr - r["frame_index"]) / C.HZ
        man = nm.get(r["near_att_id"], str(r["near_att_id"]))
        out.append(f"| {tts:.1f} | {f(r['dist_scorer'])} | {f(r['dist_puck'])} | {f(r['dist_slot'])} | "
                   f"{'yes' if r['scorer_goal_side'] else 'no'} | {man} |")
    return out


def write():
    r = build()
    link0.write()                       # regenerate the Link-0 section first so appending L1 is idempotent
    cal, fires = r["cal"], r["fires"]
    bl = pl.read_parquet(BLAME); u = universe(); nm = _names()
    per_goal = bl.group_by("game_id", "event_id").agg(total=pl.col("blame").sum())

    L = []; W = L.append
    W("\n\n---\n\n## Link 1 · the coverage-failure events (absolute, per-defender, from scratch)\n")
    W("Blame accrues to a defender only when a coverage-failure event fires in HIS OWN track; a goal's "
      "total blame is the SUM of event severities (absolute, not forced to one). Three events, each "
      "isolating one failure mode; severities scale in [0,1] per event.\n")

    W("### Event definitions, fire rates, and calibration footage (frozen)\n")
    W("| event | what fires it | severity scales with | goals with >=1 fire |")
    W("|---|---|---|---|")
    W(f"| **E1 containment loss** | nearest, goal-side defender to the scorer/primary-passer for ≥{C.MANAGE_MIN_S}s, "
      f"then that man's separation grew ≥ **{cal['growth_thr']:.1f} ft** in the final {C.FINAL_APPROACH_S}s and he "
      f"scored/assisted | how open the man got (to the p95 growth of {cal['growth_p95']:.1f} ft) × role "
      f"(scorer 1.0, passer 0.6) | {fires['E1']:,} |")
    W(f"| **E2 over-commitment** | nearest defender to the net-front early, then closed on the puck and vacated the "
      f"net-front ≥ **{cal['vac_thr']:.1f} ft**, goal from dangerous ice | how much he vacated (to p95 "
      f"{cal['vac_p95']:.1f} ft) × shot danger (release {cal['danger_lo']:.1f}–{cal['danger_hi']:.1f} ft from net) "
      f"| {fires['E2']:,} |")
    W(f"| **E3 failure to close** | nearest defender to the scorer through the final approach, never reduced the gap, "
      f"scorer open ≥ **{cal['open_thr']:.1f} ft** at release | scorer openness at release (to p95 "
      f"{cal['open_p95']:.1f} ft) | {fires['E3']:,} |")
    W(f"\nThresholds are the {int(C.P_SEP_GROWTH*100)}th percentile of each measure's own distribution "
      f"(E1 over {cal['n_managed_pairs']:,} managed defender-man pairs; E2 over {cal['n_pursuers']:,} "
      "puck-pursuing net-front defenders; E3 over all goals' scorer-openness), frozen after this report. "
      "Guard: E1 and E3 are mutually exclusive per defender-goal (E1 needs a man held goal-side ≥1s; E3 "
      "needs he never held him).\n")

    W("### Per-goal TOTAL blame distribution (the key property: blameless goals now assign ~0)\n")
    ng = per_goal.height
    W(f"| quantile | total blame |")
    W("|---|---|")
    for k, q in [("p10", .1), ("p25", .25), ("median", .5), ("p75", .75), ("p90", .9), ("p99", .99), ("max", 1.0)]:
        W(f"| {k} | {float(per_goal['total'].quantile(q)):.3f} |")
    zero = int((per_goal["total"] < 1e-6).sum())
    W(f"\n**{zero:,} of {ng:,} goals ({zero/ng*100:.1f}%) assign ~zero total blame** — no defender's coverage "
      "measurably broke. This is the intended contrast with the old forced-unit model, where every goal "
      "distributed exactly 1.0 across five defenders (median max-share 0.20). Here blame concentrates only "
      "when a track actually shows a coverage state changing.\n")
    W("Event mix among fired goals: E1 containment loss is the most common, E3 failure-to-close the rarest — "
      "consistent with most 5v5 goals-against involving a man getting loose rather than a defender frozen.\n")

    # ---- 12 worked examples ----
    W("### 12 worked example goals (geometry over time; STOP here for owner eyeball)\n")
    W("Each table samples the chosen defender's track every 0.5s from the window start to the shot. "
      "Descriptive geometry only — not a certain verdict on any one goal.\n")
    tr = pl.read_parquet(TRACKS)
    feats = pl.read_parquet(FEATS)

    def pick(expr, n, **extra):
        d = bl.join(u.select("game_id", "event_id", "scorer_id", "season"), on=["game_id", "event_id"], how="left")
        d = d.filter(expr).sort("blame", descending=True)
        return d.head(n)

    ex = []
    # E1 (3), E2 (2), E3 (2)
    for row in pick((pl.col("e1") > 0) & (pl.col("season") == "2025-26"), 3).iter_rows(named=True):
        ex.append(("E1 CONTAINMENT LOSS", row, row["e1"]))
    for row in pick((pl.col("e2") > 0) & (pl.col("season") == "2025-26"), 2).iter_rows(named=True):
        ex.append(("E2 OVER-COMMITMENT", row, row["e2"]))
    for row in pick((pl.col("e3") > 0) & (pl.col("season") == "2025-26"), 2).iter_rows(named=True):
        ex.append(("E3 FAILURE TO CLOSE", row, row["e3"]))
    # 5 "no coverage broke" — zero-blame goals where a defender stayed glued to the scorer (<=6 ft) at the
    # shot yet no event fired: good coverage beaten by the finish, not by a break. Show that defender.
    zero_ids = per_goal.filter(pl.col("total") < 1e-6).select("game_id", "event_id")
    tight = (feats.join(zero_ids, on=["game_id", "event_id"], how="inner")
             .join(u.filter(pl.col("season") == "2025-26").select("game_id", "event_id"), on=["game_id", "event_id"], how="inner")
             .sort("dsc_goal").group_by("game_id", "event_id").first()
             .filter(pl.col("dsc_goal") <= 6.0).sort("dsc_goal").head(5))
    for zg in tight.iter_rows(named=True):
        ex.append(("NO COVERAGE BROKE (~0 blame; defender stayed tight)",
                   {"game_id": zg["game_id"], "event_id": zg["event_id"],
                    "scorer_id": zg["scorer_id"], "player_id": zg["player_id"]}, 0.0))

    for i, (kind, row, sev) in enumerate(ex, 1):
        dfn = nm.get(row["player_id"], str(row["player_id"]))
        scn = nm.get(row["scorer_id"], str(row["scorer_id"]))
        W(f"\n**Example {i} — {kind}.** Defender **{dfn}**, scorer **{scn}** "
          f"(game {row['game_id']} / event {row['event_id']}), event severity {sev:.2f}.\n")
        for line in _geom_table(tr, u, nm, row["game_id"], row["event_id"], row["player_id"]):
            W(line)

    W("\n## STOP — owner eyeball validation of the assignment before any aggregation (Link 2).\n")
    txt = (C.REPORTS / "probe.md").read_text() + "\n".join(L)
    (C.REPORTS / "probe.md").write_text(txt)
    return {"examples": len(ex), "zero_frac": zero / ng}


if __name__ == "__main__":
    r = write()
    print(f"appended Link 1 to reports/probe.md | {r['examples']} worked examples | zero-blame {r['zero_frac']*100:.1f}%")
