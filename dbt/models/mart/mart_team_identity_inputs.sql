{{ config(
    partition_by={"field": "game_date", "data_type": "date", "granularity": "day"},
    cluster_by=["season", "team_id"]
) }}

-- Per-game 5v5 shot-attempt mix by seq_type, FOR (the team's own offense) and AGAINST
-- (the opponent's offense), from int_shot_sequence. This is the canonical per-game
-- sequence-share grain: mart_team_game_stats joins it for the game response, and Phase
-- 3.2's mart_team_identity aggregates it into team fingerprints. Unblocked attempts only.

with seq as (
    select
        game_id,
        team_id,
        count(*) as att,
        countif(seq_type = 'rebound') as rebound,
        countif(seq_type = 'rush') as rush,
        countif(seq_type = 'forecheck') as forecheck,
        countif(seq_type = 'cycle') as cycle,
        countif(seq_type = 'point_shot') as point_shot,
        countif(seq_type = 'other') as other_seq,
        countif(seq_cross_ice) as cross_ice
    from {{ ref('int_shot_sequence') }}
    where strength = '5v5'
    group by game_id, team_id
),

games as (
    select game_id, game_date, season, home_team_id, away_team_id
    from {{ ref('stg_boxscores') }}
),

teams as (
    select game_id, game_date, season, home_team_id as team_id, away_team_id as opponent_team_id from games
    union all
    select game_id, game_date, season, away_team_id as team_id, home_team_id as opponent_team_id from games
),

final as (
    select
        t.game_id,
        t.game_date,
        t.season,
        t.team_id,
        t.opponent_team_id,
        coalesce(s.att, 0) as attempts_for,
        coalesce(o.att, 0) as attempts_against,

        -- counts FOR
        coalesce(s.rebound, 0) as rebound_for,
        coalesce(s.rush, 0) as rush_for,
        coalesce(s.forecheck, 0) as forecheck_for,
        coalesce(s.cycle, 0) as cycle_for,
        coalesce(s.point_shot, 0) as point_shot_for,
        coalesce(s.other_seq, 0) as other_for,
        coalesce(s.cross_ice, 0) as cross_ice_for,

        -- counts AGAINST (opponent's offense)
        coalesce(o.rebound, 0) as rebound_against,
        coalesce(o.rush, 0) as rush_against,
        coalesce(o.forecheck, 0) as forecheck_against,
        coalesce(o.cycle, 0) as cycle_against,
        coalesce(o.point_shot, 0) as point_shot_against,
        coalesce(o.other_seq, 0) as other_against,
        coalesce(o.cross_ice, 0) as cross_ice_against,

        -- shares FOR
        safe_divide(s.rebound, s.att) as rebound_share_for,
        safe_divide(s.rush, s.att) as rush_share_for,
        safe_divide(s.forecheck, s.att) as forecheck_share_for,
        safe_divide(s.cycle, s.att) as cycle_share_for,
        safe_divide(s.point_shot, s.att) as point_shot_share_for,
        safe_divide(s.other_seq, s.att) as other_share_for,
        safe_divide(s.cross_ice, s.att) as cross_ice_share_for,

        -- shares AGAINST
        safe_divide(o.rebound, o.att) as rebound_share_against,
        safe_divide(o.rush, o.att) as rush_share_against,
        safe_divide(o.forecheck, o.att) as forecheck_share_against,
        safe_divide(o.cycle, o.att) as cycle_share_against,
        safe_divide(o.point_shot, o.att) as point_shot_share_against,
        safe_divide(o.other_seq, o.att) as other_share_against,
        safe_divide(o.cross_ice, o.att) as cross_ice_share_against
    from teams t
    left join seq s on s.game_id = t.game_id and s.team_id = t.team_id
    left join seq o on o.game_id = t.game_id and o.team_id = t.opponent_team_id
)

select * from final
