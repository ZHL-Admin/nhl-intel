-- One row per (game_id, event_id, entity) at each goal's release/arrival frame:
-- the puck plus every on-ice skater, team-labeled, in standard center-origin coords.
-- This is the single tracked moment Phase 6.4 renders on the rink.
--
-- RELEASE-FRAME SELECTION: the sprite payload carries no field aligning a frame's
-- epoch timeStamp to the game clock, so we pin the moment GEOMETRICALLY from the
-- tracking itself: the frame where the puck is closest to a net (|x_std| -> ~89). At a
-- goal the puck arrives at the attacked net, so this is the unambiguous, orientation-
-- independent anchor for the scoring moment (no need to decode home/away defending side).
-- Documented + orientation-checked in docs/methodology/ppt-replay-tracking.md.

with puck_frames as (
    select
        game_id,
        event_id,
        frame_index,
        frame_seconds,
        x_std,
        -- distance to whichever net the puck is nearest (nets at x_std = +/-89)
        least(abs(x_std - 89.0), abs(x_std + 89.0)) as dist_to_nearest_net
    from {{ ref('stg_ppt_tracking_frames') }}
    where is_puck
),

release_frame as (
    select game_id, event_id, frame_index, frame_seconds, dist_to_nearest_net,
        row_number() over (
            partition by game_id, event_id
            order by dist_to_nearest_net asc, frame_index asc
        ) as rn
    from puck_frames
),

chosen as (
    select game_id, event_id, frame_index,
        frame_seconds as release_frame_seconds,
        dist_to_nearest_net as puck_dist_to_net
    from release_frame
    where rn = 1
)

select
    f.game_id,
    f.event_id,
    f.season,
    c.frame_index as release_frame_index,
    c.release_frame_seconds,
    c.puck_dist_to_net,
    f.is_puck,
    f.player_id,
    f.team_id,
    f.team_abbrev,
    f.sweater_number,
    f.x_std,
    f.y_std
from {{ ref('stg_ppt_tracking_frames') }} f
join chosen c
    on f.game_id = c.game_id
    and f.event_id = c.event_id
    and f.frame_index = c.frame_index
