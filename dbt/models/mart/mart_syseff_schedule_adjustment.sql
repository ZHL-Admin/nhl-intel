{{ config(materialized='table', cluster_by=['season_label', 'team_id']) }}

-- System Effects (Phase 7) — opponent-strength schedule adjustment per (player, season, team):
-- the xG-share points a player's season number is shifted by facing an easier/harder opponent set
-- than league-average. STRENGTH-ONLY (the style-matchup track was killed — F15). DESCRIPTIVE
-- ACCOUNTING: no predictive claim, no validation bar. Typical |adjustment| ~0.003 (p90 ~0.0065).
-- Promoted as the frozen research values (re-derivation needs the frozen-Atlas-stint xG the
-- production backbone diverges from). See mart_syseff_schedule_adjustment magnitude line in the dossier.
select * from {{ ref('syseff_schedule_adjustment') }}
