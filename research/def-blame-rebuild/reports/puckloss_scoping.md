# Puck-Loss Ledger · Trajectory-Possession Rebuild — SCOPING (no build)

Scoping only: definitions, projected fire rates, phantom checks, test-case behavior for owner review
BEFORE any build. **Coverage ledger is FROZEN and untouched.** Two-ledger separation holds. Nothing here
modifies a ledger; all numbers are read-only prototype projections on 2025-26 (representative), and the
five required test cases. Limits stated throughout: goals-only, and 10 Hz (a 90 ft/s puck moves 9 ft/frame,
so fast passes/shots are 1–2 frames of transit — clean on slow puck-management, coarse on fast transition).

## Part 1 · Trajectory-based (coupling) possession

**Coupling = possession.** A skater owns the puck over a segment when the puck stays within stick-reach
(≤6 ft) AND its velocity tracks his (relative speed ≤12 ft/s — the puck moves *with* the carrier), not
merely when he is nearest. A puck near a skater but moving fast relative to him (a shot/pass passing by) is
NOT his — this kills the Quinn phantom **by construction**.

**Interaction points** (trajectory changes: direction >~30° OR speed jump >~20 ft/s) classify as:
CONTROL/HANDLE (stays coupled to the same skater — a deke), PASS (velocity change at A, straight transit,
B couples), DEFLECTION of an incoming-fast puck (pre-state fast *toward* the player, redirect near net →
NOT a possession/turnover, it was never his), BOTCHED PLAY (slow/coupled puck caroms to open ice), SHOT
(large speed increase toward net), LOSS (coupling breaks to no one/other team). The deflection
discriminator is pre-state speed + heading toward-vs-away — a judgment edge on borderline redirections
(stated limit).

**Possession disagreement (the phantom size), 2025-26:** of **446,312** frames the old proximity model
called "control," coupling **rejects 22% as phantom** (puck near but not velocity-coupled — fast-puck
misreads) and **reassigns 7%** to a different owner → **28% total disagreement**. That 28% is the scale of
the possession error the current E4 is built on, consistent with the ~33% phantom-turnover rate the reality
gate already exposed.

## Part 2 · Whole-ice turnover detection

**Definition:** a coupled team-A possession (≥3 coupled frames) that ends in an interaction NOT handing
control to another team-A skater, followed by team-B coupling — **anywhere on the ice** (the depth<64
defensive-zone restriction is removed). Attribution: the last team-A skater who was *coupled* (genuine
control), or the botched receiver per the Sillinger rule (puck arrived and coupled briefly then caromed);
a pass that never coupled to the intended receiver is the passer's. Goalies eligible. The
botched-reception-vs-bad-pass call is a logged judgment edge.

**Severity** (proposed): danger of the turnover location/resulting chance × directness (time/passes from
giveaway to goal). Cap 1.0. This is essential — see the fire rate.

### The five required test cases (prototype, full-window coupling)

| goal | expected | result | why |
|---|---|---|---|
| 2024020809-498 (Drysdale up-ice) | fire | **PARTIAL** | whole-ice removes the DZ barrier (the structural fix), but the actual giveaway (Farabee, ~1 frame in the O-zone at depth 178) is **below 10 Hz resolution** — only 2 coupled defending frames exist on the whole goal. Sustained up-ice giveaways WILL be caught; a 1-frame O-zone strip stays coarse. Honest limit. |
| 2023020882-474 (clean rush) | silent | **SILENT** ✓ | Vegas never couples the puck (0 coupled D frames) — correctly no turnover. |
| 2025020754-381 (Quinn phantom) | silent | **SILENT** ✓ | 0 coupled D frames — the 90 ft/s shot never couples to Quinn; the phantom dies by construction. |
| 2025020152-309 (Sillinger) | catch | **CATCH** ✓ | 52-frame coupled Columbus possession (Coyle→Sillinger→Werenski); attribution to the genuine coupled controller (Sillinger), not the fly-past. |
| 2025020520-1017 (goalie) | catch | **CATCH** ✓ | goalie coupling captured (Crevier→Spencer Knight); goalie-eligible attribution. |

**4 of 5 resolve correctly. The 5th (Drysdale) is structurally addressed (whole-ice) but temporally
limited (10 Hz can't establish possession for a 1-frame giveaway).** The two false-positive killers (Quinn,
clean rush) both resolve, which is the headline win.

