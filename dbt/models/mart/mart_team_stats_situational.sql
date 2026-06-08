{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "team_id"]
) }}

-- Team stats split by game situation (5v5, PP, PK, other)
-- Situation codes are 4 digits XYZW where XY=away strength, ZW=home strength

with games as (
    select
        game_id,
        game_date,
        season,
        home_team_id,
        away_team_id
    from {{ ref('stg_boxscores') }}
),

shot_attempts as (
    select
        pbp.game_id,
        pbp.season,
        pbp.event_owner_team_id as team_id,
        pbp.situation_code,
        g.home_team_id,
        g.away_team_id,
        pbp.is_goal,
        pbp.xg_value
    from {{ ref('int_shot_attempts') }} pbp
    inner join games g on pbp.game_id = g.game_id
),

situational_stats as (
    select
        game_id,
        season,
        team_id,

        -- 5v5 stats
        sum(case when situation_code = '1551' then 1 else 0 end) as shot_attempts_5v5,
        sum(case when situation_code = '1551' and is_goal then 1 else 0 end) as goals_5v5,
        sum(case when situation_code = '1551' then xg_value else 0.0 end) as xgf_5v5,

        -- Power play stats (team has more skaters)
        sum(
            case
                when team_id = home_team_id
                     and cast(substr(situation_code, 3, 2) as int64) > cast(substr(situation_code, 1, 2) as int64)
                     then 1
                when team_id = away_team_id
                     and cast(substr(situation_code, 1, 2) as int64) > cast(substr(situation_code, 3, 2) as int64)
                     then 1
                else 0
            end
        ) as shot_attempts_pp,
        sum(
            case
                when team_id = home_team_id
                     and cast(substr(situation_code, 3, 2) as int64) > cast(substr(situation_code, 1, 2) as int64)
                     and is_goal then 1
                when team_id = away_team_id
                     and cast(substr(situation_code, 1, 2) as int64) > cast(substr(situation_code, 3, 2) as int64)
                     and is_goal then 1
                else 0
            end
        ) as goals_pp,
        sum(
            case
                when team_id = home_team_id
                     and cast(substr(situation_code, 3, 2) as int64) > cast(substr(situation_code, 1, 2) as int64)
                     then xg_value
                when team_id = away_team_id
                     and cast(substr(situation_code, 1, 2) as int64) > cast(substr(situation_code, 3, 2) as int64)
                     then xg_value
                else 0.0
            end
        ) as xgf_pp,

        -- Penalty kill stats (team has fewer skaters)
        sum(
            case
                when team_id = home_team_id
                     and cast(substr(situation_code, 3, 2) as int64) < cast(substr(situation_code, 1, 2) as int64)
                     then 1
                when team_id = away_team_id
                     and cast(substr(situation_code, 1, 2) as int64) < cast(substr(situation_code, 3, 2) as int64)
                     then 1
                else 0
            end
        ) as shot_attempts_pk,
        sum(
            case
                when team_id = home_team_id
                     and cast(substr(situation_code, 3, 2) as int64) < cast(substr(situation_code, 1, 2) as int64)
                     and is_goal then 1
                when team_id = away_team_id
                     and cast(substr(situation_code, 1, 2) as int64) < cast(substr(situation_code, 3, 2) as int64)
                     and is_goal then 1
                else 0
            end
        ) as goals_pk,
        sum(
            case
                when team_id = home_team_id
                     and cast(substr(situation_code, 3, 2) as int64) < cast(substr(situation_code, 1, 2) as int64)
                     then xg_value
                when team_id = away_team_id
                     and cast(substr(situation_code, 1, 2) as int64) < cast(substr(situation_code, 3, 2) as int64)
                     then xg_value
                else 0.0
            end
        ) as xgf_pk,

        -- 4v4, 3v3 (even strength but not 5v5)
        sum(case when situation_code in ('1441', '1331') then 1 else 0 end) as shot_attempts_other_es,
        sum(case when situation_code in ('1441', '1331') and is_goal then 1 else 0 end) as goals_other_es,
        sum(case when situation_code in ('1441', '1331') then xg_value else 0.0 end) as xgf_other_es

    from shot_attempts
    group by game_id, season, team_id
),

home_teams as (
    select
        g.game_id,
        g.game_date,
        g.season,
        g.home_team_id as team_id,

        coalesce(ss.shot_attempts_5v5, 0) as shot_attempts_5v5,
        coalesce(ss.goals_5v5, 0) as goals_5v5,
        coalesce(ss.xgf_5v5, 0.0) as xgf_5v5,

        coalesce(ss.shot_attempts_pp, 0) as shot_attempts_pp,
        coalesce(ss.goals_pp, 0) as goals_pp,
        coalesce(ss.xgf_pp, 0.0) as xgf_pp,

        coalesce(ss.shot_attempts_pk, 0) as shot_attempts_pk,
        coalesce(ss.goals_pk, 0) as goals_pk,
        coalesce(ss.xgf_pk, 0.0) as xgf_pk,

        coalesce(ss.shot_attempts_other_es, 0) as shot_attempts_other_es,
        coalesce(ss.goals_other_es, 0) as goals_other_es,
        coalesce(ss.xgf_other_es, 0.0) as xgf_other_es

    from games g
    left join situational_stats ss
        on g.game_id = ss.game_id
        and g.home_team_id = ss.team_id
),

away_teams as (
    select
        g.game_id,
        g.game_date,
        g.season,
        g.away_team_id as team_id,

        coalesce(ss.shot_attempts_5v5, 0) as shot_attempts_5v5,
        coalesce(ss.goals_5v5, 0) as goals_5v5,
        coalesce(ss.xgf_5v5, 0.0) as xgf_5v5,

        coalesce(ss.shot_attempts_pp, 0) as shot_attempts_pp,
        coalesce(ss.goals_pp, 0) as goals_pp,
        coalesce(ss.xgf_pp, 0.0) as xgf_pp,

        coalesce(ss.shot_attempts_pk, 0) as shot_attempts_pk,
        coalesce(ss.goals_pk, 0) as goals_pk,
        coalesce(ss.xgf_pk, 0.0) as xgf_pk,

        coalesce(ss.shot_attempts_other_es, 0) as shot_attempts_other_es,
        coalesce(ss.goals_other_es, 0) as goals_other_es,
        coalesce(ss.xgf_other_es, 0.0) as xgf_other_es

    from games g
    left join situational_stats ss
        on g.game_id = ss.game_id
        and g.away_team_id = ss.team_id
),

final as (
    select * from home_teams
    union all
    select * from away_teams
)

select * from final
