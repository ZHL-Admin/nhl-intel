# Role-Conditioned Expected Trajectories — Measurement Specification

**Status: DEFINITION — updated after review round 1. No profiles, no diagnosis,
no per-player output until the variance-band gate (Phase 2) passes on tape.**

> **Revision note (post-review 1).** This version incorporates an agent review
> (9 issues) and the owner's rulings:
> - **Issue 1 (baseline framing) — corrected.** The goals-only norm is NOT a
>   "failure baseline." On a large fraction of goal-rushes the strong-side D
>   defended the rush normally and the goal came from elsewhere (a different man
>   left open, a rebound, a screen, a clean shot). So the median path is close to
>   a NORMAL rush-defense path, only MILDLY selected. Every deviation is framed as
>   "deviation from the **typical** rush-defense path" — blame verbs dropped, no
>   correctness asserted. Read-only confirm (b) does double duty: if non-goal rush
>   tracking exists, compare the goal-rush norm to the all-rush norm (close ⇒
>   goals-only norm validated as a "normal" proxy, survivorship tilt empirically
>   small; divergent ⇒ the concern was real). If non-goal tracking does not exist,
>   the mild selection is noted honestly and we proceed (the norm is still
>   meaningful because most goal-rushes are ordinary defense).
> - **Issue 2 (clock) — real seconds aligned on the SHOT** (shot = 0, counting
>   real seconds back). Progress-normalization to [0,1] is rejected because it
>   would warp away duration and destroy the speed/timing deviation signals.
> - **Issues 3–9 — accepted as written:** entry-geometry role ID (not the weak
>   season-side); designated entry-carrier as the trajectory anchor; per-axis
>   ORTHOGONALIZED bands; "tight" = per-axis IQR ≤ ~⅓ of the 5–95% inter-defender
>   spread AND beats a time-scrambled placebo; entry-captured filter with reported
>   count; type = 5v5 + entry_type ∈ {carried, passed} + rushdef EVEN; the
>   diagnosis may live on either D (strong-side is primary but not assumed
>   culprit).
>
> Three read-only confirms (a: qualifying entry-captured count; b: non-goal rush
> tracking existence + norm comparison if present; c: middle-lane-entry and
> drop-pass frequency) run before numbers are finalized. Nothing else computed.

This spec replaces the hand-built single-skill detector approach (gap control).
Instead of hand-defining each defensive skill with guessed thresholds, we let
thousands of same-type goals define the EXPECTED behavior empirically, and
measure each player's DEVIATION from it. Every skill (gap, forcing outside,
speed, collapse) becomes a *direction of deviation* from one expected path.

---

## 0. Why this approach (and why it replaces the detector approach)

