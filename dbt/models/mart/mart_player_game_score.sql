{{ config(materialized='table', cluster_by=['season', 'player_id']) }}

-- Single-game "game score" per player (Phase 4.3), following the public game-score family
-- (Dom Luszczyszyn): a one-number summary of a player's game. Weights live in dbt vars
-- (gs_*). Individual production (goals, assists, ixG) dominates; shots/blocks/hits are small
-- terms; the on-ice term nudges by even-strength xG share (centred at 0.5). NHL games only.

with base as (
    select
        game_id, game_date, season, player_id, team_id, position_code,
        individual_goals as goals,
        first_assists, second_assists,
        ixg, individual_shot_attempts as shots, hits,
        on_ice_xgf_pct
    from {{ ref('mart_player_game_stats') }}
    where substr(cast(game_id as string), 5, 2) in ('01', '02', '03')
),

blocks as (
    select game_id, blocking_player_id as player_id, count(*) as blocks
    from {{ ref('stg_play_by_play') }}
    where type_desc_key = 'blocked-shot' and blocking_player_id is not null
    group by 1, 2
),

scored as (
    select
        b.*, coalesce(bl.blocks, 0) as blocks,
        {{ var('gs_goal') }} * b.goals
        + {{ var('gs_primary_assist') }} * b.first_assists
        + {{ var('gs_secondary_assist') }} * b.second_assists
        + {{ var('gs_ixg') }} * b.ixg
        + {{ var('gs_shot') }} * b.shots
        + {{ var('gs_block') }} * coalesce(bl.blocks, 0)
        + {{ var('gs_hit') }} * b.hits
        + {{ var('gs_onice_xg') }} * (coalesce(b.on_ice_xgf_pct, 0.5) - 0.5) as game_score
    from base b
    left join blocks bl on b.game_id = bl.game_id and b.player_id = bl.player_id
)

select * from scored
