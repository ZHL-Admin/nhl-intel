# Phase 1 — Data inventory, assembly, and integrity

**Outcome:** the Atlas corpus is assembled and integrity-checked for **all 19,152
regular-season games, 2010-11 → 2025-26**. Almost everything was reused from
NIR's BigQuery (production untouched except one approved, verified fix); a
**563-game shift gap** was discovered, traced to an empty upstream endpoint,
recovered from the NHL HTML shift reports, and **backfilled into production**.

Machine evidence: `reports/phase1_integrity.json`, `data/html_report_availability.json`,
`data/raw/backfill_summary.json`. Figure: `reports/figures/toi_delta_hist.png`.

---

## 1.1 / 1.2 Inventory + gap matrix (carried forward)

Full catalog in **`reports/phase1-inventory.md`**. Summary:

- **Warehouse:** BigQuery `nhl-intel-498216` — `nhl_raw` (one-row-per-game JSON),
  `nhl_staging` (dbt views), `nhl_models` (Python outputs). Read-only SA.
- **Reused as source of record:** `stg_shifts` (via `raw_shift_charts`),
  `stg_play_by_play`, `raw_boxscores.playerByGameStats`, `stg_games`.
- **Gap matrix result:** shifts / events+coords / goalie-pulls / enumeration all
  **exist & usable**; per-player TOI and the penalty ledger **existed in raw but
  unstaged** → zero-fetch re-parse; only **2 pbp games** truly needed fetching.
  That was the picture *before* integrity exposed the empty-shift-array gap (§4).

## Assembled corpus (task 1.3)

Read-only adapters (`src/atlas/sources.py`) materialize Parquet under `data/parquet/`:

| table | rows | games | source |
|---|---|---|---|
| `shifts.parquet` | 14,802,522 | 19,152 | `stg_shifts` logic over `raw_shift_charts` (hardened; exact-dup removed) |
| `events.parquet` | 5,981,128 | 19,151 | `stg_play_by_play` + 2 gap-fetched pbp games |
| `boxscore_toi.parquet` | 765,976 | 19,152 | `raw_boxscores.playerByGameStats` (zero-fetch re-parse) |
| `penalty_ledger.parquet` | 149,512 | 19,125 | `raw_play_by_play.plays.details` incl. `descKey` + severity |

Column provenance is documented per-column in `sources.COLUMN_PROVENANCE`.

## What was reused vs fetched (per-season)

**Reused from BigQuery:** all shift/pbp/boxscore data for every season.
**Fetched fresh:** 2 pbp games (`2023020651`, `2024020147`) + **563 games' shift
data recovered from HTML reports** and written back to production. Per season:

| season | games | shift data source |
|---|---|---|
| 2010-11 … 2012-13 | 1230/1230/720 | BigQuery (native) |
| 2013-14 | 1230 | native + **1 HTML-backfilled** |
| 2014-15 … 2023-24 | 1230…1312 | BigQuery (native) |
| 2024-25 | 1312 | native + **57 HTML-backfilled** |
| 2025-26 | 1312 | native + **505 HTML-backfilled** |

Every regular-season game 2010-11→2025-26 now has complete shift **and** pbp data.
2010-11 is the hard floor (the shiftcharts source is empty for 2009-10 and earlier).

---

## The shift-coverage gap and its recovery (the Phase 1 story)

Integrity test 1.4a's naive form hid it, but **563 games had a `raw_shift_charts`
row whose `data` array was empty** — 0 in every season 2010-11→2023-24, then **57
in 2024-25 and 505 in 2025-26** (38% of the season). Findings, each verified live:

1. The stats **shiftcharts endpoint returns empty for all 563 games** (swept
   live: 563/563 empty, 0 recoverable). Not stale ingestion — the source lacks it.
2. The **pbp endpoint has no on-ice data** (verified on `2025020814`) — it cannot
   substitute; on-ice presence and events are genuinely two separate feeds.
3. The **NHL HTML shift reports** (`htmlreports/{season}/T{H,V}{gg}.HTM`) **do have
   the data** — 563/563 games, both home+visitor reports present.

**Recovery (approved):** a validated HTML parser (`src/atlas/shift_report.py`) →
normalize to the exact `raw_shift_charts` element shape → **idempotent
delete-then-insert into production** (`src/atlas/backfill_shifts.py`). Result:
**563 games, 422,846 shift elements, 0 unresolved players, exactly one row per
game, 0 still-empty.** Parser validated **byte-for-byte against the JSON feed** on
dual-source games (851/851 and 823/823 shift intervals match, incl. OT).

