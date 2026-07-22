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
