{{ config(materialized='table', cluster_by=['season', 'shooter_id']) }}

-- Every unblocked shot joined to the win-probability LEVERAGE at its timestamp (Phase 4.3),
-- the input to leverage-weighted (clutch) production. win_probability is sampled ~every 10s
-- but the grid is offset per segment, so we bucket BOTH sides to a global 10-second grid
-- (floor/10) and average leverage within each game-bucket. Win-prob/leverage exists for
-- 2015-16+ only (segment-context coverage); earlier shots get null leverage and are excluded.

with shots as (
    select q.game_id, q.season, q.game_date, q.event_id, q.shooter_id, q.team_id,
           q.elapsed_seconds, q.is_goal, s.xg
    from {{ ref('int_shot_sequence') }} q
    join {{ source('nhl_models', 'shot_xg') }} s
        on q.game_id = s.game_id and q.event_id = s.event_id
    where s.xg is not null
),

wp as (
    select game_id, cast(floor(elapsed_seconds / 10) * 10 as int64) as bucket,
           avg(leverage) as leverage
    from {{ source('nhl_models', 'win_probability') }}
    group by 1, 2
)

select
    sh.game_id, sh.season, sh.game_date, sh.event_id, sh.shooter_id, sh.team_id,
    sh.elapsed_seconds, sh.is_goal, sh.xg,
    w.leverage
from shots sh
left join wp w
    on w.game_id = sh.game_id
    and w.bucket = cast(floor(sh.elapsed_seconds / 10) * 10 as int64)
