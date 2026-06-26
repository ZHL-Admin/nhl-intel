{{ config(materialized='view') }}

-- Typed GM tenures (Handoff 6), one row per (gm_id, team_abbrev, start_date) on the latest snapshot.
-- The curated source of truth for trade-outcome GM attribution: a (trade, team-side, date) is
-- attributed to the tenure whose team_abbrev matches and whose [start_date, end_date] contains the
-- trade date. Attribution requires NON-OVERLAPPING tenures per team (asserted by a singular test).
-- end_date is null for the current GM; downstream attribution treats null as "through today".

with src as (
    select * from {{ source('nhl', 'raw_gm_tenures') }}
    where as_of_date = (select max(as_of_date) from {{ source('nhl', 'raw_gm_tenures') }})
),

dedup as (
    select *,
        row_number() over (
            partition by gm_id, team_abbrev, start_date
            order by ingested_at desc
        ) as rn
    from src
)

select
    gm_id,
    gm_name,
    team_abbrev,
    safe_cast(start_date as date)              as start_date,
    safe_cast(nullif(end_date, '') as date)    as end_date,
    nullif(title, '')                          as title,
    nullif(note, '')                           as note
from dedup
where rn = 1
  and gm_id is not null and gm_id != ''
  and safe_cast(start_date as date) is not null
