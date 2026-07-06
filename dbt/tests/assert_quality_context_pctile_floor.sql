-- qoc_pctile / qot_pctile must be NULL exactly when the player is below the 5v5 ranking floor
-- (MIN_TOI_5V5_FOR_RANKING = 200 min = 12000 sec). Percentiles are ranked only within the qualified
-- pool. This test returns any row that violates that iff-relationship (0 rows = pass).

select season, player_id, team_id, toi_5v5_sec, qoc_pctile, qot_pctile
from {{ ref('mart_player_quality_context') }}
where (toi_5v5_sec >= 12000 and (qoc_pctile is null or qot_pctile is null))
   or (toi_5v5_sec <  12000 and (qoc_pctile is not null or qot_pctile is not null))
