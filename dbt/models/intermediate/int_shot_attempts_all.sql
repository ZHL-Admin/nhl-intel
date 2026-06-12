-- All-situations shot attempts with xG, mirroring int_shot_attempts but WITHOUT the
-- 5v5 filter. Used for the all-situations xG worm so power-play and empty-net play
-- (and their goals) are represented. The 5v5-only int_shot_attempts remains the basis
-- for the possession/xGF% marts, which are even-strength by design.
with source as (
    select * from {{ ref('stg_play_by_play') }}
),

shot_attempts as (
    select
        game_id,
        season,
        event_id,
        period_number,
        period_type,
        time_in_period,
        situation_code,
        type_desc_key,
        x_coord,
        y_coord,
        zone_code,
        shot_type,
        shooting_player_id,
        scoring_player_id,
        goalie_in_net_id,
        blocking_player_id,
        event_owner_team_id,
        home_score,
        away_score
    from source
    where type_desc_key in ('shot-on-goal', 'goal', 'missed-shot', 'blocked-shot')
      and period_type != 'SO'
),

tagged as (
    select
        *,
        case when type_desc_key = 'goal' then true else false end as is_goal,

        case
            when abs(x_coord) > 55 and abs(y_coord) < 22 then true
            else false
        end as is_high_danger,

        case
            when type_desc_key in ('shot-on-goal', 'goal') then true
            else false
        end as is_on_net,

        case
            when type_desc_key = 'blocked-shot' then true
            else false
        end as is_blocked,

        -- Zone classification (same as int_xg_rates)
        case
            when abs(x_coord) > 70 and abs(y_coord) < 15 then 'slot'
            when abs(x_coord) between 55 and 70 and abs(y_coord) between 15 and 30 then 'circle'
            when abs(x_coord) between 40 and 70 and abs(y_coord) > 30 then 'perimeter'
            when abs(x_coord) between 25 and 55 then 'perimeter'
            when abs(x_coord) < 40 then 'point'
            else 'other'
        end as zone,

        -- Situation classification
        case
            when situation_code = '1551' then '5v5'
            when situation_code like '15%' and situation_code != '1551' then 'other'
            else 'special'
        end as situation

    from shot_attempts
    where x_coord is not null
      and y_coord is not null
),

with_xg as (
    select
        t.*,
        coalesce(xg.xg_value, 0.02) as xg_value
    from tagged t
    left join {{ ref('int_xg_rates') }} xg
        on t.season = xg.season
        and t.zone = xg.zone
        and t.is_high_danger = xg.is_high_danger
        and t.situation = xg.situation
),

final as (
    select * from with_xg
)

select * from final
