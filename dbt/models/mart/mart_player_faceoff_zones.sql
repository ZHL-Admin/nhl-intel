{{ config(
    cluster_by=["season_id", "player_id"]
) }}

-- Season-level per-player faceoff results by zone (offensive/neutral/defensive),
-- from the stats-REST faceoffwins report. This is the season "set-play" complement
-- to the event-derived per-GAME faceoff data in mart_team_faceoffs; the two are kept
-- separate on purpose (different grain + source) — see schema.yml.

with f as (
    select * from {{ ref('stg_statsrest_faceoffs') }}
)

select
    player_id,
    player_name,
    position_code,
    team_abbrevs,
    season_id,
    game_type,
    games_played,

    oz_faceoff_wins,
    oz_faceoff_losses,
    oz_faceoffs,
    nz_faceoff_wins,
    nz_faceoff_losses,
    nz_faceoffs,
    dz_faceoff_wins,
    dz_faceoff_losses,
    dz_faceoffs,

    total_faceoff_wins,
    total_faceoff_losses,
    total_faceoffs,
    faceoff_win_pct,

    -- Per-zone win percentages (null-safe)
    safe_divide(oz_faceoff_wins, oz_faceoffs) as oz_faceoff_win_pct,
    safe_divide(nz_faceoff_wins, nz_faceoffs) as nz_faceoff_win_pct,
    safe_divide(dz_faceoff_wins, dz_faceoffs) as dz_faceoff_win_pct
from f
