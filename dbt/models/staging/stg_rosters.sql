with source as (
    select * from {{ source('nhl', 'raw_play_by_play') }}
),

unnested as (
    select
        game_id,
        id as api_game_id,
        season,
        gameDate as game_date,
        ingestion_date,

        -- Unnest rosterSpots array
        player.playerId as player_id,
        player.teamId as team_id,
        player.firstName.default as first_name,
        player.lastName.default as last_name,
        player.sweaterNumber as sweater_number,
        player.positionCode as position_code,
        player.headshot as headshot_url

    from source
    cross join unnest(rosterSpots) as player
),

renamed as (
    select
        cast(game_id as int64) as game_id,
        cast(api_game_id as int64) as api_game_id,
        cast(season as string) as season,
        cast(game_date as date) as game_date,
        cast(ingestion_date as date) as ingestion_date,

        cast(player_id as int64) as player_id,
        cast(team_id as int64) as team_id,
        cast(first_name as string) as first_name,
        cast(last_name as string) as last_name,
        cast(sweater_number as int64) as sweater_number,
        cast(position_code as string) as position_code,
        cast(headshot_url as string) as headshot_url,

        current_timestamp() as _loaded_at

    from unnested
),

deduplicated as (
    select
        game_id,
        api_game_id,
        season,
        game_date,
        ingestion_date,
        player_id,
        team_id,
        first_name,
        last_name,
        sweater_number,
        position_code,
        headshot_url,
        _loaded_at,
        row_number() over (partition by game_id, player_id order by ingestion_date desc) as rn
    from renamed
),

final as (
    select
        game_id,
        api_game_id,
        season,
        game_date,
        ingestion_date,
        player_id,
        team_id,
        first_name,
        last_name,
        sweater_number,
        position_code,
        headshot_url,
        _loaded_at
    from deduplicated
    where rn = 1
)

select * from final
