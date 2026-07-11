# Phase 1 — Inventory and the regime ledger

**Project:** System Effects · **Date:** 2026-07-11 · **Seed:** 20260711
**Status:** Phase 1 complete. One design decision needs product-owner sign-off before
Phase 2 — see **§5 Decision**. Stopping here per protocol.

**Provenance pin (per instruction):** built on the frozen Atlas research committed at
`24acbab` ("Deployment Atlas: freeze the completed research project") on `master`; the
rebuild PR (#1, `8148462`) is merged. System Effects branch `research/system-effects`,
scaffold `ab7ab23`.

---

## 1. Inventory (1.1) — coaches, systems, styles, matchups, schedule

Read-only catalog. **Grain · coverage · provenance · rebuild-sensitivity.** "Rebuild-sensitive"
= derived from the production segment/shot backbone that PR #1 re-dedup'd (read frozen Atlas
instead where it matters).

### Coaches
| Asset | Grain | Coverage | Provenance |
|---|---|---|---|
| `nhl_staging.stg_game_context` | game | 2024-25, 2025-26 (3,340 games, coaches+scratches) ⚠ season mislabel UL-1 | parses `nhl_raw.raw_game_right_rail` |
| **`data/parquet/game_coaches.parquet`** (this project) | game | 2010-11 … 2023-24 (16,526 games; 2 null-coach UL-3); + officials + scratches | right-rail backfill (Gate A) |
| `nhl_models.player_coach_trust` | (player, season_window) | refreshed 2026-07-11 (4,597 rows) | `compute_coach_trust.py` — deployment-**usage** signals, not coach identity; rebuild-sensitive |

### Systems / styles
| Asset | Grain | Coverage | Provenance |
|---|---|---|---|
| `nhl_mart.mart_team_identity` | (team, season) | **2010-11 … 2025-26** (988 rows) | style fingerprints: rush/forecheck/cycle/point-shot/rebound share **for+against**, pace, shot_quality, shot_volume, hits, penalties (+pctiles). Rebuild-sensitive (refit 07-11 13:42) |
| `nhl_models.style_map` | (season, team) | **2025-26 only** (32 rows) | `compute_style_map.py` — 2D PCA of `mart_team_identity`; refit weekly; current-season display asset |
| `nhl_models.player_style_map` | (player, season) | 3,381 rows (refit 07-11) | player-level style map |
| `models_ml/train_style_effect.py` (+ `artifacts/style_coeffs.json`) | playoff **series** | model/artifact | "does a style matchup swing a playoff series beyond rating?" → goals-equivalent style weights, shrink-to-validate. Directly adjacent to our matchup track; **series-outcome** framing, not per-game/player |
| `research/deployment-atlas` `coach_fingerprints_2024_25.parquet` | (team, season) | **2024-25 only** (32) | Atlas derive: top-6 TOI share, home−away strictness (⚠ FAILED validation), zone-start polarization, close-game shortening |

### Matchup / context / schedule
| Asset | Grain | Coverage | Provenance |
|---|---|---|---|
| Atlas `rapm_variant.parquet` | (player, season) | 2010-11 … 2025-26 (13,434) | internal rating of record |
| Atlas `player_context_2024-25.parquet` | (player, season) | 2024-25 only (708) | QoC/QoT, OZ-start, PP/PK, strictness — multi-season = build-the-delta |
| Atlas with/against matrices | (season, a, b, relation) | on-demand | `api.shared_toi` from stints |
| `nhl_mart.mart_player_quality_context` | (player, season) | 2010-11 … 2025-26 (16,045) | QoC/QoT context; rebuild-sensitive |
| Atlas `games.parquet` | game | 19,149 regular, 16 seasons | **frozen game universe of record** (used here) |
| `nhl_staging.stg_games` | game | full; **date correct per game_id**, ⚠ season label UL-1 | date source (join by game_id) |
| `nhl_models.deserved_standings`, `nhl_staging.stg_standings`, `nhl_raw.raw_standings` | (season, team) / snapshot | — | standings (unused Phase 1) |

