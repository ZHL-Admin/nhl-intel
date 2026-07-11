# P4 ratings-diff dossier — retrained `player_impact` + `shot_xg`

Diff of the headline downstream player rating (`player_composite.total`, a goals-scale value) after the P3 retrains + P4 consumer re-run, vs the pre-sweep snapshot `player_composite_p4pre`. Movers are the largest `total` changes; the one-line cause is each player's single largest-moving component. Positive = the retrain raised the rating.

**How to read the cause column.** The composite components trace directly to the two retrained models: `EV offense` / `EV defense` are the RAPM `off_impact` / `def_impact` from the retrained `player_impact` (goal-cut, deduped segments; game-grouped CV; replacement pooling); `finishing` is the shot-quality residual from the retrained `shot_xg` (ice-derived strength + empty-net); `PP`/`PK`/`penalty diff`/`goalie GSAx` are unchanged in spec and move only through their shared marts. So a cause of "EV defense +3.4" means the RAPM retrain raised that player's defensive impact; "finishing −2.1" means the xG retrain changed his shot-quality credit.

**Systematic pattern (ties to R1).** The shift is not noise around zero — it is a **forward→defense redistribution**. In 2024-25 the 25 largest risers are almost entirely defensemen (Chiarot, Benoit, Bouchard, Faulk, Hague…) gaining on EV offense/defense, while the 25 largest fallers are elite forwards (Lundell, J. Hughes, Guentzel, Barkov, Draisaitl, MacKinnon, Matthews…) losing EV offense. This matches the Atlas R1 finding that the goal-cut/deduped RAPM moves value toward defensemen and toward players whose on-ice results were previously over-credited to forwards. It is also why the R1 flag below matters for any *projection* consumer.


## 2025-26 — 1063 players

**League-level shift:** mean Δ -0.12, median Δ +0.00, mean |Δ| 1.21, SD 1.83 (goals). new-vs-old total corr r=0.949, Spearman ρ=0.870. 12% of players moved >3 goals; 540 up / 498 down. Mean component contribution to the shift: EV offense -0.05, PP -0.04, EV defense -0.04.


### Top 25 risers — 2025-26

| # | player | pos | Δtotal | new | old | dominant cause |
|--:|---|---|--:|--:|--:|---|
| 1 | Evan Bouchard | D | +7.9 | 15.3 | 7.5 | EV offense +4.6 |
| 2 | Sam Malinski | D | +5.9 | 9.7 | 3.8 | EV offense +5.3 |
| 3 | Kris Letang | D | +5.5 | -5.5 | -11.0 | EV offense +4.8 |
| 4 | Damon Severson | D | +5.5 | 5.9 | 0.4 | EV offense +3.9 |
| 5 | Martin Fehérváry | D | +5.5 | -5.2 | -10.7 | EV offense +3.0 |
| 6 | Jalen Chatfield | D | +5.5 | -6.7 | -12.2 | EV defense +3.1 |
| 7 | Esa Lindell | D | +5.3 | 5.8 | 0.5 | EV defense +2.9 |
| 8 | Matt Boldy | L | +5.2 | 14.5 | 9.4 | EV defense +3.4 |
| 9 | Conor Timmins | D | +5.1 | -4.0 | -9.1 | EV offense +2.5 |
| 10 | Josh Morrissey | D | +5.1 | 3.1 | -2.0 | EV offense +3.0 |
| 11 | Parker Wotherspoon | D | +5.0 | -3.0 | -8.0 | EV offense +5.9 |
| 12 | Artem Zub | D | +4.9 | -3.7 | -8.6 | EV offense +2.9 |
| 13 | Colton Parayko | D | +4.8 | 3.5 | -1.3 | EV offense +2.9 |
| 14 | Drew Doughty | D | +4.7 | 4.0 | -0.7 | EV offense +2.5 |
| 15 | Brent Burns | D | +4.6 | 4.8 | 0.2 | EV defense +3.4 |
| 16 | Valeri Nichushkin | R | +4.6 | 4.0 | -0.6 | EV defense +2.6 |
| 17 | Erik Gudbranson | D | +4.6 | -4.9 | -9.5 | EV defense +2.7 |
| 18 | Adam Pelech | D | +4.6 | 6.2 | 1.6 | EV defense +2.0 |
| 19 | Mattias Samuelsson | D | +4.5 | 0.6 | -4.0 | EV defense +2.5 |
| 20 | Joel Edmundson | D | +4.4 | -6.7 | -11.1 | EV offense +3.7 |
| 21 | Evan Rodrigues | C | +4.4 | 2.4 | -2.0 | EV offense +3.9 |
| 22 | Connor Murphy | D | +4.4 | 1.5 | -2.9 | EV offense +2.1 |
| 23 | J.J. Moser | D | +4.3 | 9.8 | 5.5 | EV offense +2.2 |
| 24 | Mike Matheson | D | +4.3 | -4.9 | -9.2 | EV defense +2.8 |
| 25 | Miro Heiskanen | D | +4.1 | 5.2 | 1.0 | EV defense +2.6 |

