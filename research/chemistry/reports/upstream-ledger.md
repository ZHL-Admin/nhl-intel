# Upstream ledger — Chemistry

Defects found in production or frozen-data during this project. Nothing here is fixed mid-project;
each carries evidence, affected consumers, and a proposed fix layer for a later gated decision.

---

*(Inherited/known items from prior projects are recorded in their own ledgers and
`research/PROGRAM-FINDINGS.md`; the relevant one for Chemistry is that the production pair/line
marts are **rebuilt-backbone-derived** — `int_segment_*` — which System Effects measured as ~8%
divergent from the frozen Atlas stints on shot counts. Chemistry therefore derives its pair corpus
from the frozen stints, auditing the production marts rather than reusing them. Not a new defect; a
lineage constraint, recorded here for visibility.)*

---

## CL-1 (Phase 1, LOW) — `player_5v5.parquet` on-ice TOI slightly *below* the stint sum in irregular seasons

**Observation.** Reconciling Chemistry's stint-summed player-season 5v5 on-ice aggregates against the
frozen Atlas `player_5v5.parquet` (integrity 1.3c, 10,959 player-seasons): the **median ratio is
1.000 and xGF is exact**, but the derived total is **never lower** than `player_5v5` (0 cases < 0.999)
and runs **up to ~2% higher** for a minority — >1% for 655 (6.0%), >2% for 100 (0.9%). The excess is
**concentrated in irregular/early seasons**: 2019-20 (COVID pause) 249, 2014-15 123, 2012-13 (lockout)
105, 2013-14 53, 2010-11 30; 2021-22 onward is ~0. Direction is one-sided, so `player_5v5` applied a
marginally tighter 5v5 boundary/exclusion than a raw both-teams-5-skaters stint sum, more often in
those seasons.

**Evidence.** `reports/phase1_analysis.json:reconciliation_player5v5` (median, p01/p99, per-sample
ratios); the by-season >1% breakdown above. Both artifacts derive from the **same** frozen stints,
so this is an internal inconsistency between two Atlas products, not a Chemistry error.

**Affected consumers.** None materially: pair xG-*share* ratios are invariant to a common TOI scale,
Chemistry's corpus is entirely stint-derived (conservation identity holds to 0.0 across all seasons),
and the discrepancy is sub-1% for 94% of player-seasons.

**Proposed fix layer (deferred, not this project).** If ever reconciled upstream, align
`player_5v5`'s 5v5 stint-selection filter with the stint table's `strength_state=='5v5'` &
exactly-5-per-side definition. **No action taken; recorded for visibility only.**