**Takeaways for later phases.** (i) Style descriptors already exist multi-season
(`mart_team_identity`, 16 seasons) but are rebuild-sensitive — audit vs. frozen stints before
reuse (rule 7b). (ii) `train_style_effect.py` already answers a **series-level** style-matchup
question; our matchup track must be distinct (per-matchup style adjustment, not series win prob)
or explicitly extend it. (iii) coach fingerprints & player context are 2024-25-only → Phase 2
re-derives multi-season from frozen stints (accepted build-the-delta).

---

## 2. The regime ledger (1.2)

Built at `data/parquet/regime_ledger.parquet`. **235 regimes**, one row per
(team, head coach, contiguous game span). Columns: `team_id, coach_name, start_game_id,
end_game_id, start_date, end_date, games_in_regime, seasons_spanned, start_season,
end_season, is_mid_season_change, predecessor_coach`.

**Construction.** Game universe = frozen Atlas `games.parquet` (19,149 regular games,
2010-11 … 2025-26). Coaches: `game_coaches.parquet` (2010-11…2023-24) + warehouse
`stg_game_context` (2024-25/2025-26), joined by `game_id` (immunizes against UL-1).
`game_date` from a deduped `game_id→date` map (0 missing over all 19,149). Ordering for
regime detection is **`(season_start_year, game_id)`** — frozen schedule order,
rebuild-invariant — with dates attached for reporting.

**Coach-name normalization (documented; NO hardcoded alias key).**
1. NFC-normalize unicode (accents preserved, canonical form).
2. Straighten curly apostrophes `’→'`.
3. Trim ends; collapse internal whitespace to one space.
4. Preserve proper-name casing as delivered.

Genuine cross-era spelling variants are **not** auto-merged — they are surfaced by the
validation near-duplicate scan for eyeball review (below), so the ledger never bakes in an
unverified merge. **Edge case found:** the feed encodes co-coaching committees as a
slash-joined string (`"Scott Stevens/Adam Oates"`, NJ 2014-15). Left verbatim; see §4.

---

## 3. Validation (1.3) — no hardcoded answer keys

### (a) Internal consistency — PASS
Every team-game with a coach maps to exactly one regime (contiguous cumulative runs ⇒ no
overlaps possible). Coverage identity holds:

| team-games w/ coach | Σ games_in_regime | null-coach team-games (product) |
|---:|---:|---:|
| 38,296 | 38,296 ✅ | 2 (UL-3) |

### (b) Plausibility
**Regimes per team-season** (494 team-seasons):

| regimes | team-seasons |
|---:|---:|
| 1 | 424 |
| 2 | 60 |
| 3 | 3 |
| 4 | 3 |
| **8** | 1 |
| **10** | 2 |
| **11** | 1 |

The 1/2/3 mass matches the expectation ("mostly 1, occasionally 2, rarely 3"). The **tail
(8–11) is implausible for genuine coaching changes and is flagged** — root cause diagnosed in §4.

**Mid-season changes per season** (expected ~5–15; flags = <3 or >20):

| season | changes | | season | changes | | season | changes |
|---|---:|---|---|---:|---|---|---:|
| 2010-11 | **2** ⚑ | | 2015-16 | 3 | | 2020-21 | 12 |
| 2011-12 | 9 | | 2016-17 | 5 | | 2021-22 | **23** ⚑ |
| 2012-13 | 4 | | 2017-18 | 0 | | 2022-23 | **1** ⚑ |
| 2013-14 | 4 | | 2018-19 | 7 | | 2023-24 | 7 |
| 2014-15 | 14 | | 2019-20 | 8 | | 2024-25 | 5 |
| | | | | | | 2025-26 | 6 (partial) |

