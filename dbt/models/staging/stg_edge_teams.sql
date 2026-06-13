-- One row per (team, season, game_type): NHL Edge team season aggregates.
-- From team-shot-location-detail. shotLocationTotals is keyed by (position, locationCode);
-- we read the position='all' rows for the NHL danger-bucket shot profile (high/mid/long).

with dedup as (
    select entity_id, season_id, game_type, data
    from (
        select *,
            row_number() over (
                partition by entity_id, season_id, game_type, report
                order by ingestion_date desc
            ) as rn
        from {{ source('nhl', 'raw_edge_teams') }}
        where report = 'shot-location-detail'
    )
    where rn = 1
),

loc as (
    select
        entity_id as team_id,
        season_id,
        game_type,
        (select safe_cast(json_extract_scalar(x, '$.sog') as int64)
         from unnest(json_extract_array(data, '$.shotLocationTotals')) x
         where json_extract_scalar(x, '$.position') = 'all' and json_extract_scalar(x, '$.locationCode') = 'all' limit 1) as total_sog,
        (select safe_cast(json_extract_scalar(x, '$.sog') as int64)
         from unnest(json_extract_array(data, '$.shotLocationTotals')) x
         where json_extract_scalar(x, '$.position') = 'all' and json_extract_scalar(x, '$.locationCode') = 'high' limit 1) as high_danger_sog,
        (select safe_cast(json_extract_scalar(x, '$.sog') as int64)
         from unnest(json_extract_array(data, '$.shotLocationTotals')) x
         where json_extract_scalar(x, '$.position') = 'all' and json_extract_scalar(x, '$.locationCode') = 'mid' limit 1) as mid_danger_sog,
        (select safe_cast(json_extract_scalar(x, '$.sog') as int64)
         from unnest(json_extract_array(data, '$.shotLocationTotals')) x
         where json_extract_scalar(x, '$.position') = 'all' and json_extract_scalar(x, '$.locationCode') = 'long' limit 1) as long_danger_sog,
        (select safe_cast(json_extract_scalar(x, '$.goals') as int64)
         from unnest(json_extract_array(data, '$.shotLocationTotals')) x
         where json_extract_scalar(x, '$.position') = 'all' and json_extract_scalar(x, '$.locationCode') = 'high' limit 1) as high_danger_goals
    from dedup
)

select
    team_id,
    season_id,
    game_type,
    total_sog,
    high_danger_sog,
    mid_danger_sog,
    long_danger_sog,
    high_danger_goals,
    safe_divide(high_danger_sog, total_sog) as high_danger_sog_share,
    safe_divide(mid_danger_sog, total_sog) as mid_danger_sog_share,
    safe_divide(long_danger_sog, total_sog) as long_danger_sog_share
from loc
