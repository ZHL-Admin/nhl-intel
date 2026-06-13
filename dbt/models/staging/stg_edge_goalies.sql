-- One row per (goalie, season, game_type): NHL Edge goalie season aggregates.
-- NOTE (honest scope): the Edge goalie save-percentage-detail endpoint only exposes
-- gamesAbove900 / pctgGamesAbove900 plus a last-10 list of per-game save pct. It does
-- NOT carry high-danger or 5v5 save-pct splits. Our own GSAx-by-danger (Phase 2.5,
-- from the in-house xG layer) is the danger-split metric; Edge's independent
-- second-opinion for goalies is limited to these "quality start"-style fields.

with dedup as (
    select entity_id, season_id, game_type, data
    from (
        select *,
            row_number() over (
                partition by entity_id, season_id, game_type, report
                order by ingestion_date desc
            ) as rn
        from {{ source('nhl', 'raw_edge_goalies') }}
        where report = 'save-percentage-detail'
    )
    where rn = 1
)

select
    entity_id as player_id,
    season_id,
    game_type,
    safe_cast(json_extract_scalar(data, '$.savePctgDetails.gamesAbove900.value') as int64) as games_above_900,
    safe_cast(json_extract_scalar(data, '$.savePctgDetails.gamesAbove900.percentile') as float64) as games_above_900_pctile,
    safe_cast(json_extract_scalar(data, '$.savePctgDetails.pctgGamesAbove900.value') as float64) as pct_games_above_900,
    safe_cast(json_extract_scalar(data, '$.savePctgDetails.pctgGamesAbove900.percentile') as float64) as pct_games_above_900_pctile,
    (
        select avg(safe_cast(json_extract_scalar(x, '$.savePctg') as float64))
        from unnest(json_extract_array(data, '$.savePctgLast10')) x
    ) as last10_avg_save_pct
from dedup
