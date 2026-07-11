# Phase 0 — Environment, asset audit, and the coach-data probe

**Project:** System Effects (`NIR/research/system-effects/`)
**Date:** 2026-07-11 · **Seed:** 20260711 · **Python:** 3.12.2 (dedicated `.venv`)
**Status:** Phase 0 complete. Two items require a decision before Phase 1 — see
**§6 Gates**. Stopping here per protocol.

---

## 1. Scaffold (0.1)

Created under `research/system-effects/`:

```
.gitignore          # data/, .venv/, __pycache__, .pytest_cache, .DS_Store
pyproject.toml      # deps + isolated pytest (pythonpath=src, testpaths=tests)
Makefile            # one target per phase (phase0 = right-rail era probe)
README.md           # scope + removal guarantee + branch hygiene
src/syseff/__init__.py
src/syseff/config.py         # SEED, paths, READ-ONLY Atlas inputs, season spans
src/syseff/probe_rightrail.py  # 0.3(c) era probe
data/                # gitignored: cache/, parquet/
reports/phase0.md
```

**CI exclusion:** repo-root `pytest.ini` sets `testpaths = tests`, so root collection
never recurses into `research/`. `system-effects` carries its own `[tool.pytest.ini_options]`
(mirrors deployment-atlas) so its tests stay isolated. Confirmed.

**Dedicated venv:** built its own `.venv` (httpx, polars, duckdb, scikit-learn, pyarrow,
pytest) rather than borrowing the Atlas venv, so the folder is self-contained and removable.

---

## 2. Atlas asset audit (0.2)

All required frozen inputs exist, import-clean, and span the full corpus. Timestamps are the
consumed file mtimes (record of what this project reads).

| Asset | File | Rows | Season span | mtime (consumed) |
|---|---|---:|---|---|
| stints | `stints.parquet` | 5,905,129 | 2010-11 … 2025-26 (16) | 2026-07-10 16:45:15 |
| events | `events.parquet` | 5,981,128 | 2010-11 … 2025-26 (16) | 2026-07-10 13:17:01 |
| player_5v5 | `player_5v5.parquet` | 10,959 | 2010-11 … 2025-26 (16) | 2026-07-10 16:46:00 |
| rapm_variant | `rapm_variant.parquet` | 13,434 | 2010-11 … 2025-26 (16) | 2026-07-10 18:01:54 |
| context metrics | `player_context_2024-25.parquet` | 708 | **2024-25 only** | 2026-07-10 17:29:48 |
| coach fingerprints | `coach_fingerprints_2024_25.parquet` | 32 | **2024-25 only** | 2026-07-10 17:30:10 |
| movers_eval | `movers_eval.parquet` | 1,705 | (held-out movers) | 2026-07-10 18:55:27 |
| frozen predictors | `prospective_2026/frozen_predictors.parquet` | 940 | prospective 2026 (read-only) | 2026-07-10 19:45:23 |
| games | `games.parquet` | 19,149 | 2010-11 … 2025-26 (16) | 2026-07-10 15:49:24 |
| shifts | `shifts.parquet` | 14,802,522 | 2010-11 … 2025-26 (16) | 2026-07-10 15:21:56 |
| shot_xg | `shot_xg.parquet` | 1,617,677 | 2010 … 2025 (16) | 2026-07-10 16:43:26 |

**`api.py` importability:** ✅ `sys.path`-insert `deployment-atlas/src`, `from atlas import api`
imports clean. Exposes `rapm_table`, `player_context`, `team_fingerprint`, `shared_toi`.
`api.rapm_table("2024-25")` → 855 player rows. `config.PARQUET_DIR` resolves to the frozen dir.
`with_matrix`/`against_matrix` are **query-derived on demand** via `api.shared_toi` (not
materialized — the full pairwise matrix is multi-million-row), consistent with the Atlas freeze.

**⚠️ Corpus-span gap (context + fingerprints).** Context metrics and coach fingerprints are
materialized **for 2024-25 only** (708 / 32 rows). The Atlas README marks both as
**derive-on-demand** from stints, and only the one season was built. System Effects needs them
multi-season. This is a *build-the-delta* task (rule 7b): re-derive per-season context and
fingerprints from the frozen stints in the research layer, matching the Atlas formulas, without
touching Atlas files. Not a defect — noted here as scoped work for Phase 1+.

