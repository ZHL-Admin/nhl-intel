# Power ratings (Phase 3.1)

Team strength as the sum of four components, each on a **goals-per-game** scale.
See `models_ml/compute_ratings.py` for the implementation.

## Components

1. **play_5v5** - score- and opponent-adjusted 5v5 xGF% converted to a goal
   differential per game at the season's league-average 5v5 scoring.
2. **finishing** - 5v5 (goals for - xGF) per game, shrunk toward 0 by 5v5 shot
   volume with k=4000 (`FINISHING_SHRINKAGE_K`).
3. **goaltending** - even-strength GSAx (xGA - GA) per game, shrunk by EV shots
   faced with k=4000 (`GOALTENDING_SHRINKAGE_K`).
4. **special_teams** - non-5v5 goals above expected per game (PP + PK).

The three 5v5 terms additively reconstruct 5v5 goal differential; special teams is
the non-5v5 remainder, so the components do not double count.

## Opponent adjustment

Half-weighted, season-to-date (same method as the Phase 2.3 mart interim), computed
in Python from the score-adjusted xGF% input only - no dependency on the mart's own
opponent-adjusted column, so there is no circular build dependency.

## Component weights

Fit by logistic regression predicting the home win from pregame rating-component
differences (2015-16..2023-24 train), then
normalised to mean 1 so the total stays on the goals/game scale (ranking order is
invariant to positive scaling).

| component | weight | raw logit coef |
|---|---|---|
| play_5v5 | 0.993 | +0.754 |
| finishing | 1.001 | +0.761 |
| goaltending | 1.902 | +1.445 |
| special_teams | 0.103 | +0.078 |

Reading the weights: each is the predictive value of one goal/game of that component
for winning. They are not all 1.0 because the pregame season-to-date estimates differ
in reliability -- special teams regresses hard (low weight), even-strength goaltending
is comparatively stable (higher weight). Because the components scale inversely (a
heavily shrunk component has small magnitude), the weighted *contributions* stay
modest and the total stays play-driven, as the top-10 below shows.


## Win-prediction performance (rating difference -> home win)

| split | n | accuracy | log-loss |
|---|---|---|---|
| train | 11415 | 0.580 | 0.6749 |
| val | 1378 | 0.602 | 0.6678 |
| holdout | 1375 | 0.556 | 0.6813 |

Home-win base rate (train): 0.537.

## Current top-10 (2025-26)

| team_id | GP | total | play | finishing | goaltending | special |
|---|---|---|---|---|---|---|
| 21 | 95 | +0.86 | +0.62 | +0.02 | +0.12 | -0.03 |
| 12 | 102 | +0.55 | +0.62 | -0.15 | +0.04 | +0.04 |
| 14 | 89 | +0.42 | +0.36 | +0.01 | +0.03 | +0.01 |
| 7 | 95 | +0.32 | +0.09 | +0.05 | +0.09 | +0.14 |
| 9 | 86 | +0.30 | +0.43 | -0.06 | -0.03 | -0.06 |
| 68 | 88 | +0.25 | +0.21 | +0.01 | +0.02 | -0.03 |
| 15 | 82 | +0.25 | +0.02 | -0.03 | +0.14 | -0.06 |
| 29 | 82 | +0.24 | +0.24 | -0.08 | +0.05 | -0.07 |
| 5 | 88 | +0.24 | +0.16 | +0.01 | +0.03 | +0.09 |
| 25 | 88 | +0.23 | +0.09 | -0.02 | +0.07 | +0.24 |

## Deserved standings

See `models_ml/simulate_deserved.py` and `nhl_models.deserved_standings`:
each played game is replayed 10,000 times with each team's goals Poisson(its
in-game xG); points are awarded by simulated outcomes. Luck delta = actual
minus deserved points.

