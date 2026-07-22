# D-only defensive blame — statistical-estimation pass (evaluation; nothing promoted)

Estimators that borrow strength, each split-half tested on the ESTIMATE (not the raw rate), + placebo, + out-of-sample predict-next-xGA lift. 0.30 reliability bar; F25 offensive reference 0.41-0.76.


## BLEND — split-half reliability of each estimator (pooled 3-season)

| pool | estimator | n | split-half r | placebo p(null≥r) | vs 0.30 |
|---|---|---|---|---|---|
| min-60 | naive | 174 | **0.176** | 0.0115 | FAIL |
| min-60 | eb | 174 | **0.167** | 0.0175 | FAIL |
| min-60 | rapm | 174 | **0.162** | 0.018 | FAIL |
| min-100 | naive | 102 | **0.156** | 0.0635 | FAIL |
| min-100 | eb | 102 | **0.146** | 0.076 | FAIL |
| min-100 | rapm | 102 | **0.025** | 0.405 | FAIL |

**blend — predict next-season xGA/60 (n=106):** xGA-AR baseline R²=0.166; incremental over baseline → +naive +0.002, +EB +0.001, +RAPM +0.010.

## COVERAGE — split-half reliability of each estimator (pooled 3-season)

| pool | estimator | n | split-half r | placebo p(null≥r) | vs 0.30 |
|---|---|---|---|---|---|
| min-60 | naive | 174 | **0.162** | 0.018 | FAIL |
| min-60 | eb | 174 | **0.133** | 0.045 | FAIL |
| min-60 | rapm | 174 | **0.131** | 0.049 | FAIL |
| min-100 | naive | 102 | **0.161** | 0.054 | FAIL |
| min-100 | eb | 102 | **0.126** | 0.0965 | FAIL |
| min-100 | rapm | 102 | **0.046** | 0.328 | FAIL |

**coverage — predict next-season xGA/60 (n=106):** xGA-AR baseline R²=0.166; incremental over baseline → +naive +0.000, +EB +0.000, +RAPM +0.003.

## A5 feasibility — expand numerator to chances

The tracking corpus (`fused_goals`, 25,946 events / 4,250 games) is **GOALS-ONLY** — non-goal shots have no tracking frames. Extending the coverage blame-geometry to high-danger chances would multiply events ~5-10x (shots) / ~3-4x (high-danger), but is NOT computable on the current data (no frames on non-goal shots). It requires new tracking ingestion on shot events — a data-acquisition lever, not an analysis one.


## STOP — owner reads which estimator (if any) graduates.
