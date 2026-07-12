-- System Effects (Phase 7) — one row per game: home/away head coach from the right-rail
-- gameInfo block, for ALL seasons. This is the live coach source of record for the regime
-- ledger. Coaches are captured daily for FINAL games and, for 2010-11..2023-24, backfilled by
-- loading the research project's cached right-rail payloads into raw_game_right_rail via the
-- normal loader (see ingestion/backfill_coach_loader.py). Idempotent one-row-per-game via the
-- ingestion_date dedup, matching the shift-fallback convention.
--
-- Season is derived from the game_id prefix, NEVER from stg_games.season — the latter carries
-- the UL-1 mislabel (a 2015-16 block tagged 2024-25); anchoring on game_id immunizes the ledger,
-- exactly as the frozen research build did.

with rail_raw as (
    select
        game_id,
        gameInfo,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
    from {{ source('nhl', 'raw_game_right_rail') }}
),

rail as (
    select * from rail_raw where rn = 1
),

-- team ids come from stg_games (ids are trustworthy; only its season LABEL is UL-1-corrupt,
-- which we never use — season is derived from the game_id prefix below).
games as (
    select game_id, home_team_id, away_team_id from {{ ref('stg_games') }}
)

select
    r.game_id,
    -- regular-season only (game type '02'), matching the frozen corpus
    cast(substr(cast(r.game_id as string), 1, 4) as int64) as season_start_year,
    concat(
        cast(substr(cast(r.game_id as string), 1, 4) as int64), '-',
        substr(cast(cast(substr(cast(r.game_id as string), 1, 4) as int64) + 1 as string), 3, 2)
    ) as season_label,
    g.home_team_id,
    g.away_team_id,
    json_extract_scalar(r.gameInfo, '$.homeTeam.headCoach.default') as home_head_coach,
    json_extract_scalar(r.gameInfo, '$.awayTeam.headCoach.default') as away_head_coach
from rail r
join games g using (game_id)
where substr(cast(r.game_id as string), 5, 2) = '02'