The hand-built detectors (gap, shot-block, etc.) failed or struggled because
every threshold was a place to be wrong, discovered one painful tape-review at a
time. This approach inverts it: **the average of thousands of goals of the same
type IS the definition of typical**, no thresholds to guess. A player either
fits the empirical pattern or deviates, and the DIRECTION of deviation is the
description ("more central than typical while the carrier went wide," "closed to
the net earlier than typical," "lost more separation than typical").

This is role-conditioned expected-trajectory modeling. It is a DESCRIPTIVE /
diagnostic engine for explaining what happened on a goal, which sidesteps the
**per-player-season aggregation** sample wall (F29/F32/F34): we describe goals in
front of us, not project a player's season. It does not by itself resolve the
mild selection of a goals-only norm — that is handled empirically by confirm (b)
and framed honestly (Issue 1 ruling).

---

## 1. Scope — start narrow, ONE clean type first

**Phase 1 type: even-strength CONTROLLED RUSH ENTRIES, tracking DEFENSEMEN.**
Type filter (all three; reuse existing classifiers, do not rebuild):
- **5v5** (the existing even-strength tracked-goal universe), AND
- **entry_type ∈ {carried, passed}** (controlled entry; excludes dumped /
  off-frame-start), AND
- **rushdef bucket = EVEN** (defense not outnumbered) — keeps odd-man rushes out,
  which §1 defers, AND
- **entry captured**: a real in-window entry (entry_frame present, entry_frame <
  goal_frame, entry→shot length in the sane band). Report the surviving count.

Chosen deliberately: a D defending a controlled even rush has a well-defined job
(retreat, protect the middle, force the carrier outside); high-frequency ⇒ a
sharp empirical norm; exactly where "average of many = typical" is tightest.

Explicitly DEFERRED to later, separate types (pooling muddies the norm — the
contamination gap control hit when a 3-on-2 turnover scramble polluted it):
powerplay, odd-man rushes/scrambles, settled o-zone play, turnover-caused rushes,
dumped/off-frame entries. Each becomes its own type with its own norm once
Phase 1 validates.

---

## 2. The pipeline

- **Phase 0** — Type isolation + frame normalization.
- **Phase 1** — Build the expected D-trajectory (the empirical typical path).
- **Phase 2** — VARIANCE-BAND GATE (hard stop): is the pattern tight?
- **Phase 3** — Per-goal deviation + named deviation directions.
- **Phase 4** — Tape validation of deviations.

---

## 3. Phase 0 — Type isolation + frame normalization

- **Isolate** the Phase-1 type (§1). Report the count (need thousands for a
  stable norm; report how many qualify with the entry captured).
- **Normalize every goal into one coordinate frame** so trajectories are
  superimposable:
  - defended net at origin; **depth = 89 − attack_sign·x** (0 = defended net,
    ~63 = defensive blue line), so the attack always proceeds toward decreasing
    depth (existing transform);
  - **lateral = attack_sign·y**, THEN a further **carrier-side flip**: multiply
    lateral by sign(carrier lateral at the entry frame) so the entry carrier's
    side is always the same (e.g. always +). **Middle-lane entries** (|carrier
    entry lateral| below a small band) are side-ambiguous — the same near-center
    problem A0 found for D side; report their frequency (confirm c) and handle
    them as a labeled subgroup (flip undefined → keep unflipped and flag), do NOT
    force a sign.
- **Define the role by ENTRY-MOMENT GEOMETRY, not season side** (Issue 3): the
  strong-side D = the D who at the entry frame is goal-side of the entry carrier
  AND on the carrier's lane (nearer the carrier's lateral than the other D). The
  weak-side D is the other. Report how often the role is unambiguous vs contested
  (both D similar on the lane). Season tracking-side is NOT used for role ID (A0
  showed it is only ±4 ft strong).
- **Anchor = the DESIGNATED ENTRY CARRIER** (Issue 4): one fixed attacker (the
  puck-carrier at the entry frame), tracked for the whole segment even if the
  puck is later passed. The trajectory is defended relative to THIS man + the net,
  so a drop-pass does not teleport the anchor. (Carrier-change frequency reported
  in confirm c; if high, a later type may re-anchor to the puck.)
- **Re-time on a REAL clock aligned on the SHOT** (Issue 2): t = 0 at the shot
  (release_frame), counting real seconds back (t = −(goal_frame − frame)/10). The
  entry end is ragged (rushes differ in length) — that is intended; real seconds
  preserve speed and lateness as measurable deviations. Trajectories are compared
  at common real-time offsets (e.g. −2.5 s … 0 s at 0.1 s steps), truncated to
  each goal's captured span.

---

## 4. Phase 1 — Build the expected D-trajectory (the empirical typical path)

For the tracked role, across all qualifying goals, at each real-time offset:
- Collect the defender's position in **RELATIVE coordinates against two anchors,
  on orthogonalized axes** (Issue 5):
  - **relative-depth** = defender depth − carrier depth (goal-side margin);
  - **relative-lateral** = defender lateral − carrier lateral (inside/outside
    margin), on the carrier-side-flipped lateral;
  - **carrier-separation** = straight-line D↔carrier distance, reported ALONGSIDE
    (not in addition to) the two axes above, since it is ≈ f(rel-depth,
    rel-lateral) + carrier speed and is NOT orthogonal — used for the "beaten by
    speed" reading, flagged as overlapping the depth/lateral axes so a single
    breakdown is not double-counted as three.
- Compute the **expected path** = the median (and mean) relative trajectory over
  all goals, with a **per-axis variance band** (IQR / 5–95% spread) at each
  time offset. Per-axis (not a single 2D IQR) because Phase 3 decomposes by axis.
- Build the same for the **weak-side D** (a rush has two D with different jobs).

Output: the expected relative-trajectory curves + per-axis bands. This curve IS
the empirical definition of "what a D typically does on an even controlled rush
that preceded a goal." No thresholds were set.

---

## 5. Phase 2 — VARIANCE-BAND GATE (hard stop)

