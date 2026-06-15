{{ config(materialized='table') }}

-- Scorer-bias (rink) multipliers for hits, giveaways, takeaways (blueprint 3.4).
-- Home-arena scorekeepers record these subjective events at different rates. We measure
-- the bias per arena from VISITING teams only (so a team's own identity is controlled):
-- compare visiting teams' event rates in an arena against THOSE SAME teams' rates in all
-- other arenas, pooled over a rolling 3-season window for stability.
--
-- multiplier = actual_rate_in_arena / expected_rate_in_arena, where the expected rate is
-- each visiting team's elsewhere-rate weighted by how many minutes it played in the arena
-- (team-mix control). Clipped to [0.5, 2.0]. adjusted_stat = raw / multiplier.

with events as (
    select
        game_id,
        season,
        event_owner_team_id as team_id,
        countif(type_desc_key = 'hit') as hits,
        countif(type_desc_key = 'giveaway') as giveaways,
        countif(type_desc_key = 'takeaway') as takeaways
    from {{ ref('stg_play_by_play') }}
    where type_desc_key in ('hit', 'giveaway', 'takeaway')
      and event_owner_team_id is not null
    group by game_id, season, event_owner_team_id
),

game_minutes as (
    select
        game_id,
        max((period_number - 1) * 1200
            + cast(split(time_in_period, ':')[offset(0)] as int64) * 60
            + cast(split(time_in_period, ':')[offset(1)] as int64)) / 60.0 as game_minutes
    from {{ ref('stg_play_by_play') }}
    where time_in_period is not null
    group by game_id
),

game_team as (
    select
        e.season,
        e.game_id,
        e.team_id,
        b.home_team_id as arena_team_id,
        (e.team_id = b.home_team_id) as is_home,
        e.hits, e.giveaways, e.takeaways,
        m.game_minutes
    from events e
    join {{ ref('stg_boxscores') }} b on e.game_id = b.game_id
    join game_minutes m on e.game_id = m.game_id
),

-- visiting team-games only, unpivoted to long form (one row per stat)
away_long as (
    select season, game_id, team_id as visiting_team, arena_team_id, game_minutes,
           cast(substr(season, 1, 4) as int64) as yr, s.stat, s.events
    from game_team gt,
         unnest([
            struct('hits' as stat, gt.hits as events),
            struct('giveaways' as stat, gt.giveaways as events),
            struct('takeaways' as stat, gt.takeaways as events)
         ]) s
    where not gt.is_home
),

season_grid as (
    select distinct season, cast(substr(season, 1, 4) as int64) as yr from away_long
),

-- pool each (target season, arena, visiting team, stat) over the rolling 3-season window
pooled as (
    select
        t.season as target_season,
        a.arena_team_id,
        a.visiting_team,
        a.stat,
        sum(a.events) as events,
        sum(a.game_minutes) as minutes
    from away_long a
    join season_grid t on a.yr between t.yr - 2 and t.yr
    group by 1, 2, 3, 4
),

team_totals as (
    select target_season, visiting_team, stat,
           sum(events) as tot_events, sum(minutes) as tot_minutes
    from pooled
    group by 1, 2, 3
),

joined as (
    select
        p.target_season, p.arena_team_id, p.visiting_team, p.stat,
        p.events as in_events,
        p.minutes as in_minutes,
        tt.tot_events - p.events as else_events,
        tt.tot_minutes - p.minutes as else_minutes
    from pooled p
    join team_totals tt
        on p.target_season = tt.target_season
       and p.visiting_team = tt.visiting_team
       and p.stat = tt.stat
),

agg as (
    select
        target_season,
        arena_team_id,
        stat,
        safe_divide(sum(in_events), sum(in_minutes)) as actual_rate,
        safe_divide(
            sum(in_minutes * safe_divide(else_events, else_minutes)),
            sum(in_minutes)
        ) as expected_rate,
        sum(in_minutes) as sample_minutes
    from joined
    where else_minutes > 0
    group by 1, 2, 3
)

select
    target_season as season,
    arena_team_id,
    stat,
    least(greatest(safe_divide(actual_rate, expected_rate), 0.5), 2.0) as multiplier,
    sample_minutes
from agg
where expected_rate > 0
