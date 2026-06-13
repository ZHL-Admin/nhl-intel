-- Shift durations must fall within a single period: 1..1200 seconds.
-- Returns offending rows; the test passes when there are none.
select
    game_id,
    player_id,
    shift_number,
    duration_seconds
from {{ ref('stg_shifts') }}
where duration_seconds < 1 or duration_seconds > 1200
