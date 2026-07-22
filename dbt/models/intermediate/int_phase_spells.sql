{{ config(
    materialized='table',
    partition_by={"field": "game_date", "data_type": "date", "granularity": "day"},
    cluster_by=["season", "game_id"]
) }}

-- Phase Value (phase_value_v1) — spells: maximal intervals of constant (possession, zone_abs, liveness),
-- SPLIT at 5v5 strength boundaries (spec Section 5.3). Grain: one row per (spell x overlapping segment),
-- so every row is wholly inside one shift-segment and thus carries a single strength. is_5v5 is the RAPM
-- strength (int_segment_context.strength_state = '5v5'). Because the game clock (elapsed_seconds) only
-- advances during live play, summing is_5v5 spell durations reproduces total 5v5 segment time
-- (Stage 1 conservation gate). state_rel is expressed from the possessing team's perspective.

with ev as (
    select
        game_id, season, game_date, period_number, sort_order, elapsed_seconds,
        home_team_id, away_team_id, poss_after, zone_abs, is_live
    from {{ ref('int_phase_events') }}
),

-- state-change detection within (game, period): a new spell starts when the (poss, zone, live) triple
-- differs from the previous event's. '~' sentinels let NULLs compare equal.
marked as (
    select
        *,
        case
            when lag(elapsed_seconds) over w is null then 1
            when coalesce(cast(poss_after as string), '~') != coalesce(cast(lag(poss_after) over w as string), '~')
              or coalesce(zone_abs, '~')                  != coalesce(lag(zone_abs) over w, '~')
              or is_live                                  != lag(is_live) over w
                then 1
            else 0
        end as is_change
    from ev
    window w as (partition by game_id, period_number order by sort_order)
),

seq as (
    select
        *,
        sum(is_change) over (
            partition by game_id, period_number order by sort_order
            rows between unbounded preceding and current row
        ) as spell_seq
    from marked
),

-- collapse consecutive same-state events into one state spell
state_spells as (
    select
        game_id, season, game_date, period_number, spell_seq,
        min(elapsed_seconds)   as start_elapsed,
        any_value(home_team_id) as home_team_id,
        any_value(away_team_id) as away_team_id,
        any_value(poss_after)   as poss_team_id,
        any_value(zone_abs)     as zone_abs,
        any_value(is_live)      as is_live
    from seq
    group by game_id, season, game_date, period_number, spell_seq
),

-- spell end = next spell's start (within period); trailing spell gets 0 duration and is dropped below
spell_intervals as (
    select
        *,
        coalesce(
            lead(start_elapsed) over (partition by game_id, period_number order by spell_seq),
            start_elapsed
        ) as end_elapsed
    from state_spells
),

segs as (
    select game_id, segment_index, segment_start_seconds as seg_start,
           segment_end_seconds as seg_end, strength_state
    from {{ ref('int_segment_context') }}
),

-- split each spell by the segments it overlaps (strength-boundary split)
split as (
    select
        s.game_id, s.season, s.game_date, s.period_number, s.spell_seq, g.segment_index,
        s.home_team_id, s.away_team_id, s.poss_team_id, s.zone_abs, s.is_live,
        greatest(s.start_elapsed, g.seg_start) as start_elapsed,
        least(s.end_elapsed, g.seg_end)        as end_elapsed,
        g.strength_state
    from spell_intervals s
    join segs g
      on g.game_id = s.game_id
     and g.seg_start < s.end_elapsed
     and g.seg_end   > s.start_elapsed
    where s.end_elapsed > s.start_elapsed
)

select
    game_id, season, game_date, period_number, spell_seq, segment_index,
    start_elapsed, end_elapsed,
    (end_elapsed - start_elapsed) as duration_seconds,
    poss_team_id, zone_abs,
    case
        when poss_team_id is null then null
        when zone_abs = 'N' then 'P_NZ'
        when (poss_team_id = home_team_id and zone_abs = 'D_home')
          or (poss_team_id = away_team_id and zone_abs = 'D_away') then 'P_OWN_D'
        else 'P_OZ'
    end as state_rel,
    is_live,
    (strength_state = '5v5') as is_5v5
from split
where end_elapsed > start_elapsed
