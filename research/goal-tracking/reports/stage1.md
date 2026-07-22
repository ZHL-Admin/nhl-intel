# Stage 1 — Goal-against mechanism profiles

**Goal-Tracking research program** (`NIR/research/goal-tracking/`). Read-only; `make stage1` reproduces from cache. Built on the Stage 0 fused corpus.

> **LAW 1 · GOALS-ONLY.** Every tracked sequence ended in a goal; there is no tracked non-goal in this data. You may DESCRIBE and ATTRIBUTE what happened on goals and build goal-as-the-unit measurements. You may NEVER make a predictive or comparative 'what causes goals / what wins' claim from this data alone.

> **LAW 2 · FUSION.** Tracking is faithful on position (scorer within stick-reach 88% in validation) and weak on exact stick attribution in traffic (38%). Attribution NEVER comes from geometry alone: the recorded scorer/assisters from stg_play_by_play are the anchor; tracking supplies context around those labels. Cluster-level credit is acceptable; deflection micro-mechanics may remain fuzzy and are labeled as such.


> **Screen-heavy and east-west-heavy profiles implicate the defense in front of the goalie as much as the goalie himself.**


## 1.0 Working universe (AMENDMENT 2026-07-14)

**TRACKED = a ∧ b** (scorer tracked to the puck ∧ puck continuous) is the working universe for geometry fields — far broader than CLEAN (a∧b∧d, 22%) because the flight detector d does not fire on tips/tap-ins/jams (most goals). TRACKED fraction per season:

| season | goals | TRACKED | TRACKED % | flight-fired |
|---|---|---|---|---|
| 2023-24 | 8,618 | 8,001 | 92.8% | 2,273 |
| 2024-25 | 8,635 | 7,971 | 92.3% | 2,189 |
| 2025-26 | 8,693 | 7,994 | 92.0% | 2,213 |

**effective_release** = flight-start where the detector fired, else the arrival frame. release_source: arrival=19,271, flight=6,675. All release-anchored geometry (east-west window, screen count, goalie state) is recomputed at effective_release. **Handedness** for LOCATION: rosters carry none, so sourced from `stg_player_bio.shoots` (100% goalie coverage, 128 catches-L / 9 catches-R); no default needed. **No z-coordinate exists in the frames** (verified) → LOCATION high/low is omitted; glove/center/blocker only. Frame `x_std`/`y_std` only.


## 1.1 Mechanism taxonomy — rates, sensitivity, usable-n

| mechanism | definition | universe | usable-n | count | rate |
|---|---|---|---|---|---|
| EAST_WEST [G] | ew_disp_2s ≥ 15 ft | TRACKED@release | 23,966 | 15,284 | 64% |
| SCREENED [A] | screen_opp+screen_own ≥ 1 | TRACKED@release | 23,966 | 734 | 3% |
| CLEAN_LOOK [G] | screens=0 ∧ dist≥25 ft ∧ goalie_lat<3 | flight only | 6,413 | 2,772 | 43% |
| UNSET [G] | goalie_lat≥6 ∨ |depth Δ0.5s|>2 ft | TRACKED@release | 22,425 | 3,813 | 17% |
| RUSH [A] | rush_flag (entry→goal ≤6 s) | all | 25,946 | 9,304 | 36% |
| IN_ZONE [A] | not rush ∧ not off_frame_start | all | 25,524 | 1,003 | 4% |
| SECOND_CHANCE [A] | shot-family by scoring team ≤3 s prior | all | 25,946 | 4,031 | 16% |
| LOCATION [A] | net third glove/center/blocker | TRACKED@goal-line | 22,425 | — | blocker=9,367, glove=8,213, center=4,845 |

**EAST_WEST sensitivity** (frozen at 15 ft): ≥10ft=69%, ≥15ft=64%, ≥20ft=57%.

**Own-net screens** stored separately (`screened_own_net`): 758 goals have an own-team body in the screen triangle.

*Note — SCREENED is conservative (3.1%):* the frozen triangle+crease-radius screen test, evaluated at effective_release (which for the 74% no-flight goals is the puck at the net → a near-degenerate triangle), detects few screens. This is a fixed Stage-0 definition; it thins SCREENED claims (below).

## 1.1 Co-occurrence matrix (mechanisms are non-exclusive) — P(column | row) over TRACKED clips

