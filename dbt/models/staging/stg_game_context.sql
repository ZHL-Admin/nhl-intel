-- One row per game: pregame/postgame context for the GameDetail surface.
-- Sources: raw_game_landing (goal highlight links, three stars) + raw_game_right_rail
-- (scratches, coaches, season series, team stat comparisons). Heavy nested payloads
-- are stored serialized upstream; parsed here into queryable arrays/scalars.
-- Last-10 records are NOT in these payloads — the backend joins them from stg_standings.

with landing_raw as (
    select
        game_id,
        season,
        summary,
        awayTeam,
        homeTeam,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
    from {{ source('nhl', 'raw_game_landing') }}
),

landing as (
    select * from landing_raw where rn = 1
),

rail_raw as (
    select
        game_id,
        gameInfo,
        seasonSeries,
        seasonSeriesWins,
        teamGameStats,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
    from {{ source('nhl', 'raw_game_right_rail') }}
),

rail as (
    select * from rail_raw where rn = 1
)

select
    l.game_id,
    l.season,
    cast(json_extract_scalar(l.awayTeam, '$.id') as int64) as away_team_id,
    cast(json_extract_scalar(l.homeTeam, '$.id') as int64) as home_team_id,

    -- Head coaches
    json_extract_scalar(r.gameInfo, '$.awayTeam.headCoach.default') as away_head_coach,
    json_extract_scalar(r.gameInfo, '$.homeTeam.headCoach.default') as home_head_coach,

    -- Scratches per team (player id + name)
    array(
        select as struct
            cast(json_extract_scalar(s, '$.id') as int64) as player_id,
            concat(
                coalesce(json_extract_scalar(s, '$.firstName.default'), ''), ' ',
                coalesce(json_extract_scalar(s, '$.lastName.default'), '')
            ) as player_name
        from unnest(json_extract_array(r.gameInfo, '$.awayTeam.scratches')) as s
    ) as away_scratches,
    array(
        select as struct
            cast(json_extract_scalar(s, '$.id') as int64) as player_id,
            concat(
                coalesce(json_extract_scalar(s, '$.firstName.default'), ''), ' ',
                coalesce(json_extract_scalar(s, '$.lastName.default'), '')
            ) as player_name
        from unnest(json_extract_array(r.gameInfo, '$.homeTeam.scratches')) as s
    ) as home_scratches,

    -- Season series: wins summary + prior meetings
    cast(json_extract_scalar(r.seasonSeriesWins, '$.awayTeamWins') as int64) as season_series_away_wins,
    cast(json_extract_scalar(r.seasonSeriesWins, '$.homeTeamWins') as int64) as season_series_home_wins,
    cast(json_extract_scalar(r.seasonSeriesWins, '$.neededToWin') as int64) as season_series_needed_to_win,
    array(
        select as struct
            cast(json_extract_scalar(m, '$.id') as int64) as game_id,
            json_extract_scalar(m, '$.gameDate') as game_date,
            json_extract_scalar(m, '$.awayTeam.abbrev') as away_abbrev,
            cast(json_extract_scalar(m, '$.awayTeam.score') as int64) as away_score,
            json_extract_scalar(m, '$.homeTeam.abbrev') as home_abbrev,
            cast(json_extract_scalar(m, '$.homeTeam.score') as int64) as home_score
        from unnest(json_extract_array(r.seasonSeries)) as m
    ) as season_series_games,

    -- Team game stat comparisons (category / away / home)
    array(
        select as struct
            json_extract_scalar(t, '$.category') as category,
            json_extract_scalar(t, '$.awayValue') as away_value,
            json_extract_scalar(t, '$.homeValue') as home_value
        from unnest(json_extract_array(r.teamGameStats)) as t
    ) as team_game_stats,

    -- Goal highlight links keyed by event id (period carried from the scoring block)
    array(
        select as struct
            cast(json_extract_scalar(g, '$.eventId') as int64) as event_id,
            cast(json_extract_scalar(p, '$.periodDescriptor.number') as int64) as period,
            cast(json_extract_scalar(g, '$.playerId') as int64) as scorer_player_id,
            json_extract_scalar(g, '$.timeInPeriod') as time_in_period,
            json_extract_scalar(g, '$.highlightClipSharingUrl') as highlight_url,
            json_extract_scalar(g, '$.pptReplayUrl') as ppt_replay_url
        from unnest(json_extract_array(l.summary, '$.scoring')) as p,
            unnest(json_extract_array(p, '$.goals')) as g
    ) as goal_highlights

from landing l
left join rail r on l.game_id = r.game_id
