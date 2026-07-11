{{ config(materialized='table') }}

-- Shift-overlap segmentation: a SEGMENT is a maximal interval of game time during
-- which the set of skaters on the ice is unchanged. Built by collecting every shift
-- boundary timestamp per game, forming consecutive [t_i, t_{i+1}) intervals, and
-- attaching every player whose shift spans the interval.
--
-- Grain: one row per (game_id, segment_index, player_id), carrying the player's
-- team on-ice counts for that segment. This is the on-ice attribution backbone
-- consumed by int_segment_context and int_on_ice_events.

with shifts as (
    select game_id, season, player_id, team_id, shift_start_seconds, shift_end_seconds
    from {{ ref('stg_shifts') }}
),

rosters as (
    select
        game_id,
        player_id,
        position_code,
        case when position_code = 'G' then 1 else 0 end as is_goalie
    from {{ ref('stg_rosters') }}
),

-- Goal cut-points (Atlas Amendment A): a goal is a segment boundary so the score
-- state is CONSTANT within every segment. Shootout goals have no shifts and are
-- excluded. Event seconds use the same (period-1)*1200 offset as shifts.
goals as (
    select
        game_id,
        (period_number - 1) * 1200
            + cast(split(time_in_period, ':')[offset(0)] as int64) * 60
            + cast(split(time_in_period, ':')[offset(1)] as int64) as t
    from {{ ref('stg_play_by_play') }}
    where type_desc_key = 'goal'
      and period_type != 'SO'
      and time_in_period is not null
),

boundaries as (
    select distinct game_id, t
    from (
        select game_id, shift_start_seconds as t from shifts
        union distinct
        select game_id, shift_end_seconds as t from shifts
        union distinct
        select game_id, t from goals
    )
),

intervals as (
    select
        game_id,
        t as segment_start_seconds,
        lead(t) over (partition by game_id order by t) as segment_end_seconds,
        row_number() over (partition by game_id order by t) as segment_index
    from boundaries
),

valid_intervals as (
    -- drop zero-length and trailing (null end) intervals
    select
        game_id,
        segment_index,
        segment_start_seconds,
        segment_end_seconds,
        segment_end_seconds - segment_start_seconds as segment_duration
    from intervals
    where segment_end_seconds is not null
      and segment_end_seconds > segment_start_seconds
),

members as (
    -- a player is on ice for the segment when their shift spans it entirely
    select
        i.game_id,
        s.season,
        i.segment_index,
        i.segment_start_seconds,
        i.segment_end_seconds,
        i.segment_duration,
        s.player_id,
        s.team_id,
        coalesce(r.position_code, 'X') as position_code,
        coalesce(r.is_goalie, 0) as is_goalie
    from valid_intervals i
    join shifts s
        on s.game_id = i.game_id
       and s.shift_start_seconds <= i.segment_start_seconds
       and s.shift_end_seconds >= i.segment_end_seconds
    left join rosters r
        on r.game_id = s.game_id and r.player_id = s.player_id
),

team_counts as (
    select
        game_id,
        segment_index,
        team_id,
        countif(is_goalie = 0) as team_skater_count,
        countif(is_goalie = 1) as team_goalie_count
    from members
    group by game_id, segment_index, team_id
),

flagged as (
    select
        m.*,
        tc.team_skater_count,
        tc.team_goalie_count,
        max(tc.team_skater_count) over (partition by m.game_id, m.segment_index) as max_side_skaters
    from members m
    join team_counts tc
        on tc.game_id = m.game_id
       and tc.segment_index = m.segment_index
       and tc.team_id = m.team_id
)

select
    game_id,
    season,
    segment_index,
    segment_start_seconds,
    segment_end_seconds,
    segment_duration,
    player_id,
    team_id,
    position_code,
    is_goalie,
    team_skater_count,
    team_goalie_count
from flagged
-- Documented noise rule: a legal side has at most 6 skaters (6v5 with the goalie
-- pulled). Segments showing > 6 skaters per side are sub-second line-change overlaps
-- (a player stepping off and a player stepping on share a boundary second); they are
-- transient artifacts, not real on-ice states, so they are excluded here (not dropped
-- silently). The count of excluded segments is reported in validation.
where max_side_skaters <= 6
