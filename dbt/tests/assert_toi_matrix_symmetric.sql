-- The pair TOI matrix stores each unordered pair once (player_id_a < player_id_b), so there
-- must be exactly one row per (season, team_id, player_id_a, player_id_b) and no non-negative
-- shared time must ever go negative. Returns offending rows; the test passes when none.

select
    season,
    team_id,
    player_id_a,
    player_id_b,
    count(*) as n_rows,
    min(toi_together_sec) as min_toi_together_sec
from {{ ref('mart_player_toi_matrix') }}
group by 1, 2, 3, 4
having count(*) > 1
    or min(toi_together_sec) < 0