Flags **2010-11 (2)**, **2021-22 (23)**, **2022-23 (1)** — all explained in §4; each verified,
none is under-detection (e.g. Vancouver's Boudreau→Tocchet, 2023-01-24, is correctly the sole
2022-23 change).

**Name near-duplicates** (auto-flagged for eyeball; 113 distinct coaches):
`Adam Oates ~ Scott Stevens/Adam Oates` (real co-coach string, §4); the rest are distinct
real people, correctly **not** merged: `Bob~Terry Murray`, `Brent~Darryl Sutter`,
`John~Paul MacLean`.

### (c) Eyeball lists
**10 longest regimes** (all correct real tenures):
| team | coach | games | span | mid-season | predecessor |
|---|---|---:|---|:--:|---|
| 14 | Jon Cooper | 1042 | 2012-13..2025-26 | ✓ | Guy Boucher |
| 21 | Jared Bednar | 782 | 2016-17..2025-26 | – | Patrick Roy |
| 5 | Mike Sullivan | 753 | 2015-16..2024-25 | ✓ | Mike Johnston |
| 16 | Joel Quenneville | 637 | 2010-11..2018-19 | – | (none) |
| 12 | Rod Brind'Amour | 616 | 2018-19..2025-26 | – | Bill Peters |
| 52 | Paul Maurice | 600 | 2013-14..2021-22 | ✓ | Claude Noel |
| 17 | Jeff Blashill | 537 | 2015-16..2021-22 | – | Mike Babcock |
| 6 | Claude Julien | 512 | 2010-11..2016-17 | – | (none) |
| 2 | Jack Capuano | 483 | 2010-11..2016-17 | ✓ | Scott Gordon |
| 18 | Peter Laviolette | 451 | 2014-15..2019-20 | – | Barry Trotz |

**10 shortest regimes** (all 1 game — entirely the transient-interim artifact of §4):
NJ 2014-15 `Lou Lamoriello ↔ Scott Stevens/Adam Oates` flips (×5), BUF 2020-21
`Ralph Krueger ↔ Don Granato` flips (×4), and one TBL 2012-13 Cooper-debut fragment.

---

## 4. Diagnosis of the flagged anomalies (real-world, not a pipeline bug)

The raw ledger faithfully records the **bench boss of record** each game; a "contiguous
same-name span" therefore over-fragments when the bench boss changes for 1–2 games. Two
sources produce every flagged case:

1. **COVID-protocol / illness fill-ins (2020-22).** Head coach out for 1–2 games → assistant
   runs the bench → a 1-game "regime" and a flip back. Drives the 2021-22 spike (23) and the
   8–10-regime team-seasons (BUF 2020-21, MTL 2021-22).
2. **Co-coach committees.** NJ 2014-15 after firing DeBoer alternated
   `"Lou Lamoriello"` and the co-coach string `"Scott Stevens/Adam Oates"` game-to-game → 11
   regimes in one team-season.

Regime-length buckets make the split concrete:

| games in regime | # regimes |
|---|---:|
| 1–2 (transient fill-ins) | 23 |
| 3–10 | 16 |
| 11–40 | 13 |
| **41+ (real head-coaching tenures)** | **183** |

The low flags are genuine, not misses: **2022-23 (1)** was a quiet firing year (only VAN
Boudreau→Tocchet, correctly caught); **2010-11 (2)** = NJ MacLean→Lemaire + NYI
Gordon→Capuano.

**Cohort C is immune.** Its 15-games-under-each-coach floor excludes every 1–2 game interim,
so none of these artifacts can enter the experiment cohort (verified: no cohort-C change has
<15 games either side).

---

## 5. Cohorts (1.4)

### Cohort C (coach-change) — 49 qualifying changes
Mid-season changes with ≥15 games under **both** the old and new coach in the same season;
per change, skaters with ≥100 5v5 minutes under **both** (5v5 TOI from frozen stints,
quarantined + playoff stints excluded per standing rules).

