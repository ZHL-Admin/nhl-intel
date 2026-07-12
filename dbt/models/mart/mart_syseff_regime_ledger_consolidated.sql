{{ config(materialized='table', cluster_by=['team_id']) }}

-- System Effects (Phase 7) — the CONSOLIDATED regime ledger (K=4 transient fill-in absorption to
-- a fixpoint; Phase 1 §6 Option A). The iterative absorption is not naturally expressible in
-- incremental SQL, so this grain is materialized from the frozen research output (seed
-- syseff_regime_ledger_consolidated, 201 rows) and REFRESHED on the daily cadence by a small
-- Python step that re-runs syseff.regime_ledger.consolidate_ledger on the live raw ledger
-- (see docs/rebuild-reports/syseff-p7.md §7.1d). Reconciles exactly to the frozen research table.
select * from {{ ref('syseff_regime_ledger_consolidated') }}
