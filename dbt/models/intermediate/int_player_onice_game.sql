{{ config(materialized='table') }}

-- Per (game_id, player_id) even-strength (5v5) on-ice / off-ice results, oriented to the
-- player's team. On-ice = the 5v5 segments the player is on; off-ice = the player's team's
-- OTHER 5v5 segments in that game (the team is on the ice for every 5v5 segment, so its
-- game total minus the player's on-ice sum is the player's off-ice). rel_* = on minus off.
-- Raw sums are exposed so the season roll-up (mart_player_onice) and WOWY re-aggregate
-- without leakage. Skaters only (goalies carry no on-ice possession here).

with seg_results as (
    select * from {{ ref('int_segment_5v5_results') }}
),

-- skaters on ice per 5v5 segment
membership as (
    select s.game_id, s.segment_index, s.player_id, s.team_id
    from {{ ref('int_shift_segments') }} s
    join seg_results r on r.game_id = s.game_id and r.segment_index = s.segment_index
    where s.is_goalie = 0
),

-- on-ice sums per (game, player), for/against oriented to the player's team
on_ice as (
    select
        m.game_id,
        r.game_date,
        r.season,
        m.player_id,
        m.team_id,
        sum(r.segment_duration) as toi_5v5_sec,
        sum(if(m.team_id = r.home_team_id, r.xgf_home, r.xgf_away)) as on_xgf,
        sum(if(m.team_id = r.home_team_id, r.xgf_away, r.xgf_home)) as on_xga,
        sum(if(m.team_id = r.home_team_id, r.cf_home, r.cf_away)) as on_cf,
        sum(if(m.team_id = r.home_team_id, r.cf_away, r.cf_home)) as on_ca
    from membership m
    join seg_results r on r.game_id = m.game_id and r.segment_index = m.segment_index
    group by 1, 2, 3, 4, 5
),

-- team totals over all 5v5 segments of the game, per team
team_totals as (
    select
        game_id,
        home_team_id as team_id,
        sum(segment_duration) as team_toi_5v5_sec,
        sum(xgf_home) as team_xgf,
        sum(xgf_away) as team_xga,
        sum(cf_home) as team_cf,
        sum(cf_away) as team_ca
    from seg_results
    group by 1, 2
    union all
    select
        game_id,
        away_team_id as team_id,
        sum(segment_duration),
        sum(xgf_away),
        sum(xgf_home),
        sum(cf_away),
        sum(cf_home)
    from seg_results
    group by 1, 2
),

combined as (
    select
        o.game_id,
        o.game_date,
        o.season,
        o.player_id,
        o.team_id,
        o.toi_5v5_sec,
        t.team_toi_5v5_sec - o.toi_5v5_sec as off_toi_5v5_sec,
        o.on_xgf,
        o.on_xga,
        o.on_cf,
        o.on_ca,
        t.team_xgf - o.on_xgf as off_xgf,
        t.team_xga - o.on_xga as off_xga,
        t.team_cf - o.on_cf as off_cf,
        t.team_ca - o.on_ca as off_ca
    from on_ice o
    join team_totals t on t.game_id = o.game_id and t.team_id = o.team_id
)

select
    game_id,
    game_date,
    season,
    player_id,
    team_id,
    toi_5v5_sec,
    off_toi_5v5_sec,
    on_xgf,
    on_xga,
    on_cf,
    on_ca,
    off_xgf,
    off_xga,
    off_cf,
    off_ca,
    safe_divide(on_xgf, on_xgf + on_xga) as on_ice_xgf_pct,
    safe_divide(off_xgf, off_xgf + off_xga) as off_ice_xgf_pct,
    safe_divide(on_cf, on_cf + on_ca) as on_ice_cf_pct,
    safe_divide(off_cf, off_cf + off_ca) as off_ice_cf_pct,
    safe_divide(on_xgf, on_xgf + on_xga) - safe_divide(off_xgf, off_xgf + off_xga) as rel_xgf_pct,
    safe_divide(on_cf, on_cf + on_ca) - safe_divide(off_cf, off_cf + off_ca) as rel_cf_pct
from combined
