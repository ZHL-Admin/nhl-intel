{{ config(
    materialized='table',
    partition_by={"field": "game_date", "data_type": "date", "granularity": "day"},
    cluster_by=["season", "team_id"]
) }}

-- Sequence mining (blueprint 3.2): classify every UNBLOCKED shot attempt by how it
-- was generated, stored one row per shot so every downstream feature can group by it.
--
-- ORIENTATION RULE (verified empirically against goals, 2026-06-15):
--   zone_code is relative to the EVENT OWNER team. For shot events it is 'O' ~98% of
--   the time (avg |x| ~62-70 ft); 'N' events sit near centre (|x| ~12); 'D' shots are
--   the team's own end. To express a prior event's zone relative to the SHOOTING team
--   we keep 'O'/'D'/'N' when the prior event is owned by the shooter, and flip O<->D
--   when it is owned by the opponent (neutral is symmetric).
--
-- situation_code is [awayGoalie][awaySkaters][homeSkaters][homeGoalie], left-zero-padded
-- to 4 chars (e.g. '651' -> '0651' = away goalie pulled). Strength + empty-net are
-- derived from it relative to the shooting team (home/away from stg_boxscores).
--
-- Thresholds come from dbt vars (tuned in models_ml/tune_sequence_thresholds.py); SQL
-- never hardcodes them. See docs/methodology/sequence-mining.md.

