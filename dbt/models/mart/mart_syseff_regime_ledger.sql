{{ config(materialized='table', cluster_by=['team_id']) }}

-- System Effects (Phase 7) — the RAW regime ledger: one row per (team, head coach, contiguous
-- game span), derived live from stg_syseff_game_coaches. Gaps-and-islands on schedule order
-- (game_id), UL-1-immune (season from game_id prefix). Reconciles exactly to the frozen research
-- table data/parquet/regime_ledger.parquet (235 rows); the consolidated grain (K=4 fill-in
-- absorption) is mart_syseff_regime_ledger_consolidated.
--
-- Normalization mirrors the research: NFC is a no-op in BigQuery for these ASCII/Latin names;
-- curly apostrophes are straightened and internal whitespace collapsed. No hardcoded alias key.

with team_games as (
    select game_id, season_label, home_team_id as team_id,
           trim(regexp_replace(replace(home_head_coach, '’', ''''), r'\s+', ' ')) as coach
    from {{ ref('stg_syseff_game_coaches') }}
    where home_head_coach is not null
    union all
    select game_id, season_label, away_team_id as team_id,
           trim(regexp_replace(replace(away_head_coach, '’', ''''), r'\s+', ' ')) as coach
    from {{ ref('stg_syseff_game_coaches') }}
    where away_head_coach is not null
),

flagged as (
    select *,
        case when coach != lag(coach) over (partition by team_id order by game_id)
                  or lag(coach) over (partition by team_id order by game_id) is null
             then 1 else 0 end as is_new_regime
    from team_games
),

seqd as (
    select *, sum(is_new_regime) over (order by team_id, game_id
             rows between unbounded preceding and current row) as regime_seq
    from flagged
),

agg as (
    select
        regime_seq,
        any_value(team_id) as team_id,
        any_value(coach) as coach_name,
        min(game_id) as start_game_id,
        max(game_id) as end_game_id,
        count(*) as games_in_regime,
        min(season_label) as start_season,
        max(season_label) as end_season
    from seqd
    group by regime_seq
)

select
    team_id, coach_name, start_game_id, end_game_id, games_in_regime,
    start_season, end_season,
    case when start_season = end_season then start_season
         else concat(start_season, '..', end_season) end as seasons_spanned,
    lag(coach_name) over (partition by team_id order by start_game_id) as predecessor_coach,
    (lag(coach_name) over (partition by team_id order by start_game_id) is not null
     and lag(end_season) over (partition by team_id order by start_game_id) = start_season
    ) as is_mid_season_change
from agg
order by team_id, start_game_id
