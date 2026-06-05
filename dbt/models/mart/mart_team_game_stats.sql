with games as (
    select
        game_id,
        game_date,
        season,
        home_team_id,
        home_team_abbrev,
        away_team_id,
        away_team_abbrev,
        home_team_score,
        away_team_score
    from {{ ref('stg_boxscores') }}
),

shot_attempts as (
    select
        game_id,
        event_owner_team_id as team_id,
        count(*) as shot_attempts,
        sum(case when is_high_danger then 1 else 0 end) as high_danger_attempts,
        sum(case when is_goal then 1 else 0 end) as goals_5v5,
        sum(xg_value) as xgf
    from {{ ref('int_shot_attempts') }}
    group by game_id, event_owner_team_id
),

zone_entries as (
    select
        game_id,
        team_id,
        count(*) as total_entries,
        sum(case when is_controlled_entry then 1 else 0 end) as controlled_entries
    from {{ ref('int_zone_entries') }}
    where is_controlled_entry is not null
    group by game_id, team_id
),

home_teams as (
    select
        g.game_id,
        g.game_date,
        g.season,
        g.home_team_id as team_id,
        g.home_team_abbrev as team_abbrev,
        'home' as home_away,
        g.home_team_score as goals_for,
        g.away_team_score as goals_against,
        coalesce(sa_for.shot_attempts, 0) as shot_attempts_for,
        coalesce(sa_against.shot_attempts, 0) as shot_attempts_against,
        coalesce(sa_for.high_danger_attempts, 0) as high_danger_for,
        coalesce(sa_against.high_danger_attempts, 0) as high_danger_against,
        coalesce(sa_for.goals_5v5, 0) as goals_5v5_for,
        coalesce(sa_against.goals_5v5, 0) as goals_5v5_against,
        coalesce(sa_for.xgf, 0.0) as xgf,
        coalesce(sa_against.xgf, 0.0) as xga,
        coalesce(ze.total_entries, 0) as zone_entries,
        coalesce(ze.controlled_entries, 0) as controlled_zone_entries
    from games g
    left join shot_attempts sa_for
        on g.game_id = sa_for.game_id
        and g.home_team_id = sa_for.team_id
    left join shot_attempts sa_against
        on g.game_id = sa_against.game_id
        and g.away_team_id = sa_against.team_id
    left join zone_entries ze
        on g.game_id = ze.game_id
        and g.home_team_id = ze.team_id
),

away_teams as (
    select
        g.game_id,
        g.game_date,
        g.season,
        g.away_team_id as team_id,
        g.away_team_abbrev as team_abbrev,
        'away' as home_away,
        g.away_team_score as goals_for,
        g.home_team_score as goals_against,
        coalesce(sa_for.shot_attempts, 0) as shot_attempts_for,
        coalesce(sa_against.shot_attempts, 0) as shot_attempts_against,
        coalesce(sa_for.high_danger_attempts, 0) as high_danger_for,
        coalesce(sa_against.high_danger_attempts, 0) as high_danger_against,
        coalesce(sa_for.goals_5v5, 0) as goals_5v5_for,
        coalesce(sa_against.goals_5v5, 0) as goals_5v5_against,
        coalesce(sa_for.xgf, 0.0) as xgf,
        coalesce(sa_against.xgf, 0.0) as xga,
        coalesce(ze.total_entries, 0) as zone_entries,
        coalesce(ze.controlled_entries, 0) as controlled_zone_entries
    from games g
    left join shot_attempts sa_for
        on g.game_id = sa_for.game_id
        and g.away_team_id = sa_for.team_id
    left join shot_attempts sa_against
        on g.game_id = sa_against.game_id
        and g.home_team_id = sa_against.team_id
    left join zone_entries ze
        on g.game_id = ze.game_id
        and g.away_team_id = ze.team_id
),

all_teams as (
    select * from home_teams
    union all
    select * from away_teams
),

metrics_calculated as (
    select
        game_id,
        game_date,
        season,
        team_id,
        team_abbrev,
        home_away,
        goals_for,
        goals_against,
        shot_attempts_for,
        shot_attempts_against,
        high_danger_for,
        high_danger_against,
        goals_5v5_for,
        goals_5v5_against,
        xgf,
        xga,
        zone_entries,
        controlled_zone_entries,

        case
            when (shot_attempts_for + shot_attempts_against) > 0
            then cast(shot_attempts_for as float64) / (shot_attempts_for + shot_attempts_against)
            else null
        end as cf_pct,

        case
            when (xgf + xga) > 0
            then xgf / (xgf + xga)
            else null
        end as xgf_pct,

        48.0 as estimated_toi_5v5_minutes,

        case
            when high_danger_for > 0
            then (cast(high_danger_for as float64) / 48.0) * 60.0
            else 0.0
        end as hdcf_per60,

        case
            when high_danger_against > 0
            then (cast(high_danger_against as float64) / 48.0) * 60.0
            else 0.0
        end as hdca_per60,

        case
            when zone_entries > 0
            then cast(controlled_zone_entries as float64) / zone_entries
            else null
        end as zone_entry_success_rate

    from all_teams
),

final as (
    select
        game_id,
        game_date,
        season,
        team_id,
        team_abbrev,
        home_away,
        goals_for,
        goals_against,
        shot_attempts_for,
        shot_attempts_against,
        high_danger_for,
        high_danger_against,
        xgf,
        xga,
        cf_pct,
        xgf_pct,
        hdcf_per60,
        hdca_per60,
        zone_entry_success_rate,
        estimated_toi_5v5_minutes as toi_5v5_minutes
    from metrics_calculated
)

select * from final