| row \ col | EAST_WES | SCREENED | CLEAN_LO | UNSET | RUSH | IN_ZONE | SECOND_C |
|---|---|---|---|---|---|---|---|
| **EAST_WEST** (n=15284) | 100% | 2% | 5% | 20% | 35% | 4% | 15% |
| **SCREENED** (n=734) | 47% | 100% | 0% | 7% | 8% | 7% | 5% |
| **CLEAN_LOOK** (n=2232) | 35% | 0% | 100% | 3% | 53% | 3% | 2% |
| **UNSET** (n=3813) | 78% | 1% | 2% | 100% | 46% | 3% | 14% |
| **RUSH** (n=8853) | 60% | 1% | 13% | 20% | 100% | 0% | 7% |
| **IN_ZONE** (n=939) | 69% | 5% | 8% | 13% | 0% | 100% | 15% |
| **SECOND_CHANCE** (n=3734) | 60% | 1% | 1% | 15% | 16% | 4% | 100% |

Consistency checks: CLEAN_LOOK∩SCREENED = 0% (CLEAN_LOOK requires 0 screens); RUSH∩IN_ZONE = 0% (mutually exclusive by construction).

## 1.2 Goalie profiles (pooled 2023-26) + EB shrinkage + gates

Dirichlet-multinomial empirical-Bayes shrinkage toward league, prior strength **k=20 GA** (fixed), 90% CIs from 1000 posterior draws (seed 20260714). **Gates:** goalie row needs ≥40 GA (89/137 goalies qualify pooled); a mechanism cell is a *claim* only when its raw count ≥10 (low-count cells shown parenthesized).

**League rates:** EAST_WEST=64%, SCREENED=3%, CLEAN_LOOK=43%, UNSET=17%, RUSH=36%, IN_ZONE=4%, SECOND_CHANCE=16%; LOCATION glove=37%, center=22%, blocker=42%.

**Reliability verdict (§1.3): FAIL → only these pooled three-season tables ship.** *Profile is a three-season aggregate; single seasons are noise.*

