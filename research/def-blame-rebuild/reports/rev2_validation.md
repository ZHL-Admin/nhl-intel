# Defensive Blame · rev2 iter2 — TWO-LEDGER VALIDATION GATE (three-tier graded)

**Outputs are a DESCRIPTIVE per-possession coverage-failure log and an ABSOLUTE blame rate over 5v5 goals-against, never a claim of certain fault on any single goal and never a full defensive rating. We measure change in a defender's own coverage state over time, not scheme or where he should have been (avoids F26). Banned as a single-goal verdict: bad defense, fault, out of position, mistake.**

Reality-gated, two-ledger assignment on the owner's reviewed set. **PUCK-LOSS ledger** (E4 turnover; goalie eligible) and **COVERAGE ledger** (E1, E3, R3, R6, out-of-zone, R5) are reported separately and never combined. Scramble discount x0.5 on post-flip coverage; per-player cap 1.0 per ledger; E1/E2 mutually exclusive; non-overlapping stacking. **R1 framing:** the zone map encodes only the league-common situational geometry def-scheme Phase 1 found rock-stable (~1.0), not team scheme (F26); one graded, context-softened input. No tuning toward these goals beyond the rulings. Nothing promoted.

**Tally across 8 goals:** MATCH 13 · TOLERABLE MISS 6 · FAILURE 0. (iter1 had 4 FAILURES; all four are resolved.)

## Puck-loss ledger — coupling rebuild (replaces the old proximity E4)

- Puck-loss is now **coupling-based whole-ice TURNOVER** (velocity-tracking possession, no zone restriction) with directness × danger severity. Coverage ledger is FROZEN and unchanged.
- Charged turnover severity: median 0.08, p90 0.24 — harmless neutral-zone bobbles score ~0; blame concentrates on direct, dangerous giveaways.
- Coupling kills the Quinn phantom by construction (a 90 ft/s shot near a net-front defender never velocity-couples, so it is not his possession); the clean-rush case stays silent (defense never couples). See the puck-loss scoping/validation for the five test cases and the holdout 9→~1 drop.
- **LOSING-SIDE COUPLING PRECONDITION (owner ruling 2026-07-16, blind-sample follow-up):** a turnover now requires the defending team to have HELD genuine coupled control (a possession containing a control run — >=2 frames moving WITH a defender) that broke to the attacker. A board battle / net-front scramble / loose puck in traffic won by the attackers — where the defending 'touch' is a lone reach (dir_cos<=0) or a deflection won after a sustained attacker control run — is a 50/50 the attackers won, not a giveaway, and is silenced. Blind-sample effect: the two board-battle false positives drop to ~0 (0.10 / 0.05); Walman, Sharangovich, Garland, Sillinger all preserved (Sillinger's 1-frame giveaway still counts — it is the tail of Werenski's held possession). Corpus turnovers 7570→7391 (-179; 33.2%→32.5% of goals). The two net-front-scramble goals (6, 8) are NOT silenced — the defending team genuinely held the puck there (goalie 16 frames; Power 5 frames), so they are lost possessions, not battles; if the owner wants them reduced that is a separate net-front/danger consideration, not a coupling-possession one.

## Per-goal: two-ledger output vs tape ruling (graded)


### 2025020152-309

**PUCK_LOSS ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| TURNOVER | Cole Sillinger | #4 | 0.33 | 100% |
**COVERAGE ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| E1 | Charlie Coyle | #3 | 0.25 | 48% |
| OUT_OF_ZONE | Zach Werenski | #8 | 0.25 | 47% |
| E2 | Denton Mateychuk | #5 | 0.03 | 5% |

**Rulings:**
- **[MATCH]** PUCK-LOSS: Sillinger = PRIMARY [required] — reality-gated attribution reaches the genuine controller Sillinger (slow-puck control), not the fly-past touch Mateychuk — E4 primary, 100% of the puck-loss ledger.
- **[MATCH]** COVERAGE: Coyle = secondary at most — Coyle carries a secondary coverage share (E1).

### 2025020711-112

**PUCK_LOSS ledger:** *(none)*
**COVERAGE ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| R3 | Luke Hughes | #43 | 0.92 | 100% |

**Rulings:**
- **[MATCH]** COVERAGE: Hughes inside-leverage (R3) [required] — R3 fires on Hughes (0.92) — no regression from iter1.
- **[TOLERABLE]** COVERAGE: Glendening soft-close (R6) — R6 under-fires; the unpressured passer is not caught (blind spot).

### 2025020520-1017

