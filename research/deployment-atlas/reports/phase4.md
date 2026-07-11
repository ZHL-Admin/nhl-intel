# Phase 4 — RAPM audit + Atlas context layer

**Outcome:** production `player_impact` is sound in design but built on the stale,
dup-contaminated segment backbone → **a research-layer Atlas RAPM variant was
built** on the clean stint corpus and is more year-over-year stable, especially
for the recent seasons production's stale inputs hurt most. The **WOWY matrices
were DERIVED** (production marts are stale + lack an AGAINST relation). Full coach
fingerprints delivered for 2024-25.

Evidence: `reports/phase4_analysis.json`-adjacent logs; `data/parquet/rapm_variant.parquet`,
`rapm_variant_prior0.parquet`, `player_context_2024-25.parquet`,
`coach_fingerprints_2024_25.parquet`.

---

## 4.1 Spec-diff audit (Atlas spec vs production `train_rapm.py`)

| dimension | Atlas spec | production (`train_rapm.py`) | materiality |
|---|---|---|---|
| outcome / units | directional xGF/60 | `home_xg/dur*3600` per attacking dir | match |
| observation grain | 2 rows/stint (per attack dir) | `expand_rows` — 2 rows/segment | match |
| weight | stint seconds | `dur × season_weight` | match |
| off/def coefs | +1 attackers off, +1 defenders def; report off, −def | `build_design(two_sided)`, `player_impacts` centre + negate def | match |
| context: home | yes | `home` control | match |
| context: score state | yes | `home_score_state`, flipped per dir | match |
| context: zone start | yes | `zone_start_code` (O/D/N, OTF=ref) | match |
| context: game-time bucket | yes | **absent** (has back-to-back + season FE instead) | **minor diff** |
| fit window | season + prior×0.5 (sens 0/1) | 3-yr window [0.3,0.6,1.0] + independent singles | **diff** |
| lambda | ridge, **5-fold** CV grouped by game, grid 1e2–1e6 (13 pts) | **single 80/20** game holdout, grid 250–8000 (6 pts) | **material diff** |
| replacement pooling | pool <100min into REPL by pos (F/D) | **absent** (own column for everyone; toi≥200 filter at report) | **material diff** |
| exclude <5s stints | yes | `>= 4s` | trivial diff |
| exclude 753 quarantined stints | yes | n/a (uses stale segments' own >6/side filter) | diff (different exclusion) |
| strength source | the ice | `int_segment_context.strength_state` (shift-derived, the ice) | **match (good)** |
| **input lineage** | clean deduped stints incl. backfill | **`int_shift_segments` × `int_segment_context` × `int_on_ice_events`** | **material — contaminated** |

### Lineage determination + coverage
`player_impact` is built **entirely on `int_shift_segments`** (and its
descendants) — the **stale, dup-contaminated backbone** (Phase 2): a materialized
table from 2026-07-06 that **contains none of the 563 backfilled games** and only
895/1312 of 2025-26. Strength comes from `int_segment_context.strength_state`
(shift-derived — the ice, **not** situationCode; good). Effective per-season
coverage of `player_impact`'s 5v5 stints therefore **misses 57 games in 2024-25
and 505 in 2025-26 (≈38% of the season)** — inherited directly from the stale
segments. `player_impact` spans single-season windows 2015-16→2025-26 + a 3-yr window.

## 4.2 Production RAPM validation

- **YoY Spearman (400+ min both):** off 0.40–0.45, def 0.19–0.30 — in the expected
  bands, **except 2024-25→2025-26 (off 0.334, def 0.186)**, degraded by the stale
  2025-26 inputs.
- **Face validity 2024-25 (top-10 off):** MacKinnon, Hyman, Thomas, B.Tkachuk,
  M.Tkachuk, Gallagher, J.Hughes, Draisaitl, Werenski, Fox — sound.
- **Bootstrap SD sanity:** `corr(toi, off_sd) = +0.32` — SD does **not** shrink with
  TOI as naively expected. Explained by ridge shrinkage (low-TOI players shrunk to
  ~0 → small coef + small SD; high-TOI players → larger coef + larger absolute SD).
  A coefficient-of-variation view would show the expected shrinkage; flagged.

## 4.3 Atlas RAPM variant — BUILT (trigger: contaminated inputs)

Trigger met: production is built on stale/contaminated inputs (missing backfilled
games incl. 38% of 2025-26). (Zone-start + score-state *are* present in production,
so that trigger did not apply — the input trigger did.) `src/atlas/rapm.py` refits
the same two-sided ridge on the **clean Atlas stints** (deduped, backfilled,
goal-cut, quarantine-excluded, shift-strength), following the spec exactly:
2-rows/stint, y=xGF/60, weight=seconds, off/def columns, controls (home-attacking,
score state, startType, game-time bucket), **5-fold game-grouped CV** over 13
log-spaced λ (1e2–1e6), season+prior×0.5, exclude <5s + the 753 quarantined stints,
**replacement pooling** of <100-min players by F/D. Fit for 2019-20→2025-26
(2025-26 on **393,748 stints — the full backfilled season**, vs production's ~62%).

**λ CV curve (2024-25):** clean U-shape, minimum at **α=46,416** (wMSE 92.73;
endpoints 92.85 @1e2, 92.98 @1e6).

**Face validity 2024-25 (top-10 off):** MacKinnon, McDavid, B.Tkachuk, Draisaitl,
Crosby, Hyman, Gallagher, M.Tkachuk, Matthews, Thomas — cleaner than production
(McDavid/Crosby/Matthews correctly top-10). Top-10 def: Reinhart, Foligno, Tanev,
Pelech, Hanley, Benson, Blake, Foerster, Schmidt, Anderson.

### Head-to-head YoY stability (4.5)
The headline variant (prior×0.5) shows off 0.65–0.74 / def 0.60–0.71 — **but that
is inflated**: prior×0.5 makes consecutive-season fits share data (the 2025-26 fit
contains 2024-25×0.5), so their correlation overstates true stability vs
production's independent singles. **The fair comparison uses the prior=0.0
sensitivity variant (independent singles):**

| pair | variant (prior=0.0) off / def | production off / def |
|---|---|---|
| 2022-23→2023-24 | 0.453 / 0.349 | 0.454 / 0.292 |
| 2023-24→2024-25 | 0.471 / 0.364 | 0.399 / 0.280 |
| 2024-25→2025-26 | **0.406 / 0.313** | **0.334 / 0.186** |

Even fairly, the variant is **modestly-to-clearly more stable** — defence notably
so (0.31–0.36 vs 0.19–0.29) — and **the gap is largest for 2024-25→2025-26**,
exactly where production's stale/missing games bite. Bootstrap SD was not computed
for the variant (compute cost); YoY stability is the primary evidence.

## 4.4 Atlas context layer

### (a) WITH / AGAINST matrices — DERIVED
Audited `mart_player_onice`, `mart_player_toi_matrix`, `mart_player_wowy`: all
**modified 2026-07-02** — before the backfill+dedup, so **stale + missing the 563
games**; and `mart_player_toi_matrix` is **teammates-only (no AGAINST relation)**.
Both gates fail → **DERIVE** WITH (teammate) and AGAINST (opponent) shared-TOI at
5v5 from the clean stints (grain season, A, B, relation, toi).

### (b) Descriptive context per player-season (2024-25; 708 players ≥200 min)
`player_context_2024-25.parquet`: **QoC/QoT** = shared-TOI-weighted mean of
opponents'/teammates' **prior-season rating** — chosen = the **Atlas variant** (2023-24
`off+def`), since it was built and is cleaner than production. Plus **OZ start share**,
**matchup strictness** (Herfindahl of the player's opponent-forward TOI distribution —
approximated over opponent forwards, not lines; documented), and **PP/PK TOI shares**.
Highest-QoC 2024-25: Lindholm, Matthews, and checking forwards (Dickinson) — face-valid
(tough-minutes players). QoC spread is narrow (−0.006…0.064), as expected.

### (c) Coach fingerprints per team-season — full 2024-25 table

Metrics: **top6F** = top-6 forward share of team 5v5 TOI (concentration);
**HAstrict** = home−away matchup strictness for the team's top-3 defensive forwards
(last change → positive); **polar** = std dev of OZ-start share across the roster
(≥200 min); **shorten** = top-6-F TOI share in close (≤1 goal) 3rd periods minus overall.

| TEAM | top6F | HAstrict | polar | shorten | | TEAM | top6F | HAstrict | polar | shorten |
|---|---|---|---|---|---|---|---|---|---|---|
| TBL | .582 | −.013 | .080 | +.039 | | EDM | .526 | +.020 | .080 | +.039 |
| LAK | .561 | −.001 | .051 | +.060 | | BUF | .524 | −.023 | .069 | +.020 |
| CGY | .557 | +.112 | .088 | +.039 | | UTA | .523 | −.006 | .060 | +.019 |
| WPG | .554 | +.001 | .161 | +.024 | | DAL | .519 | −.005 | .066 | +.030 |
| NYR | .550 | −.004 | .137 | +.018 | | VAN | .514 | +.001 | .087 | +.030 |
| MTL | .545 | −.009 | .132 | +.023 | | CBJ | .514 | .000 | .077 | +.021 |
| FLA | .542 | −.009 | .030 | +.038 | | NSH | .513 | +.009 | .142 | +.015 |
| WSH | .539 | −.031 | .177 | +.048 | | BOS | .510 | −.001 | .148 | +.048 |
| TOR | .539 | +.021 | .126 | +.048 | | PIT | .509 | +.003 | .138 | +.013 |
| NJD | .537 | +.019 | .099 | +.051 | | VGK | .506 | −.027 | .052 | +.017 |
| OTT | .535 | −.025 | .087 | +.038 | | SJS | .506 | −.057 | .051 | +.027 |
| CHI | .532 | +.002 | .072 | +.020 | | CAR | .499 | .000 | .045 | +.033 |
| STL | .532 | −.001 | .094 | +.026 | | COL | .495 | −.080 | .115 | +.035 |
| ANA | .531 | .000 | .085 | +.018 | | | | | | |
| PHI | .531 | +.044 | .095 | +.017 | | | | | | |
| SEA | .531 | −.006 | .040 | +.039 | | | | | | |
| MIN | .530 | +.038 | .064 | +.035 | | | | | | |
| DET | .529 | +.018 | .047 | +.020 | | | | | | |
| NYI | .528 | +.035 | .052 | +.033 | | | | | | |

## 4.5 Tests / sanity

- Production validation: §4.2. Variant: §4.3 (YoY fair + inflated, λ curve, head-to-head).
- **Close-game bench shortening is positive for all 32 teams** (+0.013…+0.060) —
  coaches lean on the top-6 in close 3rd periods, as expected.
- **Home−away strictness: only 14/32 teams positive (43.75%)** — the last-change
  effect is weak in this metric. Likely because Herfindahl over *all* opponent
  forwards is too coarse (last change targets a specific top line); flagged as a
  metric-refinement item, not a pipeline error.
- Matrices: **derived** (marts stale + no AGAINST); documented in (a).

---

## Summary

- Production RAPM audited: sound design, **built on stale/contaminated segments**
  (misses 38% of 2025-26) — this triggered the variant.
- **Atlas variant built** on clean stints; more YoY-stable even in the fair
  (prior=0.0) comparison, with the largest edge on 2024-25→2025-26.
- WOWY matrices **derived**; full descriptive context + coach fingerprints for 2024-25.
- Production untouched. Upstream ledger updated (segment backbone entry stands).

**Phase 4 complete. Stopping per the preamble; awaiting Phase 5 (rule-7b-revised).**