Deviation is meaningful only if the typical pattern is TIGHT. If defenders do
wildly different things on "the same" rush, the band is huge and "deviation" is
noise.

- Report the per-axis band width at each time offset, as a fraction of the range
  of defender positions at that offset.
- **Pre-registered "tight" (Issue 6):** at each of the key offsets (entry, mid,
  shot) and on each axis (rel-depth, rel-lateral), the **IQR must be ≤ ~⅓ of the
  5–95% inter-defender spread**, AND the time-ordered band must be **materially
  tighter than a time-scrambled placebo** (same defenders, shuffled time index —
  the honest analog of the shuffled-identity placebo used across the program). A
  real time-ordered pattern beats the scramble; a smeared one does not.
- **Tight + beats placebo → proceed.**
- **Wide / no better than placebo → the type is not tight enough:** either (a)
  split finer (by rush speed, #attackers already fixed at EVEN, entry lane) and
  re-test, or (b) conclude the pattern is not recoverable at this granularity. Do
  NOT build deviation on a smeared norm.
- Show the expected path + band **visually (a plot)** so the owner can SEE whether
  defenders converge or scatter.

**STOP for owner review of the variance band before Phase 3.** Analog of the A0
knob-derivation gate: if the foundation doesn't separate, we don't build on it.

---

## 6. Phase 3 — Per-goal deviation + named deviation directions (only after Phase 2)

For each goal, take the actual defender trajectory and measure deviation from the
typical path, decomposed into interpretable directions, each **in units of the
per-axis variance band** (a deviation of N band-widths, so "large" is relative to
how consistent the pattern actually is):
- **Lateral-inside deviation** — defender more central than typical while the
  carrier goes wide → "more central than typical / carrier had the middle."
- **Depth deviation** — defender closer to net than typical too early → "closed
  to the net earlier than typical."
- **Separation deviation** — carrier gains more distance than typical → "lost more
  separation than typical / carrier's speed" (flagged as overlapping depth+lateral
  per §4).
- **Timing deviation** — the defender's key positions lag the typical clock →
  "later than typical" (well-defined only because the clock is real seconds, §3).

**Framing (Issue 1 ruling):** each direction names a **deviation from the typical
path**, NOT a verdict of wrongdoing and NOT an assertion of correct. The baseline
is typical rush-defense on plays that preceded a goal (mildly selected, not a
failure path). A deviation flags what was UNUSUAL vs that typical; some deviations
are good (a strong aggressive step-up reads as an inside/early deviation).
Whether unusual = bad still needs the outcome or a human read. Diagnostic aid,
not an automatic grade. The deviation may live on **either D** — a strong-side
deviation is not automatically the culprit (Issue 9).

---

## 7. Phase 4 — Tape validation of the deviations

- ~5 LARGE-deviation goals (per named direction where possible): confirm on tape
  that the flagged deviation corresponds to a REAL, visible thing of the named
  kind (e.g. "more central than typical" goals really show the carrier getting
  the middle).
- ~5 LOW-deviation goals: confirm these look like on-pattern, ordinary defending.
- Report the reconstructions for owner tape judgment. Only if the deviations match
  the tape is the engine validated.

**STOP for owner tape review. No per-player aggregation, no season profile, no
rating until deviations are tape-confirmed.**

---

## 8. What this is and isn't

- **IS:** a descriptive/diagnostic engine — "on this goal, this defender deviated
  from the empirical typical path in this named way." Powers goal-anatomy.
- **IS NOT (yet):** a season player rating. Whether per-player deviation
  aggregates into a stable trait is a LATER question, gated behind the same
  stability tests (F29/F32/F34), NOT assumed.
- The engine REPLACES the hand-built single-skill detectors: every skill is a
  deviation direction from one expected-trajectory model, not a threshold-tuned
  detector.

---

## 9. Discipline (carried from the whole program)

- Definition-first: this doc is reviewed before code.
- Hard gate at Phase 2 (variance band + placebo) before diagnosis is built.
- Tape-validate deviations (Phase 4) before any aggregation.
- Data-derived, not hand-set: the expected path and band come from the goals; the
  only "thresholds" are the reused type filter and the pre-stated "tight"
  definition, reviewed on the plot.
- Start narrow (one type), expand only after validation.
- Applies to the tracked role; extends to all five skaters and other goal-types
  as separate, later norms.
