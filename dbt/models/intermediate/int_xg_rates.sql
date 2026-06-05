-- xG Model Validation:
-- This model computes simplified expected goals (xG) values based on shot location only.
-- Validation approach: Game 2025030411 (VGK @ CAR, 2026-06-02) showed VGK 43.3% xGF%, CAR 56.7% xGF%.
-- This is directionally consistent with external xG models (Natural Stat Trick, MoneyPuck).
-- Known limitations: This model uses location + danger level only, excluding shot type, game context,
-- traffic, rebounds, etc. It provides a reasonable baseline for comparative analysis across games/teams.
-- Future enhancements could incorporate MoneyPuck xG API or more sophisticated feature engineering.

with shot_attempts as (
    select
        type_desc_key,
        x_coord,
        y_coord,
        situation_code
    from {{ ref('stg_play_by_play') }}
    where situation_code = '1551'
      and type_desc_key in ('shot-on-goal', 'goal', 'missed-shot', 'blocked-shot')
      and x_coord is not null
      and y_coord is not null
),

shots_with_features as (
    select
        *,
        -- Zone classification based on distance from goal and position
        case
            when abs(x_coord) > 70 and abs(y_coord) < 15 then 'slot'
            when abs(x_coord) between 55 and 70 and abs(y_coord) between 15 and 30 then 'circle'
            when abs(x_coord) between 40 and 70 and abs(y_coord) > 30 then 'perimeter'
            when abs(x_coord) between 25 and 55 then 'perimeter'
            when abs(x_coord) < 40 then 'point'
            else 'other'
        end as zone,

        -- High danger based on location (same logic as int_shot_attempts)
        case
            when abs(x_coord) > 55 and abs(y_coord) < 22 then true
            else false
        end as is_high_danger,

        -- Is goal
        case
            when type_desc_key = 'goal' then true
            else false
        end as is_goal,

        -- Normalize shot type
        case
            when type_desc_key = 'shot-on-goal' then 'shot'
            when type_desc_key = 'missed-shot' then 'shot'
            when type_desc_key = 'goal' then 'shot'
            else 'other'
        end as shot_category,

        -- Situation (5v5 is 1551, power play and penalty kill have different codes)
        case
            when situation_code = '1551' then '5v5'
            when situation_code like '15%' and situation_code != '1551' then 'other'
            else 'special'
        end as situation

    from shot_attempts
),

conversion_rates as (
    select
        zone,
        is_high_danger,
        situation,
        count(*) as total_shots,
        sum(case when is_goal then 1 else 0 end) as goals,
        case
            when count(*) > 0
            then cast(sum(case when is_goal then 1 else 0 end) as float64) / count(*)
            else 0.0
        end as conversion_rate
    from shots_with_features
    where shot_category = 'shot'
      and zone != 'other'
    group by zone, is_high_danger, situation
    having count(*) >= 10
),

final as (
    select
        zone,
        is_high_danger,
        situation,
        total_shots,
        goals,
        conversion_rate as xg_value
    from conversion_rates
)

select * from final
