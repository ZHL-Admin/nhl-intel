# Overall — a within-position percentile summary (player card only)

**Overall** is a single 0-100 number for a player's all-round standing *within his position*. It is
a deliberately modest summary: it exists to give the player card one headline figure, and it is
hedged so it can never be mistaken for a precise cross-player ranking.

`models_ml/compute_overall.py` → `nhl_models.player_overall` (skaters) and `nhl_models.goalie_overall`
(goalies). Surfaced on `GET /players/{id}` (`value.overall`) and `GET /goalies/{id}` (`overall`).

## What it is

Overall is the **weighted average of a player's within-position component percentiles, then
re-percentiled within position**:

1. Take the player's percentile (within his position group) on each lens.
2. Average them with documented weights → `overall_raw`.
3. **Re-percentile** `overall_raw` within position → `overall_percentile` (0-100).

Step 3 matters: averaging percentiles compresses toward the middle (a player in the 95th on both
lenses averages to 95, but so does a player 99th/91st, and the top of the distribution thins). Re-
percentiling restores a true within-position spread, so "Overall" reads as a genuine percentile.

### Skaters (`config.OVERALL_WEIGHTS`)

Two lenses, the same two the card's Impact-vs-Value panel shows:

| lens | source | weight |
|---|---|---|
| Production (GAR) — "what happened" | `player_gar` percentile within position | **0.55** |
| Play-Driving (RAPM) — "what tends to repeat" | RAPM-based composite percentile within position | **0.45** |

Production is weighted slightly higher because it is the **more stable lens** year to year
(production r=0.66 vs the RAPM isolated rate r=0.38; see `GAR_STABILITY_YOY` and
[value-gar.md](value-gar.md)). This is a documented, tunable choice — deliberately **not** a hidden
50/50. The two component percentiles are computed with the **same `percent_rank` and qualified
pool** as the card's value block, so the numbers Overall averages are exactly the numbers shown
beside it (consistency rule).

### Goalies (`config.OVERALL_WEIGHTS_GOALIE`)

Goalies have no play-driving axis, so Overall averages the goalie's **within-goalie radar-axis
percentiles** (read straight from `nhl_models.goalie_radar`, so they match the radar on the card):
Overall GSAx **0.40**, High-Danger GSAx **0.30**, Consistency **0.20**, Workload **0.10** — save
value leads; workload and consistency are lighter (usage / steadiness, not pure quality). Re-
percentiled within goalies.

## Two hard rules

1. **Card-only — never a sort key.** There is no `/rankings/overall` endpoint and no ranking
   endpoint reads `player_overall` / `goalie_overall` (asserted by tests). A single averaged number
   is the wrong basis for a league ladder; the leaderboards rank by an explicit lens (WAR / RAPM /
   GAR), never by Overall.
2. **Never shown without its components.** Overall summarizes; it must not *hide* the divergence
   between its parts. The `OverallSummary` component renders the number and its component
   percentiles together in one block and returns nothing at all if the components are absent — so a
   future refactor cannot split the headline number away from what built it. When the components
   diverge, the existing (reused, not rebuilt) Impact-vs-Value read explains the gap.
