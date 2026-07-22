{{ config(
    materialized='table',
    partition_by={"field": "game_date", "data_type": "date", "granularity": "day"},
    cluster_by=["season", "game_id"]
) }}

-- Phase Value (phase_value_v1) — ticks (spec Section 6.1): one row per phase_tick_seconds of LIVE 5v5
-- spell time, the duration-weighting grid for the state value function V(state). The rush/established
-- split of P_OZ is resolved HERE (spec Section 5.3): a P_OZ tick is P_OZ_RUSH iff its containing episode
-- has start_type='rush' AND (tick_elapsed - episode start) <= phase_rush_state_seconds; else P_OZ_EST.
-- A partial trailing tick shorter than half a tick length is dropped; otherwise kept with its actual
-- duration in tick_duration.

{% set tick = var('phase_tick_seconds') %}
{% set rush_state = var('phase_rush_state_seconds') %}

with spells as (
    -- live 5v5 spells with a defined possessing team (drop dead / null-possession)
    select
        game_id, season, game_date, period_number, spell_seq,
        start_elapsed, end_elapsed, poss_team_id, zone_abs, state_rel
    from {{ ref('int_phase_spells') }}
    where is_5v5 and is_live and poss_team_id is not null and state_rel is not null
      and end_elapsed > start_elapsed
),

-- generate tick start offsets across each spell; keep a partial trailing tick only if >= half a tick
ticks as (
    select
        s.*,
        tick_start,
        least(s.end_elapsed, tick_start + {{ tick }}) - tick_start as tick_duration
    from spells s,
        unnest(generate_array(s.start_elapsed, s.end_elapsed - 0.0001, {{ tick }})) as tick_start
    where (least(s.end_elapsed, tick_start + {{ tick }}) - tick_start) >= {{ tick }} / 2.0
),

-- home/away for defending-team resolution
box as (select game_id, home_team_id, away_team_id from {{ ref('stg_boxscores') }}),

resolved as (
    select
        tk.game_id, tk.season, tk.game_date, tk.period_number,
        tk.tick_start as tick_elapsed, tk.tick_duration,
        tk.poss_team_id as possession_team_id, tk.zone_abs, tk.state_rel,
        -- defending team = the team whose D zone the puck is in (only meaningful in P_OZ)
        case tk.zone_abs when 'D_home' then b.home_team_id when 'D_away' then b.away_team_id else null end
            as defending_team_id
    from ticks tk
    join box b using (game_id)
),

-- for P_OZ ticks, attach the containing episode (defending team + time) for the rush/established split
oz_ep as (
    select
        r.game_id, r.period_number, r.tick_elapsed,
        ep.episode_id,
        ep.start_type as ep_start_type,
        (r.tick_elapsed - ep.start_elapsed) as age_in_episode
    from resolved r
    join {{ ref('int_zone_episodes') }} ep
      on ep.game_id = r.game_id
     and ep.defending_team_id = r.defending_team_id
     and ep.attacker_team_id = r.possession_team_id
     and r.tick_elapsed >= ep.start_elapsed and r.tick_elapsed <= ep.end_elapsed
    where r.state_rel = 'P_OZ'
)

select
    r.game_id, r.season, r.game_date, r.period_number,
    r.tick_elapsed, r.tick_duration,
    r.possession_team_id, r.defending_team_id,
    case
        when r.state_rel = 'P_OWN_D' then 'P_OWN_D'
        when r.state_rel = 'P_NZ' then 'P_NZ'
        when oz.ep_start_type = 'rush' and oz.age_in_episode <= {{ rush_state }} then 'P_OZ_RUSH'
        else 'P_OZ_EST'
    end as state,
    oz.episode_id   -- null unless P_OZ_*
from resolved r
left join oz_ep oz
  on oz.game_id = r.game_id and oz.period_number = r.period_number and oz.tick_elapsed = r.tick_elapsed
