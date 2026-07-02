{{ config(cluster_by=["season", "position_group"]) }}

-- Per (season, player_id, position_group) transparent context around the isolated-impact (RAPM)
-- estimate. READS nhl_models.player_impact; computes NO new blended score and NO ranking. Every
-- field is kept separate so the reader sees the estimate, its uncertainty, how welded/entangled
-- the player is, whether they carry partners, their true on-off relative, and how the single
-- season diverges from the 3-year weighted window (the carryover signal that motivated the layer:
-- Seider and Edvinsson; see docs/methodology/impact-context.md).
--
-- player_impact season_window: single-season rows are plain "YYYY-YY" (no underscore); the 3-year
-- weighted window is "YYYY-YY_YYYY-YY" (contains "_"). single_vs_multi_delta is null when a player
-- has no window row (documented).

with pi as (
    select
        season_window,
        player_id,
        off_impact,
        def_impact,
        off_sd,
        def_sd,
        toi_min,
        off_impact + def_impact as total_impact
    from {{ source('nhl_models', 'player_impact') }}
),

single as (
    select
        season_window as season,
        player_id,
        off_impact,
        def_impact,
        off_sd,
        def_sd,
        toi_min as impact_toi_min,
        total_impact
    from pi
    where strpos(season_window, '_') = 0
),

multi as (
    -- one row per player (a single 3-year weighted window exists)
    select
        player_id,
        off_impact as multi_off_impact,
        def_impact as multi_def_impact,
        total_impact as multi_total_impact,
        season_window as multi_window
    from pi
    where strpos(season_window, '_') > 0
),

-- position group per (season, player): modal roster position, forwards vs defense, goalies excluded
position_group as (
    select season, player_id, position_group
    from (
        select
            season,
            player_id,
            case when position_code in ('C', 'L', 'R') then 'F' when position_code = 'D' then 'D' end as position_group,
            row_number() over (
                partition by season, player_id
                order by count(*) desc
            ) as rn
        from {{ ref('stg_rosters') }}
        where position_code in ('C', 'L', 'R', 'D')
        group by season, player_id, position_group
    )
    where rn = 1
),

-- season-aggregated on-off relative (sum raw sums across a traded player's teams, then recompute)
onice_agg as (
    select
        season,
        player_id,
        sum(toi_5v5_sec) as toi_5v5_sec,
        safe_divide(sum(on_xgf), sum(on_xgf) + sum(on_xga))
            - safe_divide(sum(off_xgf), sum(off_xgf) + sum(off_xga)) as rel_xgf_pct
    from {{ ref('mart_player_onice') }}
    group by season, player_id
),

-- entanglement from the player's primary team that season (most 5v5 TOI)
primary_team as (
    select season, player_id, team_id
    from (
        select
            season,
            player_id,
            team_id,
            row_number() over (partition by season, player_id order by toi_5v5_sec desc) as rn
        from {{ ref('mart_player_onice') }}
    )
    where rn = 1
),

ent as (
    select
        e.season,
        e.player_id,
        e.max_partner_toi_share,
        e.partner_entropy,
        e.entangled
    from {{ ref('mart_player_entanglement') }} e
    join primary_team pt
        on pt.season = e.season and pt.player_id = e.player_id and pt.team_id = e.team_id
),

carry as (
    select season, player_id, carry_score, partner_count as carry_partner_count
    from {{ ref('mart_player_carry') }}
)

select
    s.season,
    s.player_id,
    p.position_group,
    -- single-season isolated impact + uncertainty
    s.off_impact,
    s.def_impact,
    s.total_impact,
    s.off_sd,
    s.def_sd,
    s.impact_toi_min,
    -- 3-year weighted window
    m.multi_off_impact,
    m.multi_def_impact,
    m.multi_total_impact,
    m.multi_window,
    -- carryover signal (null when no window row)
    s.total_impact - m.multi_total_impact as single_vs_multi_delta,
    -- entanglement (primary team)
    e.max_partner_toi_share,
    e.partner_entropy,
    coalesce(e.entangled, false) as entangled,
    -- carry
    c.carry_score,
    c.carry_partner_count,
    -- true on-off relative + 5v5 TOI
    o.rel_xgf_pct,
    o.toi_5v5_sec
from single s
join position_group p
    on p.season = s.season and p.player_id = s.player_id
left join multi m on m.player_id = s.player_id
left join ent e on e.season = s.season and e.player_id = s.player_id
left join carry c on c.season = s.season and c.player_id = s.player_id
left join onice_agg o on o.season = s.season and o.player_id = s.player_id
