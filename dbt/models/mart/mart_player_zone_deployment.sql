{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "player_id"]
) }}

-- Player zone deployment metrics using team-level proxies
-- LIMITATION: NHL API play-by-play does not include shift-level data (which players were on ice)
-- or faceoff participant IDs. This model assigns each player their team's zone deployment stats
-- as a baseline. True player-level zone deployment requires shift tracking data.

with rosters as (
    select
        game_id,
        game_date,
        season,
        player_id,
        team_id,
        first_name,
        last_name,
        position_code
    from {{ ref('stg_rosters') }}
    where position_code in ('C', 'L', 'R', 'D')
),

team_zone_time as (
    select
        game_id,
        season,
        team_id,
        ozs_pct,
        nzs_pct,
        dzs_pct,
        total_faceoffs
    from {{ ref('mart_team_zone_time') }}
),

team_zone_entries as (
    select
        ze.game_id,
        ze.season,
        ze.team_id,
        count(*) as total_entries,
        sum(case when ze.is_controlled_entry then 1 else 0 end) as controlled_entries
    from {{ ref('int_zone_entries') }} ze
    where ze.is_controlled_entry is not null
    group by ze.game_id, ze.season, ze.team_id
),

final as (
    select
        r.game_id,
        r.game_date,
        r.season,
        r.player_id,
        r.team_id,
        r.first_name,
        r.last_name,
        r.position_code,

        -- Zone start percentages (team-level proxy)
        coalesce(tzt.ozs_pct, 0.0) as ozs_pct,
        coalesce(tzt.nzs_pct, 0.0) as nzs_pct,
        coalesce(tzt.dzs_pct, 0.0) as dzs_pct,

        -- Controlled entry success rate (team-level proxy)
        case
            when coalesce(tze.total_entries, 0) > 0
            then cast(tze.controlled_entries as float64) / tze.total_entries
            else 0.0
        end as controlled_entry_pct,

        coalesce(tze.total_entries, 0) as team_zone_entries,
        coalesce(tze.controlled_entries, 0) as team_controlled_entries

    from rosters r
    left join team_zone_time tzt
        on r.game_id = tzt.game_id
        and r.team_id = tzt.team_id
    left join team_zone_entries tze
        on r.game_id = tze.game_id
        and r.team_id = tze.team_id
)

select * from final
