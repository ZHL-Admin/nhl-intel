-- No duplicate (team_id, start_game_id) in the raw regime ledger.
select team_id, start_game_id, count(*) as n
from {{ ref('mart_syseff_regime_ledger') }}
group by team_id, start_game_id
having count(*) > 1
