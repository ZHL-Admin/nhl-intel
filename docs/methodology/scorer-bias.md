# Scorer-bias (rink) adjustment (Phase 2.3)

Home-arena scorekeepers record subjective events — **hits, giveaways, takeaways** — at
materially different rates. We measure each arena's bias from **visiting teams only**, so
a team's own playing identity is controlled for, and adjust every recorded count by the
arena's multiplier. `int_rink_bias` holds the multipliers; `adjusted = raw / multiplier`.

## Method

For each arena and stat, pooled over a **rolling 3-season window** (stability):

- **actual rate** = visiting teams' events per minute in the arena.
- **expected rate** = the same visiting teams' event rate in *all other* arenas, weighted
  by how many minutes each team played in this arena (team-mix control).
- **multiplier** = actual / expected, **clipped to [0.5, 2.0]**.

`adjusted = raw / multiplier` is applied to both the home and the away team's counts for a
game (the bias is in the *arena's recording*, not the team). Exposed as raw + `_adj` on
`mart_team_game_stats` and `mart_player_game_stats`; the frontend shows adjusted by default
with a tooltip (glossary key `scorer_bias`).

## Per-arena multipliers — 2024-25 (3-season window)

Selected arenas (full set in `int_rink_bias`):

| arena (team id) | hits | giveaways | takeaways |
|---|---|---|---|
| Toronto (10) | 1.43 | 1.20 | 1.12 |
| Tampa Bay (14) | 1.30 | 0.84 | 1.29 |
| Vegas (54) | 1.25 | 0.90 | 1.13 |
| Edmonton (22) | 1.24 | 1.29 | 1.22 |
| Dallas (25) | 1.21 | 1.05 | 1.05 |
| Boston (6) | 1.19 | 1.13 | 1.26 |
| San Jose (28) | 0.77 | 1.03 | 1.25 |
| Anaheim (24) | 0.73 | 1.04 | 0.88 |
| Columbus (29) | 0.68 | 0.76 | 0.81 |

Toronto's well-known hit inflation (1.43×) and Columbus's under-counting (0.68×) are the
extremes; multipliers average ~1.0 by construction. Example: Toronto's 2024-25 team hits
deflate from 2,489 raw to 2,100 adjusted.

## Shot-location calibration check (report only — no adjustment applied)

Per arena, the mean recorded shot distance for **visiting** teams vs the league mean. Only
one arena is more than 2 ft off in 2024-25:

| arena (team id) | arena mean (ft) | league mean (ft) | diff |
|---|---|---|---|
| Utah (67) | 36.63 | 34.38 | +2.25 |

Utah's first-season arena (Delta Center, 2024-25) records visiting shots ~2.25 ft farther
than league average. This is flagged for monitoring; **no shot-location adjustment is
applied yet** (the xG model consumes raw coordinates). Revisit if the gap persists across
seasons.
