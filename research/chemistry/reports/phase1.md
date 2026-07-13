# Phase 1 — The pair and trio corpus

**Project:** Chemistry (`NIR/research/chemistry/`)
**Date:** 2026-07-12 · **Seed:** 20260712 · **Python:** dedicated `.venv` (3.11+) · **polars** 1.42.1
**Status:** Phase 1 complete. Corpus built from the frozen Atlas stints, integrity suite green,
corpus frozen with recorded hashes. Stopping per protocol.

Reproduce: `make phase1` (reads cached season parquets; `-m chem.phase1 --rebuild` forces a fresh
build). Machine-readable results: `reports/phase1_analysis.json`. Tests: `make test` (11 pass).

---

## 1. Adopt-versus-derive record (1.1 / 1.2)

Phase 0 established that **every** production pair/line asset is rebuilt-backbone-derived
(`int_segment_*`, ~8% divergent from the frozen Atlas stints on shot counts). Per rule 7b +
strength-is-ice-derived, Chemistry therefore **derives the entire corpus from the frozen Atlas
stints** and treats the production marts as audit targets, not sources. **Nothing is adopted.**

| column group | source | derivation |
|---|---|---|
| keys `a,b,team_id,season` | derived | canonical `a<b`; pair-team-season grain (matches `mart_player_toi_matrix`) |
| outcomes `xgf,xga,cf,ca,gf,ga` | derived | summed over both-on-ice 5v5 stints (stint `home_xg/away_xg`, corsi, goals) |
| `toi` (shared) | derived | summed stint `duration_seconds` while both on ice |
| WOWY `{a,b}_without_toi/xg_share` | derived | player season on-ice total **minus** the together portion, same stint source |
| `oz_start_share` | derived | OZ / (OZ+DZ) faceoff-start stints (away OZ = home DZ) |
| score mix `share_lead/tied/trail` | derived | TOI split on the pair-side score state (away = −home) |
| `opp_rapm` (opponent strength) | derived | TOI-weighted mean **variant-RAPM** (`off_impact+def_impact`) of the opposing 5 |
| `pos_pair` (D-D/D-F/F-F) | derived | global modal F/D per player from `rosters.parquet` |

Audit targets recorded for later rule-7b validation (not used as inputs): `mart_player_wowy`
(directional together-vs-apart, full span) and `mart_player_toi_matrix` (shared TOI only). The
Phase-0 count probe already showed the frozen-derived pair count ~3% below production
(`toi_matrix`), consistent with the known backbone divergence; the frozen (ice-derived) count is the
source of record here.

**Trios (1.2).** `int_line_seasons` was audited in Phase 0 (rebuilt-backbone, F3/D2 grain,
carries line outcomes, but **2015-16+ only**). Chemistry derives the forward-trio corpus from the
frozen stints at the full 16-season span (a stint belongs to a trio when **exactly 3** of a side's 5
skaters are forwards, matching the F3 definition), 100-shared-minute floor.

---

## 2. Construction (5v5, regular season, ice-derived)

Stints are filtered to `strength_state=='5v5'`, exactly 5 skaters per side, **not** quarantined
(the 753 Atlas-quarantined stints stay excluded), and regular season. Each stint's 5 same-side
skaters expand to their `C(5,2)=10` canonical teammate pairs by fixed list indices; the stint's
outcomes/context attach once and aggregate to pair-team-season. Floors: **pairs ≥ 50 min** (3000 s),
**forward trios ≥ 100 min** (6000 s); analysis tiers flagged at 100 and 200 min.

Two construction facts recorded (details in §5): (a) the frozen Atlas stints are **already
regular-season-only** (0 of 5.9M are playoff stints), so the `~is_playoffs` filter is a documented
belt-and-braces guard, not a substantive cut; (b) the stint table's `stint_id` is **game-local**
(0..~500, only ~500 distinct values), so all per-stint joins/grouping key on a globally-unique
row index `rid`, never `stint_id` — using `stint_id` cross-joins stints across games.

---

## 3. Integrity (1.3) — all green

### 3(a) Symmetry & canonical ordering
Canonical `a<b` holds for **all 90,527** pair rows; `(season, team_id, a, b)` is unique with **0
duplicate orderings**.

### 3(b) Conservation
Identity: each player is in exactly 4 teammate pairs per stint (5 skaters − 1), so his **unfloored**
partner-summed shared TOI must equal **4 × his 5v5 on-ice TOI**. Measured per season on all
~880–1,000 players/season: the ratio is **exactly 4.0000 (max abs deviation 0.0)** in every one of
the 16 seasons — tolerance `1e-6` (float round-off only). Exact because both sides are summed from
the same integer stint durations.

### 3(c) Reconciliation vs frozen `player_5v5` (source of record)
10,959 player-seasons joined. **Median TOI ratio 1.0000, median xGF ratio 1.0000** (derived vs
`player_5v5`). The derived total is **never lower** (0 cases < 0.999) and runs ≤+1% for 94% and
≤+2% for 99% of player-seasons; the small one-sided excess concentrates in irregular seasons
(2019-20 COVID pause 249, 2012-13 lockout 105, 2010-15) and is ~0 from 2021-22 on. Immaterial to
pair xG-*share* ratios (common TOI scale cancels) and to the internally-consistent stint-derived
corpus. Logged as **upstream-ledger CL-1** (LOW) — a disagreement between two frozen Atlas products,
not a Chemistry error.

