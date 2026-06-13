-- One row per (player, season, game_type): season-level faceoff splits from the
-- stats-REST skater/faceoffwins report (zone + ev/pp/sh win/loss counts).
-- Source: nhl_raw.raw_statsrest_faceoffs (flat records; refresh job injects game_type).
-- This is SEASON-LEVEL data; it complements (does not replace) the event-derived
-- per-game faceoff data in mart_team_faceoffs — see schema.yml.

with raw as (
    select
        *,
        row_number() over (
            partition by playerId, seasonId, game_type
            order by ingestion_date desc
        ) as rn
    from {{ source('nhl', 'raw_statsrest_faceoffs') }}
),

latest as (
    select * from raw where rn = 1
)

select
    cast(playerId as int64) as player_id,
    skaterFullName as player_name,
    positionCode as position_code,
    teamAbbrevs as team_abbrevs,
    cast(seasonId as int64) as season_id,
    cast(game_type as int64) as game_type,
    cast(gamesPlayed as int64) as games_played,

    -- Zone splits
    cast(offensiveZoneFaceoffWins as int64) as oz_faceoff_wins,
    cast(offensiveZoneFaceoffLosses as int64) as oz_faceoff_losses,
    cast(offensiveZoneFaceoffs as int64) as oz_faceoffs,
    cast(neutralZoneFaceoffWins as int64) as nz_faceoff_wins,
    cast(neutralZoneFaceoffLosses as int64) as nz_faceoff_losses,
    cast(neutralZoneFaceoffs as int64) as nz_faceoffs,
    cast(defensiveZoneFaceoffWins as int64) as dz_faceoff_wins,
    cast(defensiveZoneFaceoffLosses as int64) as dz_faceoff_losses,
    cast(defensiveZoneFaceoffs as int64) as dz_faceoffs,

    -- Strength splits
    cast(evFaceoffsWon as int64) as ev_faceoff_wins,
    cast(evFaceoffsLost as int64) as ev_faceoff_losses,
    cast(ppFaceoffsWon as int64) as pp_faceoff_wins,
    cast(ppFaceoffsLost as int64) as pp_faceoff_losses,
    cast(shFaceoffsWon as int64) as sh_faceoff_wins,
    cast(shFaceoffsLost as int64) as sh_faceoff_losses,

    -- Totals
    cast(totalFaceoffWins as int64) as total_faceoff_wins,
    cast(totalFaceoffLosses as int64) as total_faceoff_losses,
    cast(totalFaceoffs as int64) as total_faceoffs,
    cast(faceoffWinPct as float64) as faceoff_win_pct,

    ingestion_date
from latest
where playerId is not null
