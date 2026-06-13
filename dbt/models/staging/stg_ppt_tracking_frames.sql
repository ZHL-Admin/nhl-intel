-- One row per (game_id, event_id, frame_index, entity): ppt-replay goal tracking.
-- Source: nhl_raw.raw_ppt_replay (frames serialized; onIce normalized to a list of
-- entities upstream, each carrying entityKey — puck is entityKey '1').
--
-- COORDINATE TRANSFORM (documented + EMPIRICALLY corrected in
-- docs/methodology/ppt-replay-tracking.md): the plan guessed "tenths of a foot, ~2000 x
-- 850", but the observed raw bounds are ~0..2400 (x) and ~0..1020 (y) — exactly
-- 12 x (200 ft) by 12 x (85 ft), i.e. the units are INCHES (12 per foot), corner-origin.
-- We convert to the SAME center-origin standard system (feet) the shot/xG models use:
--   x_std = raw_x/12 - 100   (range ~ -100..100; end boards +/-100, goal line +/-89)
--   y_std = raw_y/12 - 42.5  (range ~ -42.5..42.5)
-- With /12 every tracked entity falls within the rink; /10 put skaters ~20 ft past the
-- boards (the orientation check that caught the unit error).
-- timeStamp is deciseconds; frame_seconds is seconds since the clip's first frame.

with latest as (
    select game_id, event_id, season, frames,
        row_number() over (partition by game_id, event_id order by ingestion_date desc) as rn
    from {{ source('nhl', 'raw_ppt_replay') }}
),

dedup as (
    select game_id, event_id, season, frames from latest where rn = 1
),

frames_unnested as (
    select
        d.game_id,
        d.event_id,
        d.season,
        frame_off as frame_index,
        cast(json_extract_scalar(frame, '$.timeStamp') as int64) as timestamp_ds,
        json_extract_array(frame, '$.onIce') as on_ice
    from dedup d,
        unnest(json_extract_array(d.frames)) as frame with offset as frame_off
),

entities as (
    select
        f.game_id,
        f.event_id,
        f.season,
        f.frame_index,
        f.timestamp_ds,
        json_extract_scalar(ent, '$.entityKey') = '1' as is_puck,
        safe_cast(json_extract_scalar(ent, '$.playerId') as int64) as player_id,
        safe_cast(json_extract_scalar(ent, '$.teamId') as int64) as team_id,
        json_extract_scalar(ent, '$.teamAbbrev') as team_abbrev,
        safe_cast(json_extract_scalar(ent, '$.sweaterNumber') as int64) as sweater_number,
        safe_cast(json_extract_scalar(ent, '$.x') as float64) as raw_x,
        safe_cast(json_extract_scalar(ent, '$.y') as float64) as raw_y
    from frames_unnested f,
        unnest(f.on_ice) as ent
)

select
    game_id,
    event_id,
    season,
    frame_index,
    timestamp_ds,
    (timestamp_ds - min(timestamp_ds) over (partition by game_id, event_id)) / 10.0 as frame_seconds,
    is_puck,
    player_id,
    team_id,
    team_abbrev,
    sweater_number,
    raw_x,
    raw_y,
    raw_x / 12.0 - 100.0 as x_std,
    raw_y / 12.0 - 42.5 as y_std
from entities
