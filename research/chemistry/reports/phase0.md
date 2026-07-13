# Phase 0 — Scaffold, asset audit, and the fit-incumbent inventory

**Project:** Chemistry (`NIR/research/chemistry/`)
**Date:** 2026-07-12 · **Seed:** 20260712 · **Python:** dedicated `.venv` (3.11+)
**Status:** Phase 0 complete. One low-stakes setup decision is flagged for the record (branch
base, §6). Stopping per protocol.

---

## 1. Scaffold (0.1)

Created under `research/chemistry/`: `.gitignore` (data/, .venv/, __pycache__, .pytest_cache,
.DS_Store, reports/_*), `pyproject.toml` (polars/duckdb/pyarrow/scikit-learn + isolated pytest
`pythonpath=src, testpaths=tests`; httpx pinned as a transitive requirement of `atlas.api`'s import
chain), `Makefile` (target per phase), `README.md`, `src/chem/{__init__,config,phase0}.py`,
`tests/test_phase0.py`, `reports/`, `data/` (gitignored).

- **CI exclusion:** repo-root `pytest.ini` sets `testpaths = tests`, so root collection never
  recurses into `research/`. Chemistry carries its own `[tool.pytest.ini_options]` — confirmed.
- **Dedicated venv:** its own `.venv`, self-contained and removable.
- **Removal test:** `grep` for `chem` / `research/chemistry` imports across `backend/`,
  `models_ml/`, `dbt/`, `ingestion/`, `dags/`, `frontend/src/` → **no matches.** Deleting
  `research/chemistry/` has zero site impact. ✅

---

## 2. Frozen-asset audit (0.2)

All required frozen inputs from both prior projects exist, import-clean, and span the corpus.

| project | asset | rows | season span | mtime (consumed) |
|---|---|---:|---|---|
| Atlas | `stints.parquet` | 5,905,129 | 2010-11 … 2025-26 (16) | 2026-07-10 16:45:15 |
| Atlas | `events.parquet` | 5,981,128 | 2010-11 … 2025-26 (16) | 2026-07-10 13:17:01 |
| Atlas | `player_5v5.parquet` | 10,959 | 2010-11 … 2025-26 (16) | 2026-07-10 16:46:00 |
| Atlas | `rapm_variant.parquet` | 13,434 | 2010-11 … 2025-26 (16) | 2026-07-10 18:01:54 |
| Atlas | `movers_eval.parquet` | 1,705 | (15 season-pairs) | 2026-07-10 18:55:27 |
| Atlas | `src/atlas/api.py` | — | importable (needs httpx) | — |
| SysEff | `player_types.parquet` | 10,961 | 2010-11 … 2025-26 (16) | 2026-07-11 21:08:26 |
| SysEff | `team_season_fp.parquet` (fingerprints) | 494 | 2010-11 … 2025-26 (16) | 2026-07-11 17:32:22 |
| SysEff | `regime_ledger.parquet` (raw) | 235 | — | 2026-07-11 21:08:05 |
| SysEff | `regime_ledger_consolidated.parquet` | 201 | — | 2026-07-11 11:56:33 |
| SysEff | `src/syseff/api.py` | — | importable | — |

**API importability:** `atlas.api` (exposes `rapm_table`, `player_context`, `shared_toi`) and
`syseff.api` (exposes `portability`, `predicted_delta`, `portability_leaderboard`) both import with
`httpx` present. Parquet reads use polars directly on the frozen files; the APIs are used only where
their query logic is convenient. **Neither project's `prospective_20xx/` dir is touched.**

**Fingerprints note:** the spec's "fingerprints_v2" resolves to two frozen artifacts —
`team_season_fp.parquet` (494, **season** grain) is the accessible research parquet; the per-**regime**
`fingerprints_v2` (201) lives as a System Effects Phase-7 dbt seed (staged, not deployed). Chemistry
uses the season-grain parquet; the regime-grain one is available if a later phase needs it.

---

## 3. Production pair/line inventory (0.3a)

Read-only. **Every pair/line asset is rebuilt-backbone-derived** (`int_segment_*`), the layer System
Effects measured as ~8% divergent from the frozen Atlas stints on shot counts. Per rule 7b +
strength-is-ice-derived, Chemistry **derives its pair corpus from the frozen stints** and audits
these marts rather than reusing them.

| asset | grain | carries OUTCOMES? | coverage | lineage |
|---|---|---|---|---|
| `mart_player_toi_matrix` | (season, team, a<b) teammates | **no** — shared 5v5 TOI only | 2010-26 | `int_segment_5v5_results` (rebuilt) |
| `mart_player_toi_against` | (season, a<b) opponents | **no** — shared TOI only | 2010-26 | `int_segment_5v5_results` (rebuilt) |
| `mart_player_wowy` | (season, team, focal→partner) directional | **YES** — 5v5 xGF% together vs apart; `small_sample` < 3000 s | 2010-26, **418,594** rows | `seg_results` + `mart_player_onice` (rebuilt) |
| `int_line_seasons` | (season, team, F3 trio / D2 pair) | **YES** — line 5v5 xGF/xGA | **2015-16+ only** (segments) | `int_segment_context` (rebuilt) |
| `mart_player_entanglement` | (season, player, team) | diagnostic (max-partner share, entropy, `entangled`>0.55) | 2010-26 | `mart_player_toi_matrix` |

**Takeaways.** Production already has a pair-outcome asset (`mart_player_wowy`, full span) and a line-
outcome asset (`int_line_seasons`, 2015-16+) — but both are rebuilt-backbone, `mart_player_wowy` is
directional/naïve (raw together-vs-apart, not persistence-tested), and `int_line_seasons` is
span-limited. Chemistry's frozen-stint pair corpus (full span, ice-derived) is the *delta*, and
`mart_player_wowy` is the rule-7b audit target. `mart_player_entanglement` is the built-in
identifiability warning (O3 D-pair-locking).

