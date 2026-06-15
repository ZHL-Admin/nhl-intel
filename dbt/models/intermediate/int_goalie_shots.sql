{{ config(materialized='table') }}

-- Every UNBLOCKED shot (shot-on-goal, missed-shot, goal) faced by a goalie, with the
-- in-house xG and danger/strength labels (blueprint 12.3 / Phase 2.5).
--
-- xGA must be summed over the SAME population the xG model was trained on (all unblocked
-- shots), not just on-goal shots — the model gives P(goal | unblocked attempt), so summing
-- it over on-goal shots alone undershoots actual goals (misses are excluded). Verified:
-- xGA over all unblocked ≈ actual goals (8294 vs 8083 in 2024-25), so league GSAx ≈ 0.
-- Saves and save% are computed on on-goal shots only (a miss is not a save). The goalie is
-- goalie_in_net_id (populated on ~98.5% of misses too); empty-net shots (null goalie) are
-- excluded, so empty-net goals never count against a goalie.

{% set low_max = var('danger_low_max') %}
{% set high_min = var('danger_high_min') %}

with shots as (
    select
        p.game_id,
        p.season,
        p.game_date,
        p.event_id,
        p.goalie_in_net_id as goalie_id,
        p.event_owner_team_id as shooting_team_id,
        case when p.event_owner_team_id = b.home_team_id then b.away_team_id else b.home_team_id end as goalie_team_id,
        (p.type_desc_key = 'goal') as is_goal,
        (p.type_desc_key in ('shot-on-goal', 'goal')) as is_on_goal,
        p.situation_code
    from {{ ref('stg_play_by_play') }} p
    join {{ ref('stg_boxscores') }} b on p.game_id = b.game_id
    where p.type_desc_key in ('shot-on-goal', 'goal', 'missed-shot')
      and p.goalie_in_net_id is not null
),

with_xg as (
    select
        s.*,
        xg.xg
    from shots s
    left join {{ source('nhl_models', 'shot_xg') }} xg
        on s.game_id = xg.game_id and s.event_id = xg.event_id
),

labelled as (
    select
        game_id,
        season,
        game_date,
        event_id,
        goalie_id,
        goalie_team_id,
        shooting_team_id,
        is_goal,
        is_on_goal,
        xg,
        -- danger tier from per-shot xG (null xg -> 'unknown', e.g. rare missing coords)
        case
            when xg is null then 'unknown'
            when xg < {{ low_max }} then 'low'
            when xg < {{ high_min }} then 'medium'
            else 'high'
        end as danger_tier,
        -- strength from the goalie's perspective: even (5v5) or facing a PP/PK
        case
            when situation_code = '1551' then 'ev'
            when situation_code is null then 'other'
            else 'special'
        end as strength_vs
    from with_xg
)

select * from labelled
