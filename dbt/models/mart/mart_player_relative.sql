{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "player_id"]
) }}

-- Player performance relative to team averages
-- Positive values indicate above-team-average performance
-- Negative values indicate below-team-average performance

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

        -- Relative stats (player - team average)
        ps.ixg_per60 - coalesce(ta.team_avg_ixg_per60, 0.0) as ixg_per60_rel,
        ps.primary_points_per60 - coalesce(ta.team_avg_primary_points_per60, 0.0) as primary_points_per60_rel,
        ps.on_ice_xgf_pct - coalesce(ta.team_avg_on_ice_xgf_pct, 0.0) as on_ice_xgf_pct_rel

    from player_stats ps
    left join team_averages ta
        on ps.game_id = ta.game_id
        and ps.team_id = ta.team_id
)

select * from final
