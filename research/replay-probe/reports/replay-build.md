# Replay build — materialization + a real reconstruction read

**Project:** replay-probe (`NIR/research/replay-probe/`) · **Date:** 2026-07-13 · confirmation build.
**Scope:** `dbt run` the two already-written models, then a small **descriptive** reconstruction of the
goal buildup validated by eye against known goals. No fetch, no new modeling, no claims about causation.

> ## ⚠ BANNER CAVEAT — inherited by every downstream project on this data
> **This sample is success-conditioned: it contains GOALS ONLY.** Every sequence in `raw_ppt_replay`
> ended in a goal; there is no tracked non-goal counterfactual anywhere in the payload. So this data
> **supports descriptive goal-anatomy and goal-as-the-unit analysis** (what a goal buildup looks like,
> who was where, how the puck moved) **but cannot support predictive "what causes goals" claims** — any
> value/credit/finishing model built here is conditioned on success and has no matched non-goal sample
> to contrast against. That sample does not exist in this data and would have to come from elsewhere
> (full-game tracking). Carry this caveat verbatim into anything built downstream.

---

## Part 1 — Materialization (the paper feasibility read is now a real one)

`dbt run` of the two written-but-empty models succeeded cleanly. Both are BigQuery **views** over
`nhl_raw.raw_ppt_replay` in `nhl_staging`. Numbers below are queried back from the live views.

### `stg_ppt_tracking_frames` — the 10 Hz frame mart
One row per (goal, frame, on-ice entity); coordinates standardized to center-origin feet.

| season | frame-entity rows | goals |
|---|---:|---:|
| 2023-24 | 13,138,873 | 8,618 |
| 2024-25 | 15,616,698 | 8,635 |
| 2025-26 | 15,965,602 | 8,693 |
| **total** | **44,721,173** | **25,946** |

- **Parse failures: 0.** All **25,946 / 25,946** raw goal sprites materialized (100%). No game or goal
  failed to explode.
- **Coordinates valid:** `x_std ∈ [−101, 101]`, `y_std ∈ [−43.5, 43.5]` — inside the rink envelope
  (±100 boards / ±42.5 to the wall, with the small over-board overshoot expected for pucks/skaters at
  the boards). **Puck share = 7.75%** = exactly 1 of 13 entities per frame (12 skaters + 1 puck) ✓.
- **1,425 distinct player_ids** appear across the three seasons.

### `int_goal_release_frame` — per-goal release/arrival anchor
The single frame per goal where the puck is nearest a net, with all entities at that instant.

- **25,946 goals, 326,456 rows** (~12.6 entities/goal at the anchor frame).
- Anchor faithfulness: the puck at the release/arrival frame is on average **0.24 ft from the goal
  line** — the anchor lands on the net mouth, as designed.
- **Caveat on this model's semantics (confirmed here):** "puck nearest a net" is the **arrival /
  in-net** instant, not the true shot **release**. The reconstruction below detects the actual release
  (last stick contact before the shot flight); the two differ by ~5–15 frames on most goals.

**Net result:** the 26k raw goal sprites are now a queryable 10 Hz frame mart + release anchor. The
opportunity map's headline ("full player+puck tracking for every goal buildup, 2023–26, in-warehouse")
is **materially confirmed**, not just inferred.

---

## Part 2 — Reconstruction of the connective tissue (descriptive, validated by eye)

Play-by-play carries **zero** passes/carries/entries. The premise of Goal Anatomy is that this
connective tissue is **implicit in the trajectories** and recoverable. To test that honestly, the probe
reconstructs — from frames alone, with no ML — the puck-carrier per frame, possession segments,
**passes** (possession moving between same-team players), the **zone entry**, and the **shot release**,
then checks the reconstruction against the recorded scorer and assists (`stg_play_by_play`), which the
reconstruction never sees.

**Sample:** 16 goals (5v5, two assists, regular season), spread across 2023-24 and 2024-25, drawn
deterministically. Code: `src/replayprobe/reconstruct.py`. The decisive eye-check: *does the
reconstructed shooter/scoring-cluster match the player the NHL recorded as the scorer?*

### Headline validation numbers

| check | rate | reads as |
|---|---:|---|
| **Scorer ever within stick-reach (≤5.5 ft) of the puck in the buildup** | **88%** | **the data is faithful** — the recorded scorer is demonstrably present on the puck |
| Recorded scorer is in the reconstructed 3-player scoring cluster | 56% | the buildup chain lands on the right people about half the time |
| **Exact** reconstructed shooter == recorded scorer | **38%** | pure nearest-neighbor attribution is right on clean shots, wrong in traffic |
| Reconstructed scoring cluster overlaps a recorded assister | 56% | passes/carries recover a real assister ~half the time |
| Passes reconstructed per goal | 2 / 3 / 8 (min/med/max) | the pass network is non-trivial and present |
| Zone entry detected | 9 / 16 | the other 7 clips start with possession already in-zone (entry off-frame) — correct nulls |

