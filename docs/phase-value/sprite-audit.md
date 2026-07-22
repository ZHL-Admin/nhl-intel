# Sprite audit of the state engine — episode start_type + entry timing at goals (REPORT-ONLY)

Independent 10 Hz ground-truth from the PPT goal-replay full track, seasons 2023-24, 2024-25, 2025-26. Runs before any Stage 3 fitting; report-only input to Stage 5. Constants: window 8.0s, puck-present ≥80%, max jump 15.0ft, hysteresis 1.0s (10 frames), blue line x=25.0, carry 6.0ft.

## Attrition
- universe (5v5 non-EN goals, segment-covered, 2023-24–2025-26): **17,075**
- sprite payload exists: **16,914** (99.1%)
- parses (>=2 puck frames in window): **16,914**
- **track usable** (present ≥80%, no >15.0ft jump): **16,074**  (floor 500: OK)
- median usable working span: 8.0s

## Entry-detection status mix (usable goals)
- established_full_window: 8,550 (53.2%)
- entry: 7,522 (46.8%)
- unclear: 2 (0.0%)

## E1 — episode start_type vs sprite entry timing
**Architecture note (finding 1 is contained):** the headline components never consume the rush label — Fit A (`deny`) counts episode starts of EVERY non-faceoff type, and Fits B (`suppress`) / C (`escape`) are label-blind. Any rush-label contamination is localized to three published DIAGNOSTICS — `c_seq_rush`, `V(P_OZ_RUSH)`, `deny_rush_coef` — each of which carries the caveat where it surfaces. Per the decomposition below, `start_type='rush'` is documented as an **event-space category only** (scorer-recorded precursor events) with **no positive association** to tracking-fast entries at goals — it is ANTI-SELECTED (precision below base rate at every k), not a small subset.

### Aligned window (zero-duration episodes) — the apples-to-apples view
For zero-duration goal-only episodes the PBP rush lookback (≤4s before the goal) and the sprite window measure the SAME moment, so this is the fair precision/recall.
n = **8,326**. Rows = episode start_type, cols = sprite_rush_4 (entry ≤4s):

| start_type | sprite_rush_4=True | False | rush-rate |
|---|---|---|---|
| rush | 236 | 661 | 26.3% |
| carry_other | 2,661 | 4,768 | 35.8% |
- start_type='rush' vs sprite_rush_3: **precision 0.143 vs base rate 20.4% (BELOW base (anti-selected))**, recall 0.075 (sprite-rush goals at k=3: 1,699)
- start_type='rush' vs sprite_rush_4: **precision 0.263 vs base rate 34.8% (BELOW base (anti-selected))**, recall 0.081 (sprite-rush goals at k=4: 2,897)
- start_type='rush' vs sprite_rush_5: **precision 0.338 vs base rate 43.3% (BELOW base (anti-selected))**, recall 0.084 (sprite-rush goals at k=5: 3,603)
- start_type='rush' vs sprite_rush_6: **precision 0.386 vs base rate 49.9% (BELOW base (anti-selected))**, recall 0.083 (sprite-rush goals at k=6: 4,156)

### Full sample — WINDOW-MISMATCHED (report-only)
Full-sample start_type reflects the SEQUENCE ORIGIN (which may precede the goal by many seconds) while sprite_rush measures ENTRY-TO-GOAL, so low alignment here is partly a window mismatch, not a pure error. Kept for completeness; do not read as apples-to-apples.
n = **16,068**. Rows = episode start_type, cols = sprite_rush_4 (entry ≤4s):