Two parser bugs were found and fixed *before* trusting the data (caught by
integrity, not assumed away):
- **Overtime dropped:** OT rows label the period `"OT"`, not `"4"` — the parser
  skipped them, sinking backfilled goal-on-ice to 97.1%. Fixed (`OT`→4, `OT2`→5…,
  `SO` skipped); re-validated 41/41 OT shifts on a native OT game.

---

## 1.4 Integrity results (by data source)

Coverage gate: **0 of 19,152 games have no shift data** (was 563 before backfill).

| test | result | native games | HTML-backfilled games |
|---|---|---|---|
| **a) shift-TOI vs boxscore-TOI, ≤30s** | **99.84% PASS** (n=730,418; thr 98%) | 99.837% | **100.0%** (n=21,449) |
| **b) no overlapping shifts** | 807 rows / 352 games (0.005% of rows) | inherent source noise | — |
| **c) goal scorer on ice (±2s)** | **99.97% PASS** (n=110,449; exp >99%) | 99.970% | **99.971%** (n=3,488) |
| **d) freshness (7 games refetched)** | **prod == raw API, exact** on all 7 | — | — |

The **HTML-backfilled data is as clean as (or cleaner than) native** — 100% TOI
reconciliation, matching goal-on-ice. Freshness (task 1.4d, 7 games spanning
2011-12→2025-26 incl. one 2011-12 and one 2013-14) shows production rows equal a
fresh raw refetch exactly (events and, after dedup-key correction, shifts).

**TOI-delta histogram:** `reports/figures/toi_delta_hist.png` — 99.84% of
player-games within ±30s, tightly centered at 0.

### 10 worst games by integrity

| game_id | what's wrong |
|---|---|
| 2010020124 | 38 player-games TOI off (max 2400s) + a goal scorer not on ice — corrupt 2010-11 source game |
| 2020020146 | 28 player-games TOI off (max 2106s) + genuine overlapping shifts |
| 2020020034 | 22 player-games TOI off (max 316s) + overlaps |
| 2021020566 | 20 player-games TOI off (max 347s) |
| 2020020002 | 12 player-games TOI off (max 175s) + overlaps |
| 2021020674 | 12 player-games TOI off (max 104s) + overlaps |
| 2014020833 | 10 player-games TOI off (max 946s) |
| 2020020645 | 10 player-games TOI off (max 72s) |
| 2020020160 | 9 player-games TOI off (max 286s) + overlaps |
| 2025021163 | 8 player-games TOI off (max 1352s) + overlaps |

These are the worst **source** games (mostly 2010-11 / 2020-21), not backfill
artifacts — the same rows exist in production `stg_shifts`.

### Quarantine

Union of any-issue games: **385 (2.01%)** = 352 genuine-overlap + 33 goal-miss +
**0 no-shift**. This exceeds the 0.5% auto-quarantine bar, so per task 1.4 it is
**reported, not silently quarantined**. Nature of the residual:
- **Overlaps** are real overlapping shift *records* in the source feed (median 37s),
  present in production. They cause only minor boundary fuzziness; Phase 2's
  boundary-union stint construction absorbs them (a player is simply "on ice" over
  the union). Not a reason to drop a game.
- **33 goal-misses** are source goal/shift-timing edge cases (scorer credited but
  no covering shift within ±2s), 0.03% of goals.

Recommendation: **do not quarantine** — the corpus is usable end-to-end. Flag the
handful of severely-corrupt source games (TOI off by >300s for many players, e.g.
`2010020124`) for exclusion at model time, reported per season so they surface in
later phases.

---

## Where production disagreed with the raw API (task deliverable)

1. **Duplicate shift rows.** The raw NHL shift array repeats some `(player,
   start, end)` entries verbatim; production `stg_shifts` inherits them
   (~0.1% of rows, 2020-25). The Atlas drops exact duplicates (rule 7b extend);
   production is unchanged. Fixed TOI 99.29%→99.84% and phantom overlaps 1,486→352 games.
2. **Empty shift arrays vs available data.** 563 games had empty `raw_shift_charts`
   data while the HTML reports held the shifts. Resolved by the production backfill.
3. **Stats shiftcharts endpoint vs HTML report.** For those 563 games the JSON
   endpoint is empty but the HTML report is complete — a source-side disagreement,
   not an ingestion defect.

---

## Standing-rule (7b) audit note

`stg_shifts`, `stg_play_by_play`, `int_shift_segments`, `shot_xg`, `player_impact`
were **audited and reused, not rebuilt**. The only production write was the
approved shift backfill (recovering absent data, idempotent, verified). One item
for Phase 2: confirm `int_shift_segments` cuts stints at goals (Amendment A), or
derive Atlas stints adding goal cut-points.

**Phase 1 complete. Stopping per the preamble; awaiting Phase 2 (which will be
provided revised around rule 7b — not started from the original brief).**
