-- One row per goalie appearance, from the official boxscore goalie lines
-- (raw_boxscores.playerByGameStats.{homeTeam,awayTeam}.goalies). This is the authoritative
-- source for goalie time-on-ice and the W/L/OTL decision, which the shift charts do not cover
-- reliably for every game. Drives the record, GAA, and shutouts on mart_goalie_season.

with src as (
    select
        cast(game_id as int64) as game_id,
        cast(season as string) as season,    -- already 'YYYY-YY' in the raw boxscore
        cast(gameDate as date) as game_date,
        cast(gameType as int64) as game_type,
        homeTeam.id as home_team_id,
        awayTeam.id as away_team_id,
        playerByGameStats as pg
    from {{ source('nhl', 'raw_boxscores') }}
),

home as (
    select s.game_id, s.season, s.game_date, s.game_type, s.home_team_id as team_id,
           g.playerId as goalie_id, g.toi, g.goalsAgainst, g.shotsAgainst, g.decision, g.starter
    from src s, unnest(s.pg.homeTeam.goalies) as g
),

away as (
    select s.game_id, s.season, s.game_date, s.game_type, s.away_team_id as team_id,
           g.playerId as goalie_id, g.toi, g.goalsAgainst, g.shotsAgainst, g.decision, g.starter
    from src s, unnest(s.pg.awayTeam.goalies) as g
),

unioned as (
    select * from home
    union all
    select * from away
)

select
    game_id,
    season,
    game_date,
    game_type,
    team_id,
    goalie_id,
    -- toi is "MM:SS"; null/empty -> 0 (a dressed backup who did not play)
    case
        when toi is null or toi = '' then 0
        else cast(split(toi, ':')[offset(0)] as int64) * 60 + cast(split(toi, ':')[offset(1)] as int64)
    end as toi_seconds,
    goalsAgainst as goals_against,
    shotsAgainst as shots_against,
    decision,                         -- 'W' / 'L' / 'O' (OT/SO loss) / null (no decision)
    coalesce(starter, false) as starter
from unioned
where goalie_id is not null
  and game_type in (2, 3)             -- regular season + playoffs (NHL only)