**Also present (not required, useful):** `rapm_variant_prior0.parquet` (13k→3,071 rows,
**2022-23…2025-26 only** — a prior-0 sensitivity variant, not the rating of record);
`player_season_team_onice.parquet` (15,725, all 16); `boxscore_toi`, `penalty_ledger`,
`rosters`, `clean_xg_2023_24`, `top20_2024_25`.

---

## 3. Coach-data probe (0.3)

### 3(a) Warehouse first — **coaches are already ingested.**
`nhl_staging.stg_game_context` extracts `home_head_coach` / `away_head_coach` (plus per-team
`scratches`) from **`nhl.raw_game_right_rail`**, which is already ingested for the GameDetail
surface. So the right-rail source is not only confirmed — it is already partially in the
warehouse, parsed and queryable. **Prefer reuse** for the seasons it covers.

Coverage (from `stg_game_context`):

| season | games | both coaches present |
|---|---:|---:|
| 2024-25 | 1,887 | 100% |
| 2025-26 | 1,453 | 100% |
| **all earlier seasons** | — | **absent** |

Only 2024-25 and 2025-26 are ingested. Against the Atlas modeling corpus (regular-season
games), that covers **2,623** of 19,149 games; **16,526 games (2010-11 … 2023-24) are not in
the warehouse.**

