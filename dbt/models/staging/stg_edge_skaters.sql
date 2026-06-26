-- One row per (player, season, game_type): NHL Edge skater season aggregates,
-- pivoted from the 5 per-report rows in raw_edge_skaters into typed columns.
-- Each Edge metric ships value + league percentile + league average; we keep all
-- three where the blueprint consumes them (percentile/avg drive PercentileBarList
-- and the conversion panels). Distances/speeds are imperial (mph / miles).
-- Zone-time is captured for 'all' and 'es' (even-strength) strength codes.

with dedup as (
    select entity_id, season_id, game_type, report, data
    from (
        select *,
            row_number() over (
                partition by entity_id, season_id, game_type, report
                order by ingestion_date desc
            ) as rn
        from {{ source('nhl', 'raw_edge_skaters') }}
    )
    where rn = 1
),

per_report as (
    select
        entity_id,
        season_id,
        game_type,

        -- skating-speed-detail
        case when report = 'skating-speed-detail' then safe_cast(json_extract_scalar(data, '$.skatingSpeedDetails.maxSkatingSpeed.imperial') as float64) end as max_skating_speed_mph,
        case when report = 'skating-speed-detail' then safe_cast(json_extract_scalar(data, '$.skatingSpeedDetails.maxSkatingSpeed.percentile') as float64) end as max_skating_speed_pctile,
        case when report = 'skating-speed-detail' then safe_cast(json_extract_scalar(data, '$.skatingSpeedDetails.burstsOver22.value') as int64) end as bursts_22_plus,
        case when report = 'skating-speed-detail' then safe_cast(json_extract_scalar(data, '$.skatingSpeedDetails.burstsOver22.percentile') as float64) end as bursts_22_plus_pctile,
        case when report = 'skating-speed-detail' then safe_cast(json_extract_scalar(data, '$.skatingSpeedDetails.bursts20To22.value') as int64) end as bursts_20_to_22,
        case when report = 'skating-speed-detail' then safe_cast(json_extract_scalar(data, '$.skatingSpeedDetails.bursts18To20.value') as int64) end as bursts_18_to_20,

        -- shot-speed-detail
        case when report = 'shot-speed-detail' then safe_cast(json_extract_scalar(data, '$.shotSpeedDetails.topShotSpeed.imperial') as float64) end as max_shot_speed_mph,
        case when report = 'shot-speed-detail' then safe_cast(json_extract_scalar(data, '$.shotSpeedDetails.avgShotSpeed.imperial') as float64) end as avg_shot_speed_mph,

        -- skating-distance-detail ('all' strength row)
        case when report = 'skating-distance-detail' then (
            select safe_cast(json_extract_scalar(x, '$.distancePer60.imperial') as float64)
            from unnest(json_extract_array(data, '$.skatingDistanceDetails')) x
            where json_extract_scalar(x, '$.strengthCode') = 'all' limit 1) end as distance_per60_mi,
        case when report = 'skating-distance-detail' then (
            select safe_cast(json_extract_scalar(x, '$.distanceTotal.imperial') as float64)
            from unnest(json_extract_array(data, '$.skatingDistanceDetails')) x
            where json_extract_scalar(x, '$.strengthCode') = 'all' limit 1) end as distance_total_mi,

        -- shot-location-detail (NHL danger buckets: high / mid / long)
        case when report = 'shot-location-detail' then (
            select safe_cast(json_extract_scalar(x, '$.sog') as int64)
            from unnest(json_extract_array(data, '$.shotLocationTotals')) x
            where json_extract_scalar(x, '$.locationCode') = 'all' limit 1) end as total_sog,
        case when report = 'shot-location-detail' then (
            select safe_cast(json_extract_scalar(x, '$.sog') as int64)
            from unnest(json_extract_array(data, '$.shotLocationTotals')) x
            where json_extract_scalar(x, '$.locationCode') = 'high' limit 1) end as high_danger_sog,
        case when report = 'shot-location-detail' then (
            select safe_cast(json_extract_scalar(x, '$.goals') as int64)
            from unnest(json_extract_array(data, '$.shotLocationTotals')) x
            where json_extract_scalar(x, '$.locationCode') = 'high' limit 1) end as high_danger_goals,

        -- zone-time (no -detail suffix): 'all' and 'es' strength + zone starts
        case when report = 'zone-time' then (
            select safe_cast(json_extract_scalar(x, '$.offensiveZonePctg') as float64)
            from unnest(json_extract_array(data, '$.zoneTimeDetails')) x
            where json_extract_scalar(x, '$.strengthCode') = 'all' limit 1) end as oz_time_pct,
        case when report = 'zone-time' then (
            select safe_cast(json_extract_scalar(x, '$.neutralZonePctg') as float64)
            from unnest(json_extract_array(data, '$.zoneTimeDetails')) x
            where json_extract_scalar(x, '$.strengthCode') = 'all' limit 1) end as nz_time_pct,
        case when report = 'zone-time' then (
            select safe_cast(json_extract_scalar(x, '$.defensiveZonePctg') as float64)
            from unnest(json_extract_array(data, '$.zoneTimeDetails')) x
            where json_extract_scalar(x, '$.strengthCode') = 'all' limit 1) end as dz_time_pct,
        case when report = 'zone-time' then (
            select safe_cast(json_extract_scalar(x, '$.offensiveZonePctg') as float64)
            from unnest(json_extract_array(data, '$.zoneTimeDetails')) x
            where json_extract_scalar(x, '$.strengthCode') = 'es' limit 1) end as oz_time_pct_es,
        case when report = 'zone-time' then (
            select safe_cast(json_extract_scalar(x, '$.defensiveZonePctg') as float64)
            from unnest(json_extract_array(data, '$.zoneTimeDetails')) x
            where json_extract_scalar(x, '$.strengthCode') = 'es' limit 1) end as dz_time_pct_es,
        case when report = 'zone-time' then safe_cast(json_extract_scalar(data, '$.zoneStarts.offensiveZoneStartsPctg') as float64) end as oz_start_pct,
        case when report = 'zone-time' then safe_cast(json_extract_scalar(data, '$.zoneStarts.neutralZoneStartsPctg') as float64) end as nz_start_pct,
        case when report = 'zone-time' then safe_cast(json_extract_scalar(data, '$.zoneStarts.defensiveZoneStartsPctg') as float64) end as dz_start_pct,
        -- league percentiles for the zone starts (all situations). The OZ-start percentile is the
        -- cleanest league-relative lean signal (sidesteps the neutral-in-denominator issue).
        case when report = 'zone-time' then safe_cast(json_extract_scalar(data, '$.zoneStarts.offensiveZoneStartsPctgPercentile') as float64) end as oz_start_pctile,
        case when report = 'zone-time' then safe_cast(json_extract_scalar(data, '$.zoneStarts.defensiveZoneStartsPctgPercentile') as float64) end as dz_start_pctile
    from dedup
)

