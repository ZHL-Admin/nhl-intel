{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "player_id"]
) }}

-- Player performance relative to team averages (legacy player-minus-team-average columns:
-- ixg_per60_rel, primary_points_per60_rel, on_ice_xgf_pct_rel), PLUS the corrected
-- on-ice-minus-off-ice relative (rel_xgf_pct, rel_cf_pct) from int_player_onice_game.
-- The on-ice-minus-off-ice pair is the methodologically correct "relative" metric; the
-- legacy player-minus-team-average columns are retained here only until the backend
-- consumers (routers/teams.py, routers/players.py, services/bigquery.py) migrate in the
-- Phase 7 API pass, at which point they are dropped. See docs/PHASE0_FINDINGS.md §0.7.

with player_stats as (
    select
        game_id,
        game_date,
        season,
        player_id,
        team_id,
        first_name,
        last_name,
        position_code,
        ixg_per60,
        primary_points_per60,
        on_ice_xgf_pct
    from {{ ref('mart_player_game_stats') }}
),

team_averages as (
    select
        game_id,
        team_id,
        avg(ixg_per60) as team_avg_ixg_per60,
        avg(primary_points_per60) as team_avg_primary_points_per60,
        avg(on_ice_xgf_pct) as team_avg_on_ice_xgf_pct
    from {{ ref('mart_player_game_stats') }}
    group by game_id, team_id
),

-- Corrected relative: true per-game on-ice minus off-ice (same grain as this mart)
player_onice as (
    select
        game_id,
        player_id,
        off_ice_xgf_pct,
        rel_xgf_pct,
        rel_cf_pct
    from {{ ref('int_player_onice_game') }}
),

final as (
    select
        ps.game_id,
        ps.game_date,
        ps.season,
        ps.player_id,
        ps.team_id,
        ps.first_name,
        ps.last_name,
        ps.position_code,

        -- Individual stats
        ps.ixg_per60,
        ps.primary_points_per60,
        ps.on_ice_xgf_pct,

        -- Team averages
        ta.team_avg_ixg_per60,
        ta.team_avg_primary_points_per60,
        ta.team_avg_on_ice_xgf_pct,

        -- Legacy relative stats (player - team average). Retained for backend compatibility;
        -- superseded by the on-ice-minus-off-ice columns below.
        ps.ixg_per60 - coalesce(ta.team_avg_ixg_per60, 0.0) as ixg_per60_rel,
        ps.primary_points_per60 - coalesce(ta.team_avg_primary_points_per60, 0.0) as primary_points_per60_rel,
        ps.on_ice_xgf_pct - coalesce(ta.team_avg_on_ice_xgf_pct, 0.0) as on_ice_xgf_pct_rel,

        -- Corrected relative stats (on-ice minus off-ice, 5v5)
        po.off_ice_xgf_pct,
        po.rel_xgf_pct,
        po.rel_cf_pct

    from player_stats ps
    left join team_averages ta
        on ps.game_id = ta.game_id
        and ps.team_id = ta.team_id
    left join player_onice po
        on ps.game_id = po.game_id
        and ps.player_id = po.player_id
)

select * from final