**PUCK_LOSS ledger:** *(none)*
**COVERAGE ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| R3 | Louis Crevier | #None | 0.91 | 100% |

**Rulings:**
- **[MATCH]** PUCK-LOSS: NO turnover — Knight in-crease rebound (owner ruling) [required] — median goalie depth 4.3 ft (in the crease) + rel ~9 (puck moving PAST him, not with him) = a rebound, not a goalie possession; the accepted out-of-crease rule correctly produces no turnover. (The earlier 'Knight = PRIMARY' entry predated the out-of-crease goalie rule the owner later accepted.)
- **[MATCH]** COVERAGE: tight-cover D (Crevier) = secondary — Crevier fires R3.

### 2025020985-153

**PUCK_LOSS ledger:** *(none)*
**COVERAGE ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| OUT_OF_ZONE | Wyatt Kaiser | #44 | 0.21 | 100% |

**Rulings:**
- **[MATCH]** COVERAGE: over-pinch #44 = PRIMARY (out-of-zone/R5) [required] — Kaiser #44's transient severe over-pinch into the goal area fires out-of-zone as primary (100%).
- **[TOLERABLE]** COVERAGE: Nazar minor — not fired; a forward's minor share is below resolution (blind spot).

### 2025020390-554

**PUCK_LOSS ledger:** *(none)*
**COVERAGE ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| OUT_OF_ZONE | Lian Bichsel | #6 | 1.00 | 65% |
| OUT_OF_ZONE | Alexander Petrovic | #6 | 0.53 | 35% |

**Rulings:**
- **[MATCH]** COVERAGE: #6 = PRIMARY [required] — #6 is primary (out-of-zone 1.00) — right player, right order; mechanism is out-of-zone, tape said R4.
- **[TOLERABLE]** COVERAGE: #53 = secondary — not fired this iteration (the E4 that carried #53 in iter1 was reality-gated away as a phantom).
- **[TOLERABLE]** COVERAGE: #14 = some — minor third-player share below resolution (blind spot).

### 2025020332-299

**PUCK_LOSS ledger:** *(none)*
**COVERAGE ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| E1 | Connor Dewar | #19 | 0.50 | 41% |
| OUT_OF_ZONE | Kris Letang | #58 | 0.41 | 34% |
| E1 | Ryan Shea | #6 | 0.27 | 22% |
| E1 | Bryan Rust | #17 | 0.04 | 3% |

**Rulings:**
- **[MATCH]** COVERAGE: Dewar flagged [required] — Dewar is primary (E1, 0.50).
- **[MATCH]** COVERAGE: no E2 misfire on Dewar [required] — E1/E2 exclusion holds — E2 no longer co-fires on Dewar (the iter1 double-fire is fixed).
- **[TOLERABLE]** COVERAGE: #87 soft-close (R6) — R6 under-fires; #87 not caught (blind spot).

### 2025020798-697

**PUCK_LOSS ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| TURNOVER | Steven Stamkos | #91 | 0.03 | 100% |
**COVERAGE ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| E1 | Luke Evangelista | #77 | 0.50 | 54% |
| R3 | Nick Perbix | #48 | 0.42 | 46% |

**Rulings:**
- **[MATCH]** COVERAGE: #48 inside-leverage on Tkachuk (R3) [required] — Perbix #48 fires R3 (0.42).
- **[MATCH]** COVERAGE: Evangelista soft-close (R6) — Evangelista is flagged (E1); player caught, mechanism differs (R6 under-fires).

### 2025020754-381

**PUCK_LOSS ledger:** *(none)*
**COVERAGE ledger:**

| event | player | # | severity | share |
|---|---|---|---|---|
| R3 | Mattias Samuelsson | #23 | 0.60 | 100% |

**Rulings:**
- **[MATCH]** PUCK-LOSS: none — Quinn turnover was a PHANTOM [required] — the reality gate kills it: Quinn is 32 ft from the puck through the buildup and only near it at the shot (a ~90 ft/s puck) — never a defending possession, so no turnover.
- **[MATCH]** COVERAGE: #23 (Samuelsson) = MAJORITY [required] — with the phantom gone, #23's net-front R3 is the majority (100%).
- **[TOLERABLE]** COVERAGE: Quinn = smaller nonzero (vacated w/o support) — Quinn does not fire a coverage event; the support-arrival judgment is a blind spot.

## FAILURE-TO-ACCOUNT — build re-validation (coverage ledger only; puck-loss untouched)

