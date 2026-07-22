# Phase Value — decisions log

Every judgment call not fully pinned by the build spec. Format:
`PV-D### | date | question | decision | rationale | alternative`.

---

**PV-D001 | 2026-07-22 | The spec (§5.5) and dbt comments reference `models_ml/tune_sequence_thresholds.py` as the "mirror pattern" example, but the file does not exist in the repo.**
Decision: proceed; still follow the mirror pattern (pure-Python reference `tests/phase_value/reference_state_machine.py` ↔ dbt SQL, reconciled in `stage1_reconcile.py`). Record the absence.
Rationale: the pattern is described well enough in §5.5 to follow without the example; nothing depends on the file existing. Not a Section 0.3 STOP (an *equivalent* pattern is found elsewhere — e.g. the sequence-window tuning is documented in `docs/methodology/sequence-mining.md`).
Alternative: STOP and ask — rejected as disproportionate for a missing illustrative example.

**PV-D002 | 2026-07-22, AMENDED 2026-07-24 (owner) | `MIN_EXPOSURE_SECONDS` mirrors RAPM's real `MIN_SEGMENT_SECONDS = 5`.**
Decision (amended): **`PHASE_VALUE_CONFIG["MIN_EXPOSURE_SECONDS"] = 5`**, mirroring RAPM's actual `MIN_SEGMENT_SECONDS = 5`. Owner ruling (Stage 0 review, restated 2026-07-24, verbatim): "Use 5 for the exposure filters... the repo wins, and MIN_EXPOSURE_SECONDS should mirror the real value." Applies to the config constant, the Stage 3 `>=` exposure filters in `build_design.py` (outside_exposure_sec / inzone_sec `>= 5`), and PV-D011.
Confirmation: NO design rows were built under the old value — `build_design.py` was still a stub when this was amended, so the first build uses 5. No rebuild needed.
Superseded: the original keep-4 decision (rationale: "spec §7.2 says >= 4"). The owner ruled repo-wins; 5 is now binding.

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
Flag (binding for Stage 3): a bare rush/quick-strike goal produces a **zero-duration episode** (start==end) that contributes **one episode start and one goal with ~0 in-zone seconds** and a small `xg_inzone` at a single instant. Stage 3's `inzone_sec >= 5` row filter (per amended PV-D002) and the stint aggregation MUST NOT silently drop these — doing so would remove the most dangerous sequences (the goals themselves) from the `suppress` (xG-intensity) fit and bias it low. Handling options to decide at Stage 3: attribute the goal's/shot's xG to the containing stint regardless of the episode's ~0 duration; or count episode STARTS (for `deny`) independently of the `inzone_sec` floor. The floor is meant to drop trivial EXPOSURE, not zero-length high-danger episodes. ~54% of covered goals arrive via these goal-anchored episodes, so this is not an edge case.

