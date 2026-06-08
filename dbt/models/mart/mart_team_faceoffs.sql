{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "team_id"]
) }}

-- Faceoff statistics aggregated by team and game
-- event_owner_team_id in faceoff events represents the team that won the faceoff

with games as (
    select
        game_id,
        game_date,
        season,
        home_team_id,
        away_team_id
    from {{ ref('stg_boxscores') }}
),

faceoffs_won as (
    select
        game_id,
        season,
        event_owner_team_id as team_id,
        count(*) as total_faceoffs_won,
        sum(case when zone_code = 'O' then 1 else 0 end) as oz_faceoffs_won,
        sum(case when zone_code = 'N' then 1 else 0 end) as nz_faceoffs_won,
        sum(case when zone_code = 'D' then 1 else 0 end) as dz_faceoffs_won
    from {{ ref('stg_play_by_play') }}
    where type_desc_key = 'faceoff'
      and event_owner_team_id is not null
    group by game_id, season, event_owner_team_id
),

all_faceoffs as (
    select
        game_id,
        season,
        count(*) as total_faceoffs,
        sum(case when zone_code = 'O' then 1 else 0 end) as oz_faceoffs,
        sum(case when zone_code = 'N' then 1 else 0 end) as nz_faceoffs,
        sum(case when zone_code = 'D' then 1 else 0 end) as dz_faceoffs
    from {{ ref('stg_play_by_play') }}
    where type_desc_key = 'faceoff'
    group by game_id, season
),

home_teams as (
    select
        g.game_id,
        g.game_date,
        g.season,
        g.home_team_id as team_id,
        coalesce(fw.total_faceoffs_won, 0) as faceoffs_won,
        coalesce(fw.oz_faceoffs_won, 0) as oz_faceoffs_won,
        coalesce(fw.nz_faceoffs_won, 0) as nz_faceoffs_won,
        coalesce(fw.dz_faceoffs_won, 0) as dz_faceoffs_won,
        coalesce(af.total_faceoffs, 0) as total_faceoffs,
        coalesce(af.oz_faceoffs, 0) as total_oz_faceoffs,
        coalesce(af.nz_faceoffs, 0) as total_nz_faceoffs,
        coalesce(af.dz_faceoffs, 0) as total_dz_faceoffs
    from games g
    left join faceoffs_won fw
        on g.game_id = fw.game_id
        and g.home_team_id = fw.team_id
    left join all_faceoffs af
        on g.game_id = af.game_id
),

away_teams as (
    select
        g.game_id,
        g.game_date,
        g.season,
        g.away_team_id as team_id,
        coalesce(fw.total_faceoffs_won, 0) as faceoffs_won,
        coalesce(fw.oz_faceoffs_won, 0) as oz_faceoffs_won,
        coalesce(fw.nz_faceoffs_won, 0) as nz_faceoffs_won,
        coalesce(fw.dz_faceoffs_won, 0) as dz_faceoffs_won,
        coalesce(af.total_faceoffs, 0) as total_faceoffs,
        coalesce(af.oz_faceoffs, 0) as total_oz_faceoffs,
        coalesce(af.nz_faceoffs, 0) as total_nz_faceoffs,
        coalesce(af.dz_faceoffs, 0) as total_dz_faceoffs
    from games g
    left join faceoffs_won fw
        on g.game_id = fw.game_id
        and g.away_team_id = fw.team_id
    left join all_faceoffs af
        on g.game_id = af.game_id
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
        faceoffs_won,
        total_faceoffs - faceoffs_won as faceoffs_lost,
        total_faceoffs,
        oz_faceoffs_won,
        nz_faceoffs_won,
        dz_faceoffs_won,
        total_oz_faceoffs - oz_faceoffs_won as oz_faceoffs_lost,
        total_nz_faceoffs - nz_faceoffs_won as nz_faceoffs_lost,
        total_dz_faceoffs - dz_faceoffs_won as dz_faceoffs_lost,

        -- Overall faceoff win percentage
        case
            when total_faceoffs > 0
            then cast(faceoffs_won as float64) / total_faceoffs
            else 0.0
        end as faceoff_win_pct,

        -- Zone-specific faceoff win percentages
        case
            when total_oz_faceoffs > 0
            then cast(oz_faceoffs_won as float64) / total_oz_faceoffs
            else 0.0
        end as oz_faceoff_win_pct,

        case
            when total_nz_faceoffs > 0
            then cast(nz_faceoffs_won as float64) / total_nz_faceoffs
            else 0.0
        end as nz_faceoff_win_pct,

        case
            when total_dz_faceoffs > 0
            then cast(dz_faceoffs_won as float64) / total_dz_faceoffs
            else 0.0
        end as dz_faceoff_win_pct
    from all_teams
)

select * from final
