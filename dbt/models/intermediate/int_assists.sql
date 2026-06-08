with source as (
    select * from {{ ref('stg_play_by_play') }}
),

goals as (
    select
        game_id,
        season,
        game_date,
        event_id,
        assist1_player_id,
        assist2_player_id,
        event_owner_team_id
    from source
    where type_desc_key = 'goal'
),

first_assists as (
    select
        game_id,
        season,
        event_id as goal_event_id,
        assist1_player_id as player_id,
        1 as assist_order,
        game_date,
        event_owner_team_id as team_id
    from goals
    where assist1_player_id is not null
),

second_assists as (
    select
        game_id,
        season,
        event_id as goal_event_id,
        assist2_player_id as player_id,
        2 as assist_order,
        game_date,
        event_owner_team_id as team_id
    from goals
    where assist2_player_id is not null
),

final as (
    select * from first_assists
    union all
    select * from second_assists
)

select * from final
