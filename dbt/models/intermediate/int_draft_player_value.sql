{{ config(materialized='table') }}

-- Realized career value per drafted pick (Handoff 5, Phase B). The UNIVERSE is EVERY pick in
-- stg_draft_results (backfilled 2005-2025); a pick whose player never reached the NHL gets realized
-- value 0, NOT missing (COALESCE below). The never-NHL picks are the biggest busts and must stay in
-- every denominator — that is the whole point of the survivorship-honest curve.
--
-- Realized value = sum of pwar_hat (nhl_models.player_pwar, the WAR-units back-cast currency) over the
-- player's first var('draft_eval_window_years') NHL-eligible post-draft seasons: a player drafted in
-- year Y is first eligible in season starting Y, so the window is season_start_year in [Y, Y+W-1].
--
-- is_evaluable = draft class fully observable under the window (the headline 2010-2018). is_censored =
-- the window extends past the latest season we have, so realized value understates (shown as "still
-- developing", never in the headline summary).

{% set W = var('draft_eval_window_years') %}

with picks as (
    select * from {{ ref('stg_draft_results') }}
),

pwar as (
    select player_id,
           cast(substr(season, 1, 4) as int64) as season_start_year,
           pwar_hat, pwar_sd, games_played
    from {{ source('nhl_models', 'player_pwar') }}
),

latest_season as (
    select max(season_start_year) as max_start from pwar
),

-- value over each pick's post-draft window, joined on the resolved player
windowed as (
    select
        p.pick_key,
        sum(w.pwar_hat)                          as realized_pwar,
        sqrt(sum(pow(coalesce(w.pwar_sd, 0), 2))) as realized_pwar_sd,   -- bands combine in quadrature
        sum(w.games_played)                      as games_played_window,
        max(w.pwar_hat)                          as peak_season_pwar
    from picks p
    join pwar w
      on w.player_id = p.resolved_player_id
     and w.season_start_year between p.draft_year and p.draft_year + {{ W }} - 1
    group by 1
),

-- career games (ALL seasons) for the became-regular threshold
career as (
    select p.pick_key, sum(w.games_played) as career_gp
    from picks p
    join pwar w on w.player_id = p.resolved_player_id
    group by 1
)

select
    p.pick_key,
    p.draft_year,
    p.round,
    p.overall_pick,
    p.draft_team_abbrev,
    p.full_name,
    p.pos_group,
    p.resolved_player_id,
    p.made_nhl,
    -- realized_pwar: honest signed sum over the window (can be negative for a below-replacement
    -- player who kept playing). never-NHL / no window season => 0 (NOT missing).
    coalesce(wd.realized_pwar, 0.0)        as realized_pwar,
    -- realized_value: the ASSET value of the pick, floored at replacement (0) — a team plays a
    -- freely-available replacement instead of a net-negative player, so a pick cannot be worth < 0.
    -- This is the quantity the pick-value curve and theory test use (matches slot_war's floor).
    greatest(coalesce(wd.realized_pwar, 0.0), 0.0) as realized_value,
    coalesce(wd.realized_pwar_sd, 0.0)     as realized_pwar_sd,
    coalesce(wd.games_played_window, 0)    as games_played_window,
    coalesce(wd.peak_season_pwar, 0.0)     as peak_season_pwar,
    coalesce(c.career_gp, 0)               as career_gp,
    coalesce(c.career_gp, 0) >= {{ var('draft_regular_gp') }} as became_regular,
    -- evaluability / censoring
    p.draft_year between {{ var('draft_eval_class_min') }} and {{ var('draft_eval_class_max') }}
        as is_evaluable,
    (p.draft_year + {{ W }} - 1) > ls.max_start as is_censored
from picks p
cross join latest_season ls
left join windowed wd on wd.pick_key = p.pick_key
left join career   c  on c.pick_key  = p.pick_key
