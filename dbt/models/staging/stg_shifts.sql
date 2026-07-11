-- One row per shift per player per game.
-- Source: nhl_raw.raw_shift_charts (shift array stored as a serialized JSON string).
-- Exclusion rule (verified empirically): rows with a null/empty duration are
-- goal-event annotations (typeCode 505), not real shifts. typeCode 517 = shifts.
-- Game-elapsed seconds use (period-1)*1200 as the period offset, which is correct
-- for regulation and for every OT slot (regular-season OT is period 4 starting at
-- 3600; playoff OT periods are 1200s slots: period 4 -> 3600, period 5 -> 4800, ...).

with raw as (
    select
        game_id,
        season,
        ingestion_date,
        data,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
    from {{ source('nhl', 'raw_shift_charts') }}
),

latest as (
    select game_id, season, data from raw where rn = 1
),

shifts as (
    select
        l.game_id,
        l.season,
        cast(json_extract_scalar(shift, '$.playerId') as int64) as player_id,
        cast(json_extract_scalar(shift, '$.teamId') as int64) as team_id,
        cast(json_extract_scalar(shift, '$.period') as int64) as period,
        cast(json_extract_scalar(shift, '$.shiftNumber') as int64) as shift_number,
        cast(json_extract_scalar(shift, '$.typeCode') as int64) as type_code,
        json_extract_scalar(shift, '$.startTime') as start_mmss,
        json_extract_scalar(shift, '$.endTime') as end_mmss,
        json_extract_scalar(shift, '$.duration') as duration_mmss
    from latest l,
        unnest(json_extract_array(l.data)) as shift
),

parsed as (
    select
        game_id,
        season,
        player_id,
        team_id,
        period,
        shift_number,
        type_code,
        (period - 1) * 1200
            + cast(split(start_mmss, ':')[offset(0)] as int64) * 60
            + cast(split(start_mmss, ':')[offset(1)] as int64) as shift_start_seconds,
        (period - 1) * 1200
            + cast(split(end_mmss, ':')[offset(0)] as int64) * 60
            + cast(split(end_mmss, ':')[offset(1)] as int64) as shift_end_seconds,
        cast(split(duration_mmss, ':')[offset(0)] as int64) * 60
            + cast(split(duration_mmss, ':')[offset(1)] as int64) as duration_seconds
    from shifts
    -- Exclude goal-event annotation rows (null/empty duration).
    where duration_mmss is not null and duration_mmss != ''
)

select
    game_id,
    season,
    player_id,
    team_id,
    period,
    shift_number,
    shift_start_seconds,
    shift_end_seconds,
    duration_seconds
from parsed
where player_id is not null
    -- Documented noise rule: keep only physically valid shifts (1..1200s). Excludes
    -- ~0.01% of rows that are either zero-duration degenerate records (start == end,
    -- concentrated in 2019-20) or corrupt over-length shifts (up to ~44 min, a handful
    -- in 2021-22/2023-24). Neither represents a real on-ice interval.
    and duration_seconds between 1 and 1200
    -- Corrupt period-5+ rows in REGULAR-season games only (game_type 02): period 5 is
    -- the shootout, which has no on-ice shifts. A handful of games carry on-ice shifts
    -- mislabelled period >=5 (raw-feed corruption, ledger D7). Playoff multi-OT
    -- (period 5/6/... in game_type 03) is legitimate and untouched.
    and not (period >= 5 and substr(cast(game_id as string), 5, 2) = '02')
-- Exact-duplicate drop (matches the Atlas dedup rule): the raw NHL shift array
-- repeats some identical (player, period, start, end) rows verbatim (~0.1% of rows,
-- concentrated 2020-25). A player cannot have two identical shifts; collapse to one.
-- Fixes phantom personnel/overlaps + inflated TOI in every downstream on-ice model.
qualify row_number() over (
    partition by game_id, player_id, period, shift_start_seconds, shift_end_seconds
    order by shift_number
) = 1