### Top 25 fallers — 2025-26

| # | player | pos | Δtotal | new | old | dominant cause |
|--:|---|---|--:|--:|--:|---|
| 1 | Ivan Demidov | R | -7.4 | 1.1 | 8.5 | EV defense -4.2 |
| 2 | Nathan MacKinnon | C | -7.3 | 26.0 | 33.3 | EV offense -7.0 |
| 3 | Brandt Clarke | D | -6.3 | 5.4 | 11.7 | EV offense -4.6 |
| 4 | Macklin Celebrini | C | -6.2 | 14.2 | 20.4 | EV defense -4.7 |
| 5 | Emmitt Finnie | C | -5.9 | 3.8 | 9.8 | EV offense -4.0 |
| 6 | Brady Tkachuk | L | -5.7 | 2.0 | 7.6 | EV defense -2.6 |
| 7 | Cam Fowler | D | -5.7 | -3.8 | 1.8 | EV offense -4.0 |
| 8 | Braden Schneider | D | -5.5 | -9.6 | -4.2 | EV defense -3.3 |
| 9 | Kirill Kaprizov | L | -5.3 | 14.5 | 19.8 | PP -2.0 |
| 10 | Mikey Anderson | D | -5.2 | 0.9 | 6.2 | EV defense -3.0 |
| 11 | Teuvo Teravainen | C | -5.1 | -2.5 | 2.5 | EV offense -3.5 |
| 12 | Steven Stamkos | C | -5.1 | 10.2 | 15.3 | EV offense -4.7 |
| 13 | Andrew Peeke | D | -5.1 | -5.2 | -0.2 | EV offense -2.7 |
| 14 | Kyle Connor | L | -5.0 | 6.6 | 11.7 | EV offense -2.5 |
| 15 | Mattias Ekholm | D | -5.0 | 7.0 | 11.9 | EV defense -3.8 |
| 16 | Jordan Eberle | R | -5.0 | 0.6 | 5.6 | EV defense -2.3 |
| 17 | Brock Nelson | C | -4.9 | 8.6 | 13.6 | EV offense -3.4 |
| 18 | Sean Kuraly | C | -4.8 | -2.5 | 2.4 | EV defense -2.2 |
| 19 | Connor Brown | R | -4.7 | -0.1 | 4.6 | EV offense -1.8 |
| 20 | Trevor Zegras | C | -4.7 | 9.9 | 14.6 | EV offense -3.5 |
| 21 | Blake Coleman | L | -4.7 | 2.5 | 7.2 | EV offense -2.5 |
| 22 | Zachary Bolduc | R | -4.6 | 3.5 | 8.1 | EV defense -3.0 |
| 23 | Carter Verhaeghe | C | -4.5 | 2.2 | 6.8 | EV defense -2.7 |
| 24 | Brendan Gallagher | R | -4.5 | -1.5 | 2.9 | EV defense -3.1 |
| 25 | Evander Kane | L | -4.4 | -8.6 | -4.2 | EV defense -2.9 |

## 2024-25 — 1046 players

**League-level shift:** mean Δ -0.50, median Δ -0.00, mean |Δ| 1.81, SD 2.85 (goals). new-vs-old total corr r=0.935, Spearman ρ=0.903. 21% of players moved >3 goals; 492 up / 533 down. Mean component contribution to the shift: EV offense -0.20, EV defense -0.20, PP -0.12.