New detector: sustained-nearest to an OPEN scorer in dangerous ice, who never closed AND collapsed INSIDE his man (abandonment). Severity scales with the abandonment margin x openness (not binary).

- **Severity distribution** (n=172): median 0.27, p75 0.49, p90 0.81, max 1.00 — marginal collapses near the thresholds score ~0.12, severe ones ~1.0.
- **(a) #20 primary coverage on 2025020850-875:** YES — Ryan Greene #20 fires FTA as the top (only) coverage event (sev 0.50).
- **(b) no new false positives:** FTA fires on **0** of the 8 validation goals and **1** of the 12 holdout goals (2025020850-875). The only holdout fire is #20 (the correct catch); no previously-clean goal in either set regresses.
- **(c) newly-flagged for tape review:** corpus-wide, **82** goals have FTA as their *only* coverage event (no prior coverage failure). Each is a candidate real abandonment OR a false positive and is flagged for owner eyeball before any aggregation — not silently accepted.

## Rush-defense — INTEGRATED into the puck-loss ledger (owner-approved bucket model)

Clean rushes carry fault by coarse disadvantage BUCKET (EVEN 1.0 / SLIGHTLY 0.5 / BADLY 0.1) x 0.85 baseline rush discount; turnover-rushes route primary blame to the giveaway (already in the turnover ledger) and rush-defense is x0.25; contest gate (contested-beaten -> NULL) + forward x0.65 + one responsible defender preserved exactly. Validated on the 10 pinned goals: model charge matched owner tape on all 10 (every bucket disagreement fell on a goal the contest gate charges NULL or ~0).

