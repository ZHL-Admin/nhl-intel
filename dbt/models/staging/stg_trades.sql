{{ config(materialized='view') }}

-- Typed historical trades (Handoff 5, Phase D), one row per (trade, asset) on the latest snapshot.
-- DISTINCT from the future-ownership / live trade-engine path: this is what was actually traded.
--
-- Per asset: typed trade_date, asset_type, parsed draft-pick (year, round, round-midpoint overall),
-- a conditional flag, the team that received it (acquiring_team), and — for PLAYER assets — a
-- resolved_player_id matched on normalized name + position group against the roster/bio universe.
-- Picks are round-only (no overall, no original owner); the round midpoint stands in for the slot.
-- giving_team is the other team in a TWO-team trade (deterministic); for three-team trades it is null
-- (resolved per-asset in compute_trade_outcomes via the player's pre-trade team).
--
-- Unmatched players are kept with a null resolved_player_id and is_resolved=false — never dropped.

with src as (
    select * from {{ source('nhl', 'raw_trades') }}
    where as_of_date = (select max(as_of_date) from {{ source('nhl', 'raw_trades') }})
      and asset_type in ('Player', 'Draft Pick', 'Other')          -- drop the stray blank row
),

-- candidate player universe: latest name + position group per player_id (NHL game types only)
cand as (
    select player_id, nkey, pg from (
        select player_id,
            lower(regexp_replace(normalize(first_name || ' ' || last_name, NFD), r'[^a-zA-Z]', '')) as nkey,
            case when upper(position_code) = 'G' then 'G'
                 when upper(position_code) = 'D' then 'D' else 'F' end as pg,
            row_number() over (partition by player_id order by game_id desc) as rn
        from {{ ref('stg_rosters') }}
        where substr(cast(game_id as string), 5, 2) in ('01', '02', '03')
          and first_name is not null and last_name is not null
    )
    where rn = 1
),
cand_by_name    as (select nkey, count(distinct player_id) n, any_value(player_id) pid from cand group by nkey),
cand_by_namepos as (select nkey, pg, count(distinct player_id) n, any_value(player_id) pid from cand group by nkey, pg),

-- teams in each trade (windowed array_agg(distinct) is unsupported in BQ, so group then join)
teams_per_trade as (
    select trade_id,
        array_agg(distinct acquiring_team) as trade_teams,
        count(distinct acquiring_team)     as team_count
    from src group by trade_id
),

trades as (
    select
        trade_id,
        season,
        safe_cast(trade_date as date)                                   as trade_date,
        trade_label,
        acquiring_team,
        asset_type,
        asset,
        nullif(position, '')                                            as position,
        nullif(notes, '')                                               as notes,
        -- conditional ONLY when the note actually says so (the notes column also carries other
        -- annotations, e.g. "50% retained", which must NOT be flagged as a conditional pick)
        coalesce(lower(notes) like '%conditional%', false)              as is_conditional,
        -- salary retention: a brokered row ("X% retained") is a cap mechanism, not an acquisition
        coalesce(lower(notes) like '%retain%', false)                  as is_retention,
        safe_cast(regexp_extract(notes, r'(\d+)\s*%') as int64)         as retained_pct,
        -- player position group (for resolution + display)
        case when upper(position) = 'G' then 'G'
             when upper(position) in ('D', 'LD', 'RD') then 'D'
             when position is null or position = '' then null
             else 'F' end                                               as pos_group,
        -- draft-pick parse: "YYYY Nth Round" -> year, round
        case when asset_type = 'Draft Pick'
             then safe_cast(regexp_extract(asset, r'^(\d{4})') as int64) end as pick_year,
        case when asset_type = 'Draft Pick'
             then safe_cast(regexp_extract(asset, r'(\d+)(?:st|nd|rd|th)\s+Round') as int64) end as pick_round
    from src
),

keyed as (
    select t.*,
        tpt.trade_teams,
        tpt.team_count,
        -- normalized name for player matching
        case when asset_type = 'Player'
             then lower(regexp_replace(normalize(asset, NFD), r'[^a-zA-Z]', '')) end as nkey,
        -- round midpoint overall (32 picks/round, midpoint) — the slot stand-in for a round-only pick
        case when asset_type = 'Draft Pick' and pick_round is not null
             then (pick_round - 1) * 32 + 16 end                       as pick_overall_mid
    from trades t
    join teams_per_trade tpt using (trade_id)
)

select
    k.trade_id,
    k.season,
    k.trade_date,
    k.trade_label,
    k.acquiring_team,
    -- the OTHER team in a two-team trade (deterministic giving team); null when 3+ teams
    case when k.team_count = 2
         then (select t from unnest(k.trade_teams) t where t != k.acquiring_team limit 1) end as giving_team,
    k.team_count,
    k.asset_type,
    k.asset,
    k.position,
    k.pos_group,
    k.notes,
    k.is_conditional,
    k.is_retention,
    k.retained_pct,
    k.pick_year,
    k.pick_round,
    k.pick_overall_mid,
    -- resolution: prefer name+position (separates same-name players), fall back to a unique name
    coalesce(np.pid, nm.pid)                                            as resolved_player_id,
    case
        when k.asset_type != 'Player' then cast(null as string)
        when np.pid is not null then 'name+pos'
        when nm.pid is not null then 'name'
        else 'unmatched'
    end                                                                as match_method,
    k.asset_type = 'Player' and coalesce(np.pid, nm.pid) is not null   as is_resolved
from keyed k
left join cand_by_namepos np
    on k.asset_type = 'Player' and k.nkey = np.nkey and k.pos_group = np.pg and np.n = 1
left join cand_by_name nm
    on k.asset_type = 'Player' and k.nkey = nm.nkey and nm.n = 1
