{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "team_id"]
) }}

with games_on_date as (
    select distinct
        game_date,
        season,
        game_id
    from {{ ref('mart_team_game_stats') }}
),

team_stats as (
    select
        game_date,
        season,
        game_id,
        team_id,
        team_abbrev,
        home_away,
        goals_for,
        goals_against,
        shot_attempts_for,
        shot_attempts_against,
        cf_pct,
        hdcf_per60,
        hdca_per60,
        zone_entry_success_rate
    from {{ ref('mart_team_game_stats') }}
),

team_rolling as (
    select
        game_date,
        season,
        game_id,
        team_id,
        rolling_cf_pct_5gp,
        rolling_hdcf_per60_5gp,
        rolling_hdca_per60_5gp,
        has_full_5game_sample
    from {{ ref('mart_team_rolling') }}
),

top_players as (
    select
        game_date,
        season,
        game_id,
        player_id,
        team_id,
        first_name,
        last_name,
        position_code,
        ixg_per60,
        primary_points_per60,
        hot_cold_flag,
        row_number() over (partition by game_date, game_id, team_id order by primary_points_per60 desc) as player_rank
    from {{ ref('mart_player_game_stats') }}
    where primary_points_per60 > 0
),

combined as (
    select
        g.game_date,
        g.season,
        g.game_id,
        ts.team_id,
        ts.team_abbrev,
        ts.home_away,
        ts.goals_for,
        ts.goals_against,
        ts.shot_attempts_for,
        ts.shot_attempts_against,
        ts.cf_pct,
        ts.hdcf_per60,
        ts.hdca_per60,
        ts.zone_entry_success_rate,
        tr.rolling_cf_pct_5gp,
        tr.rolling_hdcf_per60_5gp,
        tr.rolling_hdca_per60_5gp,
        tr.has_full_5game_sample,
        tp.player_id as top_player_id,
        concat(tp.first_name, ' ', tp.last_name) as top_player_name,
        tp.position_code as top_player_position,
        tp.primary_points_per60 as top_player_points_per60,
        tp.hot_cold_flag as top_player_hot_cold

    from games_on_date g
    inner join team_stats ts
        on g.game_date = ts.game_date
        and g.season = ts.season
        and g.game_id = ts.game_id
    left join team_rolling tr
        on ts.game_date = tr.game_date
        and ts.season = tr.season
        and ts.game_id = tr.game_id
        and ts.team_id = tr.team_id
    left join top_players tp
        on ts.game_date = tp.game_date
        and ts.season = tp.season
        and ts.game_id = tp.game_id
        and ts.team_id = tp.team_id
        and tp.player_rank = 1
),

final as (
    select * from combined
)

select * from final
