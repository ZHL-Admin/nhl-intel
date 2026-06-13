-- One row per (team, date): league standings as of a date.
-- Source: nhl_raw.raw_standings (api-web standings/{date}). Localized name objects
-- (teamAbbrev, teamName) are serialized JSON strings; parsed here.
-- Carries the ranks (league/conference/division sequence) and the last-10 (l10*)
-- splits that the /games/{id}/context endpoint joins as-of game date.

with raw as (
    select
        *,
        row_number() over (
            partition by teamName, date
            order by ingestion_date desc
        ) as rn
    from {{ source('nhl', 'raw_standings') }}
),

latest as (
    select * from raw where rn = 1
)

select
    json_extract_scalar(teamAbbrev, '$.default') as team_abbrev,
    json_extract_scalar(teamName, '$.default') as team_name,
    date as standings_date,
    cast(seasonId as int64) as season_id,
    conferenceName as conference_name,
    divisionName as division_name,

    cast(gamesPlayed as int64) as games_played,
    cast(points as int64) as points,
    cast(wins as int64) as wins,
    cast(losses as int64) as losses,
    cast(otLosses as int64) as ot_losses,

    -- Ranks
    cast(leagueSequence as int64) as league_rank,
    cast(conferenceSequence as int64) as conference_rank,
    cast(divisionSequence as int64) as division_rank,
    cast(wildcardSequence as int64) as wildcard_rank,

    -- Last 10
    cast(l10Wins as int64) as l10_wins,
    cast(l10Losses as int64) as l10_losses,
    cast(l10OtLosses as int64) as l10_ot_losses,

    streakCode as streak_code,
    cast(streakCount as int64) as streak_count,

    ingestion_date
from latest
where teamName is not null
