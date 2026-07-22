# Phase Value — decisions log

Every judgment call not fully pinned by the build spec. Format:
`PV-D### | date | question | decision | rationale | alternative`.

---

**PV-D001 | 2026-07-22 | The spec (§5.5) and dbt comments reference `models_ml/tune_sequence_thresholds.py` as the "mirror pattern" example, but the file does not exist in the repo.**
Decision: proceed; still follow the mirror pattern (pure-Python reference `tests/phase_value/reference_state_machine.py` ↔ dbt SQL, reconciled in `stage1_reconcile.py`). Record the absence.
Rationale: the pattern is described well enough in §5.5 to follow without the example; nothing depends on the file existing. Not a Section 0.3 STOP (an *equivalent* pattern is found elsewhere — e.g. the sequence-window tuning is documented in `docs/methodology/sequence-mining.md`).
Alternative: STOP and ask — rejected as disproportionate for a missing illustrative example.

**PV-D002 | 2026-07-22 | Spec config comment says `MIN_EXPOSURE_SECONDS: 4` "mirrors RAPM MIN_SEGMENT_SECONDS", but train_rapm.py's actual `MIN_SEGMENT_SECONDS = 5`.**
Decision: keep `PHASE_VALUE_CONFIG["MIN_EXPOSURE_SECONDS"] = 4` (the value the spec uses explicitly and repeatedly in the Stage 3 row filters, `>= 4`), and correct the comment to state RAPM's real value is 5.
Rationale: spec = authority on intent (PV row-filter floor = 4, stated 3× in §7.2); repo = authority on mechanics (so the comment must not falsely claim RAPM=4). The 1 s gap is immaterial to a floor whose only purpose is dropping trivially-short exposure.
Alternative: set PV floor to 5 to literally equal RAPM — rejected; contradicts the spec's explicit `>= 4` filters and changes nothing meaningful.

**PV-D003 | 2026-07-22 | Spec prose (§1) describes the RAPM alpha grid as "[250..8000]", but train_rapm.py's actual `ALPHAS = list(np.logspace(2, 6, 13))` = 100 .. 1,000,000.**
Decision: reuse the REAL `ALPHAS` by import in `train_phase_value.py` (Appendix C is explicit: "reuse train_rapm's ALPHAS by import/reference. Do not fork it."). Ignore the approximate prose range.
Rationale: Appendix C's binding instruction overrides the descriptive prose; importing guarantees PV and RAPM regularization are identical by construction.
Alternative: hardcode [250..8000] — rejected; would fork the grid and violate Appendix C.

**PV-D004 | 2026-07-22 | No dbt dev-season scoping mechanism exists (spec §11 allows "a `phase_dev_seasons` var if none exists").**
Decision: add `phase_dev_seasons: []` to dbt_project.yml (list of seasons; empty = full history). PV models apply it as an optional `where season in (...)` guard.
Rationale: spec explicitly sanctions this fallback; keeps dev iterations cheap without touching existing models.
Alternative: reuse an existing var — none exists.

**PV-D005 | 2026-07-22 | Blocked-shot `event_owner_team_id` is the BLOCKING (defending) team, not the shooting team (recon check 3, 94.15%).**
Decision: in the state mapping, on a `blocked-shot` set possession = `opponent(event_owner_team_id)` (the shooting/attacking team, PV-A1) and flip the owner-relative `zone_code` O↔D to express it attacker-relative before deriving zone_abs.
Rationale: repo = authority on mechanics; recon resolved the semantic at 94% (≥90% gate). GV7 explicitly defers this to the "Stage 0 finding". Preserves PV-A1 intent while using the true owner semantics.
Alternative: take owner as the shooter (the naive reading) — rejected; empirically wrong (would put the attack in the wrong zone/possession 94% of the time).

**PV-D006 | 2026-07-22 | Two event types beyond the spec's enumerated set appear: `failed-shot-attempt` (n=24) and `shootout-complete` (n=163).**
Decision: route both to the fallback mapping row — `failed-shot-attempt` → LIVE no-op (counts toward the unmapped metric); `shootout-complete` → treat as a DEAD boundary. Both are far under the 0.5% unmapped gate.
Rationale: neither is a 5v5 possession event; shootout is out of scope entirely. Explicit assignment avoids silent mishandling.
Alternative: add dedicated mapping rows — unnecessary at these volumes; revisit only if counts grow.

**PV-D007 | 2026-07-22 | 5v5 scoping of episodes: how to keep/flag, and how to test 5v5 for 0-duration point episodes (rush goals at a whistle).**
Decision: gate an episode's 5v5 membership on its START event's `is_5v5` (robust for 0-duration episodes, where a segment-overlap test degenerates); keep episodes whose start is 5v5. Flag `clipped_by_strength` when the span contains any non-5v5 time (positive-duration only). v1 does NOT truncate a clipped episode's end to the strength boundary (the spec's stated end-at-boundary behavior) — it keeps the whole span and flags it. Clipped share measured 3.4% (< 10% expectation).
Rationale: the initial segment-overlap 5v5 filter returned NULL duration for 0-width point episodes and silently dropped rush/quick goals, tanking goal coverage to 43.8%. Start-event strength is unambiguous and lifted coverage to 98.3%. End-truncation is deferred as a v1.1 refinement; at 3.4% clipped it barely affects outcomes and the flag makes it auditable.
Alternative: full-span segment-overlap gate (drops point episodes; fails the goal-coverage gate) — rejected. Truncating clipped ends now — deferred (adds complexity for <4% of episodes).

