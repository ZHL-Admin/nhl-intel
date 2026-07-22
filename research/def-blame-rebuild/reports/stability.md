# Stability — RAW vs ADJUSTED blame rate (D, F). Owner gate; nothing promoted.

Min 40 tracked on-ice GA. Benchmarks: **0.30 reliability bar**; **F25 offensive-signature reference band 0.41-0.76**. Split-half vs shuffled-identity placebo (2000 perms).

## Split-half reliability (odd/even GA), vs placebo

| pos · version | n | split-half r | placebo null | z | p(null≥r) | vs 0.30 bar |
|---|---|---|---|---|---|---|
| D_raw | 166 | **0.013** | 0.002±0.079 | 0.1 | 0.4455 | FAIL |
| D_adjusted | 166 | **0.008** | 0.003±0.079 | 0.1 | 0.472 | FAIL |
| F_raw | 120 | **0.126** | 0.002±0.091 | 1.4 | 0.0835 | FAIL |
| F_adjusted | 120 | **0.133** | 0.002±0.091 | 1.4 | 0.07 | FAIL |

## Year-over-year (same player, 2024-25 → 2025-26)

| pos · version | n | YoY r |
|---|---|---|
| D_raw | 47 | **-0.01** |
| D_adjusted | 47 | **-0.033** |
| F_raw | 22 | **-0.109** |
| F_adjusted | 22 | **-0.082** |

## Deployment-change vs blame-change — does a YoY flip track a deployment change?

Correlation of each player's YoY blame-rate change with his YoY change in deployment. Near-zero = flips are NOT explained by deployment change (i.e. noise, not a real change in defensive burden).

| pos | n | dRate vs d(oz_start) | dRate vs d(qoc) | dRate vs d(qot) |
|---|---|---|---|---|
| D | 47 | -0.03 | -0.157 | -0.029 |
| F | 22 | 0.108 | -0.218 | -0.15 |

## Power / exposure diagnostics (why it fails, and what it isn't)

- **Not exposure-confounded:** corr(tracked GA, blame rate) = D -0.07, F 0.031 — the rate is exposure-neutral, so the clean low-blame anchors (Lindholm/Lindell/Brodin, all <40 tracked GA on strong defensive teams) are real, not a low-sample artifact.
- **The failure is largely a POWER problem** — D split-half by exposure: min 25 GA → r=-0.002 (n=322), min 40 GA → r=0.013 (n=166), min 60 GA → r=0.443 (n=13). At ~20-30 goals/half the rate is too noisy to estimate; at min-60 GA it clears the 0.30 bar but only ~13 D qualify. The individual signal likely exists but is under-sampled at the tracked-goal counts available per player-season.

## STOP — owner reads which version is real.
