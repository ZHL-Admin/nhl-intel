{{ config(materialized='table', cluster_by=["season", "team_id"]) }}

-- int_line_seasons: every forward trio and defense pair that shared >= var('line_min_5v5_minutes')
-- of 5v5 ice in a single season, with its on-ice 5v5 results. This is the training set for the
-- Lineup Lab line-fit model (Phase 5.1, blueprint 6.2).
--
-- A segment "belongs to" a trio when EXACTLY those three forwards are the team's forwards on the
-- ice for that 5v5 segment (and likewise a pair when exactly those two defensemen are on). Line
-- minutes/xG accumulate over every such segment in the season. xG for the line is the owning
-- team's xG during its segments; xG against is the opponent's. Empty-net shots are already absent
-- from nhl_models.shot_xg, so they never enter these totals.
--
-- Grain: one row per (season, team_id, line_type, line_key). line_type is 'F3' (forward trio) or
-- 'D2' (defense pair). Regular season + playoffs only (game-id type '02'/'03'); segments exist
-- 2015-16+.

with seg_5v5 as (
    select game_id, segment_index, season, segment_duration
    from {{ ref('int_segment_context') }}
    where strength_state = '5v5'
),

-- skaters on ice per (segment, team), classified forward vs defense
seg_players as (
    select
        s.game_id, s.segment_index, s.season, s.team_id, s.player_id,
        c.segment_duration,
        case
            when s.position_code = 'D' then 'D'
            when s.position_code in ('C', 'L', 'R') then 'F'
            else 'X'
        end as fd
    from {{ ref('int_shift_segments') }} s
    join seg_5v5 c using (game_id, segment_index)
    where s.is_goalie = 0
      and substr(cast(s.game_id as string), 5, 2) in ('02', '03')
),

-- the forward set and defense set per (segment, team), sorted so the key is order-invariant
seg_fwd as (
    select game_id, segment_index, season, team_id,
        any_value(segment_duration) as dur,
        array_agg(player_id order by player_id) as members,
        count(*) as n_f
    from seg_players where fd = 'F'
    group by 1, 2, 3, 4
),
seg_def as (
    select game_id, segment_index, season, team_id,
        any_value(segment_duration) as dur,
        array_agg(player_id order by player_id) as members,
        count(*) as n_d
    from seg_players where fd = 'D'
    group by 1, 2, 3, 4
),

-- xG per (segment, team) from the attribution backbone; on-goal/missed unblocked shots only
seg_team_xg as (
    select o.game_id, o.segment_index, o.event_owner_team_id as team_id, sum(x.xg) as xg
    from {{ ref('int_on_ice_events') }} o
    join {{ source('nhl_models', 'shot_xg') }} x
        on o.game_id = x.game_id and o.event_id = x.event_id
    group by 1, 2, 3
),
seg_total_xg as (
    select game_id, segment_index, sum(xg) as tot_xg
    from seg_team_xg group by 1, 2
),

-- seq-type mix of the team's for-shots per (segment, team)
seg_seq as (
    select o.game_id, o.segment_index, o.event_owner_team_id as team_id,
        countif(q.seq_type = 'rush') as rush,
        countif(q.seq_type = 'rebound') as rebound,
        countif(q.seq_type = 'forecheck') as forecheck,
        countif(q.seq_type = 'cycle') as cycle,
        countif(q.seq_type = 'point_shot') as point_shot,
        count(*) as shots
    from {{ ref('int_on_ice_events') }} o
    join {{ ref('int_shot_sequence') }} q
        on o.game_id = q.game_id and o.event_id = q.event_id
       and q.team_id = o.event_owner_team_id
    group by 1, 2, 3
),

-- per-segment line rows for both forward trios and defense pairs
seg_lines as (
    select 'F3' as line_type, game_id, segment_index, season, team_id, members, dur
    from seg_fwd where n_f = 3
    union all
    select 'D2' as line_type, game_id, segment_index, season, team_id, members, dur
    from seg_def where n_d = 2
),

seg_lines_x as (
    select
        sl.line_type, sl.game_id, sl.segment_index, sl.season, sl.team_id, sl.members, sl.dur,
        (select string_agg(cast(m as string), '-' order by m) from unnest(sl.members) m) as line_key,
        coalesce(tx.xg, 0) as xgf,
        coalesce(tot.tot_xg, 0) - coalesce(tx.xg, 0) as xga,
        coalesce(ss.rush, 0) as rush, coalesce(ss.rebound, 0) as rebound,
        coalesce(ss.forecheck, 0) as forecheck, coalesce(ss.cycle, 0) as cycle,
        coalesce(ss.point_shot, 0) as point_shot, coalesce(ss.shots, 0) as shots
    from seg_lines sl
    left join seg_team_xg tx
        on tx.game_id = sl.game_id and tx.segment_index = sl.segment_index and tx.team_id = sl.team_id
    left join seg_total_xg tot
        on tot.game_id = sl.game_id and tot.segment_index = sl.segment_index
    left join seg_seq ss
        on ss.game_id = sl.game_id and ss.segment_index = sl.segment_index and ss.team_id = sl.team_id
),

agg as (
    select
        season, team_id, line_type, line_key,
        any_value(members) as members,
        sum(dur) / 60.0 as minutes,
        sum(xgf) as xgf, sum(xga) as xga,
        sum(rush) as seq_rush, sum(rebound) as seq_rebound, sum(forecheck) as seq_forecheck,
        sum(cycle) as seq_cycle, sum(point_shot) as seq_point_shot, sum(shots) as for_shots
    from seg_lines_x
    group by season, team_id, line_type, line_key
)

select
    season,
    team_id,
    line_type,
    line_key,
    members,
    array_length(members) as n_members,
    round(minutes, 3) as minutes,
    round(xgf, 4) as xgf,
    round(xga, 4) as xga,
    -- targets
    safe_divide(xgf, xgf + xga) as xgf_pct,
    safe_divide(xgf, minutes) * 60 as xgf_per60,
    safe_divide(xga, minutes) * 60 as xga_per60,
    -- for-shot seq-type shares (null-safe via safe_divide; null when the line took no for-shots)
    for_shots,
    safe_divide(seq_rush, for_shots) as for_rush_share,
    safe_divide(seq_rebound, for_shots) as for_rebound_share,
    safe_divide(seq_forecheck, for_shots) as for_forecheck_share,
    safe_divide(seq_cycle, for_shots) as for_cycle_share,
    safe_divide(seq_point_shot, for_shots) as for_point_share
from agg
where minutes >= {{ var('line_min_5v5_minutes') }}
