{{ config(materialized='view') }}

-- Typed org prospect lists (Trade tool P5). One row per prospect on the latest snapshot, with
-- draft pedigree (overall pick) and an age computed from the parsed birth date. Keyed player_id.
-- Bounded to org lists: every prospect here came from a team's published list, never invented.

with src as (
    select * from {{ source('nhl', 'raw_prospects') }}
    where as_of_date = (select max(as_of_date) from {{ source('nhl', 'raw_prospects') }})
)

select
    player_id,
    first_name,
    last_name,
    first_name || ' ' || last_name                                as full_name,
    position_code,
    pos_group,
    shoots,
    safe_cast(birth_date as date)                                 as birth_date,
    date_diff(current_date(), safe_cast(birth_date as date), day) / 365.25 as age,
    height_in,
    weight_lb,
    org_team,
    draft_year,
    draft_round,
    draft_overall,
    draft_overall is null                                         as is_undrafted,
    season,
    as_of_date
from src