| goalie | GA | EAST_WEST | SCREENED | CLEAN_LOOK | UNSET | RUSH | SECOND_CHANCE | LOC g/c/b |
|---|---|---|---|---|---|---|---|---|
| Jake Oettinger | 547 | 67 | 2 | 45 | 13 | 33 | 17 | 37/20/42 |
| Stuart Skinner | 536 | 63 | 3 | 38 | 15 | 32 | 16 | 37/23/40 |
| Juuse Saros | 535 | 66 | 3 | 39 | 21 | 32 | 16 | 36/23/40 |
| Sergei Bobrovsky | 534 | 66 | (2) | 47 | 20 | 33 | 16 | 39/20/41 |
| Connor Hellebuyck | 507 | 68 | 3 | 46 | 14 | 31 | 18 | 38/23/39 |
| Lukas Dostal | 500 | 66 | 4 | 42 | 20 | 29 | 16 | 38/23/39 |
| Igor Shesterkin | 486 | 63 | 2 | 43 | 20 | 34 | 19 | 36/21/43 |
| Ilya Sorokin | 477 | 67 | 4 | 40 | 19 | 28 | 14 | 35/21/44 |
| Jeremy Swayman | 475 | 61 | 4 | 39 | 12 | 29 | 17 | 32/26/42 |
| Andrei Vasilevskiy | 467 | 63 | 3 | 50 | 13 | 34 | 15 | 37/22/41 |
| Jordan Binnington | 461 | 66 | (2) | 38 | 19 | 29 | 16 | 38/20/42 |
| Karel Vejmelka | 457 | 67 | 3 | 45 | 18 | 34 | 23 | 37/25/37 |
| Filip Gustavsson | 432 | 65 | 3 | 48 | 18 | 33 | 17 | 37/18/44 |
| Joey Daccord | 407 | 70 | 3 | 37 | 20 | 34 | 16 | 32/22/46 |
| Mackenzie Blackwood | 404 | 62 | 3 | 45 | 18 | 33 | 17 | 39/23/37 |
| Ukko-Pekka Luukkonen | 401 | 63 | 3 | 44 | 20 | 31 | 17 | 39/20/41 |
| Elvis Merzlikins | 399 | 64 | 4 | 44 | 15 | 31 | 15 | 33/20/47 |
| Logan Thompson | 396 | 64 | 4 | 45 | 12 | 34 | 18 | 41/23/36 |
| Alexandar Georgiev | 393 | 64 | 3 | 43 | 17 | 25 | 19 | 38/19/42 |
| Samuel Montembeault | 391 | 65 | (3) | 46 | 17 | 32 | 15 | 33/24/44 |
| Jacob Markstrom | 389 | 62 | 3 | 54 | 13 | 31 | 15 | 35/22/43 |
| Linus Ullmark | 383 | 64 | 3 | 40 | 14 | 30 | 21 | 33/21/46 |
| Cam Talbot | 378 | 61 | 4 | 42 | 16 | 31 | 15 | 38/23/40 |
| John Gibson | 372 | 67 | 4 | 48 | 14 | 34 | 16 | 36/25/38 |
| Samuel Ersson | 370 | 67 | 3 | 44 | 18 | 35 | 13 | 39/19/41 |
| Darcy Kuemper | 360 | 69 | (2) | 43 | 13 | 34 | 16 | 36/20/43 |
| Dustin Wolf | 357 | 66 | 3 | 35 | 23 | 32 | 15 | 33/24/43 |
| Kevin Lankinen | 353 | 71 | 4 | 35 | 23 | 28 | 19 | 36/20/44 |
| Tristan Jarry | 346 | 67 | 4 | 51 | 13 | 36 | 18 | 36/22/42 |
| Adin Hill | 335 | 62 | 3 | 37 | 15 | 35 | 16 | 34/22/43 |
| Joseph Woll | 329 | 67 | 4 | 47 | 20 | 33 | 16 | 37/23/40 |
| Alex Nedeljkovic | 328 | 70 | 3 | 48 | 18 | 37 | 18 | 39/20/41 |
| Joonas Korpisalo | 326 | 63 | 4 | 39 | 19 | 29 | 15 | 35/26/39 |
| Charlie Lindgren | 325 | 60 | 4 | 40 | 17 | 31 | 14 | 38/20/41 |
| Arvid Soderblom | 324 | 66 | 3 | 41 | 18 | 30 | 15 | 42/22/36 |
| Alex Lyon | 313 | 60 | 6 | 36 | 17 | 31 | 18 | 38/22/39 |
| Petr Mrazek | 310 | 67 | (2) | 49 | 14 | 36 | 16 | 39/19/42 |
| Connor Ingram | 299 | 66 | 4 | 42 | 18 | 32 | 15 | 35/20/46 |
| Dan Vladar | 298 | 70 | 4 | 45 | 13 | 32 | 15 | 35/20/45 |
| Jake Allen | 290 | 62 | (3) | 40 | 13 | 33 | 21 | 37/17/45 |
| Frederik Andersen | 278 | 64 | (1) | 43 | 15 | 37 | 16 | 37/21/42 |
| Philipp Grubauer | 262 | 62 | (4) | 37 | 18 | 32 | 18 | 38/20/42 |
| Joel Hofer | 261 | 64 | (2) | 45 | 17 | 30 | 18 | 33/21/46 |
| Anton Forsberg | 260 | 64 | (2) | 48 | 20 | 27 | 17 | 36/25/40 |
| Spencer Knight | 258 | 63 | (3) | 47 | 13 | 33 | 15 | 32/23/45 |
| Scott Wedgewood | 257 | 67 | (3) | 39 | 19 | 38 | 15 | 35/23/41 |
| Pyotr Kochetkov | 251 | 61 | (3) | 47 | 16 | 38 | 17 | 43/16/41 |
| Thatcher Demko | 248 | 61 | (3) | 46 | 18 | 33 | 17 | 37/22/42 |
| Vitek Vanecek | 241 | 68 | (1) | 47 | 17 | 33 | 19 | 39/18/43 |
| Daniil Tarasov | 240 | 62 | (3) | 48 | 19 | 33 | 16 | 35/23/42 |
| Calvin Pickard | 226 | 65 | 5 | 48 | 14 | 32 | 17 | 40/17/43 |
| Casey DeSmith | 225 | 61 | (3) | 43 | 24 | 27 | 18 | 40/16/44 |
| David Rittich | 221 | 60 | (4) | 48 | 17 | 32 | 15 | 28/26/46 |
| Ilya Samsonov | 219 | 67 | 6 | 48 | 13 | 27 | 14 | 33/18/49 |
| Anthony Stolarz | 218 | 63 | (3) | 48 | 17 | 34 | 19 | 37/22/41 |
| Jonas Johansson | 218 | 60 | (4) | 43 | 20 | 33 | 13 | 32/27/41 |
| Jonathan Quick | 217 | 62 | (4) | 45 | 18 | 33 | 14 | 35/16/49 |
| Jakub Dobes | 216 | 66 | (3) | 42 | 17 | 29 | 17 | 38/20/42 |
| Yaroslav Askarov | 204 | 67 | (5) | 42 | 16 | 31 | 18 | 41/20/39 |
| Arturs Silovs | 196 | 63 | (3) | 52 | 16 | 36 | 15 | 38/30/32 |
| Jet Greaves | 194 | 63 | (2) | 35 | 16 | 32 | 12 | 36/25/38 |
| Justus Annunen | 193 | 64 | (4) | 43 | 14 | 35 | 14 | 35/22/43 |
| Marc-Andre Fleury | 182 | 64 | (5) | 35 | 19 | 27 | 13 | 41/20/39 |
| Carter Hart | 173 | 71 | (5) | 41 | 20 | 35 | 16 | 34/24/42 |
| James Reimer | 170 | 62 | (3) | 45 | 16 | 36 | 17 | 32/21/47 |
| Ville Husso | 166 | 67 | (5) | 42 | 22 | 37 | 15 | 36/20/45 |
| Eric Comrie | 151 | 70 | (2) | 50 | 17 | 28 | 18 | 40/25/35 |
| Akira Schmid | 140 | 67 | (2) | 45 | 12 | 30 | 16 | 34/21/45 |
| Jesper Wallstedt | 134 | 68 | (3) | 48 | 19 | 26 | 16 | 39/24/37 |
| Cayden Primeau | 130 | 68 | (3) | 39 | 16 | 36 | 14 | 34/25/41 |
| Kaapo Kahkonen | 121 | 69 | (6) | 35 | 17 | 36 | 17 | 35/22/42 |
| Semyon Varlamov | 115 | 67 | (8) | 37 | 14 | 31 | 17 | 39/20/41 |
| Spencer Martin | 106 | 62 | (1) | 43 | 26 | 32 | 18 | 39/20/41 |
| Brandon Bussi | 106 | 67 | (2) | 44 | 20 | 34 | 16 | 35/22/43 |
| Devin Cooley | 105 | 65 | (3) | 43 | 20 | 33 | 17 | 37/22/41 |
| Devon Levi | 103 | 68 | (2) | 52 | 19 | 32 | 21 | 38/20/41 |
| Leevi Meriläinen | 91 | 66 | (3) | 44 | 18 | 34 | 17 | 36/20/43 |
| Ivan Fedotov | 84 | 73 | (4) | 41 | 15 | 36 | 13 | 40/21/39 |
| Nico Daws | 74 | 65 | (2) | (47) | 17 | 30 | 14 | 37/28/36 |
| Nikita Tolopilo | 71 | 72 | (4) | (48) | 16 | 38 | (9) | 32/13/55 |
| Dennis Hildeby | 69 | 70 | (3) | 51 | (14) | 33 | 15 | 40/19/41 |
| Aleksei Kolosov | 65 | 70 | (2) | (43) | 16 | 32 | 22 | 33/22/44 |
| Antti Raanta | 64 | 62 | (1) | (48) | 26 | 39 | 19 | 30/28/42 |
| Martin Jones | 56 | 70 | (2) | (40) | 19 | 31 | 17 | 34/19/47 |
| Laurent Brossoit | 52 | 71 | (5) | (36) | (11) | 27 | (14) | 32/25/43 |
| Joel Blomqvist | 52 | 60 | (2) | 52 | (18) | 44 | (7) | 45/18/37 |
| Colten Ellis | 44 | 67 | (1) | (51) | (16) | 37 | 21 | 41/24/36 |
| Marcus Hogberg | 43 | 70 | (3) | (51) | (17) | 37 | (7) | 39/29/32 |
| Jacob Fowler | 42 | 71 | (1) | (44) | (16) | 41 | (15) | 36/19/45 |

