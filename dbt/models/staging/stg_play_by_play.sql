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

        -- Unnest plays array
        play.eventId as event_id,
        play.periodDescriptor.number as period_number,
        play.periodDescriptor.periodType as period_type,
        play.timeInPeriod as time_in_period,
        play.timeRemaining as time_remaining,
        play.situationCode as situation_code,
        play.typeCode as type_code,
        play.typeDescKey as type_desc_key,
        play.sortOrder as sort_order,
        play.homeTeamDefendingSide as home_team_defending_side,

        -- Details fields (many are optional, so safely access)
        play.details.xCoord as x_coord,
        play.details.yCoord as y_coord,
        play.details.zoneCode as zone_code,
        play.details.shotType as shot_type,
        play.details.reason as reason,
        play.details.secondaryReason as secondary_reason,

        -- Player IDs
        play.details.shootingPlayerId as shooting_player_id,
        play.details.scoringPlayerId as scoring_player_id,
        play.details.goalieInNetId as goalie_in_net_id,
        play.details.assist1PlayerId as assist1_player_id,
        play.details.assist2PlayerId as assist2_player_id,
        play.details.blockingPlayerId as blocking_player_id,
        play.details.hittingPlayerId as hitting_player_id,
        play.details.hitteePlayerId as hittee_player_id,
        play.details.committedByPlayerId as committed_by_player_id,
        play.details.drawnByPlayerId as drawn_by_player_id,
        play.details.playerId as player_id,

        -- Scoring details
        play.details.homeScore as home_score,
        play.details.awayScore as away_score,
        play.details.homeSOG as home_sog,
        play.details.awaySOG as away_sog,

        -- Event owner
        play.details.eventOwnerTeamId as event_owner_team_id,

        -- Duration for penalties
        play.details.duration as duration

    from source
    cross join unnest(plays) as play
),

renamed as (
    select
        cast(game_id as int64) as game_id,
        cast(api_game_id as int64) as api_game_id,
        cast(season as int64) as season,
        cast(game_date as date) as game_date,
        cast(ingestion_date as date) as ingestion_date,

        cast(event_id as int64) as event_id,
        cast(period_number as int64) as period_number,
        cast(period_type as string) as period_type,
        cast(time_in_period as string) as time_in_period,
        cast(time_remaining as string) as time_remaining,
        cast(situation_code as string) as situation_code,
        cast(type_code as int64) as type_code,
        cast(type_desc_key as string) as type_desc_key,
        cast(sort_order as int64) as sort_order,
        cast(home_team_defending_side as string) as home_team_defending_side,

        cast(x_coord as int64) as x_coord,
        cast(y_coord as int64) as y_coord,
        cast(zone_code as string) as zone_code,
        cast(shot_type as string) as shot_type,
        cast(reason as string) as reason,
        cast(secondary_reason as string) as secondary_reason,

        cast(shooting_player_id as int64) as shooting_player_id,
        cast(scoring_player_id as int64) as scoring_player_id,
        cast(goalie_in_net_id as int64) as goalie_in_net_id,
        cast(assist1_player_id as int64) as assist1_player_id,
        cast(assist2_player_id as int64) as assist2_player_id,
        cast(blocking_player_id as int64) as blocking_player_id,
        cast(hitting_player_id as int64) as hitting_player_id,
        cast(hittee_player_id as int64) as hittee_player_id,
        cast(committed_by_player_id as int64) as committed_by_player_id,
        cast(drawn_by_player_id as int64) as drawn_by_player_id,
        cast(player_id as int64) as player_id,

        cast(home_score as int64) as home_score,
        cast(away_score as int64) as away_score,
        cast(home_sog as int64) as home_sog,
        cast(away_sog as int64) as away_sog,

        cast(event_owner_team_id as int64) as event_owner_team_id,
        cast(duration as int64) as duration,

        current_timestamp() as _loaded_at

    from unnested
),

deduplicated as (
    select
        *,
        row_number() over (partition by game_id, event_id order by ingestion_date desc) as rn
    from renamed
),

final as (
    select
        game_id,
        api_game_id,
        season,
        game_date,
        ingestion_date,
        event_id,
        period_number,
        period_type,
        time_in_period,
        time_remaining,
        situation_code,
        type_code,
        type_desc_key,
        sort_order,
        home_team_defending_side,
        x_coord,
        y_coord,
        zone_code,
        shot_type,
        reason,
        secondary_reason,
        shooting_player_id,
        scoring_player_id,
        goalie_in_net_id,
        assist1_player_id,
        assist2_player_id,
        blocking_player_id,
        hitting_player_id,
        hittee_player_id,
        committed_by_player_id,
        drawn_by_player_id,
        player_id,
        home_score,
        away_score,
        home_sog,
        away_sog,
        event_owner_team_id,
        duration,
        _loaded_at
    from deduplicated
    where rn = 1
)

select * from final
