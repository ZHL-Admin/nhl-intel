# Settled-Play Gates 1+2 — locked tiling, possession-level, per-axis, slot-stratified

Gate 1 = cell IQR / shuffled-area(same-slot) IQR (tight <1; EXPECTED to pass, not the finding). **Gate 2 (THE finding) = split-half r ≥ 0.40 on possession-collapsed per-defender means (BY GAMES) AND between/within excess ≥ 1.5.** Axes: depth (dist-to-net), latsw (strong/weak lateral), distpuck. No tape, no profile, no aggregation.

- point within-depth distribution (bimodality check for later true-point vs high-slot split): {'p10': 45.9, 'p25': 48.7, 'p50': 53.4, 'p75': 57.6, 'p90': 60.0} (44=area floor, 63=blue line)


## Gate results at ≥20 goals (≥5/half); cells with ≥8 eligible defenders

### LEAD — D primary-role cells (the individual-D-settled-coverage question)

| area | slot | axis | n_def | Gate1 IQR ratio | split-half r | excess | GATE 2 |
|---|---|---|---|---|---|---|---|
| point | strong-D | depth | 181 | 1.05 | **0.31** | 1.75 | no |
| point | strong-D | latsw | 181 | 0.98 | **0.32** | 1.63 | no |
| point | strong-D | distpuck | 181 | 0.7 | **0.35** | 1.72 | no |
| slot | D | depth | 181 | 1.09 | **0.14** | 1.24 | no |
| slot | D | latsw | 181 | 0.92 | **0.64** | 4.44 | **PASS** |
| slot | D | distpuck | 181 | 0.57 | **0.11** | 1.04 | no |
| left_halfwall | strong-D | depth | 178 | 1.01 | **0.07** | 1.35 | no |
| left_halfwall | strong-D | latsw | 178 | 1.03 | **0.5** | 3.1 | **PASS** |
| left_halfwall | strong-D | distpuck | 178 | 0.78 | **0.23** | 1.51 | no |
| right_halfwall | strong-D | depth | 168 | 1.07 | **0.26** | 1.39 | no |
| right_halfwall | strong-D | latsw | 168 | 1.04 | **0.66** | 4.6 | **PASS** |
| right_halfwall | strong-D | distpuck | 168 | 0.78 | **0.5** | 2.99 | **PASS** |
| point | D | depth | 150 | 0.88 | **0.23** | 1.91 | no |
| point | D | latsw | 150 | 0.75 | **0.75** | 5.73 | **PASS** |
| point | D | distpuck | 150 | 0.45 | **0.28** | 1.71 | no |
| behind_net | strong-D | depth | 138 | 1.48 | **0.19** | 1.32 | no |
| behind_net | strong-D | latsw | 138 | 0.72 | **-0.03** | 1.09 | no |
| behind_net | strong-D | distpuck | 138 | 0.8 | **0.16** | 1.32 | no |
| left_corner | strong-D | depth | 141 | 0.96 | **0.15** | 1.37 | no |
| left_corner | strong-D | latsw | 141 | 0.91 | **0.41** | 2.75 | **PASS** |
| left_corner | strong-D | distpuck | 141 | 0.59 | **0.18** | 1.52 | no |
| right_corner | strong-D | depth | 134 | 0.89 | **0.19** | 1.12 | no |
| right_corner | strong-D | latsw | 134 | 1.0 | **0.54** | 4.0 | **PASS** |
| right_corner | strong-D | distpuck | 134 | 0.6 | **0.43** | 2.08 | **PASS** |

### All other tested cells (D and F)

