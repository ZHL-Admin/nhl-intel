-- No duplicate (team_id, start_game_id) regime in fingerprints_v2.
select team_id, start_game_id, count(*) as n
from {{ ref('mart_syseff_fingerprints_v2') }}
group by team_id, start_game_id
having count(*) > 1
