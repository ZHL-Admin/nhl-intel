{{ config(cluster_by=["season", "team_id"]) }}

-- Per (season, player_id, team_id) partner-concentration diagnostic for the impact-context
-- layer: how welded a skater is to one linemate, which is exactly the condition under which an
-- isolated (RAPM) estimate is least separable. Built from mart_player_toi_matrix, which stores
-- each pair once (player_id_a < player_id_b), so a symmetric view is materialized first.
--
-- max_partner_toi_share = the single most-common partner's shared 5v5 TOI over the player's own
-- 5v5 TOI (mart_player_onice). partner_entropy = normalized Shannon entropy (0 = all minutes with
-- one partner, 1 = evenly spread). entangled = share > 0.55 (decision D18). qualified at the same
-- 200-5v5-minute floor RAPM uses (12000 s).

with symmetric as (
    select season, team_id, player_id_a as player_id, player_id_b as partner_id, toi_together_sec
    from {{ ref('mart_player_toi_matrix') }}
    union all
    select season, team_id, player_id_b as player_id, player_id_a as partner_id, toi_together_sec
    from {{ ref('mart_player_toi_matrix') }}
),

per_partner as (
    select season, team_id, player_id, partner_id, toi_together_sec
    from symmetric
    where toi_together_sec > 0
),

shares as (
    select
        season,
        team_id,
        player_id,
        toi_together_sec,
        toi_together_sec
            / sum(toi_together_sec) over (partition by season, team_id, player_id) as p
    from per_partner
),

ent as (
    select
        season,
        team_id,
        player_id,
        count(*) as partner_count,
        max(toi_together_sec) as max_partner_toi_sec,
        -sum(p * ln(p)) as shannon_nats
    from shares
    group by 1, 2, 3
),

own_toi as (
    select season, team_id, player_id, toi_5v5_sec
    from {{ ref('mart_player_onice') }}
)

select
    e.season,
    e.player_id,
    e.team_id,
    o.toi_5v5_sec,
    e.partner_count,
    safe_divide(e.max_partner_toi_sec, o.toi_5v5_sec) as max_partner_toi_share,
    case when e.partner_count > 1 then e.shannon_nats / ln(e.partner_count) else 0.0 end as partner_entropy,
    safe_divide(e.max_partner_toi_sec, o.toi_5v5_sec) > 0.55 as entangled,
    coalesce(o.toi_5v5_sec, 0) >= 12000 as qualified
from ent e
join own_toi o
    on o.season = e.season and o.team_id = e.team_id and o.player_id = e.player_id
