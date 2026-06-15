# Win-probability model (Phase 2.4)

Logistic regression on a (regulation seconds-remaining x score-diff) one-hot
interaction plus strength differential, goalie-pulled flags, OT state, and a
pregame team-strength prior. Target: the home team won (OT/SO wins count as wins).
State backbone is int_segment_context expanded to a time grid.

Pregame prior source: `power_rating` (Phase 3.1 power rating: pregame total_rating
difference from nhl_models.team_ratings, an opponent-and-score-adjusted goals/game prior).
Swapped from the interim season-to-date score-adjusted xGF% prior via the RATING_SOURCE constant.

### Rating-source lift (power rating vs interim xGF prior)

Refitting with the Phase 3.1 power-rating prior moves holdout (2025-26) log-loss from
the interim ~0.524 to **0.52332**, and train log-loss from ~0.496 to **0.49456**.
The lift is small by design: the pregame prior governs only the pregame/early-game
regime, after which the seconds-remaining x score-diff interaction dominates. The
prior is now the richer opponent-adjusted rating rather than a raw xGF% share.

## Metrics

| split | n | log-loss |
|---|---|---|
| train | 1,140,895 | 0.49456 |
| holdout | 94,033 | 0.52332 |

## Calibration by decile (holdout 2025-26)

| decile | n | predicted | actual |
|---|---|---|---|
| 1 | 9,404 | 0.0435 | 0.0594 |
| 2 | 9,401 | 0.2052 | 0.1974 |
| 3 | 9,387 | 0.3362 | 0.3227 |
| 4 | 9,415 | 0.4560 | 0.3927 |
| 5 | 9,383 | 0.5179 | 0.4722 |
| 6 | 9,420 | 0.5563 | 0.4397 |
| 7 | 9,404 | 0.6082 | 0.5184 |
| 8 | 9,407 | 0.7275 | 0.6877 |
| 9 | 9,393 | 0.8656 | 0.8556 |
| 10 | 9,419 | 0.9762 | 0.9784 |

## Pregame vs market (internal calibration only, blueprint 13.2)

No in-season partner-odds snapshot was available at training time; the comparison runs automatically once `stg_partner_odds` has rows.

## Leverage

leverage(t) = WP(one more home goal) - WP(one more away goal) at the same state,
stored per game in `nhl_models.win_probability`. It peaks late in one-goal games.
