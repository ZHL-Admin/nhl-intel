{{ config(materialized='view') }}

-- Historical draft RESULTS, one row per (draft_year, overall_pick) — the complete evaluation
-- universe for the Draft Value tool (Handoff 5, Phase A). Every pick is kept; a pick whose player
-- never reached the NHL resolves to a NULL resolved_player_id and carries realized value 0
-- downstream (never-NHL = 0, NOT missing — the busts are the point).
--
-- DISTINCT from stg_draft_picks (future pick OWNERSHIP). This is who was actually selected.
--
-- player_id RESOLUTION: the source carries no id (see scripts/DRAFT_RESULTS_FINDINGS.md). The
-- reliable resolver is each player's own landing draftDetails (raw_player_draft_origin), joined on
-- (draft_year, overall_pick) = (draft_year, draft_overall). Name agreement is reported as a
-- validation cross-check (name_match), never used to resolve (name matching produces false zeros:
-- it cannot tell a true bust from a roster-coverage gap).

with results as (
    select *,
        row_number() over (
            partition by draft_year, overall_pick order by _loaded_at desc
        ) as rn
    from {{ source('nhl', 'raw_draft_results') }}
),

picks as (
    select
        cast(draft_year   as int64)  as draft_year,
        cast(round        as int64)  as round,
        cast(pick_in_round as int64) as pick_in_round,
        cast(overall_pick as int64)  as overall_pick,
        cast(team_id      as int64)  as draft_team_id,
        team_abbrev                  as draft_team_abbrev,
        full_name,
        first_name,
        last_name,
        position_code,
        case when upper(position_code) = 'G' then 'G'
             when upper(position_code) = 'D' then 'D' else 'F' end as pos_group,
        country_code,
        cast(height_in as int64)     as height_in,
        cast(weight_lb as int64)     as weight_lb,
        amateur_league,
        amateur_club
    from results
    where rn = 1
),

-- authoritative draft origin per player (latest ingestion), drafted players only
origin as (
    select * from (
        select player_id, draft_year, draft_overall, draft_team_abbrev, full_name,
            row_number() over (partition by player_id order by ingestion_date desc) as rn
        from {{ source('nhl', 'raw_player_draft_origin') }}
        where is_undrafted = false and draft_year is not null and draft_overall is not null
    )
    where rn = 1
),

-- collapse to one producing player per (draft_year, overall) slot (defensive: a slot maps to one
-- player; if duplicate origins ever appear, keep the lowest player_id deterministically)
origin_by_slot as (
    select draft_year, draft_overall,
        any_value(player_id      having min player_id) as resolved_player_id,
        any_value(full_name      having min player_id) as origin_full_name,
        any_value(draft_team_abbrev having min player_id) as origin_team_abbrev
    from origin
    group by draft_year, draft_overall
)

select
    -- surrogate key for the composite (draft_year, overall_pick) uniqueness test (no dbt_utils dep)
    concat(cast(p.draft_year as string), '-', cast(p.overall_pick as string)) as pick_key,
    p.draft_year,
    p.round,
    p.pick_in_round,
    p.overall_pick,
    p.draft_team_id,
    p.draft_team_abbrev,
    p.full_name,
    p.first_name,
    p.last_name,
    p.position_code,
    p.pos_group,
    p.country_code,
    p.height_in,
    p.weight_lb,
    p.amateur_league,
    p.amateur_club,
    o.resolved_player_id,
    o.resolved_player_id is not null as made_nhl,   -- appeared in our production data
    -- validation cross-check only (not used to resolve): normalized name agreement on resolved picks
    case
        when o.resolved_player_id is null then null
        else lower(regexp_replace(normalize(p.full_name, NFD), r'[^a-zA-Z]', ''))
           = lower(regexp_replace(normalize(o.origin_full_name, NFD), r'[^a-zA-Z]', ''))
    end as name_match
from picks p
left join origin_by_slot o
    on p.draft_year = o.draft_year and p.overall_pick = o.draft_overall
