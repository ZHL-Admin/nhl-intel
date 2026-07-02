{{ config(cluster_by=["season"]) }}

-- Per (season, player_id) carry score: does a player make the linemates around them better?
-- TOI-weighted mean over partners of the WOWY field partner_with_focal_minus_partner_without
-- (the partner's on-ice xGF% WITH the focal minus WITHOUT the focal), weighted by shared 5v5 TOI
-- so tiny-sample pairings barely move it. Positive = the player's partners perform better with
-- the player than without → the player elevates partners. Grain is (season, player_id): a traded
-- player's partners across both teams roll into one score. Qualified at the 200-5v5-minute floor
-- RAPM uses (12000 s).

with wowy as (
    select
        season,
        player_id,
        partner_id,
        toi_together_sec,
        partner_with_focal_minus_partner_without as carry_delta
    from {{ ref('mart_player_wowy') }}
),

agg as (
    select
        season,
        player_id,
        safe_divide(sum(carry_delta * toi_together_sec), sum(toi_together_sec)) as carry_score,
        count(distinct partner_id) as partner_count
    from wowy
    group by 1, 2
),

player_toi as (
    select season, player_id, sum(toi_5v5_sec) as toi_5v5_sec
    from {{ ref('mart_player_onice') }}
    group by 1, 2
)

select
    a.season,
    a.player_id,
    a.carry_score,
    a.partner_count,
    t.toi_5v5_sec,
    coalesce(t.toi_5v5_sec, 0) >= 12000 as qualified
from agg a
left join player_toi t
    on t.season = a.season and t.player_id = a.player_id