| season | changes | skaters (Σ both-100min) | | season | changes | skaters |
|---|---:|---:|---|---|---:|---:|
| 2010-11 | 2 | 32 | | 2018-19 | 6 | 108 |
| 2011-12 | 6 | 115 | | 2019-20 | 7 | 132 |
| 2012-13 | 1 | 19 | | 2020-21 | 1 | 20 |
| 2013-14 | 3 | 60 | | 2021-22 | 2 | 39 |
| 2014-15 | 2 | 42 | | 2022-23 | 1 | 20 |
| 2015-16 | 2 | 35 | | 2023-24 | 6 | 110 |
| 2016-17 | 5 | 94 | | 2024-25 | 4 | 82 |
| 2017-18 | 0 | 0 | | 2025-26 | 1 | 18 |
| | | | | **Total** | **49** | **~926** |

Spot-verified against reality: 2010-11 NJ MacLean→Lemaire (16 skaters), NYI Gordon→Capuano
(16); 2024-25 BOS Montgomery→Sacco (18), CHI Richardson→Sorensen (19), DET Lalonde→McLellan
(20), STL Bannister→Montgomery. Typical overlap ~16–20 skaters/change — enough for a
within-player, across-system contrast.

### Cohort M (movers) — 1,705, imported from Atlas `movers_eval`, unchanged
15 season-transition pairs, 89–148 movers each:

| pair | n | pair | n | pair | n |
|---|--:|---|--:|---|--:|
| 2010-11→2011-12 | 138 | 2015-16→2016-17 | 89 | 2020-21→2021-22 | 135 |
| 2011-12→2012-13 | 94 | 2016-17→2017-18 | 99 | 2021-22→2022-23 | 112 |
| 2012-13→2013-14 | 92 | 2017-18→2018-19 | 95 | 2022-23→2023-24 | 124 |
| 2013-14→2014-15 | 119 | 2018-19→2019-20 | 114 | 2023-24→2024-25 | 148 |
| 2014-15→2015-16 | 99 | 2019-20→2020-21 | 112 | 2024-25→2025-26 | 135 |

---

## 6. Decision needed before Phase 2

**Regime definition vs. transient bench substitutions.** The raw ledger (§4) counts every
1–2 game COVID/illness fill-in and each co-coach-string flicker as its own regime, which
violates the 1.3(b) plausibility expectation in specific, explained cases (23 one-to-two-game
transients; 2021-22 over-count; four 8–11-regime team-seasons). Cohort C is already immune.
Options:

- **(A, recommended) Keep the raw ledger of record, add a non-destructive
  `is_transient_stint` annotation** (regime ≤ K games AND bracketed by the same coach on both
  sides ⇒ a fill-in), and define the *analysis* regime as the consolidated view (fill-ins
  absorbed into the surrounding head-coach regime). Preserves the faithful record, brings the
  consolidated counts into plausible range, and is auditable. Suggested K=4 (absorbs the
  1–2 game protocol fills and the NJ committee flicker without touching genuine short tenures
  like an 8–9 game interim that finished a season).
- **(B) Keep raw only** — accept the fragmentation and rely on Cohort C's 15-game floor
  downstream. Simplest; leaves regime-count/mid-season-count metrics noisy.
- **(C) Resolve co-coach strings + protocol fills case-by-case** with an evidence-backed
  alias/interim table — highest fidelity, but reintroduces a hand-maintained key (against the
  no-answer-key discipline).

I recommend **(A)**. It does not change the delivered schema/grain and is reversible. I did
**not** implement it — the plausibility bar in 1.3(b) is a product expectation and the "regime"
unit feeds every later phase, so this is your call. **Stopping for review.**

---

### Artifacts
`data/parquet/game_coaches.parquet` (16,526) · `data/parquet/regime_ledger.parquet` (235) ·
`reports/phase1_analysis.json` (full validation + cohorts) · `reports/upstream-ledger.md`
(UL-1..3) · tests `tests/test_regime_ledger.py` (4 pass).
