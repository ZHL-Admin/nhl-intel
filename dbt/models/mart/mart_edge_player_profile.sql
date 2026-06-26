{{ config(cluster_by=["season_id", "player_id"]) }}

-- Per player-season NHL Edge profile: skating speed/bursts, distance, shot speed,
-- zone time/zone starts (all + even-strength), and NHL danger-bucket shot share.
-- Burst rates per 60 use REAL season TOI from stg_shifts (the shift layer), null-safe
-- when TOI is unavailable. Edge is season-aggregate profile data — never per-play.

with edge as (
    select * from {{ ref('stg_edge_skaters') }}
),

toi as (
    -- Season TOI per player, with season recast to the Edge YYYYYYYY id.
    select
        player_id,
        cast(substr(season, 1, 4) as int64) * 10000
            + (cast(substr(season, 1, 4) as int64) + 1) as season_id,
        sum(duration_seconds) / 60.0 as toi_minutes
    from {{ ref('stg_shifts') }}
    group by player_id, season_id
)

select
    e.player_id,
    e.season_id,
    e.game_type,

    -- Skating speed + bursts
    e.max_skating_speed_mph,
    e.max_skating_speed_pctile,
    e.bursts_22_plus,
    e.bursts_22_plus_pctile,
    e.bursts_20_to_22,
    e.bursts_18_to_20,

    -- Shot speed
    e.avg_shot_speed_mph,
    e.max_shot_speed_mph,

    -- Distance
    e.distance_per60_mi,
    e.distance_total_mi,

    -- Zone time / starts
    e.oz_time_pct,
    e.nz_time_pct,
    e.dz_time_pct,
    e.oz_time_pct_es,
    e.dz_time_pct_es,
    e.oz_start_pct,
    e.nz_start_pct,
    e.dz_start_pct,
    e.oz_start_pctile,
    e.dz_start_pctile,

    -- Danger profile
    e.total_sog,
    e.high_danger_sog,
    e.high_danger_goals,
    safe_divide(e.high_danger_sog, e.total_sog) as high_danger_sog_share,

    -- Burst rates per 60 (real TOI denominator; null-safe when toi=0)
    t.toi_minutes,
    case when t.toi_minutes > 0 then e.bursts_22_plus / (t.toi_minutes / 60.0) end as bursts_22_plus_per60,
    case when t.toi_minutes > 0 then (coalesce(e.bursts_20_to_22, 0) + coalesce(e.bursts_22_plus, 0)) / (t.toi_minutes / 60.0) end as bursts_20_plus_per60
from edge e
left join toi t
    on e.player_id = t.player_id and e.season_id = t.season_id
