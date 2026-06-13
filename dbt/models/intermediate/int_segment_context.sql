{{ config(materialized='table') }}

-- One row per (game_id, segment_index): the game-state context of each shift
-- segment — strength state, score at segment start, score-state bucket, and whether
-- the segment begins on a faceoff (zone start). Consumed by RAPM and all on-ice
-- attribution that needs to condition on situation.
--
-- Event game-elapsed seconds are computed the same way as int_shift_segments:
-- (period_number - 1) * 1200 + mm*60 + ss.

with seg as (
    select distinct
        game_id, season, segment_index,
        segment_start_seconds, segment_end_seconds, segment_duration
    from {{ ref('int_shift_segments') }}
),

box as (
    select game_id, home_team_id, away_team_id from {{ ref('stg_boxscores') }}
),

team_counts as (
    select
        game_id, segment_index, team_id,
        max(team_skater_count) as skaters,
        max(team_goalie_count) as goalies
    from {{ ref('int_shift_segments') }}
    group by game_id, segment_index, team_id
),

pivoted as (
    select
        s.game_id, s.season, s.segment_index,
        s.segment_start_seconds, s.segment_end_seconds, s.segment_duration,
        b.home_team_id, b.away_team_id,
        max(if(tc.team_id = b.home_team_id, tc.skaters, null)) as home_skaters,
        max(if(tc.team_id = b.away_team_id, tc.skaters, null)) as away_skaters,
        max(if(tc.team_id = b.home_team_id, tc.goalies, null)) as home_goalies,
        max(if(tc.team_id = b.away_team_id, tc.goalies, null)) as away_goalies
    from seg s
    join box b using (game_id)
    left join team_counts tc
        on tc.game_id = s.game_id and tc.segment_index = s.segment_index
    group by 1, 2, 3, 4, 5, 6, 7, 8
),

pbp as (
    select
        game_id, type_desc_key, event_owner_team_id, zone_code,
        (period_number - 1) * 1200
            + cast(split(time_in_period, ':')[offset(0)] as int64) * 60
            + cast(split(time_in_period, ':')[offset(1)] as int64) as event_seconds
    from {{ ref('stg_play_by_play') }}
    where time_in_period is not null
),

goals as (
    select game_id, event_owner_team_id, event_seconds
    from pbp where type_desc_key = 'goal'
),

faceoffs as (
    select game_id, zone_code, event_seconds
    from pbp where type_desc_key = 'faceoff'
),

scored as (
    select
        p.game_id, p.segment_index,
        countif(g.event_owner_team_id = p.home_team_id and g.event_seconds <= p.segment_start_seconds) as home_score,
        countif(g.event_owner_team_id = p.away_team_id and g.event_seconds <= p.segment_start_seconds) as away_score
    from pivoted p
    left join goals g on g.game_id = p.game_id
    group by p.game_id, p.segment_index
),

zone_started as (
    -- segment begins within 2s after a faceoff -> carry that faceoff's zone code
    select
        p.game_id, p.segment_index,
        array_agg(f.zone_code order by f.event_seconds desc limit 1)[offset(0)] as faceoff_zone_code
    from pivoted p
    join faceoffs f
        on f.game_id = p.game_id
       and f.event_seconds <= p.segment_start_seconds
       and f.event_seconds >= p.segment_start_seconds - 2
    group by p.game_id, p.segment_index
)

select
    p.game_id,
    p.season,
    p.segment_index,
    p.segment_start_seconds,
    p.segment_end_seconds,
    p.segment_duration,
    p.home_team_id,
    p.away_team_id,
    p.home_skaters,
    p.away_skaters,
    p.home_goalies,
    p.away_goalies,
    -- strength state from the home perspective; EN when either goalie is pulled
    case
        when p.home_goalies = 0 or p.away_goalies = 0 then 'EN'
        else concat(cast(p.home_skaters as string), 'v', cast(p.away_skaters as string))
    end as strength_state,
    coalesce(sc.home_score, 0) as home_score,
    coalesce(sc.away_score, 0) as away_score,
    case
        when coalesce(sc.home_score, 0) > coalesce(sc.away_score, 0) then 'leading'
        when coalesce(sc.home_score, 0) < coalesce(sc.away_score, 0) then 'trailing'
        else 'tied'
    end as home_score_state,
    zs.faceoff_zone_code is not null as is_zone_start,
    zs.faceoff_zone_code as zone_start_code
from pivoted p
left join scored sc on sc.game_id = p.game_id and sc.segment_index = p.segment_index
left join zone_started zs on zs.game_id = p.game_id and zs.segment_index = p.segment_index
