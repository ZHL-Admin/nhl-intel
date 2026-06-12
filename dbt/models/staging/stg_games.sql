-- The raw_games schedule feed now stores only {game_id, date} per game, so the
-- schedule spine is enriched with played-game detail from stg_boxscores. Team,
-- score, venue, and state columns are therefore null for any scheduled-but-unplayed game.
with schedule as (
    select
        cast(game.id as int64) as game_id,
        cast(week.date as date) as game_date,
        cast(src.season as string) as season,
        cast(src.ingestion_date as date) as ingestion_date
    from {{ source('nhl', 'raw_games') }} src
    cross join unnest(src.gameWeek) as week
    cross join unnest(week.games) as game
),

schedule_deduped as (
    select * except (rn)
    from (
        select
            *,
            row_number() over (partition by game_id order by ingestion_date desc) as rn
        from schedule
    )
    where rn = 1
),

boxscores as (
    select
        game_id,
        game_type,
        start_time_utc,
        venue_name,
        eastern_utc_offset,
        venue_utc_offset,
        game_state,
        game_schedule_state,
        away_team_id,
        away_team_abbrev,
        away_team_score,
        home_team_id,
        home_team_abbrev,
        home_team_score,
        last_period_type
    from {{ ref('stg_boxscores') }}
),

final as (
    select
        s.game_id,
        s.season,
        s.game_date,
        s.ingestion_date,
        b.game_type,
        b.start_time_utc,
        b.venue_name,
        b.eastern_utc_offset,
        b.venue_utc_offset,
        b.game_state,
        b.game_schedule_state,
        b.away_team_id,
        b.away_team_abbrev,
        b.away_team_score,
        b.home_team_id,
        b.home_team_abbrev,
        b.home_team_score,
        b.last_period_type,
        current_timestamp() as _loaded_at
    from schedule_deduped s
    left join boxscores b
        on s.game_id = b.game_id
)

select * from final