| start_type | sprite_rush_4=True | False | rush-rate |
|---|---|---|---|
| rush | 370 | 1,238 | 23.0% |
| forecheck | 183 | 1,080 | 14.5% |
| carry_other | 3,518 | 8,347 | 29.7% |
| oz_faceoff | 115 | 1,217 | 8.6% |
- start_type='rush' vs sprite_rush_3: **precision 0.123 vs base rate 14.7% (BELOW base (anti-selected))**, recall 0.084 (sprite-rush goals at k=3: 2,370)
- start_type='rush' vs sprite_rush_4: **precision 0.230 vs base rate 26.1% (BELOW base (anti-selected))**, recall 0.088 (sprite-rush goals at k=4: 4,186)
- start_type='rush' vs sprite_rush_5: **precision 0.301 vs base rate 33.5% (BELOW base (anti-selected))**, recall 0.090 (sprite-rush goals at k=5: 5,377)
- start_type='rush' vs sprite_rush_6: **precision 0.361 vs base rate 39.2% (BELOW base (anti-selected))**, recall 0.092 (sprite-rush goals at k=6: 6,293)

Cross-check: oz_faceoff goals established_full_window (or crossing-free): 1,102/1,332 (82.7%) — expect overwhelming.

### Rush-label decomposition — the label is ANTI-SELECTED, not a small subset
At every k the aligned **precision sits BELOW the base rate** (0.143 vs 20.4%, 0.263 vs 34.8%, 0.338 vs 43.3%, 0.386 vs 49.9%): a random label would pick MORE tracking-fast entries than `start_type='rush'` does. Decomposing the **897** rush-labeled aligned goals: **54.3% show NO entry at all** (established_full_window — puck in-zone the whole 8 s window), and the 45.7% with an entry do not cluster in 4–7 s (median 3.7 s, only 37% in 4–7 s). A **majority have no tracking entry.**
**Caption for the three rush diagnostics** `c_seq_rush`, `V(P_OZ_RUSH)`, `deny_rush_coef` (carry verbatim wherever they surface, with the precision-vs-base numbers): _defined by scorer-recorded precursor events; the sprite audit found no positive association with tracking-fast entries at goals; event-space category only._
Recall (~0.09, flat across k) confirms the ceiling is ABSENT events (entries that generate no PBP event are invisible), so no PBP-side redefinition recovers them — the pre-committed possession-proxy limit.

### E1c — false rush-qualifier source: blocked-shot owner × zone (report-only follow-up)
Blocked-shots in the ≤4 s pre-goal window across the **487** no-tracking-entry rush-labeled goals, split by owner (relative to the scoring team) × raw `zone_code`; `n_qualifies` = how many pass `seq_rush`'s own owner-relative D/N + post-faceoff test:

| owner | zone_code | in window | qualifies |
|---|---|---|---|
| attacker-owned | D | 408 | 408 |
| attacker-owned | O | 1 | 0 |

**What the split shows — it REFUTES the N-zone/defender-owned hypothesis.** The qualifying blocked-shots are **408/408 attacker-owned with `zone_code='D'`** — zero defender-owned, zero N-zone. Mechanism the numbers support: `seq_rush` keeps `zone_code` for attacker-owned events, so a block the SCORING team owns coded in its own defensive zone (`'D'`) satisfies the D/N precursor and fires the rush label. But these are the `established_full_window` goals — the puck is tracked in the offensive zone the whole 8 s — so the block's recorded D-zone location/timing is inconsistent with the tracked possession; the block-location coordinate (or its ±2 s PBP timing) is the unreliable input, not the owner/zone rule. A real, correctly-timed attacker-owned own-zone block within 4 s of a goal entails a tracked zone entry within 4 s; no entry appears anywhere in the 8 s window on any of the 408, so these records are displaced in time by more than the clip span or misrecorded outright, and they share the exact owner-and-zone cell of the legitimate counterattack precursor, so no PBP-side rule can separate them.

**Consequence for the v1.1 note (correction):** the false qualifiers are attacker-owned **D-zone** blocks — the SAME owner×zone cell as the legitimate _block-in-own-D → counterattack_ precursor. So there is **no clean owner×zone rule** that drops the false ones without also destroying legitimate counter-rush starts, and the specific _drop-N-zone-blocks_ candidate does not apply here (there are no N-zone blocks). The surgical fix a v1.1 pass would need is a **location/timing-consistency check** on the block (does the block coordinate corroborate an actual zone exit before the entry?), which at goals is a tracking-only discriminator; wholesale blocked-shot exclusion is still wrong (it would erase the legitimate cell). **No PV action — report-only, do-not-touch on the production sequence engine applies.**

