{{ config(cluster_by=["season_id", "team_id"]) }}

-- Per team-season NHL Edge profile: NHL danger-bucket shot shares (high/mid/long)
-- from team-shot-location-detail. NOTE: Edge goalie data carries no team linkage and
-- no HD/5v5 save-pct split, so goalie HD aggregates are intentionally NOT joined here;
-- the goalie danger second-opinion lives in the Phase 2.5 goaltending marts.

select
    team_id,
    season_id,
    game_type,
    total_sog,
    high_danger_sog,
    mid_danger_sog,
    long_danger_sog,
    high_danger_goals,
    high_danger_sog_share,
    mid_danger_sog_share,
    long_danger_sog_share,
    safe_divide(high_danger_goals, high_danger_sog) as high_danger_shooting_pct
from {{ ref('stg_edge_teams') }}
