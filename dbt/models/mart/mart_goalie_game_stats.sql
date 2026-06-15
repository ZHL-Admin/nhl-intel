{{ config(
    partition_by={"field": "game_date", "data_type": "date", "granularity": "day"},
    cluster_by=["season", "goalie_id"]
) }}

-- Per goalie-game line on the in-house xG layer (Phase 2.5). xGA is summed over ALL
-- unblocked shots faced (the model's training population, so it is calibrated against
-- actual goals); shots_faced / saves / save% use on-goal shots only (a miss is not a save).
-- GSAx = xGA - GA, split by danger tier (from per-shot xG) and by strength (even vs special).

with shots as (
    select * from {{ ref('int_goalie_shots') }}
)

select
    game_id,
    season,
    game_date,
    goalie_id,
    any_value(goalie_team_id) as team_id,

    countif(is_on_goal) as shots_faced,
    countif(is_goal) as goals_against,
    countif(is_on_goal and not is_goal) as saves,
    sum(coalesce(xg, 0)) as xga,
    sum(coalesce(xg, 0)) - countif(is_goal) as gsax,
    safe_divide(countif(is_on_goal and not is_goal), countif(is_on_goal)) as save_pct,
    count(*) as unblocked_faced,

    -- by danger tier (xGA over all unblocked in tier; saves/shots on-goal in tier)
    countif(danger_tier = 'high' and is_on_goal) as high_shots,
    countif(danger_tier = 'high' and is_on_goal and not is_goal) as high_saves,
    countif(danger_tier = 'high' and is_goal) as high_ga,
    sum(if(danger_tier = 'high', coalesce(xg, 0), 0)) as high_xga,
    sum(if(danger_tier = 'high', coalesce(xg, 0), 0)) - countif(danger_tier = 'high' and is_goal) as high_gsax,
    safe_divide(countif(danger_tier = 'high' and is_on_goal and not is_goal), countif(danger_tier = 'high' and is_on_goal)) as high_save_pct,

    countif(danger_tier = 'medium' and is_on_goal) as med_shots,
    countif(danger_tier = 'medium' and is_on_goal and not is_goal) as med_saves,
    sum(if(danger_tier = 'medium', coalesce(xg, 0), 0)) - countif(danger_tier = 'medium' and is_goal) as med_gsax,

    countif(danger_tier = 'low' and is_on_goal) as low_shots,
    countif(danger_tier = 'low' and is_on_goal and not is_goal) as low_saves,
    sum(if(danger_tier = 'low', coalesce(xg, 0), 0)) - countif(danger_tier = 'low' and is_goal) as low_gsax,

    -- by strength
    sum(if(strength_vs = 'ev', coalesce(xg, 0), 0)) - countif(strength_vs = 'ev' and is_goal) as ev_gsax,
    countif(strength_vs = 'ev' and is_on_goal) as ev_shots,
    sum(if(strength_vs = 'special', coalesce(xg, 0), 0)) - countif(strength_vs = 'special' and is_goal) as special_gsax,
    countif(strength_vs = 'special' and is_on_goal) as special_shots
from shots
group by game_id, season, game_date, goalie_id
