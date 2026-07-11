-- One row per player on a team's CURRENT live roster (membership feed; NOT game-derived).
-- Source: nhl_raw.raw_rosters — forwards/defensemen/goalies stored as serialized JSON strings,
-- one row per (team_abbrev, ingestion_date). Daily snapshot appends stack.
--
-- A team's CURRENT roster is its MOST RECENT snapshot. We scope to each team's latest ingestion
-- BEFORE ranking, which is what makes DEPARTURES visible: a player dropped from a club simply stops
-- appearing in its snapshots — he generates no "removal" row — so newest-ingestion-PER-PLAYER ranking
-- would pin him to his last snapshot on that team forever (a released UFA would look rostered all
-- offseason). Keeping only rows from each team's latest snapshot turns that absence into a real
-- removal. team_id is resolved from team_abbrev via the canonical map.
--
-- TRADE-DAY TIE-BREAK: mid-trade, BOTH clubs may list a player on the SAME ingestion day (the
-- acquiring team has added him before the former team has dropped him). ingestion_date then ties, so
-- ranking on it alone is NON-DETERMINISTIC (the player flickers between the two teams across queries).
-- We resolve it deterministically to the ACQUIRING team -- the club whose membership for him is
-- NEWEST -- by tie-breaking on when he first appeared on each team (team_joined_date desc), with
-- team_abbrev as a final stable tiebreak so the result never depends on scan order.
--
-- CAVEAT (membership != performance): this fixes the team LABEL only. A just-traded player has
-- zero games with his new club, so his impact/archetype/radar/value still reflect old-team usage
-- until he plays. Consumed by int_player_current_team (live-first current-team resolution).

with raw as (
    select team_abbrev, season, ingestion_date, forwards, defensemen, goalies
    from {{ source('nhl', 'raw_rosters') }}
),

-- Unnest the three serialized position arrays into one player stream, tagging the position group.
players as (
    select r.team_abbrev, r.season, r.ingestion_date, p, 'F' as pos_group
    from raw r, unnest(json_extract_array(r.forwards)) as p
    union all
    select r.team_abbrev, r.season, r.ingestion_date, p, 'D' as pos_group
    from raw r, unnest(json_extract_array(r.defensemen)) as p
    union all
    select r.team_abbrev, r.season, r.ingestion_date, p, 'G' as pos_group
    from raw r, unnest(json_extract_array(r.goalies)) as p
),

parsed as (
    select
        cast(json_extract_scalar(p, '$.id') as int64) as player_id,
        team_abbrev,
        season,
        cast(ingestion_date as date) as ingestion_date,
        pos_group,
        json_extract_scalar(p, '$.firstName.default') as first_name,
        json_extract_scalar(p, '$.lastName.default') as last_name,
        cast(json_extract_scalar(p, '$.sweaterNumber') as int64) as sweater_number,
        json_extract_scalar(p, '$.positionCode') as position_code,
        json_extract_scalar(p, '$.shootsCatches') as shoots_catches,
        json_extract_scalar(p, '$.headshot') as headshot_url
    from players
),

-- Each team's CURRENT roster = its most recent snapshot. Scoping here (before per-player ranking)
-- is what lets a dropped player fall off: if he is absent from his team's latest snapshot he is gone,
-- even though no row ever says so explicitly.
team_latest as (
    select team_abbrev, max(ingestion_date) as latest_ingestion
    from parsed group by team_abbrev
),

current_snapshots as (
    select p.*
    from parsed p
    join team_latest tl
      on p.team_abbrev = tl.team_abbrev and p.ingestion_date = tl.latest_ingestion
),

-- When each player FIRST appeared on each team, to break a same-day two-team tie toward the acquirer.
joined as (
    select player_id, team_abbrev, min(ingestion_date) as team_joined_date
    from parsed group by player_id, team_abbrev
),

-- Within the set of current-snapshot rows, a player can still sit on TWO teams mid-trade (both clubs'
-- latest snapshots list him). Keep the acquiring team: newest snapshot, then most-recently-joined.
ranked as (
    select p.*,
        row_number() over (
            partition by p.player_id
            order by p.ingestion_date desc, j.team_joined_date desc, p.team_abbrev
        ) as rn
    from current_snapshots p
    join joined j using (player_id, team_abbrev)
),

-- Canonical team_abbrev -> team_id map, sourced from stg_games (a STAGING model, so no mart dependency).
-- A single franchise can carry MORE THAN ONE team_id over time under the SAME abbrev — e.g. Utah:
-- id 59 ("Utah Hockey Club", 2024-25) then id 68 ("Utah Mammoth", 2025-26). The live roster MUST resolve
-- to the CURRENT id or it won't line up with the base roster / team_ratings / forecast (all keyed to the
-- latest id), which would make an entire returning roster read as departed. So we take each abbrev's id
-- from its MOST RECENT game (any_value here was non-deterministic and could pin the stale id).
team_map as (
    select team_abbrev, team_id from (
        select team_abbrev, team_id,
               row_number() over (partition by team_abbrev order by game_id desc) as rn
        from (
            select home_team_id as team_id, home_team_abbrev as team_abbrev, game_id from {{ ref('stg_games') }}
            union all
            select away_team_id as team_id, away_team_abbrev as team_abbrev, game_id from {{ ref('stg_games') }}
        )
        where team_abbrev is not null and team_id is not null
    )
    where rn = 1
),

final as (
    select
        r.player_id,
        tm.team_id,
        r.team_abbrev,
        r.season,
        r.ingestion_date,
        r.first_name,
        r.last_name,
        r.first_name || ' ' || r.last_name as full_name,
        r.sweater_number,
        r.position_code,
        r.pos_group,
        r.shoots_catches,
        r.headshot_url
    from ranked r
    left join team_map tm using (team_abbrev)
    where r.rn = 1
)

select * from final
