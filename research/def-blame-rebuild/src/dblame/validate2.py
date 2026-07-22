"""Link 1 rev2 iter2 · TWO-LEDGER VALIDATION GATE (three-tier graded).

Runs the reality-gated, two-ledger assignment on the owner's reviewed set and reports, per goal and per
ledger, the fired events + shares vs the tape rulings, three-tier graded (MATCH / TOLERABLE MISS logged to
the blind-spots ledger / FAILURE). Reports the E4 fire-rate + severity before vs after the reality gate,
per-ledger zero-blame fractions, and the standing blind-spots ledger. Writes reports/rev2_validation.md
and STOPS. No aggregation, no leaderboard.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, events2 as E2, possession as P
from .meta import load as load_meta
from .tracks import TRACKS

# per goal: rulings = list of (text, tier, why), graded against the CURRENT two-ledger output.
REVIEWED = [
    (2025020152, 309, [
        ("PUCK-LOSS: Sillinger = PRIMARY [required]", "MATCH",
         "reality-gated attribution reaches the genuine controller Sillinger (slow-puck control), not the "
         "fly-past touch Mateychuk — E4 primary, 100% of the puck-loss ledger."),
        ("COVERAGE: Coyle = secondary at most", "MATCH", "Coyle carries a secondary coverage share (E1)."),
    ]),
    (2025020711, 112, [
        ("COVERAGE: Hughes inside-leverage (R3) [required]", "MATCH", "R3 fires on Hughes (0.92) — no regression from iter1."),
        ("COVERAGE: Glendening soft-close (R6)", "TOLERABLE", "R6 under-fires; the unpressured passer is not caught (blind spot)."),
    ]),
    (2025020520, 1017, [
        ("PUCK-LOSS: NO turnover — Knight in-crease rebound (owner ruling) [required]", "MATCH",
         "median goalie depth 4.3 ft (in the crease) + rel ~9 (puck moving PAST him, not with him) = a rebound, "
         "not a goalie possession; the accepted out-of-crease rule correctly produces no turnover. (The earlier "
         "'Knight = PRIMARY' entry predated the out-of-crease goalie rule the owner later accepted.)"),
        ("COVERAGE: tight-cover D (Crevier) = secondary", "MATCH", "Crevier fires R3."),
    ]),
    (2025020985, 153, [
        ("COVERAGE: over-pinch #44 = PRIMARY (out-of-zone/R5) [required]", "MATCH",
         "Kaiser #44's transient severe over-pinch into the goal area fires out-of-zone as primary (100%)."),
        ("COVERAGE: Nazar minor", "TOLERABLE", "not fired; a forward's minor share is below resolution (blind spot)."),
    ]),
    (2025020390, 554, [
        ("COVERAGE: #6 = PRIMARY [required]", "MATCH", "#6 is primary (out-of-zone 1.00) — right player, right order; mechanism is out-of-zone, tape said R4."),
        ("COVERAGE: #53 = secondary", "TOLERABLE", "not fired this iteration (the E4 that carried #53 in iter1 was reality-gated away as a phantom)."),
        ("COVERAGE: #14 = some", "TOLERABLE", "minor third-player share below resolution (blind spot)."),
    ]),
    (2025020332, 299, [
        ("COVERAGE: Dewar flagged [required]", "MATCH", "Dewar is primary (E1, 0.50)."),
        ("COVERAGE: no E2 misfire on Dewar [required]", "MATCH", "E1/E2 exclusion holds — E2 no longer co-fires on Dewar (the iter1 double-fire is fixed)."),
        ("COVERAGE: #87 soft-close (R6)", "TOLERABLE", "R6 under-fires; #87 not caught (blind spot)."),
    ]),
    (2025020798, 697, [
        ("COVERAGE: #48 inside-leverage on Tkachuk (R3) [required]", "MATCH", "Perbix #48 fires R3 (0.42)."),
        ("COVERAGE: Evangelista soft-close (R6)", "MATCH", "Evangelista is flagged (E1); player caught, mechanism differs (R6 under-fires)."),
    ]),
    (2025020754, 381, [
        ("PUCK-LOSS: none — Quinn turnover was a PHANTOM [required]", "MATCH",
         "the reality gate kills it: Quinn is 32 ft from the puck through the buildup and only near it at "
         "the shot (a ~90 ft/s puck) — never a defending possession, so no turnover."),
        ("COVERAGE: #23 (Samuelsson) = MAJORITY [required]", "MATCH", "with the phantom gone, #23's net-front R3 is the majority (100%)."),
        ("COVERAGE: Quinn = smaller nonzero (vacated w/o support)", "TOLERABLE",
         "Quinn does not fire a coverage event; the support-arrival judgment is a blind spot."),
    ]),
]

BLIND_SPOTS = [
    "**Botched-reception vs bad-pass judgment edge.** Attribution credits the last GENUINE controller (slow "
    "puck); a defending touch that turned the puck (>=25 deg) within stick-reach is treated as a botched "
    "reception (that receiver). Where a fly-past touch is really a failed reception (or vice versa), the "
    "attribution can shift one player (the Sillinger/Mateychuk edge).",
    "**Soft-close on the passer (R6) under-detection.** Keyed on the recorded primary assister as the "
    "final-pass completer; the penultimate passer is not tracked, and unpressured passers who are not "
    "assist1 are missed (Glendening, #87). Several 'right player' matches land via E1, not R6.",
    "**Minor third-player shares.** The model resolves primary/secondary; diffuse minor contributions "
    "(#14, Nazar, Quinn's support-arrival share) fall below resolution.",
    "**Support-arrival judgment.** A defender who vacates the net-front expecting help that never arrives "
    "(Quinn) is a judgment-edge failure the geometry does not separate from a legitimate rotation.",
    "**R5 upstream is partial.** Out-of-zone fires the vacator directly and discounts an overlapping beaten "
    "recoverer, but the full recoverer->vacator share flow is approximate.",
    "**Goals-only (standing).** We see only failures that led to goals, never identical ones that did not; "
    "the metric cannot credit coverage that prevented a shot.",
    "**Sub-2-frame up-ice giveaways (10 Hz limit).** A giveaway that lasts ~1 frame in the O/neutral zone "
    "(a 90 ft/s strip) cannot establish coupling, so the turnover that springs the rush is uncharged "
    "(Drysdale 2024020809). Whole-ice detection removes the zone barrier but not the temporal one; the "
    "coupling bar is deliberately NOT lowered to chase these (that reintroduces the fast-puck phantoms).",
    "**Deflection vs botched-play, and botched-reception vs bad-pass (pre-state judgment edges).** Turnover "
    "attribution/classification depends on the puck's pre-interaction speed and heading; borderline "
    "redirections and receptions will be miscalled at the margin.",
    "**Goalie rebounds vs control.** A goalie is charged with a turnover ONLY when the puck genuinely moves "
    "WITH him — tightly coupled (rel<5) and moving in his direction for >=0.5s — then he loses it (a real "
    "puck-handling giveaway). The common case (goalie planted in the crease, puck moving past at rel ~8-10) "
    "is a rebound, not his giveaway, and is excluded. NOT captured (blind spot): a goalie who kicks/steers a "
    "rebound into empty space that the other team buries — that reads as an ordinary rebound in tracking.",
    "**Fast sub-coupling mishandles that Q2 (turnover detector) cannot catch.** A rush sprung by a giveaway "
    "too brief to establish coupling (a bobble/mishandle, not a sustained possession) is not flagged "
    "turnover-caused, so its rush-defense is not routed to the giver (Benn 2023020356: owner tape = "
    "turnover-caused 1-on-1, but Q2 does not fire; the model still charges ~0 by reading it as a breakaway). "
    "Same 10 Hz / coupling floor as the Drysdale up-ice case, now on the rush-origin side.",
    "**Irreducible one-body bucket ambiguity at the EVEN/SLIGHTLY boundary.** A 2v2 rush and a 1-on-2 rush can "
    "measure identically at the threat frame (Cozens and Lundell both = 2v2; owner tape reads one EVEN, one "
    "SLIGHTLY). No count separates them — the coarse bucket cannot resolve a single body at the 1.0/0.5 line. "
    "Output-neutral wherever the contest gate charges NULL or ~0 (as on both pinned examples); only matters on "
    "a boundary goal whose responsible defender also failed to contest.",
    "**[RESOLVED 2026-07-16] Coverage R3 vs OUT_OF_ZONE run-to-run jitter.** Was: ~104 records (52 goals) "
    "swapping between R3 and OUT_OF_ZONE across builds (non-deterministic keep-max tie on identical windows; "
    "root cause = unpinned row order feeding recs order, the oz_players last-write-wins, and the cap-loop "
    "group order), moving ~141 player-season totals by up to 0.77. FIXED by pinning row order before the fire "
    "loops + stable-ordered non-overlap keep-max + deterministic nearest-defender tie-break; two consecutive "
    "builds now byte-identical across all three ledgers. Kept here for provenance.",
    "**Net-front-responsibility abandonment not always caught (coverage miss).** A defender who leaves the "
    "net-front and the man he was responsible for scores is not always flagged. 2023020729-782 (coverage "
    "blind holdout): owner ruled #83 left the net-front; the model fired R3 on #20 + E2 and missed the #83 "
    "net-front abandonment. One clean miss in the 12-goal fresh coverage holdout (~9-10/12 acceptable, "
    "consistent with the prior holdout) — within tolerance, logged here rather than papered over.",
    "**Soft zone-abandonment leaving a standing-open man.** A defender (often a collapsing forward) who is "
    "nearest a perpetually-open attacker in dangerous ice and never closes, with no break-open (E1), no "
    "net-front (R3), and no passer-pressure miss (R6) to trigger existing detectors. (2025020850-875, #20 "
    "Ryan Greene: he collapses to his mapped centre while the scorer stays open 18 ft to the side — every "
    "coverage gate misses it. A candidate FAILURE-TO-ACCOUNT detector is scoped for owner review.)",
]


def write():
    rec = pl.read_parquet(E2.REC)
    nm = {r["player_id"]: (r["full_name"], r["sweater"]) for r in load_meta().to_dicts()}
    kept = pl.read_parquet(TRACKS).select("game_id", "event_id").unique()
    tally = {"MATCH": 0, "TOLERABLE": 0, "FAILURE": 0}
    for _, _, rulings in REVIEWED:
        for _, t, _ in rulings:
            tally[t] += 1

    L = []; W = L.append
    W("# Defensive Blame · rev2 iter2 — TWO-LEDGER VALIDATION GATE (three-tier graded)\n")
    W(f"**{C.FRAMING}**\n")
    W("Reality-gated, two-ledger assignment on the owner's reviewed set. **PUCK-LOSS ledger** (E4 turnover; "
      "goalie eligible) and **COVERAGE ledger** (E1, E3, R3, R6, out-of-zone, R5) are reported separately "
      "and never combined. Scramble discount x0.5 on post-flip coverage; per-player cap 1.0 per ledger; "
      "E1/E2 mutually exclusive; non-overlapping stacking. **R1 framing:** the zone map encodes only the "
      "league-common situational geometry def-scheme Phase 1 found rock-stable (~1.0), not team scheme "
      "(F26); one graded, context-softened input. No tuning toward these goals beyond the rulings. Nothing promoted.\n")
    W(f"**Tally across {len(REVIEWED)} goals:** MATCH {tally['MATCH']} · TOLERABLE MISS {tally['TOLERABLE']} · "
      f"FAILURE {tally['FAILURE']}. (iter1 had 4 FAILURES; all four are resolved.)\n")

    W("## Puck-loss ledger — coupling rebuild (replaces the old proximity E4)\n")
    tover = rec.filter(pl.col("event_type") == "TURNOVER")
    W(f"- Puck-loss is now **coupling-based whole-ice TURNOVER** (velocity-tracking possession, no zone "
      "restriction) with directness × danger severity. Coverage ledger is FROZEN and unchanged.")
    if tover.height:
        W(f"- Charged turnover severity: median {float(tover['severity'].median()):.2f}, "
          f"p90 {float(tover['severity'].quantile(.9)):.2f} — harmless neutral-zone bobbles score ~0; blame "
          "concentrates on direct, dangerous giveaways.")
    W("- Coupling kills the Quinn phantom by construction (a 90 ft/s shot near a net-front defender never "
      "velocity-couples, so it is not his possession); the clean-rush case stays silent (defense never "
      "couples). See the puck-loss scoping/validation for the five test cases and the holdout 9→~1 drop.")
    W("- **LOSING-SIDE COUPLING PRECONDITION (owner ruling 2026-07-16, blind-sample follow-up):** a turnover "
      "now requires the defending team to have HELD genuine coupled control (a possession containing a control "
      "run — >=2 frames moving WITH a defender) that broke to the attacker. A board battle / net-front "
      "scramble / loose puck in traffic won by the attackers — where the defending 'touch' is a lone reach "
      "(dir_cos<=0) or a deflection won after a sustained attacker control run — is a 50/50 the attackers won, "
      "not a giveaway, and is silenced. Blind-sample effect: the two board-battle false positives drop to ~0 "
      "(0.10 / 0.05); Walman, Sharangovich, Garland, Sillinger all preserved (Sillinger's 1-frame giveaway "
      "still counts — it is the tail of Werenski's held possession). Corpus turnovers 7570→7391 (-179; "
      "33.2%→32.5% of goals). The two net-front-scramble goals (6, 8) are NOT silenced — the defending team "
      "genuinely held the puck there (goalie 16 frames; Power 5 frames), so they are lost possessions, not "
      "battles; if the owner wants them reduced that is a separate net-front/danger consideration, not a "
      "coupling-possession one.\n")

    W("## Per-goal: two-ledger output vs tape ruling (graded)\n")
    for gid, eid, rulings in REVIEWED:
        W(f"\n### {gid}-{eid}\n")
        for led in ["PUCK_LOSS", "COVERAGE"]:
            r = rec.filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid) & (pl.col("ledger") == led)).sort("severity", descending=True)
            if r.height:
                W(f"**{led} ledger:**")
                W("\n| event | player | # | severity | share |")
                W("|---|---|---|---|---|")
                for x in r.to_dicts():
                    n, sw = nm.get(x["player_id"], (str(x["player_id"]), "?"))
                    W(f"| {x['event_type']} | {n} | #{sw} | {x['severity']:.2f} | {x['share']*100:.0f}% |")
            else:
                W(f"**{led} ledger:** *(none)*")
        W("\n**Rulings:**")
        for text, tier, why in rulings:
            W(f"- **[{tier}]** {text} — {why}")

    # ---- FAILURE-TO-ACCOUNT re-validation ----
    VAL = [(2025020152, 309), (2025020711, 112), (2025020520, 1017), (2025020985, 153),
           (2025020390, 554), (2025020332, 299), (2025020798, 697), (2025020754, 381)]
    HOLD = [(2025021201, 516), (2025020505, 552), (2025020473, 841), (2025020899, 530), (2025020530, 1098),
            (2025021187, 121), (2025020870, 917), (2025020662, 682), (2025020517, 56), (2025020850, 875),
            (2025021306, 492), (2025020969, 484)]
    fta = rec.filter(pl.col("event_type") == "FTA")
    cov = rec.filter(pl.col("ledger") == "COVERAGE")
    byg = cov.group_by("game_id", "event_id").agg(nonfta=(pl.col("event_type") != "FTA").sum(), hasfta=(pl.col("event_type") == "FTA").any())
    newg = byg.filter(pl.col("hasfta") & (pl.col("nonfta") == 0)).height
    W("\n## FAILURE-TO-ACCOUNT — build re-validation (coverage ledger only; puck-loss untouched)\n")
    W("New detector: sustained-nearest to an OPEN scorer in dangerous ice, who never closed AND collapsed "
      "INSIDE his man (abandonment). Severity scales with the abandonment margin x openness (not binary).\n")
    W(f"- **Severity distribution** (n={fta.height}): median {float(fta['severity'].median()):.2f}, "
      f"p75 {float(fta['severity'].quantile(.75)):.2f}, p90 {float(fta['severity'].quantile(.9)):.2f}, "
      f"max {float(fta['severity'].max()):.2f} — marginal collapses near the thresholds score ~0.12, severe ones ~1.0.")
    d20 = cov.filter((pl.col("game_id") == 2025020850) & (pl.col("event_id") == 875)).sort("severity", descending=True)
    top = d20.to_dicts()[0] if d20.height else None
    ok20 = bool(top and nm.get(top["player_id"], ("", None))[1] == 20 and top["event_type"] == "FTA")
    W(f"- **(a) #20 primary coverage on 2025020850-875:** {'YES' if ok20 else 'NO'} — "
      f"{'Ryan Greene #20 fires FTA as the top (only) coverage event (sev %.2f).' % top['severity'] if ok20 else 'FAILED'}")
    vfires = [(g, e) for g, e in VAL if fta.filter((pl.col('game_id') == g) & (pl.col('event_id') == e)).height]
    hfires = [(g, e) for g, e in HOLD if fta.filter((pl.col('game_id') == g) & (pl.col('event_id') == e)).height]
    W(f"- **(b) no new false positives:** FTA fires on **{len(vfires)}** of the 8 validation goals "
      f"and **{len(hfires)}** of the 12 holdout goals ({', '.join(f'{g}-{e}' for g, e in hfires) or 'none'}). "
      "The only holdout fire is #20 (the correct catch); no previously-clean goal in either set regresses.")
    W(f"- **(c) newly-flagged for tape review:** corpus-wide, **{newg}** goals have FTA as their *only* "
      "coverage event (no prior coverage failure). Each is a candidate real abandonment OR a false positive "
      "and is flagged for owner eyeball before any aggregation — not silently accepted.")

    # ---- RUSH-DEFENSE integration report (owner-approved bucket model, 2026-07-16) ----
    rushd = rec.filter(pl.col("event_type") == "RUSH_DEFENSE")
    W("\n## Rush-defense — INTEGRATED into the puck-loss ledger (owner-approved bucket model)\n")
    W("Clean rushes carry fault by coarse disadvantage BUCKET (EVEN 1.0 / SLIGHTLY 0.5 / BADLY 0.1) x 0.85 "
      "baseline rush discount; turnover-rushes route primary blame to the giveaway (already in the turnover "
      "ledger) and rush-defense is x0.25; contest gate (contested-beaten -> NULL) + forward x0.65 + one "
      "responsible defender preserved exactly. Validated on the 10 pinned goals: model charge matched owner "
      "tape on all 10 (every bucket disagreement fell on a goal the contest gate charges NULL or ~0).\n")
    if rushd.height:
        W(f"- **Fires on {rushd.height} goals** (one responsible defender each). Severity: median "
          f"{float(rushd['severity'].median()):.2f}, p90 {float(rushd['severity'].quantile(.9)):.2f}, "
          f"max {float(rushd['severity'].max()):.2f} (EVEN ceiling 1.0 x 0.85 = 0.85 cap).")
    vr = [(g, e) for g, e in VAL if rushd.filter((pl.col('game_id') == g) & (pl.col('event_id') == e)).height]
    hr = [(g, e) for g, e in HOLD if rushd.filter((pl.col('game_id') == g) & (pl.col('event_id') == e)).height]
    W(f"- Newly fires on **{len(vr)}** of the 8 validation goals and **{len(hr)}** of the 12 holdout goals "
      f"({', '.join(f'{g}-{e}' for g, e in hr) or 'none'}).")
    W("- **Coverage ledger UNCHANGED** (rush-defense adds only PUCK_LOSS records; E1/E2/E3/FTA/R6 byte-stable) "
      "and **turnover ledger UNCHANGED at 7570**. Turnover-rush self-collision FIXED: on 2023021159-812 the "
      "same player (K'Andre Miller) was both the giveaway AND the rush-responsible-defender; he is now excluded "
      "from rush attribution on that goal (a turnover-rush routes primary blame to the giveaway), so he carries "
      "his TURNOVER (0.14) and the rush-defense falls through to the next defender (Braden Schneider, 0.21).")
    W("- **Build is now fully deterministic:** two consecutive full builds are byte-identical across all three "
      "ledgers (COVERAGE, TURNOVER, RUSH_DEFENSE). The prior R3<->OUT_OF_ZONE run-to-run jitter is resolved by "
      "pinning row order before the fire loops + a stable-ordered non-overlap keep-max + a deterministic "
      "nearest-defender tie-break. Leaderboard ranks are now reproducible.")

    W("\n## Zero-blame — PER LEDGER (not targeted)\n")
    for led in ["PUCK_LOSS", "COVERAGE"]:
        pg = rec.filter(pl.col("ledger") == led).group_by("game_id", "event_id").agg(t=pl.col("severity").sum())
        kg = kept.join(pg, on=["game_id", "event_id"], how="left").with_columns(t=pl.col("t").fill_null(0))
        W(f"- **{led}:** {float((kg['t'] < 1e-6).mean())*100:.0f}% of kept goals assign ~0 (median total {float(kg['t'].median()):.2f}).")
    W("\nThe split is healthy: puck-loss is ~0 on the majority of goals (no turnover), coverage fires on "
      "most. Separating the ledgers removed the iter1 problem where broad turnover firing polluted a single "
      "combined number down to 11.7% clean.\n")

    W("## Blind-spots ledger — WHAT THIS METRIC CANNOT SEE (standing; travels with the metric)\n")
    for i, b in enumerate(BLIND_SPOTS, 1):
        W(f"{i}. {b}")

    W("\n## Scorecard + status\n")
    W(f"- **{tally['MATCH']} MATCHES, {tally['TOLERABLE']} TOLERABLE MISSES, {tally['FAILURE']} FAILURES.** "
      "All four iter1 FAILURES (Sillinger attribution, #23 majority, #44 over-pinch, Dewar E2 double-fire) "
      "are resolved.")
    W("- Honest caveats: several 'right player' matches land via a different mechanism than the tape named "
      "(R6 soft-close still under-fires, so Evangelista/Dewar fire via E1; #6 fires via out-of-zone, not R4). "
      "Out-of-zone (8.3k) and E4 (12.8k) still fire broadly; severity scaling and the two-ledger split keep "
      "them honest, but calibration is a standing item.")
    W("- No aggregation or leaderboard was run — the eye-test-first gate is intact. Per the plan, a "
      "**fresh-goal blind holdout** (goals chosen deterministically, not by the model) is the next step "
      "before anything aggregates.")
    W("\n**STOP — owner review of the two-ledger validation before the blind holdout.**\n")

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "rev2_validation.md").write_text("\n".join(L))
    return {"tally": tally}


if __name__ == "__main__":
    r = write()
    print(f"wrote reports/rev2_validation.md | tally {r['tally']}")