**PV-D009 amendment | 2026-07-24 (precision pass — owner review) | Exact 5v5 scoping mechanics for boundary-crossing episodes.**
Answers to the three mechanics questions, and the implemented columns:
- **(a) start + start_type = pre-5v5 segmentation truth.** `start_elapsed`/`start_sort` = the FIRST in-zone spell's start (the true pre-5v5 event for a boundary-crosser); `start_type` is computed from that event (rush/ozfo/forecheck windows anchor on `start_sort`). Unchanged — kept as segmentation truth.
- **(b) base outcomes now span the FULL episode, ALL strengths; 5v5-restricted columns added.** `duration_seconds`, `n_unblocked`, `xg_against`, `goals` = full span, all strengths (segmentation truth). NEW columns `duration_5v5_seconds` (= the episode's 5v5-segment overlap), `attempts_5v5`, `xg_5v5`, `goals_5v5` = the 5v5-restricted subset. **Stage 2 `C_seq` MUST consume `xg_5v5` and Stage 3 measures MUST consume the `*_5v5` columns** — this is what prevents the league constants absorbing PP-tail xG (measured: base xG 19,075 vs xg_5v5 17,590 over 3 seasons; ~1,485 PP-tail xG excluded from the 5v5 column).
- **(c) clipped + entry-side flag.** `clipped_by_strength` = the span contains any non-5v5 time (either side, unchanged). NEW `started_outside_5v5` = the start instant is not 5v5 (isolates the ENTRY-side crossing). Quantified/logged: **started_outside_5v5 = 1.10% of episodes (4,127/375,593)** — their start instant lies outside any 5v5 stint, so they contribute **no `episode_start` to Stage 3 Fit A (`deny`)**. Deliberate: `deny` counts sequences *started* under 5v5; a sequence started on the PP is not a 5v5 denial. clipped_by_strength = 4.71%.
Pinned by golden vector **GV11** (boundary-crossing episode kept, start=pre-5v5, start_5v5=False, keep_5v5=True). Reference/SQL keep-rule unchanged, reconciliation stays 0.0000%.

**PV-D010 amendment | 2026-07-24 (precision pass) | The exclusion axis is NO-SEGMENT games, not preseason — and it matches RAPM exactly.**
Correction to the original PV-D010 framing: preseason is NOT uniformly excluded. `int_segment_context` contains 23,395 segment-covered preseason (game-type '01') rows, and PV produces 4,717 preseason episodes from them. This MATCHES RAPM: `train_rapm.PULL_SQL` filters `int_segment_context` only by strength_state + segment_duration + season — it has **NO game-type filter** (the only `substr(game_id,5,2) in ('02','03')` is in the back-to-back CONTROL helper, not the stint universe). So RAPM's universe = segment-covered games including segment-covered preseason, and PV includes exactly the same games. **Verified exclusion of no-segment games from ALL 5v5 PV consumption:** no-segment games produce 0 episodes and 0 spells (the spell×segment join yields nothing); they appear only in `int_phase_events` with is_5v5=false, which no 5v5 quantity consumes. Decision: do NOT add a game-type filter to PV — matching RAPM exactly is the binding requirement (Section 1). If preseason should be dropped, it is a platform-wide change to the RAPM universe too, not a PV-only divergence — flagged for the owner, not taken unilaterally.
**Owner ruling 2026-07-24: ACCEPTED.** PV matches RAPM's universe including segment-covered preseason — correct call, correctly flagged rather than taken unilaterally. The platform-wide question (should the RAPM stint universe include preseason at all) is **parked as a separate future conversation**; no action taken here.

**PV-D012 | 2026-07-24 | Blocked-shot ~5.7% owner-inconsistency: DECLINE row-wise blocker-team resolution in v1.**
Decision: keep the global owner heuristic (possession → opponent(event_owner_team_id), PV-D005); do NOT resolve the blocker's team per-row from `blocking_player_id` via a shift/roster join in v1.
Rationale: (1) impact is bounded — the ~5.7% owner-appears-to-be-shooter rows are ~0.6% of all events, and blocked-shots rarely change zone_abs (block location is near the true zone); (2) it is already covered by the pre-registered Stage 5 blocked-shot possession sensitivity; (3) adopting it would require threading a roster-resolved possession field through the pure-Python reference (which currently takes only `owner`), eroding the "reference IS the spec" simplicity, plus new golden vectors + a reconciliation pass. The cost/benefit favors deferring to v1.1, gated behind whatever the Stage 5 sensitivity shows.
Alternative: adopt the join now — declined for v1 (bounded impact, already sensitivity-covered). Revisit if Stage 5 flags blocked-shot possession as material.

**PV-D013 | 2026-07-24 (Stage 2, rewritten after owner review) | State value function — hard gate + a measurement-validity check on V(P_OZ_RUSH).**
The hard gate `V(P_OZ_EST) > V(P_NZ) > V(P_OWN_D)` PASSES pooled (0.00520 > 0.00143 > -0.00027, gap ~5 se); it is unaffected by everything below.
- **V(P_OZ_RUSH) at the 5 s grid is a GRANULARITY ARTIFACT, not a finding.** The rush state's lifetime
  (`phase_rush_state_seconds` = 5 s) equals the tick grid (5 s) and sub-2.5 s partial ticks are dropped, so a
  rush episode that scores within ~2.5 s of entry contributes ZERO rush ticks — its goal instead credits the
  preceding P_NZ / P_OZ_EST windows. Quantified: **23.0% of rush episodes contribute zero rush ticks, and
  71.2% of *scoring* rush episodes do** (their mean 5v5 duration is 2.14 s, below the 2.5 s floor). The most
  successful rushes are excised from the rush state's own sample, biasing V(P_OZ_RUSH) DOWN and V(P_OZ_EST) UP.
  **Measurement-validity check (not a sensitivity re-tune): a tick=2 s diagnostic rebuild** (dry-run $0.0035,
  logged) doubles rush n (121k → 249k) and RESTORES the spec-expected order: **V(P_OZ_RUSH) 0.00542 >
  V(P_OZ_EST) 0.00514** at 2 s. So the 5 s ordering is an artifact of the grid, not "established out-earns rush."
  **Decision:** keep the 5 s production grid (per spec `phase_tick_seconds`=5); the methodology carries a
  granularity caveat and leans on the artifact-free view — **`c_seq_rush` = 0.0589 (the HIGHEST episode xG cost
  among start types)** — for the "rush is dangerous" statement, NOT on V(P_OZ_RUSH). The prior "established
  out-earns rush" interpretation is WITHDRAWN.
- **|V(P_NZ)| and |V(P_OWN_D)| < 0.003** (below the spec's expectation-band floor). Both are genuinely near
  zero (V(P_OWN_D) near-zero is spec-anticipated). The coarse structure P_OZ_EST >> {P_NZ, P_OWN_D ~ 0} is
  what matters; the fine P_NZ vs P_OWN_D order flips within ~1 se in 2/11 seasons (pooled gap ~5 se). No action.
- **~1.3% of P_OZ ticks lack an episode_id link** (default to P_OZ_EST; does not affect the gate). Cause: a
  linkage/materialization gap, NOT a boundary-rounding edge (only 0.4% sit within 2.5 s of an episode edge).
  Ticks are generated across long, sparse-event P_OZ spells (from segment-split `int_phase_spells`) whose
  bracketing events lie outside the sampled window, and the tick↔episode TIME-containment join across two
  separately-materialized derivations of the same state (spells vs `int_zone_episodes` state-spell spans)
  leaves that spell-time outside the matching episode's `[start,end]`. v1.1 fix: link on shared spell identity
  rather than time-containment. Diagnostic-only in v1.

**PV-D008 amendment | 2026-07-24 (sprite audit) | zero-duration goal-only episodes are a MIX, not "predominantly rapid entries."**
Sprite ground-truth (16,074 usable goals): within zero-duration goal-only episodes, **57.9% are genuine rapid entries and 42.1% are established_full_window** (puck demonstrably in the O-zone the full 8 s but PBP logged zero possession events — i.e. scorer UNDER-RECORDING of a settled possession). The PV-D008 "predominantly rapid entries" framing holds as a majority but overstates it. No construction change (owner ruling PV-D014); this is a meaning refinement, carried into Known Limitations. The 42.1% under-recorded share shows meaningful arena spread (p10 35% / p90 50%, top ~58% vs bottom ~29%), so `deny` may inherit scorekeeper bias — flagged as a Stage 5 input and a v1.1 rink-adjustment candidate.

**PV-D014 | 2026-07-24 (owner ruling, sprite audit review) | Ship v1 state engine AS-IS; no definitional changes before the Stage 3 freeze.**
Decision: both sprite-audit findings are measurements of the PRE-COMMITTED possession-proxy limitation (entries that generate no PBP event are invisible), not fixable PBP-side. The k∈{3,4,5,6} sweep shows recall pinned at ~0.08–0.09 because the ceiling is ABSENT events, not window size — no redefinition can manufacture missing events. So: freeze the state-engine definitions as-is; the audit is report-only input to Stage 5. `start_type='rush'` is documented as an "event-visible rush" (a small, non-random subset of true rushes). `deny` measures "event-visible threatening sequences allowed"; accounting stays consistent because `C_seq` prices exactly the universe the coefficient counts. Finding 1 is architecturally contained: `deny`/`suppress`/`escape` never consume the rush label; contamination is localized to the diagnostics `c_seq_rush` / `V(P_OZ_RUSH)` / `deny_rush_coef`, each caveated. `phase_rush_state_seconds` stays 5 (sprite entries: median 3.8 s, p75 5.3 s — 5 s captures ~70%).
Deferred alternative (logged, NOT adopted): an **age-based P_OZ_RUSH/EST split independent of start_type** — cleaner state semantics, but it only improves a diagnostic surface, forces mid-project rebuilds, and still mislabels dwell when the true entry predates the first event. v1.1 candidate.
Alternative (adopt a definitional change now) — REJECTED per the above; the freeze engages when Stage 3 fitting begins.

**PV-D015 | 2026-07-24 (owner, pre-registered Stage 5 diagnostic — before any fits complete) | Arena-bias diagnostic for `deny`.**
Registered now, report-only: **correlate team-level `deny` aggregates (minutes-weighted, per season) against home-arena under-recording rate** (the `established_full_window` share within zero-duration episodes, from the sprite audit's arena table, PV-D008 amendment / sprite-audit E3b). A material correlation means `deny` partially measures scorekeeper behavior rather than defense. Report it **beside the Stage 5 smell tests either way**, and it is the **activation test for the v1.1 rink adjustment** of the possession proxy. Pre-registered so the criterion is fixed before results exist; `validate_phase_value.py` implements it in Stage 5.
