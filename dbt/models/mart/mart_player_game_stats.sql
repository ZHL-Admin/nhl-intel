{{ config(
    partition_by={
      "field": "game_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["season", "player_id"]
) }}

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
),

-- Individual counting stats span ALL situations (incl. power play / empty net) so a
-- player's goals, shots and xG aren't undercounted. Possession context (on-ice xGF%)
-- remains 5v5 via mart_team_game_stats below.
-- Goal events carry the shooter in scoring_player_id (shooting_player_id is null), so
-- attribute every shot attempt to coalesce(shooting_player_id, scoring_player_id),
-- otherwise goals are never credited to the scorer.
player_shots as (
    select
        game_id,
        coalesce(shooting_player_id, scoring_player_id) as player_id,
        count(*) as individual_shot_attempts,
        sum(case when is_goal then 1 else 0 end) as individual_goals,
        sum(case when is_high_danger then 1 else 0 end) as individual_high_danger_attempts,
        sum(xg_value) as ixg
    from {{ ref('int_shot_attempts_all') }}
    where coalesce(shooting_player_id, scoring_player_id) is not null
    group by game_id, coalesce(shooting_player_id, scoring_player_id)
),

player_first_assists as (
    select
        game_id,
        player_id,
        count(*) as first_assists
    from {{ ref('int_assists') }}
    where assist_order = 1
    group by game_id, player_id
),

player_second_assists as (
    select
        game_id,
        player_id,
        count(*) as second_assists
    from {{ ref('int_assists') }}
    where assist_order = 2
    group by game_id, player_id
),

player_penalties as (
    select
        game_id,
        committed_by_player_id as player_id,
        sum(coalesce(duration, 0)) as pim
    from {{ ref('stg_play_by_play') }}
    where type_desc_key = 'penalty'
      and committed_by_player_id is not null
    group by game_id, committed_by_player_id
),

-- Individual unblocked attempts by sequence type (Phase 2.1). int_shot_sequence is
-- unblocked-only, so these sum to <= individual_shot_attempts (which includes blocks).
player_seq as (
    select
        game_id,
        shooter_id as player_id,
        countif(seq_type = 'rebound') as seq_rebound_attempts,
        countif(seq_type = 'rush') as seq_rush_attempts,
        countif(seq_type = 'forecheck') as seq_forecheck_attempts,
        countif(seq_type = 'cycle') as seq_cycle_attempts,
        countif(seq_type = 'point_shot') as seq_point_shot_attempts,
        countif(seq_type = 'other') as seq_other_attempts,
        countif(seq_cross_ice) as seq_cross_ice_attempts
    from {{ ref('int_shot_sequence') }}
    where shooter_id is not null
    group by game_id, shooter_id
),

team_xg as (
    select
        game_id,
        team_id,
        xgf_pct
    from {{ ref('mart_team_game_stats') }}
),

