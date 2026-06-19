{{ config(materialized='view') }}

-- Typed, parsed view over the dated contract snapshot (Trade tool P3; raw is source-faithful
-- strings, stg does all the parsing). One row per raw contract row (one player-contract per
-- snapshot). Season-aware: remaining_years is measured from the snapshot's season, so the same
-- contract correctly counts down as later snapshots arrive.
--
-- Parsing rules:
--   * dollars  "$17,000,000" / "$0" / "" -> INT64 (strip non-digits; blank -> null)
--   * term     "8 yrs"                    -> INT64 years
--   * waivers  "Yes"/"No"                 -> BOOL
--   * expiry   "UFA (Group 6)" etc.       -> kept verbatim + is_ufa flag on the UFA prefix

with src as (
    select * from {{ source('nhl', 'raw_contracts') }}
),

parsed as (
    select
        player_name_src,
        team,
        pos,
        safe_cast(nullif(regexp_replace(age, r'[^0-9]', ''), '') as int64)        as age,

        -- season spine: the calendar year the snapshot's season opens in ("2025-26" -> 2025)
        season,
        as_of_date,
        safe_cast(substr(season, 1, 4) as int64)                                  as season_start_year,

        -- money (cap charge is flat across the term; cash split is for the current snapshot year)
        safe_cast(nullif(regexp_replace(cap_hit,       r'[^0-9-]', ''), '') as int64) as cap_hit,
        safe_cast(nullif(regexp_replace(total,         r'[^0-9-]', ''), '') as int64) as total_value,
        safe_cast(nullif(regexp_replace(aav,           r'[^0-9-]', ''), '') as int64) as aav,
        safe_cast(nullif(regexp_replace(base_salary,   r'[^0-9-]', ''), '') as int64) as base_salary,
        safe_cast(nullif(regexp_replace(signing_bonus, r'[^0-9-]', ''), '') as int64) as signing_bonus,
        safe_cast(nullif(regexp_replace(perf_bonus,    r'[^0-9-]', ''), '') as int64) as perf_bonus,

        -- term + season-aware countdown
        safe_cast(regexp_extract(term, r'(\d+)') as int64)                        as term_years,
        safe_cast(nullif(regexp_replace(contract_start, r'[^0-9]', ''), '') as int64) as contract_start_year,
        safe_cast(nullif(regexp_replace(expiry_year,    r'[^0-9]', ''), '') as int64) as expiry_year,

        -- status
        nullif(trim(sign_status), '')                                             as sign_status,
        safe_cast(nullif(regexp_replace(sign_age, r'[^0-9]', ''), '') as int64)   as sign_age,
        nullif(trim(expiry_status), '')                                           as expiry_status,
        starts_with(upper(trim(expiry_status)), 'UFA')                            as is_ufa,
        lower(trim(waivers_exempt)) = 'yes'                                        as waivers_exempt,
        nullif(trim(signed_by), '')                                               as signed_by,
        nullif(trim(contract_type), '')                                           as contract_type,
        upper(trim(contract_type)) = 'ELC'                                        as is_elc,

        ingested_at
    from src
)

select
    *,
    -- seasons left on the deal, counting the snapshot season itself (expiry_year is the July the
    -- contract ends, so a deal expiring 2027 from a 2025-26 snapshot has 2 seasons: 25-26, 26-27).
    -- Counted from the later of the snapshot season and the contract's own start, so a not-yet-
    -- started extension (signed now, begins next season) reports its full term, never term+1.
    greatest(0, coalesce(expiry_year, season_start_year)
                - greatest(season_start_year, coalesce(contract_start_year, season_start_year))) as remaining_years,
    -- current cash this snapshot year (perf bonus is conditional, excluded from guaranteed cash)
    coalesce(base_salary, 0) + coalesce(signing_bonus, 0)                         as cash_this_year
from parsed
