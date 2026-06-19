{{ config(materialized='table') }}

-- One row per matched player per snapshot: the parsed contract joined to the canonical player_id
-- (Trade tool P3). This is the PLAYER contract layer — prospects without an NHL player_id are
-- absent by design (the contract->id map only carries confident matches; prospects/picks are
-- valued in the futures layer instead). The cap schedule here is the flat cap hit carried over
-- the remaining years, since the snapshot stores a single cap charge per contract, not a
-- per-year cash schedule.
--
-- Keyed (player_id, as_of_date). A handful of source rows duplicate (e.g. a doubled CSV line);
-- we keep the highest cap hit per key so a dedup never silently drops the real (larger) deal.

with mapped as (
    select
        m.player_id,
        m.match_method,
        m.confidence as match_confidence,
        c.*
    from {{ source('nhl_models', 'contract_player_map') }} m
    join {{ ref('stg_contracts') }} c
      on  c.player_name_src = m.player_name_src
      and c.team            = m.team
      and c.season          = m.season
      and c.as_of_date      = m.as_of_date
),

deduped as (
    select *,
        row_number() over (
            partition by player_id, as_of_date
            order by cap_hit desc, term_years desc
        ) as rn
    from mapped
)

select
    player_id,
    season,
    as_of_date,
    season_start_year,
    team                                                as contract_team,
    pos                                                 as contract_pos,
    contract_type,
    is_elc,

    -- cap + cash
    cap_hit,
    aav,
    total_value,
    base_salary,
    signing_bonus,
    perf_bonus,
    cash_this_year,

    -- term / countdown (season-aware)
    term_years,
    contract_start_year,
    expiry_year,
    remaining_years,
    cap_hit * remaining_years                           as total_remaining_cap,

    -- status
    sign_status,
    sign_age,
    expiry_status,
    is_ufa,
    waivers_exempt,
    signed_by,

    -- provenance: how the player_id was resolved (auditable; surname tier = medium)
    match_method,
    match_confidence,

    current_timestamp()                                 as _loaded_at
from deduped
where rn = 1
