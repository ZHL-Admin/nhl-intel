{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "team_id"]
) }}

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
    from {{ ref('int_zone_entry_proxy') }}
    where is_controlled_entry is not null
    group by game_id, team_id
),

period_stats as (
    select
        game_id,
        event_owner_team_id as team_id,
        period_number,
        count(*) as cf,
        sum(xg_value) as xgf,
        sum(case when is_goal then 1 else 0 end) as gf
    from {{ ref('int_shot_attempts') }}
    where period_number in (1, 2, 3, 4)
    group by game_id, event_owner_team_id, period_number
),

period_pivoted as (
    select
        game_id,
        team_id,
        sum(case when period_number = 1 then cf else 0 end) as cf_p1,
        sum(case when period_number = 2 then cf else 0 end) as cf_p2,
        sum(case when period_number = 3 then cf else 0 end) as cf_p3,
        sum(case when period_number = 1 then xgf else 0 end) as xgf_p1,
        sum(case when period_number = 2 then xgf else 0 end) as xgf_p2,
        sum(case when period_number = 3 then xgf else 0 end) as xgf_p3,
        sum(case when period_number = 1 then gf else 0 end) as gf_p1,
        sum(case when period_number = 2 then gf else 0 end) as gf_p2,
        sum(case when period_number = 3 then gf else 0 end) as gf_p3
    from period_stats
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
        coalesce(ze.controlled_entries, 0) as controlled_zone_entries,
        coalesce(pp_for.cf_p1, 0) as cf_p1,
        coalesce(pp_for.cf_p2, 0) as cf_p2,
        coalesce(pp_for.cf_p3, 0) as cf_p3,
        coalesce(pp_against.cf_p1, 0) as ca_p1,
        coalesce(pp_against.cf_p2, 0) as ca_p2,
        coalesce(pp_against.cf_p3, 0) as ca_p3,
        coalesce(pp_for.xgf_p1, 0.0) as xgf_p1,
        coalesce(pp_for.xgf_p2, 0.0) as xgf_p2,
        coalesce(pp_for.xgf_p3, 0.0) as xgf_p3,
        coalesce(pp_against.xgf_p1, 0.0) as xga_p1,
        coalesce(pp_against.xgf_p2, 0.0) as xga_p2,
        coalesce(pp_against.xgf_p3, 0.0) as xga_p3,
        coalesce(pp_for.gf_p1, 0) as gf_p1,
        coalesce(pp_for.gf_p2, 0) as gf_p2,
        coalesce(pp_for.gf_p3, 0) as gf_p3,
        coalesce(pp_against.gf_p1, 0) as ga_p1,
        coalesce(pp_against.gf_p2, 0) as ga_p2,
        coalesce(pp_against.gf_p3, 0) as ga_p3
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
    left join period_pivoted pp_for
        on g.game_id = pp_for.game_id
        and g.home_team_id = pp_for.team_id
    left join period_pivoted pp_against
        on g.game_id = pp_against.game_id
        and g.away_team_id = pp_against.team_id
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
        coalesce(ze.controlled_entries, 0) as controlled_zone_entries,
        coalesce(pp_for.cf_p1, 0) as cf_p1,
        coalesce(pp_for.cf_p2, 0) as cf_p2,
        coalesce(pp_for.cf_p3, 0) as cf_p3,
        coalesce(pp_against.cf_p1, 0) as ca_p1,
        coalesce(pp_against.cf_p2, 0) as ca_p2,
        coalesce(pp_against.cf_p3, 0) as ca_p3,
        coalesce(pp_for.xgf_p1, 0.0) as xgf_p1,
        coalesce(pp_for.xgf_p2, 0.0) as xgf_p2,
        coalesce(pp_for.xgf_p3, 0.0) as xgf_p3,
        coalesce(pp_against.xgf_p1, 0.0) as xga_p1,
        coalesce(pp_against.xgf_p2, 0.0) as xga_p2,
        coalesce(pp_against.xgf_p3, 0.0) as xga_p3,
        coalesce(pp_for.gf_p1, 0) as gf_p1,
        coalesce(pp_for.gf_p2, 0) as gf_p2,
        coalesce(pp_for.gf_p3, 0) as gf_p3,
        coalesce(pp_against.gf_p1, 0) as ga_p1,
        coalesce(pp_against.gf_p2, 0) as ga_p2,
        coalesce(pp_against.gf_p3, 0) as ga_p3
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
    left join period_pivoted pp_for
        on g.game_id = pp_for.game_id
        and g.away_team_id = pp_for.team_id
    left join period_pivoted pp_against
        on g.game_id = pp_against.game_id
        and g.home_team_id = pp_against.team_id
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
        cf_p1,
        cf_p2,
        cf_p3,
        ca_p1,
        ca_p2,
        ca_p3,
        xgf_p1,
        xgf_p2,
        xgf_p3,
        xga_p1,
        xga_p2,
        xga_p3,
        gf_p1,
        gf_p2,
        gf_p3,
        ga_p1,
        ga_p2,
        ga_p3,

        case
            when (shot_attempts_for + shot_attempts_against) > 0
            then cast(shot_attempts_for as float64) / (shot_attempts_for + shot_attempts_against)
            else null
        end as cf_pct,

        case
            when (cf_p1 + ca_p1) > 0
            then cast(cf_p1 as float64) / (cf_p1 + ca_p1)
            else null
        end as cf_pct_p1,

        case
            when (cf_p2 + ca_p2) > 0
            then cast(cf_p2 as float64) / (cf_p2 + ca_p2)
            else null
        end as cf_pct_p2,

        case
            when (cf_p3 + ca_p3) > 0
            then cast(cf_p3 as float64) / (cf_p3 + ca_p3)
            else null
        end as cf_pct_p3,

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
        end as zone_entry_proxy_success_rate

    from all_teams
),

final as (
    select
        m.game_id,
        m.game_date,
        m.season,
        m.team_id,
        m.team_abbrev,
        m.home_away,
        m.goals_for,
        m.goals_against,
        m.shot_attempts_for,
        m.shot_attempts_against,
        m.high_danger_for,
        m.high_danger_against,
        m.xgf,
        m.xga,
        m.cf_pct,
        m.xgf_pct,
        m.hdcf_per60,
        m.hdca_per60,
        m.zone_entry_proxy_success_rate,
        m.estimated_toi_5v5_minutes as toi_5v5_minutes,
        m.cf_p1,
        m.cf_p2,
        m.cf_p3,
        m.ca_p1,
        m.ca_p2,
        m.ca_p3,
        m.cf_pct_p1,
        m.cf_pct_p2,
        m.cf_pct_p3,
        m.xgf_p1,
        m.xgf_p2,
        m.xgf_p3,
        m.xga_p1,
        m.xga_p2,
        m.xga_p3,
        m.gf_p1,
        m.gf_p2,
        m.gf_p3,
        m.ga_p1,
        m.ga_p2,
        m.ga_p3,
        -- 5v5 sequence-mix shares (Phase 2.1): for = own offense, against = opp offense
        ii.rebound_share_for,
        ii.rush_share_for,
        ii.forecheck_share_for,
        ii.cycle_share_for,
        ii.point_shot_share_for,
        ii.other_share_for,
        ii.cross_ice_share_for,
        ii.rebound_share_against,
        ii.rush_share_against,
        ii.forecheck_share_against,
        ii.cycle_share_against,
        ii.point_shot_share_against,
        ii.other_share_against,
        ii.cross_ice_share_against
    from metrics_calculated m
    left join {{ ref('mart_team_identity_inputs') }} ii
        on m.game_id = ii.game_id and m.team_id = ii.team_id
)

select * from final
