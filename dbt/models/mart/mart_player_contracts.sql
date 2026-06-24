{{ config(materialized='table') }}

-- One row per matched player per snapshot: the parsed contract joined to the canonical player_id
-- (Trade tool P3). Two sources are unioned here:
--   * SIGNED contracts  (contract_player_map + stg_contracts)      -> contract_status='signed'
--   * PENDING RFAs       (rfa_player_map + stg_contracts_rfa)        -> contract_status='rfa_projected'
-- An RFA's deal has expired, so there are no signed terms; we carry his PROJECTED next deal
-- (proj_cap over proj_term, starting next league year) as the contract and derive his team from his
-- latest NHL game (the RFA feed has no team). SIGNED WINS: an RFA row is dropped if the player still
-- holds a signed deal, so nobody is double-counted. Prospects/picks without an NHL id are absent
-- (valued in the futures layer).
--
-- Keyed (player_id, as_of_date). Source rows can duplicate (a doubled CSV line, or the RFA feed
-- listing a player twice); we keep the highest cap hit per key so a dedup never drops the real deal.

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

signed_final as (
    select
        player_id, season, as_of_date, season_start_year,
        team                                                as contract_team,
        pos                                                 as contract_pos,
        contract_type, is_elc,
        cap_hit, aav, total_value, base_salary, signing_bonus, perf_bonus, cash_this_year,
        term_years, contract_start_year, expiry_year, remaining_years,
        cap_hit * remaining_years                           as total_remaining_cap,
        sign_status, sign_age, expiry_status, is_ufa, waivers_exempt, signed_by,
        match_method, match_confidence,
        'signed'                                            as contract_status,
        cast(null as int64)                                 as qo
    from (
        select *, row_number() over (
            partition by player_id, as_of_date order by cap_hit desc, term_years desc) as rn
        from mapped
    )
    where rn = 1
),

-- each player's CURRENT NHL team (from his latest NHL game; intl games excluded) — the RFA feed has
-- no team, so this supplies it. Preseason ('01') is included as a fallback so a prospect-level RFA who
-- only appeared in an NHL camp still gets his org; game_id desc prefers a regular/playoff game ('02'/
-- '03' sort higher than '01' within a season) when he has one.
roster_team as (
    select player_id, team_abbrev from (
        select s.player_id, t.abbrev as team_abbrev,
            row_number() over (partition by s.player_id order by s.game_id desc) as rn
        from {{ ref('stg_rosters') }} s
        join (select team_id, any_value(team_abbrev) as abbrev
              from {{ ref('mart_team_game_stats') }} group by team_id) t
          on s.team_id = t.team_id
        where substr(cast(s.game_id as string), 5, 2) in ('01', '02', '03')
    )
    where rn = 1
),

rfa_final as (
    select
        player_id, season, as_of_date, season_start_year,
        contract_team, contract_pos, contract_type, is_elc,
        cap_hit, aav, total_value, base_salary, signing_bonus, perf_bonus, cash_this_year,
        term_years, contract_start_year, expiry_year, remaining_years, total_remaining_cap,
        sign_status, sign_age, expiry_status, is_ufa, waivers_exempt, signed_by,
        match_method, match_confidence, contract_status, qo
    from (
        select
            map.player_id,
            r.season, r.as_of_date, r.season_start_year,
            rt.team_abbrev                                  as contract_team,
            r.pos                                           as contract_pos,
            r.contract_type,
            false                                           as is_elc,
            -- the projected next deal; when the source didn't project one ("-"), fall back to the
            -- qualifying offer over 1 year (the floor to retain his rights)
            coalesce(r.proj_cap, r.qo)                      as cap_hit,
            coalesce(r.proj_cap, r.qo)                      as aav,
            coalesce(r.proj_cap, r.qo) * coalesce(r.proj_term, 1) as total_value,
            cast(null as int64)                             as base_salary,
            cast(null as int64)                             as signing_bonus,
            cast(null as int64)                             as perf_bonus,
            cast(null as int64)                             as cash_this_year,
            coalesce(r.proj_term, 1)                        as term_years,
            r.season_start_year + 1                         as contract_start_year,  -- new deal next yr
            r.season_start_year + 1 + coalesce(r.proj_term, 1) as expiry_year,
            coalesce(r.proj_term, 1)                        as remaining_years,
            coalesce(r.proj_cap, r.qo) * coalesce(r.proj_term, 1) as total_remaining_cap,
            cast(null as string)                            as sign_status,
            cast(null as int64)                             as sign_age,
            r.expiry_status, r.is_ufa,
            cast(null as boolean)                           as waivers_exempt,
            cast(null as string)                            as signed_by,
            map.match_method, map.confidence                as match_confidence,
            'rfa_projected'                                 as contract_status,
            r.qo,
            row_number() over (partition by map.player_id, r.as_of_date
                               order by coalesce(r.proj_cap, r.qo) desc) as rn
        from {{ source('nhl_models', 'rfa_player_map') }} map
        join {{ ref('stg_contracts_rfa') }} r
          on  r.player_name_src = map.player_name_src
          and r.season          = map.season
          and r.as_of_date      = map.as_of_date
        left join roster_team rt on rt.player_id = map.player_id
        where map.player_id not in (select player_id from signed_final)   -- signed contract WINS
    )
    where rn = 1
)

select *, current_timestamp() as _loaded_at from signed_final
union all
select *, current_timestamp() as _loaded_at from rfa_final
