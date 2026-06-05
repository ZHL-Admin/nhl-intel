with rosters as (
    select
        game_id,
        game_date,
        player_id,
        team_id,
        first_name,
        last_name,
        position_code
    from {{ ref('stg_rosters') }}
),

player_shots as (
    select
        game_id,
        shooting_player_id as player_id,
        count(*) as individual_shot_attempts,
        sum(case when is_goal then 1 else 0 end) as individual_goals,
        sum(case when is_high_danger then 1 else 0 end) as individual_high_danger_attempts,
        sum(xg_value) as ixg
    from {{ ref('int_shot_attempts') }}
    where shooting_player_id is not null
    group by game_id, shooting_player_id
),

player_assists as (
    select
        game_id,
        assist1_player_id as player_id,
        count(*) as primary_assists
    from {{ ref('stg_play_by_play') }}
    where assist1_player_id is not null
      and type_desc_key = 'goal'
      and situation_code = '1551'
    group by game_id, assist1_player_id
),

team_xg as (
    select
        game_id,
        team_id,
        xgf_pct
    from {{ ref('mart_team_game_stats') }}
),

player_stats_combined as (
    select
        r.game_id,
        r.game_date,
        r.player_id,
        r.team_id,
        r.first_name,
        r.last_name,
        r.position_code,
        coalesce(ps.individual_shot_attempts, 0) as individual_shot_attempts,
        coalesce(ps.individual_goals, 0) as individual_goals,
        coalesce(ps.individual_high_danger_attempts, 0) as individual_high_danger_attempts,
        coalesce(ps.ixg, 0.0) as ixg,
        coalesce(pa.primary_assists, 0) as primary_assists,
        coalesce(tx.xgf_pct, 0.5) as team_xgf_pct,

        15.0 as estimated_toi_5v5_minutes

    from rosters r
    left join player_shots ps
        on r.game_id = ps.game_id
        and r.player_id = ps.player_id
    left join player_assists pa
        on r.game_id = pa.game_id
        and r.player_id = pa.player_id
    left join team_xg tx
        on r.game_id = tx.game_id
        and r.team_id = tx.team_id
    where r.position_code in ('C', 'L', 'R', 'D')
),

metrics_calculated as (
    select
        game_id,
        game_date,
        player_id,
        team_id,
        first_name,
        last_name,
        position_code,
        individual_shot_attempts,
        individual_goals,
        individual_high_danger_attempts,
        primary_assists,
        ixg,
        team_xgf_pct,
        estimated_toi_5v5_minutes as toi_5v5,

        case
            when estimated_toi_5v5_minutes > 0
            then (ixg / estimated_toi_5v5_minutes) * 60.0
            else 0.0
        end as ixg_per60,

        ((individual_goals + primary_assists) / estimated_toi_5v5_minutes) * 60.0 as primary_points_per60

    from player_stats_combined
),

season_averages as (
    select
        player_id,
        avg(ixg_per60) as season_avg_ixg_per60
    from metrics_calculated
    group by player_id
),

with_flags as (
    select
        m.*,
        sa.season_avg_ixg_per60,
        -- On-ice xGF% proxy: use team xGF% as approximation
        -- Note: True on-ice xGF% requires shift-by-shift tracking not available in this model
        m.team_xgf_pct as on_ice_xgf_pct,
        case
            when sa.season_avg_ixg_per60 > 0.1 and m.ixg_per60 > sa.season_avg_ixg_per60 * 1.15 then 'hot'
            when sa.season_avg_ixg_per60 > 0.1 and m.ixg_per60 < sa.season_avg_ixg_per60 * 0.85 then 'cold'
            else 'neutral'
        end as hot_cold_flag
    from metrics_calculated m
    left join season_averages sa
        on m.player_id = sa.player_id
),

final as (
    select
        game_id,
        game_date,
        player_id,
        team_id,
        first_name,
        last_name,
        position_code,
        toi_5v5,
        individual_shot_attempts,
        individual_goals,
        primary_assists,
        individual_high_danger_attempts,
        ixg,
        ixg_per60,
        on_ice_xgf_pct,
        primary_points_per60,
        season_avg_ixg_per60,
        hot_cold_flag
    from with_flags
)

select * from final
