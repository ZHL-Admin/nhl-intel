# Composite value stack (Phase 4.2)

Per player-season, total value decomposed into components on a common **goals** scale
(`models_ml/compute_composite.py` -> `nhl_models.player_composite`). The product rule:
components are ALWAYS shown, never a total-only number.

| component | definition |
|---|---|
| `ev_offense` | RAPM offence (xGF/60) x 5v5 TOI/60 |
| `ev_defense` | RAPM defence x 5v5 TOI/60 |
| `pp` | PP impact x PP TOI/60 |
| `pk` | PK impact x PK TOI/60 |
| `finishing` | (goals - ixG) shrunk toward 0 by individual shot volume (k=350; shooting talent stabilises ~350 shots — the team-level k of 4000 would erase all player signal) |
| `penalty_diff` | (penalties drawn - taken) x 0.2 (a power play is worth ~0.2 expected goals) |
| `goalie_gsax` | season GSAx (goalies only) |

`total` = sum of components. `total_sd` combines the component standard deviations in
quadrature (RAPM bootstrap SDs scaled by TOI; finishing ~ Poisson on goals). Windows mirror
`player_impact`: recent single seasons plus the 3-season weighted window.

## Validation

Top-20 (3-season window) is the league's best — MacKinnon, Panarin, Draisaitl, McDavid,
Kaprizov, Marner, Adam Fox, Quinn Hughes — and top goalies by composite are
Shesterkin / L. Thompson / Hellebuyck. Component splits read correctly: pure finishers carry
their value in `finishing`, playmaking drivers in `ev_offense`, PP specialists in `pp`.

## Surfaces

`GET /players/{id}` returns the components + total + sd; the PlayerProfile header renders the
diverging `ComponentStackBar` with an uncertainty whisker. The Players index ranks within
archetype by `total`, rendering the same stack per row.
