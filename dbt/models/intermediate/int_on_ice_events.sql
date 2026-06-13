{{ config(materialized='table') }}

-- Every play-by-play event joined to its containing shift segment, producing the
-- on-ice player_ids FOR (the event-owner team) and AGAINST (the opponent).
--
-- This is the attribution backbone every later phase consumes: on-ice xG share,
-- RAPM design rows, GSAx (goalie in net), chemistry, and coach-trust all start here.
-- Event game-elapsed seconds are computed consistently with int_shift_segments.

with events as (
    select
        game_id,
        event_id,
        sort_order,
        type_desc_key,
        event_owner_team_id,
        (period_number - 1) * 1200
            + cast(split(time_in_period, ':')[offset(0)] as int64) * 60
            + cast(split(time_in_period, ':')[offset(1)] as int64) as event_seconds
    from {{ ref('stg_play_by_play') }}
    where time_in_period is not null
),

segments as (
    select distinct
        game_id, segment_index, segment_start_seconds, segment_end_seconds
    from {{ ref('int_shift_segments') }}
),

members as (
    select game_id, segment_index, player_id, team_id
    from {{ ref('int_shift_segments') }}
),

event_segments as (
    -- An event belongs to the segment (segment_start, segment_end]. The half-open
    -- side is the LOWER bound: stoppage events (goals, whistles) carry the timestamp
    -- at which the on-ice players' shifts END, so the event must attribute to the
    -- segment ending at T (the line that was playing), not the post-faceoff segment
    -- starting at T. The opening event at t=0 is matched to the first segment.
    select e.*, s.segment_index
    from events e
    join segments s
        on s.game_id = e.game_id
       and e.event_seconds <= s.segment_end_seconds
       and (
            e.event_seconds > s.segment_start_seconds
            or (e.event_seconds = 0 and s.segment_start_seconds = 0)
       )
)

select
    es.game_id,
    es.event_id,
    es.sort_order,
    es.type_desc_key,
    es.event_owner_team_id,
    es.event_seconds,
    es.segment_index,
    array_agg(distinct if(m.team_id = es.event_owner_team_id, m.player_id, null) ignore nulls) as on_ice_for,
    array_agg(distinct if(m.team_id != es.event_owner_team_id, m.player_id, null) ignore nulls) as on_ice_against
from event_segments es
left join members m
    on m.game_id = es.game_id and m.segment_index = es.segment_index
group by 1, 2, 3, 4, 5, 6, 7
