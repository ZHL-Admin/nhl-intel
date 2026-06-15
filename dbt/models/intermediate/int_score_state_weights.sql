{{ config(materialized='table') }}

-- Score-state adjustment weights (blueprint 3.5). Trailing teams shoot more, so raw
-- 5v5 shot shares are biased by game script. We compute the league-average 5v5 shot
-- attempt RATE (attempts per minute) by score state per season, then weight each event
-- by tied_rate / state_rate so a score-adjusted share neutralises the score effect.
--
-- Score state is from the shooting/skating team's perspective:
--   down2plus (≤ -2), down1, tied (0), up1, up2plus (≥ +2).
-- Time-in-state comes from 5v5 segment durations (int_segment_context); attempts come
-- from unblocked 5v5 shots with the score read just before the event.

{% set bucket %}
case when {d} <= -2 then 'down2plus'
     when {d} = -1 then 'down1'
     when {d} = 0 then 'tied'
     when {d} = 1 then 'up1'
     else 'up2plus' end
{% endset %}

with seg_time as (
    -- each 5v5 segment contributes its duration to the home team's state and (mirrored)
    -- to the away team's state
    select season, state, sum(minutes) as minutes
    from (
        select season, segment_duration / 60.0 as minutes,
               {{ bucket | replace('{d}', '(home_score - away_score)') }} as state
        from {{ ref('int_segment_context') }}
        where strength_state = '5v5'
        union all
        select season, segment_duration / 60.0 as minutes,
               {{ bucket | replace('{d}', '(away_score - home_score)') }} as state
        from {{ ref('int_segment_context') }}
        where strength_state = '5v5'
    )
    group by season, state
),

running as (
    select game_id, sort_order,
        coalesce(last_value(home_score ignore nulls) over w, 0) as home_pre,
        coalesce(last_value(away_score ignore nulls) over w, 0) as away_pre
    from {{ ref('stg_play_by_play') }}
    window w as (partition by game_id order by sort_order rows between unbounded preceding and 1 preceding)
),

attempts as (
    select season, state, count(*) as attempts
    from (
        select p.season,
            {{ bucket | replace('{d}',
               '(case when p.event_owner_team_id = b.home_team_id then r.home_pre - r.away_pre else r.away_pre - r.home_pre end)') }} as state
        from {{ ref('stg_play_by_play') }} p
        join {{ ref('stg_boxscores') }} b on p.game_id = b.game_id
        join running r on p.game_id = r.game_id and p.sort_order = r.sort_order
        where p.situation_code = '1551'
          and p.type_desc_key in ('shot-on-goal', 'missed-shot', 'goal')
          and p.x_coord is not null
    )
    group by season, state
),

rates as (
    select
        a.season,
        a.state,
        safe_divide(a.attempts, t.minutes) as rate,
        a.attempts,
        t.minutes
    from attempts a
    join seg_time t on a.season = t.season and a.state = t.state
),

tied as (
    select season, rate as tied_rate from rates where state = 'tied'
)

select
    r.season,
    r.state,
    r.rate,
    r.attempts,
    r.minutes,
    safe_divide(t.tied_rate, r.rate) as weight
from rates r
join tied t on r.season = t.season
