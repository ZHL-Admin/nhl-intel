{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "player_id"]
) }}

-- Player shooting luck analysis: actual shooting % vs expected shooting %
-- Positive shooting_luck indicates player is scoring above expected (hot/lucky)
-- Negative shooting_luck indicates player is scoring below expected (cold/unlucky)

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
        individual_shot_attempts,
        individual_goals,
        ixg
    from {{ ref('mart_player_game_stats') }}
),

final as (
    select
        game_id,
        game_date,
        season,
        player_id,
        team_id,
        first_name,
        last_name,
        position_code,
        individual_shot_attempts,
        individual_goals,
        ixg,

        -- Actual shooting percentage
        case
            when individual_shot_attempts > 0
            then cast(individual_goals as float64) / individual_shot_attempts
            else 0.0
        end as actual_sh_pct,

        -- Expected shooting percentage
        case
            when individual_shot_attempts > 0
            then ixg / individual_shot_attempts
            else 0.0
        end as expected_sh_pct,

        -- Shooting luck differential
        case
            when individual_shot_attempts > 0
            then (cast(individual_goals as float64) / individual_shot_attempts) - (ixg / individual_shot_attempts)
            else 0.0
        end as shooting_luck,

        -- Goals above/below expected
        cast(individual_goals as float64) - ixg as goals_above_expected

    from player_stats
)

select * from final
