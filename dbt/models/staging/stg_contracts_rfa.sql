{{ config(materialized='view') }}

-- Typed, parsed view over the pending-RFA snapshot (raw_contracts_rfa). An RFA's current deal has
-- expired, so there are NO signed terms: the source carries the PROJECTED next deal (proj_cap /
-- proj_term), the qualifying offer, and last-season production. NO team (derived downstream in
-- mart_player_contracts from the player's latest NHL game). One row per RFA per snapshot; the source
-- can duplicate a player row, so mart_player_contracts dedupes on (player_id, as_of_date).
--
-- Parsing mirrors stg_contracts: dollars "$3,082,778" -> INT64, "2 yrs" -> INT64 years.

with src as (
    select * from {{ source('nhl', 'raw_contracts_rfa') }}
)

select
    player_name_src,
    pos,
    nullif(trim(hand), '')                                                        as shoots,
    nullif(trim(birthplace), '')                                                  as birthplace,
    safe_cast(nullif(regexp_replace(age, r'[^0-9]', ''), '') as int64)            as age,

    season,
    as_of_date,
    safe_cast(substr(season, 1, 4) as int64)                                      as season_start_year,

    -- the PROJECTED next deal (the analyst's estimate of what he re-signs for)
    safe_cast(nullif(regexp_replace(proj_cap, r'[^0-9]', ''), '') as int64)       as proj_cap,
    safe_cast(regexp_extract(proj_term, r'(\d+)') as int64)                       as proj_term,
    -- the qualifying offer (floor to retain his rights) + his expiring cap hit, for context
    safe_cast(nullif(regexp_replace(qo, r'[^0-9]', ''), '') as int64)             as qo,
    safe_cast(nullif(regexp_replace(current_cap, r'[^0-9]', ''), '') as int64)    as current_cap,

    -- last-season production (context only; value comes from nhl_models.player_gar via player_id)
    safe_cast(nullif(regexp_replace(gp, r'[^0-9]', ''), '') as int64)             as gp,
    safe_cast(nullif(regexp_replace(points, r'[^0-9]', ''), '') as int64)         as points,
    safe_cast(nullif(points_per_game, '') as float64)                             as points_per_game,
    nullif(trim(toi), '')                                                         as toi,

    -- status: a pending RFA (team holds his rights), never a UFA
    'RFA'                                                                         as expiry_status,
    false                                                                         as is_ufa,
    'RFA (projected)'                                                             as contract_type,

    ingested_at
from src