player_stats_combined as (
    select
        r.game_id,
        r.game_date,
        r.season,
        r.player_id,
        r.team_id,
        r.first_name,
        r.last_name,
        r.position_code,
        coalesce(ps.individual_shot_attempts, 0) as individual_shot_attempts,
        coalesce(ps.individual_goals, 0) as individual_goals,
        coalesce(ps.individual_high_danger_attempts, 0) as ihdcf,
        coalesce(ps.ixg, 0.0) as ixg,
        coalesce(pfa.first_assists, 0) as first_assists,
        coalesce(psa.second_assists, 0) as second_assists,
        coalesce(pp.pim, 0) as pim,
        -- Real rush attempts now that the sequence layer (Phase 2.1) exists.
        coalesce(pq.seq_rush_attempts, 0) as rush_attempts,
        coalesce(pq.seq_rebound_attempts, 0) as seq_rebound_attempts,
        coalesce(pq.seq_rush_attempts, 0) as seq_rush_attempts,
        coalesce(pq.seq_forecheck_attempts, 0) as seq_forecheck_attempts,
        coalesce(pq.seq_cycle_attempts, 0) as seq_cycle_attempts,
        coalesce(pq.seq_point_shot_attempts, 0) as seq_point_shot_attempts,
        coalesce(pq.seq_other_attempts, 0) as seq_other_attempts,
        coalesce(pq.seq_cross_ice_attempts, 0) as seq_cross_ice_attempts,
        coalesce(tx.xgf_pct, 0.5) as team_xgf_pct,

        15.0 as estimated_toi_5v5_minutes

    from rosters r
    left join player_shots ps
        on r.game_id = ps.game_id
        and r.player_id = ps.player_id
    left join player_seq pq
        on r.game_id = pq.game_id
        and r.player_id = pq.player_id
    left join player_first_assists pfa
        on r.game_id = pfa.game_id
        and r.player_id = pfa.player_id
    left join player_second_assists psa
        on r.game_id = psa.game_id
        and r.player_id = psa.player_id
    left join player_penalties pp
        on r.game_id = pp.game_id
        and r.player_id = pp.player_id
    left join team_xg tx
        on r.game_id = tx.game_id
        and r.team_id = tx.team_id
    where r.position_code in ('C', 'L', 'R', 'D', 'G')
),

metrics_calculated as (
    select
        game_id,
        game_date,
        season,
        player_id,
        team_id,
        first_name,
        last_name,
        position_code,
        individual_shot_attempts,
        individual_goals,
        ihdcf,
        first_assists,
        second_assists,
        pim,
        rush_attempts,
        seq_rebound_attempts,
        seq_rush_attempts,
        seq_forecheck_attempts,
        seq_cycle_attempts,
        seq_point_shot_attempts,
        seq_other_attempts,
        seq_cross_ice_attempts,
        ixg,
        team_xgf_pct,
        estimated_toi_5v5_minutes as toi_5v5,

        case
            when estimated_toi_5v5_minutes > 0
            then (ixg / estimated_toi_5v5_minutes) * 60.0
            else 0.0
        end as ixg_per60,

        ((individual_goals + first_assists) / estimated_toi_5v5_minutes) * 60.0 as primary_points_per60

    from player_stats_combined
),

season_averages as (
    select
        player_id,
        season,
        avg(ixg_per60) as season_avg_ixg_per60
    from metrics_calculated
    group by player_id, season
),

with_flags as (
    select
        m.*,
        sa.season_avg_ixg_per60,
        -- On-ice xGF% proxy: use team xGF% as approximation
        -- Note: True on-ice xGF% requires shift-by-shift tracking not available in this model
        m.team_xgf_pct as on_ice_xgf_pct,
        case
            when sa.season_avg_ixg_per60 > 0.1 and m.ixg_per60 > sa.season_avg_ixg_per60 * 1.15 then 'hot'
            when sa.season_avg_ixg_per60 > 0.1 and m.ixg_per60 < sa.season_avg_ixg_per60 * 0.85 then 'cold'
            else 'neutral'
        end as hot_cold_flag
    from metrics_calculated m
    left join season_averages sa
        on m.player_id = sa.player_id
        and m.season = sa.season
),

final as (
    select
        game_id,
        game_date,
        season,
        player_id,
        team_id,
        first_name,
        last_name,
        position_code,
        toi_5v5,
        individual_shot_attempts,
        individual_goals,
        first_assists,
        second_assists,
        ihdcf,
        rush_attempts,
        seq_rebound_attempts,
        seq_rush_attempts,
        seq_forecheck_attempts,
        seq_cycle_attempts,
        seq_point_shot_attempts,
        seq_other_attempts,
        seq_cross_ice_attempts,
        pim,
        ixg,
        ixg_per60,
        on_ice_xgf_pct,
        primary_points_per60,
        season_avg_ixg_per60,
        hot_cold_flag
    from with_flags
)

select * from final