The 88% vs 38% gap is the whole story: **the tracking faithfully places the scorer on the puck; what's
hard is *attributing* the shot geometrically when bodies are stacked.** This is an attribution-modeling
problem, not a data problem.

### Worked eye-checks (the reconstruction is faithful where the play is clean)

- **`2023020002-787` (EXACT).** Scorer 8477987 walks the puck out from behind the net (fr76→81, stick
  distance 1.2–4.1 ft) and tucks it in at fr82–83. Reconstruction: shooter = 8477987, and **both
  assisters (8481568, 8484144) are in the scoring cluster.** Full chain recovered.
- **`2024020001-1730882` (EXACT).** An 8-pass buildup; reconstructed shooter = scorer 8480002, one
  assister (8479414) in the cluster. Long possession sequences reconstruct well.
- **`2023020001-154` (cluster hit, shooter miss).** Scorer 8476453 carries the slot (fr77, 3.1 ft) and
  shoots; the puck **flies ~50 ft to the net** (fr79→82). Reconstruction puts the scorer in the cluster
  and recovers **both assisters**, but the *exact* shooter is mis-assigned to a linemate the shot flew
  past — see error mode 1.
- **`2024020002-258` (miss).** A **7-player net-front scramble** (crowd = 7 at the goal). The scorer
  8479420 is 0.4 ft from the puck — right on it — but so are four other bodies; nearest-neighbor cannot
  tell whose stick scored. See error mode 2.

### Honest error modes (why exact attribution fails, quantified)

The misses are not random — they cluster on a specific, expected geometry. Splitting the 16 goals:

| outcome | n | avg net-front crowd @goal | median scorer-to-puck dist |
|---|---:|---:|---:|
| exact shooter match | 6 | 1.7 | 2.8 ft |
| cluster hit, shooter miss | 3 | 1.0 | 3.1 ft |
| scorer not in cluster | 7 | **2.6** | **1.9 ft** |

The misses have **bigger crowds but smaller scorer-to-puck distance** — the scorer is *right on the
puck* (deflection/tip/jam) but buried in a pack, so the wrong body wins the nearest-neighbor. Concretely:

1. **Shot fly-by past a screen.** On a shot from distance, the puck detaches from every skater and can
   pass within 2–3 ft of a stationary screen/defender mid-flight. Naive "nearest skater to the puck"
   tags the screen, not the shooter. (Mitigated here by a shot-flight detector that places the release
   at the *start* of the fast net-ward run, not mid-flight — this is what lifted exact from 6% to 38%.)
2. **Net-front scramble / deflection / tip.** Crowd ≥ 3 in front: no clean carrier exists, and the
   scorer's stick is one of several within a foot of the puck. Among the 4 scramble goals (crowd ≥ 3),
   only 1 reconstructed exactly. **This is a genuine limit of geometry-without-stick-tracking**, not a
   fixable bug — the sprites give body positions, not stick blades or puck-contact events.
3. **Gapped / delayed puck tracking.** A minority of clips (e.g. `2024020001-1731224`) have a ~1.5 s gap
   between the shot and the puck reading in-net, breaking flight detection; the anchor lands early and
   the scorer is never near the (mis-placed) release. Rare but real.
4. **Behind-the-net vs in-net.** The goal-mouth box had to be bounded on both sides (goal line ≤ |x| ≤
   back-of-net); without the upper bound the puck against the *end boards* (11 ft past the line) reads
   as "in net." Fixed here; flagged because any downstream release/geometry model must bound it too.

**Bottom line on reconstruction:** the connective tissue — carriers, 2–8 passes/goal, entries, and the
release/arrival frames — **is really there and reconstructs**, and the recorded scorer is on the puck
88% of the time, confirming fidelity. **Exact shot attribution from body-position geometry alone is
~38% and saturates on scrambles/deflections;** a production Goal-Credit / Pass-Atlas model will need
either accepted cluster-level (not exact-shooter) credit, or a smarter possession model — but the raw
material for it is present and faithful.

---

## Confirmation of the opportunity map

The paper read in `reports/probe.md` is **confirmed, not corrected**, on every checkable point: the
data is full player+puck tracking at 10 Hz for every goal buildup, 2023–26, in the warehouse; it
materializes losslessly (0 parse failures) into a 44.7M-row frame mart; and the connective events pbp
lacks are genuinely reconstructable from it. The one thing the reconstruction *sharpens* rather than
confirms is difficulty: **descriptive** goal anatomy (who was on the ice, how the puck moved, the pass
count, the entry, the release geometry) is solidly buildable; **exact per-event shot credit** is bounded
by scramble/deflection ambiguity and by the goals-only banner caveat above. Build the descriptive
family first; treat any credit/finishing model as success-conditioned and cluster-level, not causal.

**STOP for owner review** — the two marts are live and the reconstruction is validated; no project is
written and nothing downstream is committed pending your read.