### Top 25 risers — 2024-25

| # | player | pos | Δtotal | new | old | dominant cause |
|--:|---|---|--:|--:|--:|---|
| 1 | Ben Chiarot | D | +11.3 | -12.6 | -23.9 | EV defense +6.4 |
| 2 | Simon Benoit | D | +11.3 | -15.1 | -26.4 | EV defense +5.2 |
| 3 | Evan Bouchard | D | +11.2 | 13.3 | 2.2 | EV offense +6.4 |
| 4 | Adam Fantilli | C | +10.0 | -0.9 | -10.9 | EV offense +7.2 |
| 5 | Justin Faulk | D | +9.1 | -10.2 | -19.4 | EV offense +7.8 |
| 6 | Nicolas Hague | D | +8.9 | -6.0 | -14.9 | EV defense +4.2 |
| 7 | Ryan Lindgren | D | +8.5 | -7.8 | -16.3 | EV offense +5.4 |
| 8 | Cody Ceci | D | +8.5 | -19.0 | -27.5 | EV offense +4.1 |
| 9 | Brent Burns | D | +8.1 | -0.2 | -8.3 | EV defense +8.1 |
| 10 | Chandler Stephenson | C | +7.2 | -7.5 | -14.8 | EV defense +4.2 |
| 11 | Noah Hanifin | D | +7.1 | 6.8 | -0.2 | EV defense +2.6 |
| 12 | Dmitry Orlov | D | +6.8 | -0.7 | -7.5 | EV offense +4.1 |
| 13 | David Savard | D | +6.8 | -9.0 | -15.8 | EV offense +3.8 |
| 14 | Nick Jensen | D | +6.5 | -2.8 | -9.4 | EV defense +3.1 |
| 15 | Mike Matheson | D | +6.5 | -13.0 | -19.5 | EV offense +4.1 |
| 16 | Colton Parayko | D | +6.5 | 4.9 | -1.6 | EV offense +4.1 |
| 17 | Gustav Forsling | D | +6.4 | 6.7 | 0.4 | EV offense +3.8 |
| 18 | Jack Roslovic | C | +5.8 | -2.0 | -7.7 | EV defense +3.4 |
| 19 | Kris Letang | D | +5.7 | -5.4 | -11.1 | EV defense +3.0 |
| 20 | Vincent Trocheck | C | +5.7 | -5.2 | -10.8 | EV offense +3.4 |
| 21 | Shane Wright | C | +5.6 | -1.4 | -6.9 | EV defense +4.9 |
| 22 | Brock Faber | D | +5.4 | -6.9 | -12.3 | EV defense +3.6 |
| 23 | Uvis Balinskis | D | +5.4 | 0.4 | -5.0 | EV offense +2.5 |
| 24 | Ryan Pulock | D | +5.3 | -8.7 | -14.0 | EV defense +3.0 |
| 25 | Radko Gudas | D | +5.3 | -5.5 | -10.8 | PK +2.6 |

### Top 25 fallers — 2024-25

