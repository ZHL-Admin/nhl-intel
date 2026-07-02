{{ config(materialized='table') }}

-- Per-5v5-segment shot results from the home and away perspective: for/against expected
-- goals (from nhl_models.shot_xg via int_on_ice_events, the same pull as
-- models_ml/train_rapm.py), Corsi attempt counts, and goals. This is the shared
-- even-strength segment fact behind int_player_onice_game, mart_player_toi_matrix, and
-- mart_player_wowy, so every player on-ice number reconciles with mart_team_game_stats
-- (event_owner_team_id is the attacking team for all four attempt types).

with seg as (
    select
        game_id,
        season,
        segment_index,
        segment_duration,
        home_team_id,
        away_team_id,
        home_score_state,
        zone_start_code
    from {{ ref('int_segment_context') }}
    where strength_state = '5v5'
      and segment_duration > 0
),

-- NHL regular season + playoffs only (matches train_rapm.py); excludes preseason (01) and
-- non-NHL game types so preseason 5v5 does not pollute the xGF% denominators.
nhl_games as (
    select game_id, game_date
    from {{ ref('stg_boxscores') }}
    where substr(cast(game_id as string), 5, 2) in ('02', '03')
),

-- Corsi (all four attempt types) and goals per side, from the on-ice event stream.
corsi as (
    select
        e.game_id,
        e.segment_index,
        countif(e.type_desc_key in ('shot-on-goal', 'goal', 'missed-shot', 'blocked-shot')
                and e.event_owner_team_id = seg.home_team_id) as cf_home,
        countif(e.type_desc_key in ('shot-on-goal', 'goal', 'missed-shot', 'blocked-shot')
                and e.event_owner_team_id = seg.away_team_id) as cf_away,
        countif(e.type_desc_key = 'goal' and e.event_owner_team_id = seg.home_team_id) as gf_home,
        countif(e.type_desc_key = 'goal' and e.event_owner_team_id = seg.away_team_id) as gf_away
    from {{ ref('int_on_ice_events') }} e
    join seg on e.game_id = seg.game_id and e.segment_index = seg.segment_index
    group by 1, 2
),

-- Expected goals per side, joining shot_xg per shot (unblocked, non-empty-net only).
expected as (
    select
        e.game_id,
        e.segment_index,
        sum(if(e.event_owner_team_id = seg.home_team_id, x.xg, 0.0)) as xgf_home,
        sum(if(e.event_owner_team_id = seg.away_team_id, x.xg, 0.0)) as xgf_away
    from {{ ref('int_on_ice_events') }} e
    join seg on e.game_id = seg.game_id and e.segment_index = seg.segment_index
    join {{ source('nhl_models', 'shot_xg') }} x
        on e.game_id = x.game_id and e.event_id = x.event_id
    where x.xg is not null
    group by 1, 2
),

final as (
    select
        seg.game_id,
        seg.season,
        g.game_date,
        seg.segment_index,
        seg.segment_duration,
        seg.home_team_id,
        seg.away_team_id,
        seg.home_score_state,
        seg.zone_start_code,
        coalesce(x.xgf_home, 0.0) as xgf_home,
        coalesce(x.xgf_away, 0.0) as xgf_away,
        coalesce(c.cf_home, 0) as cf_home,
        coalesce(c.cf_away, 0) as cf_away,
        coalesce(c.gf_home, 0) as gf_home,
        coalesce(c.gf_away, 0) as gf_away
    from seg
    join nhl_games g on g.game_id = seg.game_id
    left join corsi c on c.game_id = seg.game_id and c.segment_index = seg.segment_index
    left join expected x on x.game_id = seg.game_id and x.segment_index = seg.segment_index
)

select * from final
