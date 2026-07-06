# Player Context (Layer 2) — Methodology

The Context tab and `GET /players/{id}/context` compose, in one fetch, the situation-dependence
of a player's value.

## Quality of competition / teammates (QoC / QoT)
`mart_player_quality_context` (dbt), grain (season, player_id, team_id). For each 5v5 segment
(strength_state='5v5', 5 skaters/side), every OTHER on-ice skater is a teammate (same team_id) or an
opponent, weighted by segment_duration. Each is scored by their **prior-season** shrunk WAR rate
(`player_prior_quality` = the Marcel rate as of S-1, rookies = 0) — so the metric is **leak-free by
construction**. `qoc_war_rate` / `qot_war_rate` are the TOI-weighted means; `qoc_pctile` / `qot_pctile`
are ranked **only within the qualified pool** (5v5 TOI ≥ 200 min), so a low-TOI player cannot top the
percentile on noise. Below-floor players keep the raw rates but carry **null percentiles**, which the
UI **mutes** (never hides). v1 is LEVELS only; performance-by-QoC-tercile is v1.1.

## WOWY (with-or-without-you)
Served from `mart_player_wowy` (already materialized). D17: `small_sample = toi_together_sec < 3000`
(50 min) passes through untouched; the UI renders small-sample rows muted. The linemate-dependence
input `together_minus_focal_alone` is precomputed in the mart.

## Serving
`mart_player_quality_context` + `player_prior_quality` are in `serving_tables.yml`. Weekly Monday
gate: `compute_gar >> compute_prior_quality >> dbt build mart_player_quality_context >> export`.
