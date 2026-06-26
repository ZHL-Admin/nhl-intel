-- GM attribution joins a trade to the single tenure containing its date, so two tenures for the same
-- team must never overlap in time. Returns offending overlapping pairs; the test passes when none.
-- The current GM's null end_date is treated as "through today" for the overlap check.

with t as (
    select team_abbrev, gm_id, start_date, coalesce(end_date, current_date()) as end_date
    from {{ ref('stg_gm_tenures') }}
)

select
    a.team_abbrev,
    a.gm_id   as gm_a,
    b.gm_id   as gm_b,
    a.start_date as start_a,
    b.start_date as start_b
from t a
join t b
  on a.team_abbrev = b.team_abbrev
 and a.start_date < b.start_date     -- order the pair so each overlap appears once
 and a.end_date > b.start_date       -- a's range extends past b's start => overlap
