# In-house xG model (Phase 2.2)

Gradient-boosted (LightGBM) binary classifier over unblocked, non-empty-net,
non-shootout shots. Empty-net shots are excluded from training and scoring and
carry `xg = NULL` (and are dropped from team xG totals). Blocked shots are
excluded entirely (their coordinates are the block location). Shootouts excluded.

## Splits

- train: 2010-11 .. 2023-24 (1,514,800 shots)
- val: 2024-25 (hyperparameter grid + early stopping)
- holdout: 2025-26 (reported only)

## Features

Grouped into the decomposition buckets exposed per shot:
- **location**: distance to net (|x| normalised to the 89 ft goal line) and absolute angle
- **shot_type**: wrist / slap / snap / backhand / tip-in / deflected / wrap-around / other
- **strength**: 5v5 / PP / SH / other (relative to the shooting team)
- **sequence**: rebound, rush, forecheck, cross-ice (royal road), time since faceoff/turnover
- **game_state**: period, shooting-team home flag, score differential (clipped ±3)

Chosen hyperparameters: `{'num_leaves': 31, 'learning_rate': 0.05, 'min_child_samples': 200}`, 79 boosting rounds.

## Metrics

| split | n | log-loss | AUC |
|---|---|---|---|
| val | 121,957 | 0.22059 | 0.7443 |
| holdout | 120,669 | 0.22702 | 0.7335 |

## Calibration (10 bins, predicted vs actual goal rate)

### val

| bin | n | predicted | actual |
|---|---|---|---|
| 1 | 12,186 | 0.0081 | 0.0057 |
| 2 | 12,206 | 0.0130 | 0.0107 |
| 3 | 12,195 | 0.0184 | 0.0188 |
| 4 | 12,195 | 0.0266 | 0.0269 |
| 5 | 12,196 | 0.0390 | 0.0455 |
| 6 | 12,196 | 0.0529 | 0.0594 |
| 7 | 12,196 | 0.0702 | 0.0813 |
| 8 | 12,195 | 0.0948 | 0.1053 |
| 9 | 12,196 | 0.1373 | 0.1396 |
| 10 | 12,196 | 0.2207 | 0.1696 |

### holdout

| bin | n | predicted | actual |
|---|---|---|---|
| 1 | 12,067 | 0.0085 | 0.0069 |
| 2 | 12,067 | 0.0140 | 0.0109 |
| 3 | 12,067 | 0.0202 | 0.0196 |
| 4 | 12,066 | 0.0298 | 0.0326 |
| 5 | 12,067 | 0.0435 | 0.0452 |
| 6 | 12,067 | 0.0582 | 0.0685 |
| 7 | 12,066 | 0.0772 | 0.0908 |
| 8 | 12,068 | 0.1049 | 0.1100 |
| 9 | 12,067 | 0.1491 | 0.1278 |
| 10 | 12,067 | 0.2275 | 0.1674 |

## Predicted vs actual goals per season

(total xG vs actual goals; should agree within ~3%)

| season | shots | actual | predicted | % err |
|---|---|---|---|---|
| 2010-11 | 112,937 | 7,129 | 7181.6 | +0.7% |
| 2011-12 | 109,119 | 6,759 | 6883.4 | +1.8% |
| 2012-13 | 65,894 | 4,104 | 4118.8 | +0.4% |
| 2013-14 | 110,222 | 6,836 | 6875.7 | +0.6% |
| 2014-15 | 110,603 | 6,831 | 6920.7 | +1.3% |
| 2015-16 | 110,214 | 6,787 | 6938.8 | +2.2% |
| 2016-17 | 113,168 | 7,091 | 7165.5 | +1.1% |
| 2017-18 | 119,347 | 7,593 | 7490.6 | -1.3% |
| 2018-19 | 117,229 | 7,660 | 7426.7 | -3.0% |
| 2019-20 | 92,705 | 6,152 | 5950.4 | -3.3% |
| 2020-21 | 77,976 | 5,185 | 5014.7 | -3.3% |
| 2021-22 | 125,521 | 8,568 | 8408.6 | -1.9% |
| 2022-23 | 124,874 | 8,627 | 8820.4 | +2.2% |
| 2023-24 | 124,991 | 8,377 | 8554.3 | +2.1% |
| 2024-25 | 121,957 | 8,083 | 8305.6 | +2.8% |
| 2025-26 | 120,669 | 8,203 | 8844.2 | +7.8% |

## Decomposition

Per shot, LightGBM `pred_contrib` log-odds contributions are rolled up into the
five buckets above and converted to probability-space deltas applied sequentially
from the base rate (location -> shot_type -> strength -> sequence -> game_state).
The five deltas plus `base_rate` sum to `xg`. Stored in `nhl_models.shot_xg`.
