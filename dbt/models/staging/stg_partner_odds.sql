-- Partner sportsbook odds → de-vigged implied win probabilities.
-- Source: nhl_raw.raw_partner_odds (api-web partner-game/{cc}/now snapshots).
--
-- INTERNAL CALIBRATION ONLY (blueprint 13.2): this model exists solely so the
-- Phase 2.4 win-probability work can benchmark against the market. There is and
-- must be NO backend endpoint and NO frontend surface for odds.
--
-- PENDING IN-SEASON VALIDATION: the probe ran in the offseason with an empty
-- games[] array, so the exact per-side american-odds field path could not be
-- captured from a live payload (see scripts/STATSREST_FINDINGS.md). The de-vig
-- math below is final and correct; the only thing to confirm against the first
-- in-season snapshot is the JSON path of the american odds (home_american_odds /
-- away_american_odds). Until then this model yields rows only when games[] is
-- non-empty, and odds columns may be null if the path differs.

with snapshots as (
    select
        ingestion_date,
        season,
        json_extract_array(games) as game_array
    from {{ source('nhl', 'raw_partner_odds') }}
),

games as (
    select
        s.ingestion_date,
        s.season,
        cast(json_extract_scalar(g, '$.gameId') as int64) as game_id,
        -- Candidate american-odds paths (confirm against first in-season payload).
        safe_cast(json_extract_scalar(g, '$.homeOdds') as float64) as home_american_odds,
        safe_cast(json_extract_scalar(g, '$.awayOdds') as float64) as away_american_odds
    from snapshots s,
        unnest(s.game_array) as g
),

implied as (
    select
        *,
        -- American odds → decimal odds → raw implied probability.
        case
            when home_american_odds is null then null
            when home_american_odds > 0 then 1.0 / (1.0 + home_american_odds / 100.0)
            else 1.0 / (1.0 + 100.0 / abs(home_american_odds))
        end as home_implied_raw,
        case
            when away_american_odds is null then null
            when away_american_odds > 0 then 1.0 / (1.0 + away_american_odds / 100.0)
            else 1.0 / (1.0 + 100.0 / abs(away_american_odds))
        end as away_implied_raw
    from games
)

select
    game_id,
    season,
    ingestion_date,
    home_american_odds,
    away_american_odds,
    home_implied_raw,
    away_implied_raw,
    -- De-vig: normalize the pair to sum to 1 (removes the bookmaker hold).
    safe_divide(home_implied_raw, home_implied_raw + away_implied_raw) as home_win_prob_devig,
    safe_divide(away_implied_raw, home_implied_raw + away_implied_raw) as away_win_prob_devig
from implied
where game_id is not null