select
    entity_id as player_id,
    season_id,
    game_type,
    max(max_skating_speed_mph) as max_skating_speed_mph,
    max(max_skating_speed_pctile) as max_skating_speed_pctile,
    max(bursts_22_plus) as bursts_22_plus,
    max(bursts_22_plus_pctile) as bursts_22_plus_pctile,
    max(bursts_20_to_22) as bursts_20_to_22,
    max(bursts_18_to_20) as bursts_18_to_20,
    max(max_shot_speed_mph) as max_shot_speed_mph,
    max(avg_shot_speed_mph) as avg_shot_speed_mph,
    max(distance_per60_mi) as distance_per60_mi,
    max(distance_total_mi) as distance_total_mi,
    max(total_sog) as total_sog,
    max(high_danger_sog) as high_danger_sog,
    max(high_danger_goals) as high_danger_goals,
    max(oz_time_pct) as oz_time_pct,
    max(nz_time_pct) as nz_time_pct,
    max(dz_time_pct) as dz_time_pct,
    max(oz_time_pct_es) as oz_time_pct_es,
    max(dz_time_pct_es) as dz_time_pct_es,
    max(oz_start_pct) as oz_start_pct,
    max(nz_start_pct) as nz_start_pct,
    max(dz_start_pct) as dz_start_pct,
    max(oz_start_pctile) as oz_start_pctile,
    max(dz_start_pctile) as dz_start_pctile
from per_report
group by player_id, season_id, game_type
