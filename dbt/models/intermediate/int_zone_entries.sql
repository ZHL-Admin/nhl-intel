with source as (
    select * from {{ ref('stg_play_by_play') }}
),

events_with_lag as (
    select
        game_id,
        event_id,
        period_number,
        sort_order,
        type_desc_key,
        zone_code,
        event_owner_team_id,
        situation_code,
        lag(zone_code) over (partition by game_id, event_owner_team_id order by sort_order) as prev_zone_code,
        lag(type_desc_key) over (partition by game_id, event_owner_team_id order by sort_order) as prev_event_type
    from source
    where situation_code = '1551'
      and event_owner_team_id is not null
),

zone_entries as (
    select
        game_id,
        event_id,
        period_number,
        event_owner_team_id as team_id,
        type_desc_key,
        zone_code,
        prev_zone_code,

        case
            when zone_code = 'O' and prev_zone_code in ('N', 'D') and type_desc_key not in ('faceoff', 'penalty') then true
            else false
        end as is_zone_entry,

        case
            when zone_code = 'O' and prev_zone_code in ('N', 'D')
                 and type_desc_key in ('shot-on-goal', 'goal', 'takeaway', 'hit') then true
            when zone_code = 'O' and prev_zone_code in ('N', 'D')
                 and type_desc_key in ('giveaway', 'blocked-shot') then false
            else null
        end as is_controlled_entry

    from events_with_lag
),

final as (
    select
        game_id,
        event_id,
        period_number,
        team_id,
        is_zone_entry,
        is_controlled_entry
    from zone_entries
    where is_zone_entry = true
)

select * from final
