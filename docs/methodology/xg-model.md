# In-house xG model (Phase 2.2)

Gradient-boosted (LightGBM) binary classifier over unblocked, non-empty-net,
non-shootout shots. Empty-net shots are excluded from training and scoring and
carry `xg = NULL` (and are dropped from team xG totals). Blocked shots are
excluded entirely (their coordinates are the block location). Shootouts excluded.

## Splits

- train: 2010-11 .. 2023-24 (1,513,063 shots)
- val: 2024-25 (hyperparameter grid + early stopping)
- holdout: 2025-26 (reported only)

## Features

Grouped into the decomposition buckets exposed per shot:
- **location**: distance to net (|x| normalised to the 89 ft goal line) and absolute angle
- **shot_type**: wrist / slap / snap / backhand / tip-in / deflected / wrap-around / other
- **strength**: 5v5 / PP / SH / other (relative to the shooting team)
- **sequence**: rebound, rush, forecheck, cross-ice (royal road), time since faceoff/turnover
- **game_state**: period, shooting-team home flag, score differential (clipped ±3)

Chosen hyperparameters: `{'num_leaves': 63, 'learning_rate': 0.05, 'min_child_samples': 200}`, 55 boosting rounds.

## Metrics

| split | n | log-loss | AUC |
|---|---|---|---|
| val | 121,957 | 0.22062 | 0.7441 |
| holdout | 120,410 | 0.22689 | 0.7334 |

## Calibration (10 bins, predicted vs actual goal rate)

### val

| bin | n | predicted | actual |
|---|---|---|---|
| 1 | 12,185 | 0.0107 | 0.0055 |
| 2 | 12,201 | 0.0150 | 0.0110 |
| 3 | 12,198 | 0.0204 | 0.0190 |
| 4 | 12,192 | 0.0281 | 0.0267 |
| 5 | 12,202 | 0.0403 | 0.0430 |
| 6 | 12,196 | 0.0532 | 0.0621 |
| 7 | 12,196 | 0.0702 | 0.0827 |
| 8 | 12,195 | 0.0937 | 0.1042 |
| 9 | 12,196 | 0.1342 | 0.1377 |
| 10 | 12,196 | 0.2143 | 0.1709 |

### holdout

| bin | n | predicted | actual |
|---|---|---|---|
| 1 | 12,034 | 0.0110 | 0.0070 |
| 2 | 12,029 | 0.0160 | 0.0110 |
| 3 | 12,060 | 0.0221 | 0.0192 |
| 4 | 12,040 | 0.0314 | 0.0335 |
| 5 | 12,042 | 0.0445 | 0.0440 |
| 6 | 12,041 | 0.0584 | 0.0682 |
| 7 | 12,040 | 0.0770 | 0.0919 |
| 8 | 12,042 | 0.1030 | 0.1083 |
| 9 | 12,041 | 0.1457 | 0.1276 |
| 10 | 12,041 | 0.2206 | 0.1690 |

## Predicted vs actual goals per season

(total xG vs actual goals; should agree within ~3%)

| season | shots | actual | predicted | % err |
|---|---|---|---|---|
| 2010-11 | 111,236 | 6,998 | 7066.0 | +1.0% |
| 2011-12 | 108,537 | 6,726 | 6850.6 | +1.9% |
| 2012-13 | 65,894 | 4,104 | 4120.9 | +0.4% |
| 2013-14 | 110,221 | 6,836 | 6878.0 | +0.6% |
| 2014-15 | 111,176 | 6,832 | 6949.7 | +1.7% |
| 2015-16 | 109,031 | 6,670 | 6855.8 | +2.8% |
| 2016-17 | 114,182 | 7,091 | 7211.8 | +1.7% |
| 2017-18 | 119,450 | 7,594 | 7501.2 | -1.2% |
| 2018-19 | 117,265 | 7,660 | 7436.1 | -2.9% |
| 2019-20 | 92,722 | 6,164 | 5942.0 | -3.6% |
| 2020-21 | 77,976 | 5,185 | 5015.7 | -3.3% |
| 2021-22 | 125,510 | 8,566 | 8395.7 | -2.0% |
| 2022-23 | 124,872 | 8,627 | 8784.9 | +1.8% |
| 2023-24 | 124,991 | 8,377 | 8546.2 | +2.0% |
| 2024-25 | 121,957 | 8,083 | 8294.0 | +2.6% |
| 2025-26 | 120,410 | 8,185 | 8786.9 | +7.4% |

## Decomposition

Per shot, LightGBM `pred_contrib` log-odds contributions are rolled up into the
five buckets above and converted to probability-space deltas applied sequentially
from the base rate (location -> shot_type -> strength -> sequence -> game_state).
The five deltas plus `base_rate` sum to `xg`. Stored in `nhl_models.shot_xg`.
