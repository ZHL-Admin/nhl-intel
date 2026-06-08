with source as (
    select * from {{ ref('int_shot_attempts') }}
),

normalized as (
    select
        *,
        case
            when shot_type in ('wrist', 'snap') then 'snap'
            when shot_type = 'slap' then 'slapshot'
            when shot_type in ('tip-in', 'deflected') then 'tip-deflection'
            when shot_type = 'backhand' then 'backhand'
            when shot_type = 'wrap-around' then 'wraparound'
            else 'other'
        end as normalized_shot_type
    from source
),

final as (
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
        shooting_player_id,
        scoring_player_id,
        goalie_in_net_id,
        blocking_player_id,
        event_owner_team_id,
        home_score,
        away_score,
        is_goal,
        is_high_danger,
        is_on_net,
        is_blocked,
        zone,
        situation,
        xg_value,
        normalized_shot_type as shot_type
    from normalized
)

select * from final