- **Fires on 1800 goals** (one responsible defender each). Severity: median 0.21, p90 0.85, max 0.85 (EVEN ceiling 1.0 x 0.85 = 0.85 cap).
- Newly fires on **0** of the 8 validation goals and **0** of the 12 holdout goals (none).
- **Coverage ledger UNCHANGED** (rush-defense adds only PUCK_LOSS records; E1/E2/E3/FTA/R6 byte-stable) and **turnover ledger UNCHANGED at 7570**. Turnover-rush self-collision FIXED: on 2023021159-812 the same player (K'Andre Miller) was both the giveaway AND the rush-responsible-defender; he is now excluded from rush attribution on that goal (a turnover-rush routes primary blame to the giveaway), so he carries his TURNOVER (0.14) and the rush-defense falls through to the next defender (Braden Schneider, 0.21).
- **Build is now fully deterministic:** two consecutive full builds are byte-identical across all three ledgers (COVERAGE, TURNOVER, RUSH_DEFENSE). The prior R3<->OUT_OF_ZONE run-to-run jitter is resolved by pinning row order before the fire loops + a stable-ordered non-overlap keep-max + a deterministic nearest-defender tie-break. Leaderboard ranks are now reproducible.

## Zero-blame — PER LEDGER (not targeted)

- **PUCK_LOSS:** 52% of kept goals assign ~0 (median total 0.00).
- **COVERAGE:** 26% of kept goals assign ~0 (median total 0.32).

The split is healthy: puck-loss is ~0 on the majority of goals (no turnover), coverage fires on most. Separating the ledgers removed the iter1 problem where broad turnover firing polluted a single combined number down to 11.7% clean.

## Blind-spots ledger — WHAT THIS METRIC CANNOT SEE (standing; travels with the metric)

1. **Botched-reception vs bad-pass judgment edge.** Attribution credits the last GENUINE controller (slow puck); a defending touch that turned the puck (>=25 deg) within stick-reach is treated as a botched reception (that receiver). Where a fly-past touch is really a failed reception (or vice versa), the attribution can shift one player (the Sillinger/Mateychuk edge).
2. **Soft-close on the passer (R6) under-detection.** Keyed on the recorded primary assister as the final-pass completer; the penultimate passer is not tracked, and unpressured passers who are not assist1 are missed (Glendening, #87). Several 'right player' matches land via E1, not R6.
3. **Minor third-player shares.** The model resolves primary/secondary; diffuse minor contributions (#14, Nazar, Quinn's support-arrival share) fall below resolution.
4. **Support-arrival judgment.** A defender who vacates the net-front expecting help that never arrives (Quinn) is a judgment-edge failure the geometry does not separate from a legitimate rotation.
5. **R5 upstream is partial.** Out-of-zone fires the vacator directly and discounts an overlapping beaten recoverer, but the full recoverer->vacator share flow is approximate.
6. **Goals-only (standing).** We see only failures that led to goals, never identical ones that did not; the metric cannot credit coverage that prevented a shot.
7. **Sub-2-frame up-ice giveaways (10 Hz limit).** A giveaway that lasts ~1 frame in the O/neutral zone (a 90 ft/s strip) cannot establish coupling, so the turnover that springs the rush is uncharged (Drysdale 2024020809). Whole-ice detection removes the zone barrier but not the temporal one; the coupling bar is deliberately NOT lowered to chase these (that reintroduces the fast-puck phantoms).
8. **Deflection vs botched-play, and botched-reception vs bad-pass (pre-state judgment edges).** Turnover attribution/classification depends on the puck's pre-interaction speed and heading; borderline redirections and receptions will be miscalled at the margin.
9. **Goalie rebounds vs control.** A goalie is charged with a turnover ONLY when the puck genuinely moves WITH him — tightly coupled (rel<5) and moving in his direction for >=0.5s — then he loses it (a real puck-handling giveaway). The common case (goalie planted in the crease, puck moving past at rel ~8-10) is a rebound, not his giveaway, and is excluded. NOT captured (blind spot): a goalie who kicks/steers a rebound into empty space that the other team buries — that reads as an ordinary rebound in tracking.
10. **Fast sub-coupling mishandles that Q2 (turnover detector) cannot catch.** A rush sprung by a giveaway too brief to establish coupling (a bobble/mishandle, not a sustained possession) is not flagged turnover-caused, so its rush-defense is not routed to the giver (Benn 2023020356: owner tape = turnover-caused 1-on-1, but Q2 does not fire; the model still charges ~0 by reading it as a breakaway). Same 10 Hz / coupling floor as the Drysdale up-ice case, now on the rush-origin side.
11. **Irreducible one-body bucket ambiguity at the EVEN/SLIGHTLY boundary.** A 2v2 rush and a 1-on-2 rush can measure identically at the threat frame (Cozens and Lundell both = 2v2; owner tape reads one EVEN, one SLIGHTLY). No count separates them — the coarse bucket cannot resolve a single body at the 1.0/0.5 line. Output-neutral wherever the contest gate charges NULL or ~0 (as on both pinned examples); only matters on a boundary goal whose responsible defender also failed to contest.
12. **[RESOLVED 2026-07-16] Coverage R3 vs OUT_OF_ZONE run-to-run jitter.** Was: ~104 records (52 goals) swapping between R3 and OUT_OF_ZONE across builds (non-deterministic keep-max tie on identical windows; root cause = unpinned row order feeding recs order, the oz_players last-write-wins, and the cap-loop group order), moving ~141 player-season totals by up to 0.77. FIXED by pinning row order before the fire loops + stable-ordered non-overlap keep-max + deterministic nearest-defender tie-break; two consecutive builds now byte-identical across all three ledgers. Kept here for provenance.
13. **Net-front-responsibility abandonment not always caught (coverage miss).** A defender who leaves the net-front and the man he was responsible for scores is not always flagged. 2023020729-782 (coverage blind holdout): owner ruled #83 left the net-front; the model fired R3 on #20 + E2 and missed the #83 net-front abandonment. One clean miss in the 12-goal fresh coverage holdout (~9-10/12 acceptable, consistent with the prior holdout) — within tolerance, logged here rather than papered over.
14. **Soft zone-abandonment leaving a standing-open man.** A defender (often a collapsing forward) who is nearest a perpetually-open attacker in dangerous ice and never closes, with no break-open (E1), no net-front (R3), and no passer-pressure miss (R6) to trigger existing detectors. (2025020850-875, #20 Ryan Greene: he collapses to his mapped centre while the scorer stays open 18 ft to the side — every coverage gate misses it. A candidate FAILURE-TO-ACCOUNT detector is scoped for owner review.)

## Scorecard + status

- **13 MATCHES, 6 TOLERABLE MISSES, 0 FAILURES.** All four iter1 FAILURES (Sillinger attribution, #23 majority, #44 over-pinch, Dewar E2 double-fire) are resolved.
- Honest caveats: several 'right player' matches land via a different mechanism than the tape named (R6 soft-close still under-fires, so Evangelista/Dewar fire via E1; #6 fires via out-of-zone, not R4). Out-of-zone (8.3k) and E4 (12.8k) still fire broadly; severity scaling and the two-ledger split keep them honest, but calibration is a standing item.
- No aggregation or leaderboard was run — the eye-test-first gate is intact. Per the plan, a **fresh-goal blind holdout** (goals chosen deterministically, not by the model) is the next step before anything aggregates.

**STOP — owner review of the two-ledger validation before the blind holdout.**