**Fire rate + phantom check (2025-26):** a whole-ice turnover *exists* on **46%** of goals (any coupled
defending possession that flips). That is far above the owner's tape rate (~1 in 12 ≈ **8%**), because most
of the 46% are harmless (a neutral-zone bobble loosely followed by a goal). Like FTA's naive 24.6%, the raw
existence rate is tautological; **directness × danger severity is what concentrates real blame** — a build
must gate charged turnovers to the ~8–15% that directly spring the goal, with the rest scoring ~0. The raw
46% is NOT the charged rate; it is the candidate pool.

## Part 3 · Rush classification + odd-man-scaled rush defense

**Origin split (2025-26, 7,694 goals):** rush (carried/dumped/passed) **40%** · settled/pre-existing
(off_frame_start) **58%** · other 2%.

**Branch for rush goals:** TURNOVER-RUSH (a Part-2 turnover created it → PRIMARY fault to the giveaway in
the puck-loss ledger; any rush-defense fault further discounted) vs CLEAN RUSH (no turnover → a new
RUSH-DEFENSE event, odd-man scaled).

**Odd-man at the point of danger** (defenders goal-side of the puck vs attackers in the danger lane,
measured at the final approach — backcheckers who recover are counted). Most common configurations:

| defenders v attackers | goals | reading |
|---|---|---|
| 1 v 1 | 850 | fair 1-on-1 — full expected-to-stop |
| 2 v 2 | 596 | even — full |
| 3 v 2 | 558 | defense has numbers — full (this shouldn't score) |
| 2 v 1 | 516 | defense up a man — full |
| 4 v 3 | 483 | even-ish — full |
| **0 v 1** | **474** | **breakaway — no defender goal-side → ~0 (no play)** |
| 3 v 3 | 453 | even — full |
| 5 v 4 | 369 | even-ish — full |

**Proposed RUSH-DEFENSE severity curve** (fixed function of nd defenders, na attackers at danger):

| situation | scale |
|---|---|
| nd ≥ na (even or defense has numbers) | **1.0** — should have been stopped |
| na = nd + 1 (down a man, e.g. 2-on-1) | **0.5** |
| na = nd + 2 (down two, 3-on-1) | **0.2** |
| na ≥ nd + 3, or nd = 0 (breakaway / overwhelming) | **~0** — some rushes just beat you |

So a clean 1-on-1 or a beaten 2-on-2 carries full rush-defense fault; a genuine breakaway (474 goals) or a
3-on-1 carries little to none — fault tracks how fair the situation was.

## What the current rush-guarded coverage goals would get

The coverage rush-guard suppressed FTA on fresh rushes (106 fires removed). Under this proposal those goals
route as: TURNOVER-RUSH → puck-loss (if a coupled up-ice/transition turnover is detected and directness-
significant); CLEAN RUSH → RUSH-DEFENSE (odd-man scaled); genuine breakaway/unavoidable → **~0** (correct).
A build would report the exact three-way split; the projection is that a large share of fresh-rush goals are
either clean unavoidable rushes (→0) or turnover-rushes (→ puck-loss), with a minority of fair clean rushes
getting RUSH-DEFENSE fault.

## Limits (stated)

- **Goals-only:** we see only failures that led to goals, never identical ones that didn't.
- **10 Hz:** fast transition is coarse — a sub-2-frame giveaway (Drysdale) can't establish coupling;
  whole-ice removes the *zone* barrier but not the *temporal* one.
- **Judgment edges:** deflection-of-incoming vs botched-play, and botched-reception vs bad-pass, are
  pre-state-dependent calls that will be wrong at the margin.

## Recommendation

Ready in principle: coupling kills the two false positives (Quinn, clean rush) and catches the two real
turnovers (Sillinger, goalie) — the possession foundation is sound and the 28% disagreement quantifies the
prize. Two things the build must get right, both learned from FAILURE-TO-ACCOUNT: (1) **directness-scaled
severity** to bring the 46% candidate pool down to the ~8% charged rate the tape supports; (2) accept the
10 Hz limit on the fastest up-ice giveaways rather than lowering the coupling bar to chase them (that would
reintroduce phantoms). The odd-man RUSH-DEFENSE curve is a clean, fixed function ready to implement.

**STOP — owner rules on build after the fire rates and test-case behavior, as with FAILURE-TO-ACCOUNT.**
