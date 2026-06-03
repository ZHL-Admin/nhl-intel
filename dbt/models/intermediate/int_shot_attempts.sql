with source as (
    select * from {{ ref('stg_play_by_play') }}
),

shot_attempts_5v5 as (
    select
        game_id,
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
    where situation_code = '1551'
      and type_desc_key in ('shot-on-goal', 'goal', 'missed-shot', 'blocked-shot')
),

tagged as (
    select
        *,
        case
            when type_desc_key = 'goal' then true
            else false
        end as is_goal,

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
        end as is_blocked

    from shot_attempts_5v5
    where x_coord is not null
      and y_coord is not null
),

final as (
    select * from tagged
)

select * from final
