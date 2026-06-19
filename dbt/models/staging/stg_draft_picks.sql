{{ config(materialized='view') }}

-- Future draft picks as tradeable assets (Trade tool P5). One row per (owner_team, draft_year,
-- round) on the latest snapshot. years_out lets the value layer discount picks further in the
-- future. ownership_source is carried through so the UI can flag the own-picks ASSUMPTION (pick
-- trades are not in any feed we have) rather than presenting assumed ownership as fact.

with src as (
    select * from {{ source('nhl', 'raw_draft_picks') }}
    where as_of_date = (select max(as_of_date) from {{ source('nhl', 'raw_draft_picks') }})
)

select
    draft_year,
    round,
    original_team,
    owner_team,
    ownership_source,
    nullif(note, '')                                              as note,
    -- seasons until this draft, from the snapshot season's opening year ("2025-26" -> 2025)
    draft_year - safe_cast(substr(season, 1, 4) as int64)         as years_out,
    season,
    as_of_date
from src
