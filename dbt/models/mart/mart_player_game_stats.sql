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
        sum(case when is_high_danger then 1 else 0 end) as individual_high_danger_attempts
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
        coalesce(pa.primary_assists, 0) as primary_assists,

        15.0 as estimated_toi_5v5_minutes

    from rosters r
    left join player_shots ps
        on r.game_id = ps.game_id
        and r.player_id = ps.player_id
    left join player_assists pa
        on r.game_id = pa.game_id
        and r.player_id = pa.player_id
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
        estimated_toi_5v5_minutes as toi_5v5,

        (cast(individual_high_danger_attempts as float64) / estimated_toi_5v5_minutes) * 60.0 as ixg_per60,

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
        case
            when sa.season_avg_ixg_per60 > 0 and m.ixg_per60 > sa.season_avg_ixg_per60 * 1.15 then 'hot'
            when sa.season_avg_ixg_per60 > 0 and m.ixg_per60 < sa.season_avg_ixg_per60 * 0.85 then 'cold'
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
        ixg_per60,
        primary_points_per60,
        season_avg_ixg_per60,
        hot_cold_flag
    from with_flags
)

select * from final
