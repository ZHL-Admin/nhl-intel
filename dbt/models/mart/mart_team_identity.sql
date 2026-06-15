{{
  config(
    materialized='table',
    cluster_by=['season', 'team_id']
  )
}}

-- Team identity fingerprints (blueprint 5.1) enriched with NHL Edge zone time (12.1).
-- One row per (season, team_id, window) where window is 'season' (all games) or 'last25'
-- (the team's most recent 25 games that season). Regular season + playoffs only. Every
-- fingerprint metric carries a league percentile (percent_rank within season+window).
--
-- 5v5 attempts/seq mix come from mart_team_identity_inputs; 5v5 xGF and PP shot mix come
-- from shot_xg joined to int_shot_sequence (non-empty-net). Team offensive-zone time is
-- TOI-weighted even-strength skater Edge zone time (the team-level Edge zone-time endpoint
-- 404s; documented proxy). Territory-to-danger conversion = 5v5 xGF per OZ minute.
-- Penalties/hits are expressed per 60 treating each game as 60 minutes (OT negligible).

with games as (
    select
        m.game_id, m.game_date, m.season, m.team_id,
        ii.opponent_team_id,
        m.toi_5v5_minutes,
        m.hits_adj,
        ii.attempts_for, ii.attempts_against,
        ii.rebound_for, ii.rush_for, ii.forecheck_for, ii.cycle_for, ii.point_shot_for,
        ii.rebound_against, ii.rush_against, ii.forecheck_against, ii.cycle_against,
        ii.point_shot_against,
        row_number() over (
            partition by m.team_id, m.season order by m.game_date desc) as recency
    from {{ ref('mart_team_game_stats') }} m
    join {{ ref('mart_team_identity_inputs') }} ii
        on m.game_id = ii.game_id and m.team_id = ii.team_id
    where substr(cast(m.game_id as string), 5, 2) in ('02', '03')
),

-- 5v5 xGF and PP shot mix per (game, team), from the xG layer + strength label.
shots as (
    select s.game_id, s.team_id, q.strength, q.seq_point_shot, s.xg
    from {{ source('nhl_models', 'shot_xg') }} s
    join {{ ref('int_shot_sequence') }} q
        on s.game_id = q.game_id and s.event_id = q.event_id
    where s.xg is not null
),
shot_agg as (
    select game_id, team_id,
        sum(if(strength = '5v5', xg, 0)) as xgf_5v5,
        countif(strength = 'PP') as pp_shots,
        countif(strength = 'PP' and seq_point_shot) as pp_point_shots
    from shots group by 1, 2
),

-- Penalties committed per (game, team). Excludes 'delayed-penalty' announcements.
pen as (
    select game_id, event_owner_team_id as team_id, count(*) as penalties
    from {{ ref('stg_play_by_play') }}
    where type_desc_key = 'penalty' and event_owner_team_id is not null
    group by 1, 2
),

game_base as (
    select g.*,
        coalesce(sa.xgf_5v5, 0) as xgf_5v5,
        coalesce(sa.pp_shots, 0) as pp_shots,
        coalesce(sa.pp_point_shots, 0) as pp_point_shots,
        coalesce(pt.penalties, 0) as pen_taken,
        coalesce(pd.penalties, 0) as pen_drawn
    from games g
    left join shot_agg sa on g.game_id = sa.game_id and g.team_id = sa.team_id
    left join pen pt on g.game_id = pt.game_id and g.team_id = pt.team_id
    left join pen pd on g.game_id = pd.game_id and g.opponent_team_id = pd.team_id
),

-- duplicate each game into the 'season' window and (when recent enough) 'last25'
windowed as (
    select gb.*, window_kind
    from game_base gb, unnest(['season', 'last25']) as window_kind
    where window_kind = 'season' or gb.recency <= 25
),

-- TOI-weighted even-strength skater zone time -> team OZ/DZ time pct (season level).
player_team as (
    select season, player_id, team_id
    from (
        select season, player_id, team_id,
            row_number() over (partition by season, player_id
                               order by sum(duration_seconds) desc) as rn
        from {{ ref('stg_shifts') }}
        group by season, player_id, team_id
    )
    where rn = 1
),
edge_zone as (
    select pt.season, pt.team_id,
        safe_divide(sum(e.oz_time_pct_es * e.toi_minutes), sum(e.toi_minutes)) as oz_time_pct,
        safe_divide(sum(e.dz_time_pct_es * e.toi_minutes), sum(e.toi_minutes)) as dz_time_pct
    from {{ ref('mart_edge_player_profile') }} e
    join player_team pt
        on e.player_id = pt.player_id
        and e.season_id = cast(substr(pt.season, 1, 4) || '20' || substr(pt.season, 6, 2) as int64)
    where e.toi_minutes > 0
    group by 1, 2
),

agg as (
    select season, team_id, window_kind,
        count(*) as games,
        sum(toi_5v5_minutes) as toi_5v5_total,
        sum(xgf_5v5) as xgf_5v5_total,
        -- offense mix (for): share of 5v5 attempts by sequence type
        safe_divide(sum(rush_for), sum(attempts_for)) as rush_share_for,
        safe_divide(sum(forecheck_for), sum(attempts_for)) as forecheck_share_for,
        safe_divide(sum(cycle_for), sum(attempts_for)) as cycle_share_for,
        safe_divide(sum(point_shot_for), sum(attempts_for)) as point_shot_share_for,
        safe_divide(sum(rebound_for), sum(attempts_for)) as rebound_share_for,
        -- defense mix (against): share of 5v5 attempts allowed by sequence type
        safe_divide(sum(rush_against), sum(attempts_against)) as rush_share_against,
        safe_divide(sum(forecheck_against), sum(attempts_against)) as forecheck_share_against,
        safe_divide(sum(cycle_against), sum(attempts_against)) as cycle_share_against,
        safe_divide(sum(point_shot_against), sum(attempts_against)) as point_shot_share_against,
        safe_divide(sum(rebound_against), sum(attempts_against)) as rebound_share_against,
        -- pace, quality, volume
        safe_divide(sum(attempts_for) + sum(attempts_against), sum(toi_5v5_minutes)) as pace,
        safe_divide(sum(xgf_5v5), sum(attempts_for)) as shot_quality,
        safe_divide(sum(attempts_for), sum(toi_5v5_minutes)) * 60 as shot_volume_per60,
        -- aggression (per ~60-min game)
        safe_divide(sum(hits_adj), count(*)) as hits_per60,
        safe_divide(sum(pen_taken), count(*)) as penalties_taken_per60,
        safe_divide(sum(pen_drawn), count(*)) as penalties_drawn_per60,
        -- PP structure
        safe_divide(sum(pp_point_shots), sum(pp_shots)) as pp_point_shot_share
    from windowed
    group by 1, 2, 3
),

joined as (
    select a.*,
        ez.oz_time_pct, ez.dz_time_pct,
        -- territory-to-danger conversion: 5v5 xGF per minute of offensive-zone time
        safe_divide(a.xgf_5v5_total, ez.oz_time_pct * a.toi_5v5_total) as oz_conversion
    from agg a
    left join edge_zone ez on a.season = ez.season and a.team_id = ez.team_id
),

-- league percentile (within season + window) for every fingerprint metric
final as (
    select *,
        {% set pct_metrics = [
            'rush_share_for','forecheck_share_for','cycle_share_for','point_shot_share_for',
            'rebound_share_for','rush_share_against','forecheck_share_against',
            'cycle_share_against','point_shot_share_against','rebound_share_against',
            'pace','shot_quality','shot_volume_per60','hits_per60',
            'penalties_taken_per60','penalties_drawn_per60','pp_point_shot_share',
            'oz_time_pct','dz_time_pct','oz_conversion'
        ] %}
        {% for m in pct_metrics %}
        percent_rank() over (partition by season, window_kind order by {{ m }})
            as {{ m }}_pctile{{ ',' if not loop.last }}
        {% endfor %}
    from joined
)

select * from final
