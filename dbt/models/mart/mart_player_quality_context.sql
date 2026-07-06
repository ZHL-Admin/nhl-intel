{{ config(materialized='table') }}

-- Quality of Competition / Teammates (spec 7.2). For each (season, player, team), the TOI-weighted
-- mean PRIOR-SEASON WAR rate of the skaters he FACED (QoC) and PLAYED WITH (QoT) at 5v5, plus the
-- within-position percentiles. Leak-free by construction: quality comes from player_prior_quality,
-- each skater's rate as of the PREVIOUS season, so this season's results never feed the metric.
-- Method mirrors the WOWY marts (segment co-occurrence): within a 5v5 segment, every other skater is
-- a teammate (same team_id) or an opponent (different team_id), weighted by segment_duration.

with seg as (
    select
        s.game_id, s.segment_index, s.season, s.player_id, s.team_id, s.position_code,
        s.segment_duration as dur
    from {{ ref('int_shift_segments') }} s
    join {{ ref('int_segment_context') }} c
        on s.game_id = c.game_id and s.segment_index = c.segment_index
    where c.strength_state = '5v5'
      and c.home_skaters = 5 and c.away_skaters = 5
      and s.is_goalie = 0
      and s.segment_duration > 0
),

-- focal player's actual 5v5 TOI (weight basis) + position group, per (season, player, team)
focal as (
    select
        season, player_id, team_id,
        sum(dur) as toi_5v5_sec,
        if(countif(position_code = 'D') >= countif(position_code <> 'D'), 'D', 'F') as pos_group
    from seg
    group by 1, 2, 3
),

-- within-segment focal x other-skater pairs (self excluded); teammate = same team_id
pairs as (
    select
        f.season, f.player_id, f.team_id, f.dur,
        (f.team_id = o.team_id) as is_teammate,
        o.player_id as other_id
    from seg f
    join seg o
        on f.game_id = o.game_id and f.segment_index = o.segment_index
       and f.player_id <> o.player_id
),

scored as (
    select
        p.season, p.player_id, p.team_id, p.dur, p.is_teammate,
        coalesce(pq.prior_war_rate, 0.0) as qual      -- rookies / no prior -> replacement (0)
    from pairs p
    left join {{ source('nhl_models', 'player_prior_quality') }} pq
        on pq.player_id = p.other_id and pq.season = p.season
),

agg as (
    select
        season, player_id, team_id,
        safe_divide(sum(if(not is_teammate, dur * qual, 0)), sum(if(not is_teammate, dur, 0))) as qoc_war_rate,
        safe_divide(sum(if(is_teammate,     dur * qual, 0)), sum(if(is_teammate,     dur, 0))) as qot_war_rate
    from scored
    group by 1, 2, 3
),

joined as (
    select
        f.season, f.player_id, f.team_id, f.pos_group, f.toi_5v5_sec,
        a.qoc_war_rate, a.qot_war_rate
    from focal f
    join agg a on a.season = f.season and a.player_id = f.player_id and a.team_id = f.team_id
    where f.toi_5v5_sec > 0
)

-- Percentiles are computed ONLY within the qualified pool (5v5 TOI >= the ranking floor of
-- MIN_TOI_5V5_FOR_RANKING = 200 min = 12000 sec), per position group + season, so a low-TOI player
-- cannot occupy an extreme percentile on noise. Below-floor players keep raw qoc/qot rates but carry
-- NULL percentiles; /context passes the nulls through and the UI mutes them.
select
    season, player_id, team_id, pos_group, toi_5v5_sec,
    qoc_war_rate, qot_war_rate,
    if(toi_5v5_sec >= 12000,
       percent_rank() over (partition by season, pos_group, (toi_5v5_sec >= 12000) order by qoc_war_rate),
       null) as qoc_pctile,
    if(toi_5v5_sec >= 12000,
       percent_rank() over (partition by season, pos_group, (toi_5v5_sec >= 12000) order by qot_war_rate),
       null) as qot_pctile
from joined