(Cells are EB-shrunk shares ×100; parenthesized = raw count <10, not a claim. Full table incl. per-season rows and 90% CIs in `data/parquet/goalie_profiles.parquet`.)

## 1.3 Reliability gate (pre-stated) + year-over-year

Goalies with ≥60 GA pooled: **83**. Split each goalie's GA odd/even by game date; correlate per-goalie mechanism-share vectors across halves vs a placebo shuffling goalie identity (2000 perms). **PASS bar:** a majority of mechanisms with r≥0.30 AND placebo p<0.05.

- **1/10 mechanisms pass → GATE: FAIL.** Only **UNSET** (the goalie's own movement) is a reliable within-goalie trait; east-west, screened, rush, location and clean-look shares do not replicate across halves. **This is the empirical basis for the defense caveat: how a goalie is beaten is mostly the situation/defense in front of him, not a persistent goalie signature.**

| mechanism | n goalies | split-half r | placebo p | passes |
|---|---|---|---|---|
| UNSET | 83 | 0.34 | 0.001 | Y |
| SECOND_CHANCE | 83 | 0.14 | 0.099 | · |
| CLEAN_LOOK | 83 | 0.10 | 0.193 | · |
| EAST_WEST | 83 | 0.07 | 0.273 | · |
| LOC_center | 83 | 0.04 | 0.333 | · |
| IN_ZONE | 83 | 0.03 | 0.392 | · |
| LOC_blocker | 83 | 0.03 | 0.403 | · |
| RUSH | 83 | -0.01 | 0.531 | · |
| SCREENED | 83 | -0.05 | 0.707 | · |
| LOC_glove | 83 | -0.15 | 0.909 | · |

**Year-over-year same-goalie correlation** (descriptive, consecutive seasons ≥60 GA): EAST_WEST=0.01, SCREENED=-0.21, CLEAN_LOOK=0.05, UNSET=0.19, RUSH=-0.01, IN_ZONE=0.10, SECOND_CHANCE=-0.05, LOC_glove=0.15, LOC_center=0.06, LOC_blocker=0.07 (105 goalie-season pairs). Uniformly near zero — consistent with the split-half FAIL.

## 1.4 Exhibits (pooled, gated)

*Screen-heavy and east-west-heavy profiles implicate the defense in front of the goalie as much as the goalie himself.*


**Top-10 screen-beaten** (EB-shrunk share; only goalies with ≥10 such goals):

| rank | goalie | GA | count | EB share | 90% CI |
|---|---|---|---|---|---|
| 1 | Ilya Samsonov | 219 | 12 | 6% | 3–9% |
| 2 | Alex Lyon | 313 | 16 | 6% | 4–8% |
| 3 | Calvin Pickard | 226 | 10 | 5% | 3–7% |
| 4 | Joseph Woll | 329 | 13 | 4% | 3–6% |
| 5 | Tristan Jarry | 346 | 14 | 4% | 3–6% |
| 6 | Connor Ingram | 299 | 12 | 4% | 2–6% |
| 7 | Kevin Lankinen | 353 | 14 | 4% | 3–6% |
| 8 | John Gibson | 372 | 14 | 4% | 2–6% |
| 9 | Charlie Lindgren | 325 | 12 | 4% | 2–6% |
| 10 | Cam Talbot | 378 | 14 | 4% | 2–6% |

**Top-10 east-west-beaten** (EB-shrunk share; only goalies with ≥10 such goals):

| rank | goalie | GA | count | EB share | 90% CI |
|---|---|---|---|---|---|
| 1 | Ivan Fedotov | 84 | 57 | 73% | 65–80% |
| 2 | Nikita Tolopilo | 71 | 48 | 72% | 64–79% |
| 3 | Jacob Fowler | 42 | 29 | 71% | 61–81% |
| 4 | Laurent Brossoit | 52 | 36 | 71% | 62–79% |
| 5 | Kevin Lankinen | 353 | 234 | 71% | 67–74% |
| 6 | Carter Hart | 173 | 108 | 71% | 65–76% |
| 7 | Martin Jones | 56 | 37 | 70% | 61–79% |
| 8 | Dennis Hildeby | 69 | 44 | 70% | 63–78% |
| 9 | Marcus Hogberg | 43 | 29 | 70% | 60–79% |
| 10 | Alex Nedeljkovic | 328 | 209 | 70% | 65–74% |

**Top-10 clean-look-beaten** (EB-shrunk share; only goalies with ≥10 such goals):

| rank | goalie | GA | count | EB share | 90% CI |
|---|---|---|---|---|---|
| 1 | Jacob Markstrom | 389 | 52 | 54% | 46–61% |
| 2 | Arturs Silovs | 196 | 26 | 52% | 42–62% |
| 3 | Joel Blomqvist | 52 | 13 | 52% | 39–64% |
| 4 | Devon Levi | 103 | 15 | 52% | 40–63% |
| 5 | Tristan Jarry | 346 | 48 | 51% | 43–59% |
| 6 | Dennis Hildeby | 69 | 13 | 51% | 38–63% |
| 7 | Eric Comrie | 151 | 21 | 50% | 40–61% |
| 8 | Andrei Vasilevskiy | 467 | 71 | 50% | 44–57% |
| 9 | Petr Mrazek | 310 | 33 | 49% | 40–57% |
| 10 | Calvin Pickard | 226 | 32 | 48% | 40–57% |

**Worked profile:** _placeholder — owner to name a goalie at the gate._ On naming, this renders that goalie's full pooled mechanism mix (counts, EB shares, 90% CIs, LOCATION split) with the verbatim caveat above.

## Reproducibility & tests

- `make stage1` = mechanisms → profiles → reliability → tests → report, all from the Stage-0 cache (seed 20260714). Ratio metrics ship with absolute counts throughout.
- Upstream ledger unchanged (`reports/upstream-ledger.md`).

**STOP for owner review.**
