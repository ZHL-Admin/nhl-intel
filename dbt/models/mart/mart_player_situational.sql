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

-- All shot attempts across EVERY strength state (not the 5v5-only int_shot_attempts), so PP/PK
-- columns populate. A GOAL event carries scoring_player_id (not shooting_player_id), so attribute
-- the shooter via COALESCE — otherwise every goal is dropped and the goals_* columns read 0.
-- PP/PK are decided by the player's team's skater count vs the opponent's, parsed from
-- situation_code = [awayGoalie][awaySkaters][homeSkaters][homeGoalie] (the canonical parsing also
-- used by the goaltending/special-teams services): away skaters = char 2, home skaters = char 3.
shot_attempts as (
    select
        pbp.game_id,
        pbp.season,
        coalesce(pbp.shooting_player_id, pbp.scoring_player_id) as player_id,
        pbp.event_owner_team_id as team_id,
        pbp.situation_code,
        pbp.is_goal,
        pbp.xg_value,
        (
            (pbp.event_owner_team_id = g.home_team_id
                and safe_cast(substr(pbp.situation_code, 3, 1) as int64) > safe_cast(substr(pbp.situation_code, 2, 1) as int64))
            or (pbp.event_owner_team_id = g.away_team_id
                and safe_cast(substr(pbp.situation_code, 2, 1) as int64) > safe_cast(substr(pbp.situation_code, 3, 1) as int64))
        ) as is_pp,
        (
            (pbp.event_owner_team_id = g.home_team_id
                and safe_cast(substr(pbp.situation_code, 3, 1) as int64) < safe_cast(substr(pbp.situation_code, 2, 1) as int64))
            or (pbp.event_owner_team_id = g.away_team_id
                and safe_cast(substr(pbp.situation_code, 2, 1) as int64) < safe_cast(substr(pbp.situation_code, 3, 1) as int64))
        ) as is_pk
    from {{ ref('int_shot_attempts_all') }} pbp
    inner join games g on pbp.game_id = g.game_id
    where coalesce(pbp.shooting_player_id, pbp.scoring_player_id) is not null
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
        sum(case when is_pp then 1 else 0 end) as shots_pp,
        sum(case when is_pp and is_goal then 1 else 0 end) as goals_pp,
        sum(case when is_pp then xg_value else 0.0 end) as ixg_pp,

        -- Penalty kill stats (team has fewer skaters)
        sum(case when is_pk then 1 else 0 end) as shots_pk,
        sum(case when is_pk and is_goal then 1 else 0 end) as goals_pk,
        sum(case when is_pk then xg_value else 0.0 end) as ixg_pk,

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