| area | slot | axis | pos | n_def | Gate1 | split-half r | excess | GATE 2 |
|---|---|---|---|---|---|---|---|---|
| point | weak-low-F | depth | F | 10 | 0.9 | 0.97 | 18.74 | **PASS** |
| point | low-F | depth | F | 37 | 0.85 | 0.81 | 6.86 | **PASS** |
| point | strong-low-F | depth | F | 153 | 0.89 | 0.75 | 7.76 | **PASS** |
| behind_net | D | latsw | D | 97 | 1.61 | 0.69 | 5.93 | **PASS** |
| point | low-F | distpuck | F | 37 | 0.68 | 0.69 | 4.76 | **PASS** |
| behind_net | strong-low-F | depth | F | 149 | 1.34 | 0.67 | 4.12 | **PASS** |
| point | strong-low-F | distpuck | F | 153 | 0.71 | 0.65 | 4.46 | **PASS** |
| behind_net | strong-low-F | distpuck | F | 149 | 0.92 | 0.6 | 3.45 | **PASS** |
| right_halfwall | net-front | latsw | D | 37 | 0.93 | 0.59 | 2.55 | **PASS** |
| right_halfwall | strong-low-F | depth | F | 150 | 0.85 | 0.56 | 3.6 | **PASS** |
| left_halfwall | strong-low-F | depth | F | 166 | 0.84 | 0.55 | 4.23 | **PASS** |
| point | weak-low-F | distpuck | F | 10 | 0.82 | 0.53 | 5.03 | **PASS** |
| left_halfwall | net-front | latsw | D | 42 | 0.93 | 0.53 | 2.04 | **PASS** |
| right_halfwall | net-front | depth | D | 37 | 0.7 | 0.49 | 2.56 | **PASS** |
| right_corner | net-front | latsw | D | 59 | 1.03 | 0.49 | 2.69 | **PASS** |
| slot | low-F | depth | F | 254 | 0.89 | 0.49 | 2.6 | **PASS** |
| left_corner | strong-low-F | depth | F | 137 | 1.01 | 0.49 | 3.17 | **PASS** |
| left_halfwall | strong-low-F | latsw | F | 166 | 0.99 | 0.44 | 2.15 | **PASS** |
| point | low-F | latsw | F | 37 | 0.85 | 0.44 | 2.69 | **PASS** |
| right_corner | strong-low-F | depth | F | 156 | 1.01 | 0.43 | 3.17 | **PASS** |
| slot | net-front | latsw | D | 84 | 1.07 | 0.42 | 2.12 | **PASS** |
| behind_net | low-F | depth | F | 114 | 1.03 | 0.38 | 1.81 | no |
| left_halfwall | net-front | depth | D | 42 | 0.67 | 0.37 | 1.8 | no |
| left_corner | net-front | distpuck | D | 57 | 0.48 | 0.36 | 1.56 | no |
| left_halfwall | net-front | distpuck | D | 42 | 0.38 | 0.36 | 1.42 | no |
| left_corner | net-front | latsw | D | 57 | 1.03 | 0.34 | 1.83 | no |
| right_corner | high-F | distpuck | F | 75 | 0.9 | 0.33 | 1.99 | no |
| left_halfwall | high-F | distpuck | F | 247 | 0.9 | 0.33 | 1.86 | no |
| point | high-F | depth | F | 363 | 0.72 | 0.33 | 2.31 | no |
| left_halfwall | high-F | depth | F | 247 | 1.06 | 0.31 | 1.82 | no |
| right_halfwall | strong-low-F | latsw | F | 150 | 1.04 | 0.29 | 1.79 | no |
| left_halfwall | strong-low-F | distpuck | F | 166 | 0.84 | 0.29 | 1.98 | no |
| left_corner | strong-low-F | distpuck | F | 137 | 0.83 | 0.29 | 1.78 | no |
| point | weak-D | depth | D | 79 | 0.93 | 0.29 | 1.37 | no |
| left_corner | net-front | depth | D | 57 | 0.89 | 0.28 | 1.75 | no |
| right_halfwall | high-F | distpuck | F | 269 | 0.88 | 0.28 | 1.8 | no |
| right_corner | high-F | depth | F | 75 | 1.1 | 0.28 | 1.71 | no |
| point | high-F | distpuck | F | 363 | 0.54 | 0.28 | 1.62 | no |
| right_halfwall | net-front | distpuck | D | 37 | 0.38 | 0.26 | 1.41 | no |
| right_halfwall | high-F | depth | F | 269 | 1.03 | 0.26 | 1.86 | no |
| right_corner | strong-low-F | distpuck | F | 156 | 0.8 | 0.26 | 1.94 | no |
| slot | high-F | latsw | F | 216 | 0.96 | 0.26 | 1.62 | no |
| slot | low-F | latsw | F | 254 | 0.92 | 0.24 | 1.55 | no |
| behind_net | low-F | distpuck | F | 114 | 0.76 | 0.24 | 1.54 | no |
| right_halfwall | high-F | latsw | F | 269 | 0.96 | 0.23 | 1.4 | no |
| point | net-front | distpuck | D | 84 | 0.33 | 0.22 | 1.6 | no |
| left_halfwall | high-F | latsw | F | 247 | 0.99 | 0.22 | 1.3 | no |
| left_halfwall | weak-D | latsw | D | 34 | 0.73 | 0.21 | 1.2 | no |
| left_halfwall | weak-D | distpuck | D | 34 | 0.8 | 0.2 | 1.3 | no |
| behind_net | low-F | latsw | F | 114 | 1.25 | 0.2 | 1.34 | no |
| point | strong-low-F | latsw | F | 153 | 0.93 | 0.19 | 1.58 | no |
| left_corner | strong-low-F | latsw | F | 137 | 1.02 | 0.19 | 1.56 | no |
| right_corner | high-F | latsw | F | 75 | 1.07 | 0.19 | 1.42 | no |
| left_corner | high-F | latsw | F | 48 | 1.12 | 0.19 | 1.74 | no |
| behind_net | strong-low-F | latsw | F | 149 | 0.94 | 0.18 | 1.17 | no |
| right_halfwall | strong-low-F | distpuck | F | 150 | 0.88 | 0.18 | 1.72 | no |
| behind_net | D | distpuck | D | 97 | 0.69 | 0.18 | 1.28 | no |
| point | net-front | latsw | D | 84 | 0.87 | 0.17 | 1.41 | no |
| right_corner | net-front | depth | D | 59 | 0.9 | 0.16 | 1.52 | no |
| point | net-front | depth | D | 84 | 0.48 | 0.15 | 1.01 | no |
| point | weak-D | latsw | D | 79 | 0.71 | 0.15 | 1.08 | no |
| left_corner | high-F | distpuck | F | 48 | 0.93 | 0.15 | 1.42 | no |
| behind_net | D | depth | D | 97 | 1.63 | 0.14 | 1.23 | no |
| behind_net | net-front | depth | D | 190 | 1.75 | 0.13 | 1.5 | no |
| behind_net | net-front | latsw | D | 190 | 1.05 | 0.12 | 1.35 | no |
| behind_net | high-F | latsw | F | 180 | 1.24 | 0.1 | 1.33 | no |
| point | high-F | latsw | F | 363 | 0.86 | 0.1 | 1.11 | no |
| slot | high-F | depth | F | 216 | 1.26 | 0.1 | 1.29 | no |
| right_corner | strong-low-F | latsw | F | 156 | 1.03 | 0.09 | 1.6 | no |
| slot | net-front | depth | D | 84 | 0.76 | 0.08 | 0.93 | no |
| slot | high-F | distpuck | F | 216 | 0.81 | 0.07 | 1.22 | no |
| point | weak-low-F | latsw | F | 10 | 0.86 | 0.06 | 1.44 | no |
| behind_net | high-F | distpuck | F | 180 | 0.76 | 0.05 | 1.12 | no |
| behind_net | high-F | depth | F | 180 | 1.06 | 0.04 | 1.06 | no |
| slot | low-F | distpuck | F | 254 | 0.65 | 0.04 | 1.15 | no |
| slot | net-front | distpuck | D | 84 | 0.39 | 0.04 | 1.16 | no |
| right_corner | net-front | distpuck | D | 59 | 0.49 | 0.03 | 1.46 | no |
| right_halfwall | weak-D | latsw | D | 39 | 0.77 | 0.03 | 1.15 | no |
| left_corner | high-F | depth | F | 48 | 1.14 | 0.02 | 1.01 | no |
| point | weak-D | distpuck | D | 79 | 0.69 | 0.0 | 1.0 | no |
| right_halfwall | weak-D | distpuck | D | 39 | 0.81 | -0.01 | 0.95 | no |
| behind_net | net-front | distpuck | D | 190 | 0.42 | -0.01 | 0.96 | no |
| right_halfwall | weak-D | depth | D | 39 | 1.04 | -0.26 | 0.61 | no |
| left_halfwall | weak-D | depth | D | 34 | 1.09 | -0.29 | 0.74 | no |