| # | player | pos | Δtotal | new | old | dominant cause |
|--:|---|---|--:|--:|--:|---|
| 1 | Anton Lundell | C | -14.8 | 6.4 | 21.2 | EV offense -7.7 |
| 2 | Jack Hughes | C | -14.5 | 12.9 | 27.3 | EV defense -6.3 |
| 3 | Jake Guentzel | C | -13.3 | 15.0 | 28.3 | EV offense -4.9 |
| 4 | Thomas Harley | D | -13.2 | 16.7 | 29.8 | EV offense -6.9 |
| 5 | Aleksander Barkov | C | -10.7 | 11.0 | 21.7 | EV offense -6.7 |
| 6 | Sebastian Aho | C | -10.4 | 10.0 | 20.4 | EV offense -5.9 |
| 7 | Matthew Tkachuk | L | -9.9 | 9.6 | 19.5 | EV offense -5.8 |
| 8 | Jake Walman | D | -9.8 | 5.3 | 15.1 | EV offense -5.1 |
| 9 | Thomas Chabot | D | -9.8 | 5.8 | 15.5 | EV offense -6.4 |
| 10 | Adam Fox | D | -9.7 | 11.6 | 21.3 | EV offense -5.0 |
| 11 | Zach Werenski | D | -9.7 | 14.2 | 23.9 | EV offense -7.2 |
| 12 | Brady Tkachuk | L | -9.6 | 2.2 | 11.7 | EV offense -6.2 |
| 13 | Leon Draisaitl | C | -9.5 | 34.1 | 43.5 | EV offense -5.3 |
| 14 | Nathan MacKinnon | C | -9.5 | 18.9 | 28.4 | EV offense -7.5 |
| 15 | Auston Matthews | C | -9.3 | 7.0 | 16.3 | EV offense -5.9 |
| 16 | Brandon Hagel | L | -9.1 | 11.9 | 21.0 | EV offense -4.8 |
| 17 | Mark Stone | R | -9.1 | 5.9 | 15.0 | EV defense -6.0 |
| 18 | Nick Suzuki | C | -8.9 | 8.2 | 17.2 | EV defense -5.4 |
| 19 | Marcus Foligno | L | -8.7 | 6.8 | 15.5 | EV defense -4.2 |
| 20 | Artemi Panarin | L | -8.7 | 15.4 | 24.1 | EV offense -6.1 |
| 21 | Zach Hyman | L | -8.6 | 4.2 | 12.8 | EV offense -7.1 |
| 22 | Moritz Seider | D | -8.3 | 3.0 | 11.3 | EV defense -5.8 |
| 23 | Robert Thomas | C | -7.9 | 10.4 | 18.3 | EV offense -6.6 |
| 24 | Ilya Mikheyev | R | -7.9 | 2.5 | 10.3 | EV defense -4.8 |
| 25 | Brett Kulak | D | -7.7 | 6.2 | 13.9 | EV defense -4.4 |

## Retrained `player_impact` — YoY Spearman (offense & defense)

Consecutive single-season windows, players with 400+ min in both. Spearman of `off_impact` and `def_impact` (the P3 report gave only the offense Pearson range).

| transition | n | offense ρ | defense ρ |
|---|--:|--:|--:|
| 2021-22→2022-23 | 523 | 0.518 | 0.319 |
| 2022-23→2023-24 | 534 | 0.464 | 0.335 |
| 2023-24→2024-25 | 542 | 0.491 | 0.359 |
| 2024-25→2025-26 | 540 | 0.432 | 0.313 |

## R1 flag — consumers that project from `player_impact` as a sole value input

Per the standing R1 rule this is **flag-only**: no consumer behavior was changed
in P4. The Atlas R1 finding is that the context-**adjusted** metric predicts
*movers* well (+3.7%) but **understates *stayers* (−7.4%)** — the adjustment
removes team/role context that actually persists for a player who stays put.

**Flagged (project future value from the adjusted lens with no raw component):**

- **`models_ml/project_roster_forecast.py`** — next-season team strength is built
  from each player's projected next-season WAR.
- **`models_ml/compute_contract_value.py`** — surplus = projected WAR × cap; the
  projection core is `blended_war_rate` (a recency/games-weighted blend of the
  last N single-season WARs, sample-regressed toward the mean).
- **`roster_player_projection`** (same `blended_war_rate` core).

All three inherit their value signal from `player_gar` → `player_impact` (RAPM).
The multi-season blend + regression-to-mean damps *variance*, but the R1 stayer
bias is a *systematic* offset, so regression does not remove it.

**NOT flagged (descriptive, not projections):** `compute_composite`,
`compute_gar`, `compute_player_radar`, `compute_deployment_efficiency`,
`build_verdict_payload`/`generate_verdicts`, `mart_player_impact_context`. These
describe what happened; R1 is about forecasting forward.

**Recommendation (for a future gated change — not applied here):** in the shared
projection core, use a **conditional raw/adjusted blend** keyed on the
stayer/mover distinction — when a player is projected to stay in the same
team/role, blend a share of his **raw** (unadjusted) on-ice production back in to
correct the −7.4% stayer understatement; keep the pure adjusted lens for players
changing team/role, where it is the more accurate predictor (+3.7%). The blend
weight is the natural tuning knob and should be fit against the R1 mover/stayer
holdout, not hand-set.
