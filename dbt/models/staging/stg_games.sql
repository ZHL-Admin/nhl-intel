with source as (
    select
        season,
        ingestion_date,
        gameWeek
    from {{ source('nhl', 'raw_games') }}
),

flattened as (
    select
        source.ingestion_date,
        source.season as season_str,
        week.date as game_date,
        game.id as game_id,
        game.season as api_season_id,
        game.gameType as game_type,
        game.venue.default as venue_name,
        game.neutralSite as is_neutral_site,
        game.startTimeUTC as start_time_utc,
        game.easternUTCOffset as eastern_utc_offset,
        game.venueUTCOffset as venue_utc_offset,
        game.gameState as game_state,
        game.gameScheduleState as game_schedule_state,
        game.awayTeam.id as away_team_id,
        game.awayTeam.abbrev as away_team_abbrev,
        game.awayTeam.score as away_team_score,
        game.awayTeam.placeName.default as away_team_city,
        game.homeTeam.id as home_team_id,
        game.homeTeam.abbrev as home_team_abbrev,
        game.homeTeam.score as home_team_score,
        game.homeTeam.placeName.default as home_team_city,
        game.periodDescriptor.number as period_number,
        game.periodDescriptor.periodType as period_type,
        game.gameOutcome.lastPeriodType as last_period_type
    from source
    cross join unnest(gameWeek) as week
    cross join unnest(week.games) as game
),

renamed as (
    select
        cast(game_id as int64) as game_id,
        cast(season_str as string) as season,
        cast(api_season_id as int64) as api_season_id,
        cast(game_type as int64) as game_type,
        cast(game_date as date) as game_date,
        cast(start_time_utc as timestamp) as start_time_utc,
        cast(venue_name as string) as venue_name,
        cast(is_neutral_site as bool) as is_neutral_site,
        cast(eastern_utc_offset as string) as eastern_utc_offset,
        cast(venue_utc_offset as string) as venue_utc_offset,
        cast(game_state as string) as game_state,
        cast(game_schedule_state as string) as game_schedule_state,
        cast(away_team_id as int64) as away_team_id,
        cast(away_team_abbrev as string) as away_team_abbrev,
        cast(away_team_score as int64) as away_team_score,
        cast(away_team_city as string) as away_team_city,
        cast(home_team_id as int64) as home_team_id,
        cast(home_team_abbrev as string) as home_team_abbrev,
        cast(home_team_score as int64) as home_team_score,
        cast(home_team_city as string) as home_team_city,
        cast(period_number as int64) as period_number,
        cast(period_type as string) as period_type,
        cast(last_period_type as string) as last_period_type,
        cast(ingestion_date as date) as ingestion_date,
        current_timestamp() as _loaded_at
    from flattened
),

deduped as (
    select
        *,
        row_number() over (partition by game_id order by _loaded_at desc) as row_num
    from renamed
),

final as (
    select * except (row_num)
    from deduped
    where row_num = 1
)

select * from final
