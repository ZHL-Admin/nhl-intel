{{ config(materialized='table') }}

-- The unified tradeable-asset layer (Trade tool P7): every rostered player, prospect, and draft
-- pick as ONE row with ONE interface, all in the same WAR + dollar currency, so a future trade
-- engine can net any mix of them cleanly. Value and cost are kept as TWO SEPARATE AXES (not
-- collapsed into surplus alone): the TALENT axis (value_war / value_dollars + band) is what a player
-- is worth, the COST axis (cap_hit, remaining_years, cost_dollars) is what they are owed, and
-- surplus is the convenience difference. A fairly paid star has near-zero surplus but a large talent
-- value — both must be visible.
--   player   <- player_contract_value (projected value vs cap surplus; high/medium/proxy confidence)
--   prospect <- futures_value (asset_kind='prospect'; proxy)   -- deduped against players below
--   pick     <- futures_value (asset_kind='pick'; proxy; cost ≈ 0)
-- A prospect who is also a rostered player (has a contract value row) is represented ONCE, as the
-- player — the grounded contract value supersedes the proxy prospect value, so no double counting.

with names as (
    select player_id, any_value(first_name || ' ' || last_name) as name
    from {{ ref('stg_rosters') }}
    where substr(cast(game_id as string), 5, 2) in ('01', '02', '03')
    group by player_id
),

players as (
    select
        'player:' || cast(v.player_id as string)            as asset_id,
        'player'                                             as asset_type,
        v.player_id,
        coalesce(n.name, cast(v.player_id as string))        as label,
        c.contract_team                                      as org_team,
        -- actual listed position (e.g. "C/LW", "RD") not just the F/D group, for exploration; a
        -- pending RFA (expired deal, team still holds his rights) is tagged so the picker shows it
        replace(coalesce(c.contract_pos, v.pos_group), ', ', '/') || ' · '
          || cast(v.age as string) || 'y'
          || case when c.contract_status = 'rfa_projected' then ' · RFA' else '' end as pos_or_slot,
        -- talent axis (value + band, WAR and dollars)
        v.value_war, v.value_war_low, v.value_war_high,
        v.value_dollars, v.value_dollars_low, v.value_dollars_high,
        -- cost axis
        v.cap_hit, v.remaining_years, v.cost_dollars,
        -- surplus (value minus cost) + band — DOLLARS (cap-aware) and CAP-SHARE (era-neutral)
        v.total_discounted_surplus                           as surplus_dollars,
        v.surplus_low, v.surplus_high,
        v.total_discounted_surplus_share                     as surplus_capshare,
        -- TERM-NORMALIZED per-year rate = mean of each year's surplus as a share of THAT year's cap.
        -- The board SORT KEY: ranks value density, not term length (cumulative surplus_capshare above
        -- is kept as the displayed magnitude). Computed from the per-year schedule, not re-modelled.
        (select avg(cast(json_value(e, '$.surplus_share') as float64))
           from unnest(json_extract_array(v.cap_share_schedule)) as e) as surplus_capshare_per_year,
        v.surplus_share_low                                  as surplus_capshare_low,
        v.surplus_share_high                                 as surplus_capshare_high,
        v.cap_growth_surplus,                                -- how much of the surplus is cap growth
        v.confidence,
        case when c.contract_status = 'rfa_projected'
             then 'Pending RFA — ' || coalesce(c.contract_team, 'his team')
                  || ' holds his rights; cost is the projected next deal ($'
                  || cast(cast(round(c.cap_hit / 1e6, 1) as numeric) as string) || 'M x '
                  || cast(c.term_years as string) || 'y), QO $'
                  || cast(cast(round(c.qo / 1e6, 2) as numeric) as string) || 'M'
             else cast(null as string) end                   as note,
        -- 'signed' | 'rfa_projected' — lets the surplus/contract leaderboards drop projected RFA deals
        -- (a projected next deal is not a signed contract) while the asset layer still carries them
        c.contract_status
    from {{ source('nhl_models', 'player_contract_value') }} v
    left join {{ ref('mart_player_contracts') }} c
        on v.player_id = c.player_id and v.as_of_date = c.as_of_date
    left join names n on v.player_id = n.player_id
),

prospects as (
    select
        f.asset_id, 'prospect' as asset_type, f.player_id,
        f.label, f.org_team, f.pos_or_slot,
        f.value_war, f.value_war_low, f.value_war_high,
        f.value_dollars, f.value_dollars_low, f.value_dollars_high,
        cast(null as int64) as cap_hit, cast(null as int64) as remaining_years, f.cost_dollars,
        f.surplus_dollars,
        f.value_dollars_low  as surplus_low,
        f.value_dollars_high as surplus_high,
        -- futures carry ~no cap cost, so their cap-share surplus is a NOMINAL value/cap (2025-26 cap)
        f.surplus_dollars    / 95500000.0 as surplus_capshare,
        cast(null as float64)              as surplus_capshare_per_year,
        f.value_dollars_low  / 95500000.0 as surplus_capshare_low,
        f.value_dollars_high / 95500000.0 as surplus_capshare_high,
        cast(null as int64) as cap_growth_surplus,
        f.confidence, f.ownership_note as note,
        cast(null as string) as contract_status
    from {{ source('nhl_models', 'futures_value') }} f
    where f.asset_kind = 'prospect'
      -- dedup: drop prospects already represented as a rostered player (contract value wins)
      and f.player_id not in (select player_id from {{ source('nhl_models', 'player_contract_value') }})
),

picks as (
    select
        f.asset_id, 'pick' as asset_type, cast(null as int64) as player_id,
        f.label, f.org_team, f.pos_or_slot,
        f.value_war, f.value_war_low, f.value_war_high,
        f.value_dollars, f.value_dollars_low, f.value_dollars_high,
        cast(null as int64) as cap_hit, cast(null as int64) as remaining_years, f.cost_dollars,
        f.surplus_dollars,
        f.value_dollars_low  as surplus_low,
        f.value_dollars_high as surplus_high,
        f.surplus_dollars    / 95500000.0 as surplus_capshare,
        cast(null as float64)              as surplus_capshare_per_year,
        f.value_dollars_low  / 95500000.0 as surplus_capshare_low,
        f.value_dollars_high / 95500000.0 as surplus_capshare_high,
        cast(null as int64) as cap_growth_surplus,
        f.confidence, f.ownership_note as note,
        cast(null as string) as contract_status
    from {{ source('nhl_models', 'futures_value') }} f
    where f.asset_kind = 'pick'
)

select *, lower(label) as label_lower, current_timestamp() as _loaded_at from players
union all
select *, lower(label) as label_lower, current_timestamp() as _loaded_at from prospects
union all
select *, lower(label) as label_lower, current_timestamp() as _loaded_at from picks
