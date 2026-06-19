{{ config(materialized='table') }}

-- The unified tradeable-asset layer (Trade tool P7): every rostered player, prospect, and draft
-- pick as ONE row with ONE interface — an identity, a value with a band, a cost, a surplus, and a
-- confidence tag, all in the same WAR + dollar currency — so a future trade engine can net any mix
-- of them cleanly. Three sources, harmonized:
--   player   <- player_contract_value (projected value vs cap surplus; high/medium/proxy confidence)
--   prospect <- futures_value (asset_kind='prospect'; proxy)   -- deduped against players below
--   pick     <- futures_value (asset_kind='pick'; proxy)
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
        v.pos_group || ' · ' || cast(v.age as string) || 'y' as pos_or_slot,
        v.value_war, v.value_war_low, v.value_war_high,
        v.value_dollars,
        v.cost_dollars,
        v.total_discounted_surplus                           as surplus_dollars,
        v.surplus_low, v.surplus_high,
        v.confidence,
        cast(null as string)                                 as note
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
        f.value_dollars, f.cost_dollars,
        f.surplus_dollars,
        f.value_dollars_low  as surplus_low,
        f.value_dollars_high as surplus_high,
        f.confidence, f.ownership_note as note
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
        f.value_dollars, f.cost_dollars,
        f.surplus_dollars,
        f.value_dollars_low  as surplus_low,
        f.value_dollars_high as surplus_high,
        f.confidence, f.ownership_note as note
    from {{ source('nhl_models', 'futures_value') }} f
    where f.asset_kind = 'pick'
)

select *, lower(label) as label_lower, current_timestamp() as _loaded_at from players
union all
select *, lower(label) as label_lower, current_timestamp() as _loaded_at from prospects
union all
select *, lower(label) as label_lower, current_timestamp() as _loaded_at from picks