**PV-D008 | 2026-07-22 (amended) | A terminating attacker goal (live=false) must anchor/end a DZ episode — as a BOUNDARY convention (a), NOT zone coercion (b).**
Decision: an attacker `goal` spell counts as in-zone for episode membership **only if its recorded `zone_abs` IS the defensive zone** (spec §5.4's raw-interval condition is possession+zone; the `(is_live OR goal)` clause relaxes ONLY liveness). The code does NOT coerce a goal's zone to the DZ. A goal recorded outside the DZ (zone_code 'N'/'D') stays outside and anchors no episode. Applied identically in the reference (`in_zone: s.poss==attacker and s.zone==dz and (s.live or is_atk_goal)`) and SQL (`zone_abs = d_dzone and (is_live or spell_has_goal)`). Locked by golden vectors GV9 (outside-zone goal → no episode) and GV10 (bare rush DZ goal → zero-duration episode).
Rationale: this is the honest reading — it covers rush/quick-strike goals that occur IN the DZ while leaving genuinely outside-zone goals uncovered, which is exactly why the gate was set at 90% not 100%. In-scope goal coverage 99.95%; residual = outside-zone only (0 DZ artifacts).
Alternative (b) zone coercion (force every goal's zone to the DZ) — REJECTED: bends the definition to pass the gate; would falsely cover neutral-zone/own-zone goals.

**PV-D009 | 2026-07-22 | Episode 5v5 scoping must not drop 5v5 goals in sequences that begin in non-5v5 (a PP expires, the goal is 5v5).**
Decision: keep an episode iff **any of its in-zone spells contains a 5v5 event** (`any_5v5`); flag `clipped_by_strength` when the span has non-5v5 time. Replaces the earlier start-event-only gate (PV-D007), which dropped ~1.7% of 5v5 goals whose episode STARTED in non-5v5 (tail of a PP/4v4) and crossed into 5v5. Reference and SQL use the identical rule (per-event / per-spell 5v5), so reconciliation stays **0.0000%**. Also fixed the mirror `dz_ok`/goal-anchor to use `spell_has_goal` (any goal in a spell) rather than the spell's first event, closing a 1-in-17,073 stoppage-before-goal edge. Clipped share 4.7% (< 10%).
Rationale: the start-event gate was a coverage artifact, not honest residual (95 DZ goals dropped). Any-in-zone-5v5 covers them; Stage 3 intersects with 5v5 stints for exact strength accounting, so boundary/clipped episodes do not pollute the fits. Supersedes PV-D007's start-event gating (the 0-duration robustness reason still holds — any_5v5 is also robust there).
Alternative: start-event gate (drops 1.7% of 5v5 goals) — rejected.

**PV-D010 | 2026-07-22 | The goal-coverage gate is computed on the 5v5 (segment-covered) universe; preseason/no-segment games are out of scope.**
Decision: compute goal coverage over goals in games present in `int_segment_context` (the RAPM stint universe). `int_phase_events.is_5v5` requires a segment strength_state='5v5' (NO situation_code fallback), matching the RAPM 5v5 filter exactly; `int_shot_sequence.strength` DOES fall back to situation_code, so it labels ~395 preseason goals (in games with no shift data) '5v5'. Those games produce no episodes and are legitimately out of the 5v5 scope. In-scope coverage 99.95%; the 237 preseason "5v5" goals are excluded from the denominator.
Rationale: 5v5 is defined by the segment engine; a game with no segments has no defined 5v5. Matching RAPM exactly is the spec's requirement. The is_5v5 vs int_shot_sequence.strength divergence is confined to no-segment games and documented here.
Alternative: add a situation_code fallback to is_5v5 — rejected in v1 (would diverge from the RAPM stint filter the spec says to match exactly).

**PV-D011 | 2026-07-22 | Zero-duration goal-only episodes: Stage 3 must handle them deliberately, not silently drop the most dangerous events.**
Flag (binding for Stage 3): a bare rush/quick-strike goal produces a **zero-duration episode** (start==end) that contributes **one episode start and one goal with ~0 in-zone seconds** and a small `xg_inzone` at a single instant. Stage 3's `inzone_sec >= 4` row filter and the stint aggregation MUST NOT silently drop these — doing so would remove the most dangerous sequences (the goals themselves) from the `suppress` (xG-intensity) fit and bias it low. Handling options to decide at Stage 3: attribute the goal's/shot's xG to the containing stint regardless of the episode's ~0 duration; or count episode STARTS (for `deny`) independently of the `inzone_sec` floor. The floor is meant to drop trivial EXPOSURE, not zero-length high-danger episodes. ~54% of covered goals arrive via these goal-anchored episodes, so this is not an edge case.
