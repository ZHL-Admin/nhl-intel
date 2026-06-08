{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "team_id"]
) }}

-- Zone time derived from faceoff locations as a proxy
-- Exact zone time requires zone entry/exit event sequencing not available in play-by-play
-- Using zone start percentages: OZS% = offensive zone faceoffs / total faceoffs

with games as (
    select
        game_id,
        game_date,
        season,
        home_team_id,
        away_team_id
    from {{ ref('stg_boxscores') }}
),

faceoffs as (
    select
        game_id,
        season,
        zone_code,
        event_owner_team_id as team_id
    from {{ ref('stg_play_by_play') }}
    where type_desc_key = 'faceoff'
      and zone_code is not null
),

team_faceoffs as (
    select
        game_id,
        season,
        team_id,
        count(*) as total_faceoffs,
        sum(case when zone_code = 'O' then 1 else 0 end) as oz_faceoffs,
        sum(case when zone_code = 'N' then 1 else 0 end) as nz_faceoffs,
        sum(case when zone_code = 'D' then 1 else 0 end) as dz_faceoffs
    from faceoffs
    group by game_id, season, team_id
),

home_teams as (
    select
        g.game_id,
        g.game_date,
        g.season,
        g.home_team_id as team_id,
        coalesce(tf.total_faceoffs, 0) as total_faceoffs,
        coalesce(tf.oz_faceoffs, 0) as oz_faceoffs,
        coalesce(tf.nz_faceoffs, 0) as nz_faceoffs,
        coalesce(tf.dz_faceoffs, 0) as dz_faceoffs
    from games g
    left join team_faceoffs tf
        on g.game_id = tf.game_id
        and g.home_team_id = tf.team_id
),

away_teams as (
    select
        g.game_id,
        g.game_date,
        g.season,
        g.away_team_id as team_id,
        coalesce(tf.total_faceoffs, 0) as total_faceoffs,
        coalesce(tf.oz_faceoffs, 0) as oz_faceoffs,
        coalesce(tf.nz_faceoffs, 0) as nz_faceoffs,
        coalesce(tf.dz_faceoffs, 0) as dz_faceoffs
    from games g
    left join team_faceoffs tf
        on g.game_id = tf.game_id
        and g.away_team_id = tf.team_id
),

all_teams as (
    select * from home_teams
    union all
    select * from away_teams
),

final as (
    select
        game_id,
        game_date,
        season,
        team_id,
        total_faceoffs,
        oz_faceoffs,
        nz_faceoffs,
        dz_faceoffs,
        case
            when total_faceoffs > 0
            then cast(oz_faceoffs as float64) / total_faceoffs
            else 0.0
        end as ozs_pct,
        case
            when total_faceoffs > 0
            then cast(nz_faceoffs as float64) / total_faceoffs
            else 0.0
        end as nzs_pct,
        case
            when total_faceoffs > 0
            then cast(dz_faceoffs as float64) / total_faceoffs
            else 0.0
        end as dzs_pct,
        -- oz_pct, nz_pct, dz_pct are same as ozs_pct, nzs_pct, dzs_pct in this methodology
        case
            when total_faceoffs > 0
            then cast(oz_faceoffs as float64) / total_faceoffs
            else 0.0
        end as oz_pct,
        case
            when total_faceoffs > 0
            then cast(nz_faceoffs as float64) / total_faceoffs
            else 0.0
        end as nz_pct,
        case
            when total_faceoffs > 0
            then cast(dz_faceoffs as float64) / total_faceoffs
            else 0.0
        end as dz_pct
    from all_teams
)

select * from final
