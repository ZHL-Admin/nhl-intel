{{ config(materialized='table') }}

-- System Effects (Phase 7) — per-metric VALIDATION STATUS for fingerprints_v2: split-half
-- reliability, coaching-sensitivity (Phase 2 discontinuity test), and caveat language. Consumers
-- MUST read this alongside the fingerprint values: only zone_start_polarization and
-- top6_fwd_toi_share are coaching-sensitive; top6 carries its stability caveat; style and PK
-- metrics are roster properties (descriptive context, not coaching claims); home_away_strictness
-- retains its Atlas failed-validation caveat and is not carried in the values table.
select * from {{ ref('syseff_fingerprint_metric_status') }}
