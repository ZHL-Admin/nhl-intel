# Win-probability model (Phase 2.4)

Logistic regression on a (regulation seconds-remaining x score-diff) one-hot
interaction plus strength differential, goalie-pulled flags, OT state, and a
pregame team-strength prior. Target: the home team won (OT/SO wins count as wins).
State backbone is int_segment_context expanded to a time grid.

Pregame prior source: `interim_xgf` (interim season-to-date score-adjusted
xGF% difference; swapped to the Phase 3 power rating via the RATING_SOURCE constant).

## Metrics

| split | n | log-loss |
|---|---|---|
| train | 1,140,895 | 0.49568 |
| holdout | 94,033 | 0.52373 |

## Calibration by decile (holdout 2025-26)

| decile | n | predicted | actual |
|---|---|---|---|
| 1 | 9,399 | 0.0442 | 0.0472 |
| 2 | 9,401 | 0.2003 | 0.2063 |
| 3 | 9,397 | 0.3359 | 0.3531 |
| 4 | 9,416 | 0.4583 | 0.4123 |
| 5 | 9,394 | 0.5212 | 0.3972 |
| 6 | 9,398 | 0.5606 | 0.4372 |
| 7 | 9,415 | 0.6156 | 0.5809 |
| 8 | 9,395 | 0.7318 | 0.6469 |
| 9 | 9,412 | 0.8711 | 0.8644 |
| 10 | 9,406 | 0.9744 | 0.9786 |

## Pregame vs market (internal calibration only, blueprint 13.2)

No in-season partner-odds snapshot was available at training time; the comparison runs automatically once `stg_partner_odds` has rows.

## Leverage

leverage(t) = WP(one more home goal) - WP(one more away goal) at the same state,
stored per game in `nhl_models.win_probability`. It peaks late in one-goal games.