## Gate results at ≥33 goals (≥5/half); cells with ≥8 eligible defenders

### LEAD — D primary-role cells (the individual-D-settled-coverage question)

| area | slot | axis | n_def | Gate1 IQR ratio | split-half r | excess | GATE 2 |
|---|---|---|---|---|---|---|---|
| point | strong-D | depth | 148 | 1.05 | **0.29** | 1.74 | no |
| point | strong-D | latsw | 148 | 0.98 | **0.2** | 1.4 | no |
| point | strong-D | distpuck | 148 | 0.7 | **0.27** | 1.64 | no |
| slot | D | depth | 137 | 1.09 | **0.19** | 1.29 | no |
| slot | D | latsw | 137 | 0.92 | **0.73** | 5.23 | **PASS** |
| slot | D | distpuck | 137 | 0.57 | **0.14** | 1.02 | no |
| left_halfwall | strong-D | depth | 124 | 1.01 | **0.17** | 1.5 | no |
| left_halfwall | strong-D | latsw | 124 | 1.03 | **0.54** | 3.1 | **PASS** |
| left_halfwall | strong-D | distpuck | 124 | 0.78 | **0.26** | 1.7 | no |
| right_halfwall | strong-D | depth | 120 | 1.07 | **0.12** | 1.19 | no |
| right_halfwall | strong-D | latsw | 120 | 1.04 | **0.69** | 5.37 | **PASS** |
| right_halfwall | strong-D | distpuck | 120 | 0.78 | **0.54** | 3.34 | **PASS** |
| point | D | depth | 78 | 0.88 | **0.21** | 1.68 | no |
| point | D | latsw | 78 | 0.75 | **0.83** | 8.71 | **PASS** |
| point | D | distpuck | 78 | 0.45 | **0.36** | 1.86 | no |
| behind_net | strong-D | depth | 55 | 1.48 | **0.18** | 1.27 | no |
| behind_net | strong-D | latsw | 55 | 0.72 | **0.22** | 1.24 | no |
| behind_net | strong-D | distpuck | 55 | 0.8 | **0.06** | 1.09 | no |
| left_corner | strong-D | depth | 52 | 0.96 | **0.24** | 1.31 | no |
| left_corner | strong-D | latsw | 52 | 0.91 | **0.32** | 2.4 | no |
| left_corner | strong-D | distpuck | 52 | 0.59 | **0.06** | 1.47 | no |
| right_corner | strong-D | depth | 69 | 0.89 | **0.04** | 0.92 | no |
| right_corner | strong-D | latsw | 69 | 1.0 | **0.45** | 3.18 | **PASS** |
| right_corner | strong-D | distpuck | 69 | 0.6 | **0.32** | 1.68 | no |

