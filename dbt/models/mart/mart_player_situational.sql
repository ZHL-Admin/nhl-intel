{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "player_id"]
) }}

-- Player stats split by game situation (5v5, PP, PK, other)
-- Situation codes are 4 digits XYZW where XY=away strength, ZW=home strength

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

games as (
    select
        game_id,
        home_team_id,
        away_team_id
    from {{ ref('stg_boxscores') }}
),

shot_attempts as (
    select
        pbp.game_id,
        pbp.season,
        pbp.shooting_player_id as player_id,
        pbp.event_owner_team_id as team_id,
        pbp.situation_code,
        g.home_team_id,
        g.away_team_id,
        pbp.is_goal,
        pbp.xg_value
    from {{ ref('int_shot_attempts') }} pbp
    inner join games g on pbp.game_id = g.game_id
    where pbp.shooting_player_id is not null
),

situational_shots as (
    select
        game_id,
        season,
        player_id,
        team_id,

        -- 5v5 stats
        sum(case when situation_code = '1551' then 1 else 0 end) as shots_5v5,
        sum(case when situation_code = '1551' and is_goal then 1 else 0 end) as goals_5v5,
        sum(case when situation_code = '1551' then xg_value else 0.0 end) as ixg_5v5,

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
        ) as shots_pp,
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
        ) as ixg_pp,

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
        ) as shots_pk,
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
        ) as ixg_pk,

        -- 4v4, 3v3 (even strength but not 5v5)
        sum(case when situation_code in ('1441', '1331') then 1 else 0 end) as shots_other_es,
        sum(case when situation_code in ('1441', '1331') and is_goal then 1 else 0 end) as goals_other_es,
        sum(case when situation_code in ('1441', '1331') then xg_value else 0.0 end) as ixg_other_es

    from shot_attempts
    group by game_id, season, player_id, team_id
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

        coalesce(ss.shots_5v5, 0) as shots_5v5,
        coalesce(ss.goals_5v5, 0) as goals_5v5,
        coalesce(ss.ixg_5v5, 0.0) as ixg_5v5,

        coalesce(ss.shots_pp, 0) as shots_pp,
        coalesce(ss.goals_pp, 0) as goals_pp,
        coalesce(ss.ixg_pp, 0.0) as ixg_pp,

        coalesce(ss.shots_pk, 0) as shots_pk,
        coalesce(ss.goals_pk, 0) as goals_pk,
        coalesce(ss.ixg_pk, 0.0) as ixg_pk,

        coalesce(ss.shots_other_es, 0) as shots_other_es,
        coalesce(ss.goals_other_es, 0) as goals_other_es,
        coalesce(ss.ixg_other_es, 0.0) as ixg_other_es

    from rosters r
    left join situational_shots ss
        on r.game_id = ss.game_id
        and r.player_id = ss.player_id
)

select * from final
