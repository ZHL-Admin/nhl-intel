# System Effects

Research project that measures what coaching **systems** do to the players inside them
and to the opponents across from them: per-player **portability** scores and per-matchup
**style adjustments**, validated predictively before anything is claimed or promoted.

Isolated research layer under `NIR/research/system-effects`. **Removable by deleting this
folder with zero impact on the site** — production code never imports from here, and
production BigQuery is read-only except the explicitly gated Phase 7 promotion.

- **Reads (read-only):** frozen Deployment Atlas parquet (`../deployment-atlas/data/parquet`)
  via `atlas.api`; production BigQuery (`nhl_staging` / `nhl_models`) for audit + coach data.
- **Never modifies:** Atlas assets, or production — except gated Phase 7.
- **Seed:** `20260711` (all randomness seeded and recorded).
- **Stack:** Python 3.11+, httpx, polars, duckdb, scikit-learn, pyarrow; pytest under `tests/`.
- **Reproduce:** `make venv` then `make phaseN`. Every phase reproducible from cache and
  ends by writing `reports/phaseN.md`, then stops.

## Reports
`reports/phase{0..6}.md` · `reports/phase5-summer-addendum.md` · `reports/phase2-addendum.md` ·
`reports/FINDINGS.md` (this project, one page) · `reports/upstream-ledger.md` (defects found in
production/Atlas data). Cross-project findings: `../PROGRAM-FINDINGS.md`.

## Reproduce
`make venv` once, then `make all` (every phase + addendum from cache) or `make phaseN`.
`make report` lists the reports; `make test` runs the suite. Every phase ends by writing
`reports/phaseN.md`, then stops.

---

## Schema freeze (Phase 6.1) — **frozen 2026-07-11**

All tables live under `data/parquet/` (gitignored) and are reproducible from cache. Provenance is
**derive** (built in this research layer from frozen Atlas assets) unless marked **adopt** (reused
from an audited existing asset). Nothing here is production; promotion is Phase 7 only.

### Regime ledger
| table | grain | rows | provenance |
|---|---|---:|---|
| `regime_ledger.parquet` | (team, head coach, contiguous span) — **raw**, annotated | 235 | derive: right-rail coach backfill (2010-24) + warehouse `stg_game_context` (2024-26) + frozen Atlas `games.parquet`; `is_transient_stint`/`absorbed_into` added |
| `regime_ledger_consolidated.parquet` | consolidated analysis regime (K=4 fill-in absorption) | 201 | derive: consolidation of the raw ledger (Phase 1 §6 Option A) |

### Fingerprints v2 (per (team, regime) and (team, season))
| table | grain | provenance |
|---|---|---|
| `seq/{season}.parquet` (16) | shot-sequence-typed events | **adopt** the Atlas `int_shot_sequence` seq_type rules (reimplemented in `sequence.py`), applied to frozen events |
| `prim/{season}.parquet` (16) | summable (game, team) style/pace/location/forecheck primitives | derive from frozen stints+events, score-close where the metric responds to score state |
| `deploy/{season}.parquet` (16) | (game, team, player) 5v5 TOI + OZ/DZ starts | derive |
| `pk/{season}.parquet` (16) | (game, team) PK shot-location-against | derive |
| `team_season_fp.parquet` | (team, season) deployment + style fingerprint vector (494) | derive via the metric aggregator |

Per-metric **split-half reliability** and **coaching-sensitivity status** are frozen in
`reports/phase2.md` (+ `phase2-addendum.md`). Status summary: **coaching-sensitive** =
`zone_start_polarization` (ratio 1.9, p=0.0005) and `top6_fwd_toi_share` (ratio 1.3, p=0.023,
**stability-caveated** — no YoY persistence); **roster-property (not coaching-sensitive)** = all
style metrics (rush/cycle/forecheck/point-shot shares, shot-location, pace, forecheck-pressure)
and the PK location profile. Reliability spans r 0.61–0.99 (deployment 0.91–0.99; style/PK/location
0.57–0.85).

### Player types (pooling layer)
| table | grain | rows | provenance |
|---|---|---:|---|
| `player_types.parquet` | (player, season) with 200+ 5v5 min → 1 of 6 types | 10,961 | derive: position-stratified KMeans (seed 20260711) on RAPM off/def, OZ share, PP/PK frac, per-game TOI |

### Context primitives (multi-season build-the-delta; reconciled vs Atlas 2024-25)
| table | grain | provenance |
|---|---|---|
| `pctx/{season}.parquet` (16) | (player, team, season): 5v5 TOI, PP/PK sec, OZ/DZ starts | derive from frozen stints (Atlas `player_context` was 2024-25 only) |
| `onice/{season}.parquet` (16) | (game, team, player) 5v5 on-ice xGF/xGA (all + close) | derive |
| `depfull/{season}.parquet` (16) | (game, team, player) 5v5 TOI + PP/PK + OZ/DZ starts | derive |
| `game_coaches.parquet` | (game) home/away coach + officials + scratches, 2010-24 | derive: right-rail backfill (16,526 games) |

### Portability surface (internal, descriptive)
| table | grain | rows | provenance |
|---|---|---:|---|
| `portability.parquet` | (player, season, team): sys_contrib (+CI), system_dependence (+CI), `material`, portability | 11,395 | derive from Design B decomposition (RAPM offset vs deployment+type×deployment), 300-boot CI |
| `portability_model.json` | frozen coefficients + DEPLOY standardization + bootstrap draws | — | derive |

**Materiality rule (amendment 4.1a, frozen):** the public/primary framing is the **absolute**
system contribution `sys` (xG-share pts, with CI); the `system_dependence` ratio is secondary. A
player is labelled **system-dependent** only where `sys` 90% CI excludes zero **AND** |sys| ≥
**0.004** (= p79 of |sys| in the 2024-25 700+-min pool; p68 in the full table).

### Schedule adjustment (opponent-track survivor, descriptive-only)
| table | grain | provenance |
|---|---|---|
| `schedule_adjustment.parquet` | (player, season, team): strength-only opponent-schedule adjustment | derive (style-matchup interactions were killed at the Phase 3 gate — F15) |

### Evaluation tables
| table | grain | provenance |
|---|---|---|
| Design A | `reports/phase3_designA.json` | derive: Cohort C DiD + mediation over `depfull`/`onice` |
| Design B | `reports/phase3_designB.json` | derive: grouped-CV ridge on player-season-team rows |
| 5A frozen eval | `frozen_eval/{movers_eval_frame,stayers_eval_frame,season_start_regime_deploy,target_splithalf}.parquet` | derive; **frozen before any 5A metric was computed** |
| Prospective 2027 | `prospective_2027/frozen_predictors.parquet` | derive; 2025-26 predictor inputs frozen for the internal-track registration |

## Branch hygiene
This project reads the **frozen** Atlas parquet, not rebuilt production tables, so it must
not entangle with the concurrent `rebuild/dedup-segments-retrain` work order. Do System
Effects work on its own branch (see reports/phase0.md).
