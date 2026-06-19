-- mart_player_contracts is one row per (player_id, as_of_date). The dedup in the model keeps
-- the highest cap hit per key, so this asserts the grain held (no duplicate player-snapshot rows
-- leaked through). Returns offending keys; the test passes when there are none.
select
    player_id,
    as_of_date,
    count(*) as n
from {{ ref('mart_player_contracts') }}
group by player_id, as_of_date
having count(*) > 1
