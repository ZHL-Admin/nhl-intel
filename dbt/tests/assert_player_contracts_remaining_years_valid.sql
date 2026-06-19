-- Remaining years on a contract must be a sane, non-negative count. An active snapshot should
-- carry deals expiring at or after the snapshot season, so remaining_years lands in 0..8 (the
-- max NHL term is 8). Anything negative or absurdly large signals a bad expiry_year/season parse.
-- Returns offending rows; the test passes when there are none.
select
    player_id,
    as_of_date,
    expiry_year,
    season_start_year,
    remaining_years
from {{ ref('mart_player_contracts') }}
where remaining_years is null
   or remaining_years < 0
   or remaining_years > 8
