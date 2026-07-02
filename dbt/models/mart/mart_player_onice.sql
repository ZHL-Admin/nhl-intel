{{ config(cluster_by=["season", "team_id"]) }}

-- Season on-ice / off-ice 5v5 profile per (season, player_id, team_id), rolled up from
-- int_player_onice_game. rel_xgf_pct / rel_cf_pct are the TRUE on-ice-minus-off-ice
-- relatives (the corrected replacement for the player-minus-team-average proxy that
-- mart_player_relative historically carried). Raw sums are kept so mart_player_wowy can
-- subtract the together portion without recomputing from segments.

with games as (
    select * from {{ ref('int_player_onice_game') }}
),

agg as (
    select
        season,
        player_id,
        team_id,
        sum(toi_5v5_sec) as toi_5v5_sec,
        sum(off_toi_5v5_sec) as off_toi_5v5_sec,
        sum(on_xgf) as on_xgf,
        sum(on_xga) as on_xga,
        sum(on_cf) as on_cf,
        sum(on_ca) as on_ca,
        sum(off_xgf) as off_xgf,
        sum(off_xga) as off_xga,
        sum(off_cf) as off_cf,
        sum(off_ca) as off_ca
    from games
    group by 1, 2, 3
)

select
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
from agg