Also already present: `nhl_models.player_coach_trust` (`compute_coach_trust.py`, "eye-test
usage" — how a coach deploys a player, results-independent). It is **keyed by deployment, not
coach identity**, and is stale-backbone-derived (last modified 2026-06-16, pre-rebuild). Noted
as a possible reference for Phase 3, not a coach-identity source.

### 3(b) Cached raw payloads — no right-rail.
The Atlas raw cache stores `boxscore.json` / `pbp.json` / `shifts.json` per game. Inspected
`2023020204/boxscore.json`: the gamecenter **boxscore** endpoint carries **no coach field** at
any depth (confirmed by recursive key scan). The right-rail block was never cached by Atlas.
So there is no coach data to harvest from the Atlas cache — the warehouse right-rail (§3a) is
the only existing store.

### 3(c) Era coverage — **right-rail carries headCoach across every era.**
Pre-authorized six-request probe (one regular-season game per era), cached to
`data/cache/probe/right_rail/`, ≤5 req/s with exponential backoff:

| era | game_id | home coach | away coach | referees | linesmen | scratches (h/a) |
|---|---|---|---|:--:|:--:|:--:|
| 2010 | 2010020500 | Joe Sacco | Terry Murray | ✅ | ✅ | 3/3 |
| 2013 | 2013020500 | Mike Babcock | Jon Cooper | ✅ | ✅ | 3/3 |
| 2016 | 2016020500 | Jon Cooper | Ken Hitchcock | ✅ | ✅ | 3/3 |
| 2019 | 2019020500 | Jared Bednar | Alain Nasreddine | ✅ | ✅ | 1/3 |
| 2022 | 2022020500 | Dave Hakstol | Rick Bowness | ✅ | ✅ | 2/3 |
| 2024 | 2024020500 | Rod Brind'Amour | Patrick Roy | ✅ | ✅ | 3/3 |

**Determination:** `right-rail` populates `gameInfo.{home,away}Team.headCoach.default` for
**all eras back to 2010-11** — and referees, linesmen, and scratches in the same payload every
time. **No HTML `RO{gg}.HTM` fallback is needed for coaches.** The documented fallback stays on
record only as insurance for any individual 404 during a full pass.

---

## 4. Downstream-dependency check — `player_archetypes` (0.4)

**Lineage:** `player_archetypes` is written by `models_ml/fit_archetypes_v2.py` /
`archetype_features_v2.py`, whose features read the **segment backbone**:
`nhl_staging.int_shift_segments`, `int_segment_context`, `int_on_ice_events`, plus
`mart_player_game_stats` and `nhl_models.player_coach_trust`. It is therefore
**stale-backbone-derived** — built on exactly the `int_shift_segments` layer the concurrent
rebuild is deduping.

**Freshness (BigQuery `__TABLES__`):**

| table | rows | last_modified |
|---|---:|---|
| `int_shift_segments` | 75,345,527 | **2026-07-11 03:05:15** (rebuilt) |
| `int_segment_context` | 6,375,205 | **2026-07-11 03:05:36** (rebuilt) |
| `player_archetypes` | 7,119 | **2026-06-17 16:17:03** (stale) |
| `player_coach_trust` | 4,522 | 2026-06-16 19:25:46 (stale) |

The segment backbone was rebuilt on this branch today (2026-07-11); `player_archetypes` has
**not** been re-fit since 2026-06-17. It is stale-backbone-derived **and** currently stale.

**Decision (per 0.4):** Phase 3 will **not** depend on production `player_archetypes`. It will
derive **simple archetype pools from Atlas assets** (position + Atlas-variant RAPM off/def +
context: QoC/QoT, OZ-start share, PP/PK share), which are frozen and internally consistent.
Recorded so Phase 3 does not silently inherit a stale, rebuild-divergent pooling layer.

---

## 5. Assumptions in the brief vs. reality

- ✅ **Corpus size** — brief: "19,149 games, 5.9M stints." Verified exactly: 19,149 games;
  5,905,129 stints; 16 seasons 2010-11 … 2025-26.
- 🔀 **Coach-data framing** — brief treats existence as confirmed and the probe as
  "coverage and economics." Reality is stronger: the right-rail is **already ingested** in the
  warehouse (`raw_game_right_rail` → `stg_game_context`) for 2024-25/2025-26, with coaches
  **and** scratches pre-parsed. The economics question narrows to the 16,526-game historical
  backfill; the recent two seasons are free.
- ⚠️ **Context / fingerprints span** — the brief lists them as frozen inputs; only **2024-25**
  is materialized. Multi-season use requires research-layer re-derivation from stints (§2).
- ⚠️ **Branch entanglement** — I am currently on **`rebuild/dedup-segments-retrain`**, the very
  branch the brief warns must not entangle with this project. Phase 0 only reads frozen parquet
  and BigQuery (branch-independent) and adds untracked files under `research/system-effects/`,
  so nothing is entangled yet — but System Effects should get its **own branch** off a clean
  base before any commit. Flagged as a gate (§6).
- ℹ️ `rapm_variant_prior0` covers 2022-26 only (a sensitivity variant); the rating of record
  `rapm_variant` covers all 16 seasons.

No upstream data defects found in Phase 0. `reports/upstream-ledger.md` not yet created (empty).

---

## 6. Gates — decisions needed before proceeding

**Gate A — Historical coach fetch (economics).** The era probe proves right-rail works for
every season; the warehouse already holds 2024-25/2025-26. Remaining backfill to cover the
full modeling corpus is **16,526 games (2010-11 … 2023-24)** → at ≤5 req/s, **≈55 min**, cached
+ resumable via manifest. Because right-rail carries referees, linesmen, and scratches in the
same payload at zero extra request cost, I recommend capturing all of them in one pass (serves
the officials / healthy-scratch items on the research catalog).
- **Recommendation:** approve a resumable, cached, rate-limited right-rail backfill of the
  16,526 pre-2024-25 games; reuse warehouse `stg_game_context` for 2024-25/2025-26 rather than
  re-fetch; store coaches + officials + scratches. (Optional narrower scope: primary window
  2015-16…2023-24 only = 10,887 games ≈ 36 min, with pre-2015 fetched later if needed.)
- **Not run** without approval, per the network-fetch gate.

**Gate B — Branch.** Create a dedicated branch (e.g. `research/system-effects`) off a clean
base (master) for all System Effects commits, to keep it disentangled from
`rebuild/dedup-segments-retrain`. Awaiting confirmation before committing the scaffold.

---

## 7. Removal-test verification

- `grep` for `syseff` / `system_effects` across `backend/`, `models_ml/`, `dbt/`, `ingestion/`,
  `dags/`, `frontend/src/` → **no matches.** No production code imports this project.
- All derived data is gitignored (`data/`); the folder writes nowhere outside itself except
  read-only queries against Atlas parquet and production BigQuery.
- **Deleting `research/system-effects/` has zero impact on the site.** ✅
