-- Every matched NHL contract's cap hit must clear the league minimum salary.
-- The 2025-26 NHL minimum is $775,000; we test a slightly looser $700,000 floor so a
-- legitimately buried/edge deal does not trip the test, while a parsing error (cents lost,
-- a blank coerced to 0, a two-way AHL figure) that drops a cap hit far below the minimum does.
-- Returns offending rows; the test passes when there are none.
select
    player_id,
    as_of_date,
    cap_hit
from {{ ref('mart_player_contracts') }}
where cap_hit is null or cap_hit < 700000