---

## 4. The fit incumbent (0.3b)

**What powers Player Fit / Better Fits today = the Lineup Lab line-fit model + Player Fit's LINE
dimension.** This is what Chemistry would replace/upgrade.

- **`models_ml/train_linefit.py` → `artifacts/linefit_v1.joblib`** (trained **2026-07-11 09:25**):
  a **cold-start** predictor of a hypothetical line's 5v5 results (three LightGBM heads: xGF%,
  xGF/60, xGA/60) from its members' **individual** player-season profiles. Trained on
  `int_line_seasons` (rebuilt-backbone, 2015-16+), GroupKFold by season, weighted by shared minutes;
  ships only if it beats (a) the member-mean individual xGF% and (b) the team-season xGF%.
- **"Chemistry" today is hand-crafted STATIC similarity, not a learned/validated trait**
  (`linefit_features.aggregate_line`): archetype-cosine, shot-location overlap, handedness balance,
  burst-rate spread, o-zone-tilt — profile-similarity proxies, **no observed pair outcome enters the
  features**. At *scoring* time, `score_line.py` adds a **"chemistry-blended projection"** only when
  the exact line has real shared history — i.e. a naïve blend with observed WOWY, not a persistence-
  tested pair trait.
- **`models_ml/score_team_fit.py` (Player Fit):** `fit = floor + (1−floor)·match`, `match =
  weighted(need, style, LINE)`; the **LINE** dimension consumes the linefit model's "pairwise
  contributions (talent-independent)."

**Does it make chemistry-like claims today?** Yes — "pairwise chemistry features" and a "chemistry-
blended projection." But the chemistry is (i) static profile similarity and (ii) a naïve observed-
history blend; **neither tests whether pair over/under-performance beyond individual quality is a
persistent trait, and neither validates on never-before-seen pairs.** That gap is exactly this
project's mandate — the keystone persistence test (Phase 2) and out-of-sample pair validation
(Phase 5) are what would justify replacing the hand-crafted proxies + naïve blend with a learned,
validated pair-fit embedding.

---

## 5. Derivation cost probe (0.4)

**Feasibility CONFIRMED.** Pair outcomes are computable from the frozen stints by both-on-ice
subsetting: each 5v5 stint's 5 same-side skaters expand to C(5,2)=10 unordered teammate pairs, each
pair accruing the stint's `duration` and `home_xg`/`away_xg` (for/against). Timing probe on
**2024-25** (in-memory, nothing written): 452,784 5v5 stints → 6,120 teammate pairs ≥ 50 shared
minutes.

**Reconciliation vs production** (`mart_player_toi_matrix`, 2024-25): frozen **6,120** vs production
**6,329** pairs ≥ 50 min — frozen ~3% lower, consistent with the known ~8% shot/segment backbone
divergence, and the frozen (ice-derived) count is the source of record.

**Corpus size @ 50-min (3000 s) floor** (teammate pairs; production estimate, frozen ~3% fewer):

| per season | total 2010-26 |
|---|---|
| ~5,000 – 6,400 pair-seasons | **93,144** (frozen-derived ≈ 90k) |

**Compute.** The naïve `map_elements`(itertools.combinations) path took **~82 s/season** (~22 min
for 16 seasons). This is a Python-UDF bottleneck; a vectorized expansion (fixed 10-pair index /
self-join within stint) will cut it to **~2–4 min total**. **Phase 1 will vectorize; no corpus was
built here.**

---

## 6. Assumptions in the spec vs. reality

- 🔀 **Pair-outcome availability** — the spec asked whether the pair marts carry outcomes or "only
  shared TOI." Reality: `toi_matrix`/`toi_against` are **TOI-only**; **`mart_player_wowy`** (named so,
  not "mart_wowy") **does carry pair outcomes** (xGF% together-vs-apart, full 16-season span,
  directional); `int_line_seasons` carries **line** outcomes but is **2015-16+ only**.
- ⚠️ **All pair/line marts are rebuilt-backbone** (`int_segment_*`) → not the frozen source of
  record; Chemistry derives from stints and audits them (rule 7b). Recorded in
  `reports/upstream-ledger.md` as a lineage constraint (not a new defect).
- ℹ️ **`atlas.api` needs `httpx`** (transitive via its fetch stack); added to deps. Parquet is read
  directly with polars regardless.
- ℹ️ **fingerprints_v2 grain** — season-grain `team_season_fp` is the frozen parquet; per-regime is a
  staged SysEff Phase-7 seed (§2).

No corpus or model built in Phase 0. Frozen inputs untouched.

---

## 7. Branch base — flagged for the record (0.1)

The preamble asks for a branch "off current master." The working tree currently carries **uncommitted
System Effects P3–P7 + Jolt work** (untracked files + a few modified tracked files) on top of the 5
committed SysEff P0–P2 commits; a hard checkout to bare `master` would have **deleted the committed
SysEff sources from the working tree** and disrupted that in-progress project. I therefore branched
`research/chemistry` off the **current research tip** (which contains the frozen SysEff assets
Chemistry reads), preserving all prior work. Chemistry is folder-isolated under `research/chemistry/`
regardless of branch base, so this has no functional effect. **Recommendation:** acceptable as-is;
if a pure-master base is required, commit/stash the SysEff work first and rebase — say the word.

---

### Artifacts
`src/chem/{config,phase0}.py` · `reports/phase0.md` · `reports/upstream-ledger.md` · tests
`tests/test_phase0.py` (3 pass). Reproduce the light audit: `make phase0`.
