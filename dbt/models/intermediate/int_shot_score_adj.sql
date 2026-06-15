{{ config(materialized='table') }}

-- Per (game, team) score-state-weighted 5v5 shot aggregates (blueprint 3.5), the inputs
-- to cf_pct_score_adj / xgf_pct_score_adj on mart_team_game_stats. Each 5v5 Corsi event
-- is weighted by int_score_state_weights.weight for the shooting team's score state read
-- just before the event; xG events are weighted the same way (weight * xg).

with running as (
    select game_id, sort_order,
        coalesce(last_value(home_score ignore nulls) over w, 0) as home_pre,
        coalesce(last_value(away_score ignore nulls) over w, 0) as away_pre
    from {{ ref('stg_play_by_play') }}
    window w as (partition by game_id order by sort_order rows between unbounded preceding and 1 preceding)
),

corsi as (
    select
        p.game_id,
        p.season,
        p.event_owner_team_id as team_id,
        case
            when (case when p.event_owner_team_id = b.home_team_id
                       then r.home_pre - r.away_pre else r.away_pre - r.home_pre end) <= -2 then 'down2plus'
            when (case when p.event_owner_team_id = b.home_team_id
                       then r.home_pre - r.away_pre else r.away_pre - r.home_pre end) = -1 then 'down1'
            when (case when p.event_owner_team_id = b.home_team_id
                       then r.home_pre - r.away_pre else r.away_pre - r.home_pre end) = 0 then 'tied'
            when (case when p.event_owner_team_id = b.home_team_id
                       then r.home_pre - r.away_pre else r.away_pre - r.home_pre end) = 1 then 'up1'
            else 'up2plus'
        end as state,
        coalesce(xg.xg, 0.0) as xg
    from {{ ref('stg_play_by_play') }} p
    join {{ ref('stg_boxscores') }} b on p.game_id = b.game_id
    join running r on p.game_id = r.game_id and p.sort_order = r.sort_order
    left join {{ source('nhl_models', 'shot_xg') }} xg
        on p.game_id = xg.game_id and p.event_id = xg.event_id
    where p.situation_code = '1551'
      and p.type_desc_key in ('shot-on-goal', 'missed-shot', 'goal', 'blocked-shot')
      and p.event_owner_team_id is not null
),

weighted as (
    select
        c.game_id,
        c.team_id,
        w.weight,
        c.xg
    from corsi c
    join {{ ref('int_score_state_weights') }} w
        on c.season = w.season and c.state = w.state
)

select
    game_id,
    team_id,
    sum(weight) as weighted_cf,
    sum(weight * xg) as weighted_xgf,
    count(*) as raw_cf,
    sum(xg) as raw_xgf
from weighted
group by game_id, team_id
