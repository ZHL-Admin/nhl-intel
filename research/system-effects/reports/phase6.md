# Phase 6 — Packaging, findings, prospective registration

**Project:** System Effects · **Date:** 2026-07-11 · **Seed:** 20260711
**Status:** Phase 6 complete. Deliverables: the project's one-page `reports/FINDINGS.md`, the frozen
2026-27 prospective registration, the schema freeze, and the program-ledger relocation. Stopping
per protocol.

---

## 6.0 Program-ledger relocation (governance correction)

Completed-project reports are frozen and do not grow. The System Effects section that had been
appended to the frozen `research/deployment-atlas/reports/FINDINGS.md` has been **relocated**:

- **Created** `research/PROGRAM-FINDINGS.md` — the shared, growing cross-project findings ledger.
  The System Effects section (F12–F15, the System Tax answer, the INVESTIGATE decision, upstream
  additions) was moved into it **verbatim**, with the F12 nuance preserved ("summer style
  directional is positive but unconfirmed — too weak to confirm in sixteen years, never proven
  zero") and the open-question threads (the Jolt, the D/high-TOI concentration) carried forward.
- **Restored** the Atlas `reports/FINDINGS.md` to its **frozen original content**, plus a single
  pointer line to the program ledger. Verified: `git diff` shows the Atlas file changed by exactly
  that one pointer block; no frozen Atlas data or `api.py` was touched.

Going forward: project reports freeze; `PROGRAM-FINDINGS.md` is the one that grows.

## 6.1 Schema freeze (in `README.md`)

Every derived table is documented in `README.md` with grain, row count, and **adopt-vs-derive
provenance**, frozen **2026-07-11**: the regime ledger (raw 235 + consolidated 201), fingerprints
v2 (seq/prim/deploy/pk primitives + `team_season_fp`, with per-metric reliability and
coaching-sensitivity status carried from `phase2.md`), `player_types` (10,961), the context
primitives (pctx/onice/depfull, reconciled vs Atlas 2024-25), `portability` (with the 4.1a
materiality rule stated), `schedule_adjustment`, the Design A/B and 5A evaluation tables, and the
`frozen_eval` copies. One asset is **adopt** (the Atlas `int_shot_sequence` seq_type rules, reused
in `sequence.py`); everything else is **derive** from frozen Atlas assets.

## 6.2 Reproducibility (`make all`, `make report`)

`make all` reproduces every phase and addendum **from cache**, then runs the suite. Wall times
(this run; primitives already cached):

| step | wall time |
|---|---:|
| phase1 (regime ledger + cohorts) | 3s |
| phase2 (fingerprints, discontinuity) | 13s |
| phase3 (pooling, both tracks, stability) | 47s |
| phase4 (portability + schedule surfaces) | 45s |
| phase5 (5A validation, LOSO refits) | 26s |
| summer (F12 addendum) | 13s |
| prospective (2027 predictor freeze) | 0s |
| **total** | **147s** |

**All tests green: 21 passed.** `make report` lists the reports of record.

## 6.3 Project findings — `reports/FINDINGS.md`

A one-page, plain-language summary is frozen at `reports/FINDINGS.md`: what was built; what
validated (deployment as the coach-owned lever in both windows; the portability machinery; the
schedule normalization); what fell short or died (5A INVESTIGATE at +0.81%; the opponent
style-matchup kill; the summer style null with its positive-but-unconfirmed nuance; the PK null);
the decisions stated without editorializing; the five most surprising findings; the upstream
ledger's final state (UL-1 flagged for a future gated production fix); and the open questions —
the **Jolt** (the unexplained new-coach result bump; an event-time study is the queued next
addendum) and the **D / high-TOI concentration** thread.

## 6.4 Prospective registration — 2026-27 (internal track only)

Registered and frozen at `reports/registration_2027.md`. Confirmation:

- **Predictors frozen now:** `data/parquet/prospective_2027/frozen_predictors.parquet` — 719
  candidate players' **2025-26** values (variant RAPM `q`, player `type_id`, position, 5v5 TOI,
  the `high_toi_tier` flag). 469 F, 250 D, 245 in the high-TOI tier.
- **Cohort resolves at season start:** free agency is in progress, so the mover set (who changed
  teams over summer 2026) resolves naturally at 2026-27 opening; **only the predictor inputs freeze
  now**. The frozen challenger model is `portability_model.json` (Design B through 2025-26 —
  leakage-clean for 2026-27+ outcomes).
- **Test:** variant (incumbent) vs variant + deployment (challenger), target = mean 2026-27/2027-28
  5v5 on-ice xG share (400+ prorated min), **PRIMARY rule fixed: SHIP ≥ 3% MAE improvement with CI
  excluding zero; INVESTIGATE 0–3%/CI-spanning; KILL ≤ 0** — the same 3% bar as 5A.
- **Pre-specified secondary subgroups:** defensemen and the high-TOI tier (mirroring the
  retrospective concentration), secondary claims only.
- **Amendments** allowed only before outcome data exists, dated in the registration's amendment log
  (currently empty).

---

**STOP.** Phase 7 (conditional, gated production promotion) requires the Phase 5/6 reports accepted
in writing by the product owner, and then only through Phase 7's work-order process. Nothing in
this project has been promoted.

### Artifacts
`research/PROGRAM-FINDINGS.md` · `reports/FINDINGS.md` · `reports/registration_2027.md` ·
`data/parquet/prospective_2027/frozen_predictors.parquet` · `README.md` (schema freeze) ·
`Makefile` (`all`, `report`, `prospective` targets). 21 tests pass. Repro: `make all`.
