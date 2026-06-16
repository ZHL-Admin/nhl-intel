{{ config(materialized='view') }}

-- One row per player: bio (birth date, height, weight, handedness) from the player landing
-- endpoint (Phase 4.4; scripts/ingest_player_bio.py -> nhl_raw.raw_player_bio). Needed for
-- age (aging curves) and height/weight (career twins) — boxscore rosterSpots carry no bio.
-- Keeps the latest ingestion per player.

with ranked as (
    select *,
        row_number() over (partition by player_id order by ingestion_date desc) as rn
    from {{ source('nhl', 'raw_player_bio') }}
    where birth_date is not null
)

select
    player_id,
    birth_date,
    height_in,
    weight_lb,
    shoots,
    position
from ranked
where rn = 1