## E2 — entry-to-goal time (the independent instrument on PV-D013)
Entries (n=7,522): median 3.80s; p25 2.80s; p75 5.30s.
- share of entries < 2.5 s (below the 5 s tick grid's half-tick floor): **13.6%**
- share of entries < 5.0 s (within one rush-state lifetime): **70.2%**
Among sprite-rush entries specifically, the < 2.5 s share is the population the 5 s grid structurally excludes from P_OZ_RUSH — the direct measurement behind PV-D013's granularity artifact.

## E3 — PV-D008 audit: zero-duration goal-only episodes
Usable goals whose episode is zero-duration: **8,326**. Claim under test: predominantly genuine rapid entries, not scorer under-recording of longer possessions.
- entry: 4,820 (57.9%)
- established_full_window: 3,505 (42.1%)
- unclear: 1 (0.0%)
- of those with a detected entry: median entry 3.60s; share < 2.5 s 15.4% (rapid entries support the claim; established_full_window would suggest under-recording).

**Reframe (finding 2 changes `deny`'s meaning, not its construction):** `deny` measures **event-visible threatening sequences allowed**, not all threatening sequences; the ~42% established_full_window share is under-recorded settled possession the PBP engine cannot see. The accounting stays internally consistent because `C_seq` prices exactly the same universe the coefficient counts. PV-D011 handling is unchanged (episode start → Fit A, goal xG → Fit B, exposure filter on stint totals); the zero-duration population is material to goal coverage and Fit B's xG mass, NOT to Fit A's episode counts.

## E3b — arena diagnostic on the under-recorded share (finding 2)
established_full_window share within zero-duration episodes, per arena-season (n≥20 goals): league mean **42.1%**, across 96 arena-seasons spread p10 35.3% / median 41.9% / p90 49.7% (sd 5.9 pts).
If this concentrates by arena, `deny` inherits scorekeeper bias the way hits/GV/TK do (int_rink_bias). Report-only now; flagged as a **Stage 5 input** and a **v1.1 rink-adjustment candidate** for the possession proxy. Top/bottom arena-seasons:
  - Bridgestone Arena 2025-26: 58% (n=72)
  - Ball Arena 2024-25: 58% (n=86)
  - Madison Square Garden 2024-25: 56% (n=95)
  - Canadian Tire Centre 2024-25: 29% (n=73)
  - Benchmark International Arena 2025-26: 32% (n=82)
  - United Center 2023-24: 32% (n=75)

## Honest limits
- **Conditioning on success:** this audits labels AT GOALS only; precision/recall here do NOT transfer to non-goal episodes (the vast majority of the model's exposure).
- No exit validation, no non-goal validation.
- **Anchor is arrival, not release** (replay-probe read): the release-frame pinning finds the puck's arrival/in-net instant, ~5–15 frames AFTER true shot release, so entry-to-goal times include shot flight and `sprite_rush_k` is slightly **conservative** (real entries are marginally faster than measured).
- Tolerate ±2 s of PBP timing slop in any event-to-frame comparison; the geometric release-frame pinning avoids clock decoding but is not exact.
- Clip-start truncation right-censors entry times beyond ~8 s (established_full_window absorbs them).
- carry_flag (nearest attacking skater within 6 ft at the crossing) is descriptive-only and deferred in this pass pending a team-labeling reliability check (Section A2/C); noted rather than improvised.

## Inherited banner caveat (verbatim, carried from research/replay-probe/reports/replay-build.md)
> **This sample is success-conditioned: it contains GOALS ONLY.** Every sequence in `raw_ppt_replay` ended in a goal; there is no tracked non-goal counterfactual anywhere in the payload. So this data **supports descriptive goal-anatomy and goal-as-the-unit analysis** (what a goal buildup looks like, who was where, how the puck moved) **but cannot support predictive "what causes goals" claims** — any value/credit/finishing model built here is conditioned on success and has no matched non-goal sample to contrast against. That sample does not exist in this data and would have to come from elsewhere (full-game tracking). Carry this caveat verbatim into anything built downstream.