{% set rebound_w = var('rebound_window_seconds') %}
{% set rush_w = var('rush_window_seconds') %}
{% set forecheck_w = var('forecheck_window_seconds') %}
{% set cross_ice_w = var('cross_ice_window_seconds') %}
{% set cycle_w = 10 %}      {# continuous OZ-presence lookback for the cycle label #}
{% set flag_lookback = 12 %}  {# max of all flag windows + cushion for the band join #}
{% set timing_lookback = 60 %} {# wider window for time_since_faceoff / time_since_turnover #}

with pbp as (
    select
        game_id,
        season,
        game_date,
        event_id,
        sort_order,
        period_number,
        type_desc_key,
        situation_code,
        event_owner_team_id,
        zone_code,
        x_coord,
        y_coord,
        shooting_player_id,
        scoring_player_id,
        goalie_in_net_id,
        (period_number - 1) * 1200
            + cast(split(time_in_period, ':')[offset(0)] as int64) * 60
            + cast(split(time_in_period, ':')[offset(1)] as int64) as elapsed_seconds
    from {{ ref('stg_play_by_play') }}
    where time_in_period is not null
),

boxscores as (
    select game_id, home_team_id, away_team_id
    from {{ ref('stg_boxscores') }}
),

-- ICE-DERIVED strength + goalie presence per shot (findings F3/D5): the shot's
-- segment strength state from the rebuilt backbone, replacing the situationCode
-- reads below. int_on_ice_events attributes each event to its stint.
ice_state as (
    select e.game_id, e.event_id, c.home_skaters, c.away_skaters,
           c.home_goalies, c.away_goalies
    from {{ ref('int_on_ice_events') }} e
    join {{ ref('int_segment_context') }} c
      on e.game_id = c.game_id and e.segment_index = c.segment_index
),

shots as (
    select
        p.game_id,
        p.season,
        p.game_date,
        p.event_id,
        p.sort_order,
        p.period_number,
        p.elapsed_seconds,
        p.event_owner_team_id as team_id,
        coalesce(p.shooting_player_id, p.scoring_player_id) as shooter_id,
        p.type_desc_key,
        p.x_coord,
        p.y_coord,
        p.zone_code,
        p.situation_code,
        p.goalie_in_net_id,
        (p.type_desc_key = 'goal') as is_goal,
        (p.event_owner_team_id = b.home_team_id) as shooter_is_home,
        -- ICE-derived on-ice counts (fall back to situationCode digits if the shot
        -- didn't attribute to a segment, e.g. the 3 pbp-only games or edge cases)
        coalesce(ice.home_skaters, cast(substr(lpad(coalesce(p.situation_code,''),4,'0'), 3, 1) as int64)) as home_sk,
        coalesce(ice.away_skaters, cast(substr(lpad(coalesce(p.situation_code,''),4,'0'), 2, 1) as int64)) as away_sk,
        coalesce(ice.home_goalies, if(substr(lpad(coalesce(p.situation_code,''),4,'0'),4,1)='0',0,1)) as home_g,
        coalesce(ice.away_goalies, if(substr(lpad(coalesce(p.situation_code,''),4,'0'),1,1)='0',0,1)) as away_g
    from pbp p
    join boxscores b on p.game_id = b.game_id
    left join ice_state ice on ice.game_id = p.game_id and ice.event_id = p.event_id
    where p.type_desc_key in ('shot-on-goal', 'missed-shot', 'goal')
      and p.x_coord is not null
      and p.y_coord is not null
),

shots_strength as (
    select * from shots
),

shots_typed as (
    select
        game_id, season, game_date, event_id, sort_order, period_number,
        elapsed_seconds, team_id, shooter_id, type_desc_key, x_coord, y_coord,
        zone_code, situation_code, is_goal,
        -- strength relative to the shooting team, from the ICE (findings F3): shift-
        -- derived on-ice skater counts, not situationCode (whose ~4% timing lag the
        -- Atlas quantified). 5v5 requires both goalies on the ice.
        case
            when home_sk is null or away_sk is null then 'other'
            when home_sk = 5 and away_sk = 5 and home_g > 0 and away_g > 0 then '5v5'
            when shooter_is_home and home_sk > away_sk then 'PP'
            when shooter_is_home and home_sk < away_sk then 'SH'
            when (not shooter_is_home) and away_sk > home_sk then 'PP'
            when (not shooter_is_home) and away_sk < home_sk then 'SH'
            else 'other'   -- even strength but not 5v5 (4v4, 3v3), or odd artifacts
        end as strength,
        -- empty net = ICE TRUTH (finding D5): the goalie actually facing the shot
        -- (goalie_in_net_id) is absent. Replaces the situationCode-digit test, which
        -- scored ~1867 empty-net attempts because it lagged goalie pulls.
        (goalie_in_net_id is null) as is_empty_net,
        -- a point shot is a property of the shot itself
        (abs(x_coord) <= 40 and zone_code = 'O') as seq_point_shot
    from shots_strength
),

-- All prior events within the flag lookback window, with zone re-expressed relative to
-- the shooting team. e_sort < s.sort_order guarantees the event strictly precedes.
prior_flags_raw as (
    select
        s.game_id,
        s.event_id,
        s.y_coord as s_y,
        s.elapsed_seconds - e.elapsed_seconds as dt,
        e.sort_order as e_sort,
        e.type_desc_key as e_type,
        e.y_coord as e_y,
        (e.event_owner_team_id = s.team_id) as e_same_team,
        case
            when e.event_owner_team_id = s.team_id then e.zone_code
            when e.zone_code = 'O' then 'D'
            when e.zone_code = 'D' then 'O'
            else 'N'
        end as e_zone_rel
    from shots_typed s
    join pbp e
        on e.game_id = s.game_id
       and e.sort_order < s.sort_order
       and s.elapsed_seconds - e.elapsed_seconds between 0 and {{ flag_lookback }}
),

prior_flags as (
    select
        *,
        -- most-recent faceoff (highest sort) within the flag window, for the
        -- "no intervening faceoff" rush rule
        max(if(e_type = 'faceoff', e_sort, null))
            over (partition by game_id, event_id) as fo_sort_in_window
    from prior_flags_raw
),

flag_agg as (
    select
        game_id,
        event_id,
        -- same-team unblocked attempt within the rebound window
        logical_or(
            e_type in ('shot-on-goal', 'missed-shot', 'goal')
            and e_same_team
            and dt <= {{ rebound_w }}
        ) as seq_rebound,
        -- any event in the shooting team's def/neutral zone within the rush window,
        -- occurring after every faceoff in the window (no intervening faceoff)
        logical_or(
            e_zone_rel in ('D', 'N')
            and dt <= {{ rush_w }}
            and (fo_sort_in_window is null or e_sort > fo_sort_in_window)
        ) as seq_rush,
        -- puck recovered by the shooting team in its offensive zone: own takeaway or
        -- opponent giveaway, within the forecheck window
        logical_or(
            e_zone_rel = 'O'
            and dt <= {{ forecheck_w }}
            and (
                (e_type = 'takeaway' and e_same_team)
                or (e_type = 'giveaway' and not e_same_team)
            )
        ) as seq_forecheck,
        -- same-team event on the opposite y-half (royal-road proxy) within the window
        logical_or(
            e_same_team
            and dt <= {{ cross_ice_w }}
            and sign(e_y) != sign(s_y)
            and abs(e_y) >= 10
            and abs(s_y) >= 10
        ) as seq_cross_ice,
        -- cycle eligibility: sustained OZ presence = no def/neutral event by either team
        -- in the cycle window, and at least one OZ event present
        countif(e_zone_rel in ('D', 'N') and dt <= {{ cycle_w }}) as dn_events_cycle,
        countif(e_zone_rel = 'O' and dt <= {{ cycle_w }}) as oz_events_cycle
    from prior_flags
    group by game_id, event_id
),

-- Wider window purely for the timing features (nearest faceoff / turnover), capped 60s.
timing_agg as (
    select
        s.game_id,
        s.event_id,
        min(if(e.type_desc_key = 'faceoff', s.elapsed_seconds - e.elapsed_seconds, null)) as time_since_faceoff,
        min(if(e.type_desc_key in ('takeaway', 'giveaway'), s.elapsed_seconds - e.elapsed_seconds, null)) as time_since_turnover
    from shots_typed s
    join pbp e
        on e.game_id = s.game_id
       and e.sort_order < s.sort_order
       and s.elapsed_seconds - e.elapsed_seconds between 0 and {{ timing_lookback }}
       and e.type_desc_key in ('faceoff', 'takeaway', 'giveaway')
    group by s.game_id, s.event_id
),

assembled as (
    select
        s.game_id,
        s.season,
        s.game_date,
        s.event_id,
        s.team_id,
        s.shooter_id,
        s.sort_order,
        s.period_number,
        s.elapsed_seconds,
        s.strength,
        s.x_coord,
        s.y_coord,
        s.zone_code,
        s.type_desc_key,
        s.is_goal,
        s.is_empty_net,
        coalesce(f.seq_rebound, false) as seq_rebound,
        coalesce(f.seq_rush, false) as seq_rush,
        coalesce(f.seq_forecheck, false) as seq_forecheck,
        coalesce(f.seq_cross_ice, false) as seq_cross_ice,
        s.seq_point_shot,
        (coalesce(f.dn_events_cycle, 0) = 0 and coalesce(f.oz_events_cycle, 0) >= 1) as seq_cycle,
        least(coalesce(t.time_since_faceoff, 60), 60) as time_since_faceoff,
        least(coalesce(t.time_since_turnover, 60), 60) as time_since_turnover,
        -- raw nulls preserved as a separate signal would be lossy; cap-at-60 with null
        -- collapse is intentional (see methodology). Keep explicit null when none in 60s.
        t.time_since_faceoff as _tsf_raw,
        t.time_since_turnover as _tst_raw
    from shots_typed s
    left join flag_agg f using (game_id, event_id)
    left join timing_agg t using (game_id, event_id)
),

final as (
    select
        game_id,
        season,
        game_date,
        event_id,
        team_id,
        shooter_id,
        sort_order,
        period_number,
        elapsed_seconds,
        strength,
        x_coord,
        y_coord,
        zone_code,
        type_desc_key,
        is_goal,
        is_empty_net,
        seq_rebound,
        seq_rush,
        seq_forecheck,
        seq_cross_ice,
        seq_point_shot,
        seq_cycle,
        -- single precedence label: rebound > rush > forecheck > cycle > point_shot > other
        case
            when seq_rebound then 'rebound'
            when seq_rush then 'rush'
            when seq_forecheck then 'forecheck'
            when seq_cycle then 'cycle'
            when seq_point_shot then 'point_shot'
            else 'other'
        end as seq_type,
        case when _tsf_raw is null then null else time_since_faceoff end as time_since_faceoff,
        case when _tst_raw is null then null else time_since_turnover end as time_since_turnover
    from assembled
)

select * from final