### All other tested cells (D and F)

| area | slot | axis | pos | n_def | Gate1 | split-half r | excess | GATE 2 |
|---|---|---|---|---|---|---|---|---|
| left_corner | net-front | distpuck | D | 8 | 0.48 | 0.77 | 2.36 | **PASS** |
| left_halfwall | strong-low-F | depth | F | 38 | 0.84 | 0.76 | 6.54 | **PASS** |
| point | strong-low-F | depth | F | 35 | 0.89 | 0.76 | 10.06 | **PASS** |
| point | strong-low-F | distpuck | F | 35 | 0.71 | 0.62 | 5.31 | **PASS** |
| slot | net-front | latsw | D | 14 | 1.07 | 0.61 | 4.96 | **PASS** |
| right_halfwall | strong-low-F | depth | F | 25 | 0.85 | 0.61 | 4.96 | **PASS** |
| behind_net | D | latsw | D | 11 | 1.61 | 0.58 | 5.3 | **PASS** |
| left_corner | net-front | depth | D | 8 | 0.89 | 0.55 | 2.34 | **PASS** |
| left_halfwall | strong-low-F | latsw | F | 38 | 0.99 | 0.48 | 2.16 | **PASS** |
| right_halfwall | high-F | distpuck | F | 74 | 0.88 | 0.46 | 2.29 | **PASS** |
| slot | low-F | depth | F | 57 | 0.89 | 0.45 | 2.54 | **PASS** |
| right_halfwall | strong-low-F | latsw | F | 25 | 1.04 | 0.45 | 2.72 | **PASS** |
| point | high-F | depth | F | 239 | 0.72 | 0.4 | 2.52 | no |
| left_halfwall | high-F | distpuck | F | 63 | 0.9 | 0.39 | 2.6 | no |
| right_halfwall | high-F | depth | F | 74 | 1.03 | 0.38 | 1.87 | no |
| left_corner | net-front | latsw | D | 8 | 1.03 | 0.37 | 1.79 | no |
| right_corner | strong-low-F | depth | F | 18 | 1.01 | 0.36 | 2.51 | no |
| point | net-front | distpuck | D | 23 | 0.33 | 0.35 | 1.97 | no |
| point | strong-low-F | latsw | F | 35 | 0.93 | 0.34 | 1.66 | no |
| behind_net | D | distpuck | D | 11 | 0.69 | 0.33 | 2.15 | no |
| point | net-front | latsw | D | 23 | 0.87 | 0.33 | 1.39 | no |
| left_halfwall | high-F | depth | F | 63 | 1.06 | 0.32 | 2.07 | no |
| point | high-F | distpuck | F | 239 | 0.54 | 0.31 | 1.85 | no |
| right_halfwall | high-F | latsw | F | 74 | 0.96 | 0.31 | 1.79 | no |
| right_corner | strong-low-F | distpuck | F | 18 | 0.8 | 0.28 | 2.31 | no |
| behind_net | high-F | latsw | F | 21 | 1.24 | 0.26 | 1.48 | no |
| right_halfwall | strong-low-F | distpuck | F | 25 | 0.88 | 0.26 | 2.39 | no |
| slot | low-F | latsw | F | 57 | 0.92 | 0.24 | 1.82 | no |
| left_halfwall | high-F | latsw | F | 63 | 0.99 | 0.23 | 1.57 | no |
| right_corner | strong-low-F | latsw | F | 18 | 1.03 | 0.22 | 1.58 | no |
| slot | high-F | latsw | F | 46 | 0.96 | 0.22 | 1.7 | no |
| behind_net | net-front | depth | D | 101 | 1.75 | 0.21 | 1.8 | no |
| behind_net | net-front | latsw | D | 101 | 1.05 | 0.18 | 1.57 | no |
| left_corner | strong-low-F | distpuck | F | 10 | 0.83 | 0.18 | 1.02 | no |
| slot | high-F | distpuck | F | 46 | 0.81 | 0.17 | 1.14 | no |
| left_halfwall | strong-low-F | distpuck | F | 38 | 0.84 | 0.15 | 1.55 | no |
| slot | high-F | depth | F | 46 | 1.26 | 0.15 | 1.13 | no |
| point | net-front | depth | D | 23 | 0.48 | 0.14 | 1.35 | no |
| point | high-F | latsw | F | 239 | 0.86 | 0.11 | 1.21 | no |
| behind_net | net-front | distpuck | D | 101 | 0.42 | 0.11 | 1.02 | no |
| slot | net-front | depth | D | 14 | 0.76 | 0.06 | 0.92 | no |
| behind_net | D | depth | D | 11 | 1.63 | 0.03 | 1.59 | no |
| left_corner | strong-low-F | depth | F | 10 | 1.01 | -0.02 | 0.92 | no |
| behind_net | high-F | distpuck | F | 21 | 0.76 | -0.06 | 0.71 | no |
| slot | low-F | distpuck | F | 57 | 0.65 | -0.07 | 1.18 | no |
| behind_net | high-F | depth | F | 21 | 1.06 | -0.09 | 0.71 | no |
| slot | net-front | distpuck | D | 14 | 0.39 | -0.35 | 0.84 | no |
| left_corner | strong-low-F | latsw | F | 10 | 1.02 | -0.48 | 0.54 | no |

## Summary

- Gate-2 PASS cells (r≥0.40 AND excess≥1.5): **29 at ≥20 goals**, **18 at ≥33 goals**.
- Real signal should STRENGTHEN on the cleaner ≥33 cells; noise would not.

## STOP — Gate results for owner review. No tape, no profile, no aggregation.
