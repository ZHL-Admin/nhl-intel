{{ config(cluster_by=["season", "team_id"]) }}

-- With-Or-Without-You per (season, team_id, focal player_id, partner_id): 5v5 on-ice xGF%
-- with the pair together vs each player apart from the other. Directional — one row per
-- ordered focal->partner, so the focal's "without partner" split is always the focal's.
--
-- Method (leakage-free): together sums come from segment co-occurrence; each player's
-- apart-from-partner split is that player's season on-ice total minus the together portion
-- (mart_player_onice carries the raw season on-ice sums). small_sample flags pairs under
-- 3000 shared seconds (50 minutes, decision D17).

with seg_results as (
    select
        game_id,
        season,
        segment_index,
        segment_duration,
        home_team_id,
        away_team_id,
        xgf_home,
        xgf_away
    from {{ ref('int_segment_5v5_results') }}
),

-- per (game, segment, skater): the skater's team for/against xG for that segment
player_seg as (
    select
        s.game_id,
        s.season,
        s.segment_index,
        s.team_id,
        s.player_id,
        r.segment_duration as dur,
        if(s.team_id = r.home_team_id, r.xgf_home, r.xgf_away) as seg_xgf,
        if(s.team_id = r.home_team_id, r.xgf_away, r.xgf_home) as seg_xga
    from {{ ref('int_shift_segments') }} s
    join seg_results r on r.game_id = s.game_id and r.segment_index = s.segment_index
    where s.is_goalie = 0
),

-- undirected together sums for each same-team pair that shared a 5v5 segment
together_undirected as (
    select
        a.season,
        a.team_id,
        a.player_id as p_lo,
        b.player_id as p_hi,
        sum(a.dur) as toi_together_sec,
        sum(a.seg_xgf) as tog_xgf,
        sum(a.seg_xga) as tog_xga
    from player_seg a
    join player_seg b
        on a.game_id = b.game_id
       and a.segment_index = b.segment_index
       and a.team_id = b.team_id
       and a.player_id < b.player_id
    group by 1, 2, 3, 4
),

-- expand to directional (focal -> partner)
together as (
    select season, team_id, p_lo as player_id, p_hi as partner_id, toi_together_sec, tog_xgf, tog_xga
    from together_undirected
    union all
    select season, team_id, p_hi as player_id, p_lo as partner_id, toi_together_sec, tog_xgf, tog_xga
    from together_undirected
),

-- per-player season on-ice totals (the "with anyone" baseline)
totals as (
    select season, team_id, player_id, toi_5v5_sec, on_xgf, on_xga
    from {{ ref('mart_player_onice') }}
),

final as (
    select
        t.season,
        t.team_id,
        t.player_id,
        t.partner_id,
        t.toi_together_sec,
        f.toi_5v5_sec - t.toi_together_sec as focal_without_partner_toi_sec,
        p.toi_5v5_sec - t.toi_together_sec as partner_without_focal_toi_sec,
        safe_divide(t.tog_xgf, t.tog_xgf + t.tog_xga) as xgf_pct_together,
        safe_divide(t.tog_xgf, t.toi_together_sec / 3600.0) as xgf_per60_together,
        safe_divide(t.tog_xga, t.toi_together_sec / 3600.0) as xga_per60_together,
        safe_divide(f.on_xgf - t.tog_xgf, (f.on_xgf - t.tog_xgf) + (f.on_xga - t.tog_xga))
            as xgf_pct_focal_without_partner,
        safe_divide(p.on_xgf - t.tog_xgf, (p.on_xgf - t.tog_xgf) + (p.on_xga - t.tog_xga))
            as xgf_pct_partner_without_focal,
        t.toi_together_sec < 3000 as small_sample
    from together t
    join totals f on f.season = t.season and f.team_id = t.team_id and f.player_id = t.player_id
    join totals p on p.season = t.season and p.team_id = t.team_id and p.player_id = t.partner_id
)

select
    season,
    team_id,
    player_id,
    partner_id,
    toi_together_sec,
    focal_without_partner_toi_sec,
    partner_without_focal_toi_sec,
    xgf_pct_together,
    xgf_per60_together,
    xga_per60_together,
    xgf_pct_focal_without_partner,
    xgf_pct_partner_without_focal,
    -- does the focal line drive results up when together vs. when the focal is apart?
    xgf_pct_together - xgf_pct_focal_without_partner as together_minus_focal_alone,
    -- does the partner perform better with the focal than without (the carry signal)?
    xgf_pct_together - xgf_pct_partner_without_focal as partner_with_focal_minus_partner_without,
    small_sample
from final
