{{ config(materialized='table', cluster_by=['team_id']) }}

-- System Effects (Phase 7) — system fingerprints v2, one row per (team, consolidated regime):
-- deployment (top6_fwd_toi_share, zone_start_polarization), style (pace, rush/cycle/forecheck/
-- point-shot shares, shot-location-against), and PK shot-location-against. Score-close where the
-- metric responds to score state (Phase 2). PROMOTED AS THE FROZEN RESEARCH VALUES (source of
-- record): re-derivation from production sources FAILS reconciliation — the production shot/stint
-- backbone diverges from the frozen Atlas layer (mean |Δ| 0.002–0.005, max 0.0125, ≫ float
-- tolerance) and production carries no per-regime / score-close / deployment / PK grain. Per-metric
-- reliability and coaching-sensitivity STATUS is mart_syseff_fingerprint_metric_status.
select * from {{ ref('syseff_fingerprints_v2') }}
