# Goaltending: GSAx and danger splits (Phase 2.5)

Goals Saved Above Expected (**GSAx**) measures a goalie against the in-house xG model:
`GSAx = xGA - GA`, where xGA is the expected goals against and GA the actual goals against.

## Definitions

- **xGA** is summed over **all unblocked shots faced** (shot-on-goal, missed-shot, goal) —
  the same population the xG model was trained on — so xGA is calibrated against actual
  goals. Summing only on-goal shots would undershoot (the model gives P(goal | unblocked
  attempt), diluted by misses): verified, on-goal-only xGA was 5,721 vs 8,083 actual goals
  in 2024-25, while all-unblocked xGA was 8,294 (within 2.6%).
- **Shots faced / saves / save%** use **on-goal shots only** (a miss is not a save).
- The goalie is `goalie_in_net_id` (populated on ~98.5% of misses too). **Empty-net shots
  (null goalie) are excluded**, so empty-net goals never count against a goalie.

## Danger tiers (dbt vars)

Per-shot xG bounds, half-open `[lo, hi)`:

| tier | xG range |
|---|---|
| low | < 0.05 |
| medium | 0.05 – 0.15 |
| high | ≥ 0.15 |

GSAx is split by tier (`high_gsax`, `med_gsax`, `low_gsax`) and by strength (`ev_gsax`,
`special_gsax`). Mirrors `models_ml/config.DANGER_TIERS`.

## Validation

- **League GSAx ≈ 0** for recent seasons (2024-25: +20.0, 2023-24: −52.8 over ~108
  goalies). Older seasons drift more negative as league finishing vs the model shifts.
- **Top-5 GSAx, 2024-25** (≥1,200 shots): Hellebuyck (+41.5), Thompson (+30.2),
  Shesterkin (+23.2), Vasilevskiy (+21.2), Montembeault (+21.2) — the league's best, as
  expected.
- **Known bias:** league **high-danger** GSAx is systematically positive (+556 in 2024-25)
  because the xG model slightly over-predicts the highest-danger shots (its top calibration
  bin predicts ~0.21 vs ~0.17 actual). HD GSAx is therefore comparative (goalie vs goalie),
  not an absolute zero-sum; documented here so it is not mistaken for universal elite HD
  goaltending.

## Cross-validation vs NHL Edge (blueprint 12.3)

`mart_goalie_season` joins NHL Edge's goalie data as an independent second opinion. Edge
exposes only an **overall last-10 save pct** for goalies (no high-danger split), so the
sources are named distinctly: `our_hd_gsax` / `our_hd_save_pct` (ours) vs
`edge_last10_save_pct` (Edge). Agreement, 2024-25 (≥800 shots, n=44):

| comparison | correlation |
|---|---|
| our overall save% vs Edge last-10 save% | **0.72** |
| our HD save% vs Edge last-10 save% | 0.33 |

The strong overall agreement validates our save metric against an independent source; the
weaker HD correlation is expected since Edge's number is not danger-split. This page is the
12.3 cross-validation asset and is extended in Phase 7.