### 3(d) Corpus size & composition

**Total: 90,527 pair-team-seasons ≥ 50 min** (pre-2015 broken out: 26,898; 2015-16+: 63,629).
Forward trios ≥ 100 min: **3,187** (pre-2015: 911; ≥200-min tier: 1,111).

*Tier totals (shared-TOI):* 50-min 30,115 · 100-min 29,461 · 200-min 30,951 — balanced thirds; the
200-min tier is largest in full seasons and collapses in shortened ones (2012-13 lockout: 695;
2020-21: 1,058; 2019-20 COVID: 1,789 — vs ~2,000–2,280 elsewhere).

*Position mix:* **D-F 56,341 (62.2%) · F-F 26,375 (29.1%) · D-D 7,811 (8.6%)** — tracks the per-stint
combinatorics of 3F+2D (6 D-F, 3 F-F, 1 D-D), with D-D over-represented at the higher tiers because
defensemen accrue shared minutes fastest.

*Shared-TOI distribution (minutes):* min 50 · p25 84 · **median 143** · p75 244 · p90 351 · p99 710
· max **1,397** (the top D-pair-season). Right-skewed, as expected.

**O3 pair-locking refresh.** Across *all* partners, D and F look similar (top-partner share median
~0.12–0.13, ~28 partners, entropy ~2.8–2.9 nats) — the D-locking signal is diluted because a
defenseman's partners are mostly forwards. Cut to **same-position** partners it appears sharply, and
is reported **with absolute magnitude** (rule 4.1a):

| position | top same-pos partner share (median / p90) | absolute top-partner shared min (median / p90) | same-pos partners (median) |
|---|---|---|---|
| **D** (D-D) | **0.479 / 0.782** | **314 / 827 min** | 9 |
| **F** (F-F) | 0.261 / 0.412 | 271 / 680 min | 18 |

A defenseman pours ~48% of his D-partner minutes (p90 78%) into a single top D-partner — nearly
double a forward's 26% — over hundreds of real shared minutes. **This is O3, and it is this
project's identifiability warning made concrete:** for many defensemen, "the pair" and "the player"
are close to collinear in the data, which Phase 2's persistence test must confront directly.

---

## 4. Freeze (1.4)

Combined corpus written to `data/parquet/frozen/` (deterministic sort → stable hashes; re-running
from cache reproduces the identical sha256):

| file | rows | season span | sha256 (first 16) |
|---|---:|---|---|
| `pairs_corpus.parquet` | 90,527 | 2010-11 … 2025-26 (16) | `baaed981f5af153b…` |
| `trios_corpus.parquet` | 3,187 | 2010-11 … 2025-26 (16) | `df2b7dfdb56a8a0f…` |

Full hashes + build parameters in `data/parquet/frozen/MANIFEST.json` (seed 20260712, floors 3000 /
6000 s). Per-season parquets are cached under `data/parquet/{pairs,trios,player_onice}/`.

---

## 5. Assumptions in the spec vs. reality

- ⚠️ **`stint_id` is game-local, not a global key** — only ~500 distinct values (0..~497 per game);
  the unique key is `(game_id, stint_id)`. Chemistry keys all per-stint expansion/joins on a
  generated unique `rid`. (An interim self-join-on-`stint_id` build silently cross-joined stints
  across games — caught by the brute-force pair-count validation and the reconciliation; corrected.)
- ℹ️ **Regular-season filter is a no-op on the frozen source** — the frozen Atlas stints carry **0
  playoff stints** (verified across all 16 seasons); the `~is_playoffs` filter is retained as a
  documented guard.
- ℹ️ **Opponent strength** is the TOI-weighted mean of the opposing 5's **variant-RAPM**
  (`off_impact+def_impact`); players without a RAPM row (thin TOI) contribute 0 to the mean.
- ℹ️ **`pos_pair`** uses each player's **global** modal F/D (position is slowly-varying); adequate for
  the D-D/D-F/F-F label. Per-season position is available if a later phase needs it.
- ℹ️ **WOWY "without"** is season-level (across teams) minus the together portion — the standard
  apart split; 0% of pairs have a null WOWY split.
- ℹ️ **Performance** — the vectorized expansion runs ~3 s/season for pairs, ~1.4 s for trios
  (full 16-season build + integrity + freeze ≈ 2 min). The earlier eager-concat path thrashed memory
  and was replaced.

---

### Artifacts
`src/chem/corpus.py` (build) · `src/chem/phase1.py` (integrity + freeze) · `reports/phase1.md` ·
`reports/phase1_analysis.json` · `reports/upstream-ledger.md` (CL-1) ·
`data/parquet/frozen/{pairs_corpus,trios_corpus}.parquet` + `MANIFEST.json` ·
tests `tests/test_phase1.py` (8 pass; 11 total). Frozen Atlas/System-Effects inputs untouched.

**STOP** — awaiting go-ahead for Phase 2 (the keystone persistence test).
