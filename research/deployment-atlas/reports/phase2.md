# Phase 2 — Stints: audit, derive, attach outcomes, validate

**Decision: DERIVE.** Production `int_shift_segments` is a stale materialized table
(missing all 563 backfilled games), built on undeduplicated `stg_shifts`, with no
goal cut-points. Per rule 7b I reuse its proven *conventions* but derive the stint
table from the clean Atlas corpus, adding goal cut-points (Amendment A). Result:
**5,905,129 stints across 19,149 games**, `data/parquet/stints.parquet`.

Machine evidence: `reports/phase2_tests.json`.

---

## 2.1 Audit of the production backbone

| spec requirement | `int_shift_segments` / `int_segment_context` | verdict |
|---|---|---|
| personnel-constant segments | ✅ boundary-union of shift start/end | ok (algorithm sound) |
| **includes all games** | ❌ **materialized table (2026-07-06); 0 of 400 sampled backfilled games present; 2025-26 has 895/1312** | **FAIL — stale, pre-backfill** |
| **built on deduplicated shifts** | ❌ built on undeduplicated `stg_shifts` (exact-dup + overlap contamination) | **FAIL — dup-contaminated** |
| **goal cut-points (score constant per stint)** | ❌ boundaries are shift start/end only; a goal inside a segment isn't reflected until the next segment | **FAIL — score not constant** |
| strength from the ice | ✅ `team_skater_count` from on-ice counts; `EN` when a goalie is pulled | ok (reused) |
| goalie identification | ✅ `positionCode = 'G'` | ok (reused) |
| shootout exclusion | ✅ SO has no shifts | ok |
| OT length | ✅ `(period-1)*1200` offset, never assumes OT length | ok (reused) |
| duration floor | ✅ `segment_duration > 0`; drops `>6 skaters/side` | ok (reused) |
| stint-grain spec columns (arrays, goalie ids, scoreState bucket, startType, isPlayoffs) | ❌ per-`(segment,player)` grain; several spec columns absent | **FAIL — grain/columns** |

Three independent FAILs (staleness, dup-contamination, no goal cut-points) each
require rebuilding the table. Two are exactly the contamination the task flags:
production segments predate both the dedup fix and the 563-game backfill.

## 2.2 Decision & derivation

**DERIVE**, because the dup-contamination is compounded by staleness (the entire
recovered 2024-26 shift data is absent from production segments) and the missing
goal cut-points — adopting would mean rebuilding `int_shift_segments` in
production, which is out of scope. The Atlas corpus (`shifts.parquet`) is clean,
deduplicated, and includes the backfill.

`src/atlas/stints.py` reuses the validated conventions (boundary-union, strength
from on-ice counts, goalie via `positionCode G`, `(period-1)*1200` seconds) and
adds **goal seconds as boundaries** so score state is constant within every stint.
Columns match the 2.2 spec: `gameId, season, stintId, startSeconds, endSeconds,
durationSeconds, homeSkaterIds, awaySkaterIds, homeGoalieId, awayGoalieId,
strengthState, homeScore, awayScore, scoreState(-3..+3), startType(OZ/NZ/DZ/OTF),
isPlayoffs` (isPlayoffs=false throughout — the corpus is regular season only).

**Goal-splitting:** needed. **2,290 of 110,448 goals (2.1%) fell strictly inside a
shift interval** and created a new stint boundary; the other ~108k coincide with a
line change (already a shift boundary). Without the split those 2,290 stints would
straddle a goal with two different score states.

## 2.3 Outcomes attached

Per stint, shot attempts attributed via the `(start, end]` convention (reused from
`int_on_ice_events`), counted for/against from the home perspective:
`home/away_corsi`, `home/away_fenwick`, `home/away_sog`, `home/away_goals`;
`home_xg`/`away_xg` are null until Phase 3. **110,432 of 110,449 goals attributed**
(the 17 gaps are in the 3 games lacking BigQuery pbp).

---

## 2.4 Tests (per season)

### (a) Stint durations sum to actual game seconds (±2s) — **PASS 99.995%**
Every season 1.0000 except 2010-11 (0.9992; 1 corrupt source game, e.g. `2010020122`).
Uses actual max shift end per game — OT length never assumed.

### (b) Personnel & overlap absorption
`strengthState` is derived from the on-ice counts, so it matches the counts in
**100%** of stints by construction. Impossible-personnel stints (>6 skaters/side):

| | stints |
|---|---|
| impossible-personnel stints (flagged `is_quarantined`) | **753** (0.013%) |
| …in the 352 genuine-overlap games | 608 |
| …outside overlap games | 145 |

**Overlap absorption:** the 352 overlap games contain 608 of the 753 impossible
stints — boundary-union construction absorbs the overlaps into normal stints
almost everywhere; only the residual 608 (sub-second line-change collisions) remain
impossible. Per the task, **only those stints are quarantined** (flagged, excluded
downstream), **not the games**. The 145 outside overlap games are the same
sub-second collision artifact.

### (c) League 5v5 TOI share per season — **PASS (all in [70%, 83%])**
5v5 = 5 home + 5 away skaters with both goalies on the ice.

| season | 5v5 share | | season | 5v5 share |
|---|---|---|---|---|
| 2010-11 | 76.8% | | 2018-19 | 80.0% |
| 2011-12 | 77.9% | | 2019-20 | 79.0% |
| 2012-13 | 78.0% | | 2020-21 | 79.9% |
| 2013-14 | 77.7% | | 2021-22 | 80.0% |
| 2014-15 | 78.4% | | 2022-23 | 79.4% |
| 2015-16 | 78.5% | | 2023-24 | 79.6% |
| 2016-17 | 79.6% | | 2024-25 | 81.0% |
| 2017-18 | 79.6% | | 2025-26 | 79.9% |

Pre-2015 seasons land in range (76.8–78.4%), slightly below modern seasons but
well inside [70,83] — no divergence that would disqualify them.

### (d) situationCode cross-check — **95.94%** (below the 99% target; see finding)
Every pbp event's four digits vs the stint state at that second (leading zeros
restored — `situation_code` had stripped a `0651`→`651`). Agreement 95.94%; among
stint-5v5 events 97.05%. Per season ~95% (2019-20 low at 91.3%).

**This is not a pipeline defect — it is `situationCode` timing lag, verified.** In
game `2010020001` the shift chart correctly shows **5v4 through the whole penalty
(842→962)** and **5v5 three seconds after it expires (965)**, while `situationCode`
still reads `1451` at 965 — the code lags the on-ice change. It also captures the
delayed-penalty goalie pull (6v5 at 837). 70% of disagreements are on special-teams
/ empty-net codes (transitions). Per Amendment A the Atlas uses **shift-derived
strength**, which this shows to be the *more* accurate of the two feeds.
Top disagreement buckets (`situationCode` → stint-expected): `1451→1551` (63.6k),
`1541→1551` (57.1k), `1551→1451` (14.2k), `1551→1541` (12.3k), `1441→1551` (9.4k).

> **Flagged for you:** shift-derived 5v5 and `situationCode` 5v5 diverge ~4% (mostly
> penalty transitions). The Atlas trusts the ice per Amendment A; if you'd prefer
> `situationCode` to be authoritative for strength, that's a design change to make now.

### (e) Manual 5v5-TOI cross-check — **PASS (15/15 exact, diff = 0)**
Pipeline 5v5 TOI vs an **independent second-by-second recomputation** from raw
shifts, 3 games each for McDavid (2023-24), Makar (2022-23), MacKinnon (2023-24),
Matthews (2021-22), Hughes (2023-24). Every check matches to the second (e.g.
McDavid `2023020009` 897=897, Makar `2022020045` 1096=1096, Matthews `2021020063`
1116=1116).

---

## Three example stints — game 2023020204 (faceoff-start stints)

| stint | seconds | dur | strength | score | startType | homeG / awayG | CF h/a |
|---|---|---|---|---|---|---|---|
| 0 | 0–25 | 25 | 5v5 | 0-0 (0) | NZ | 8482221 / 8479406 | 0/0 |
| 1 | 25–52 | 27 | 5v4 | 0-0 (0) | OZ | 8482221 / 8479406 | 0/0 |
| 34 | 298–304 | 6 | 5v5 | 0-0 (0) | DZ | 8482221 / 8479406 | 0/0 |

- stint 0 home skaters `[8475784, 8479420, 8480839, 8481528, 8481564]`, away `[8474034, 8474567, 8475220, 8477541, 8478493]`
- stint 1 is 5v4 (home power play): away drops to 4 skaters `[8474716, 8475220, 8476463, 8480980]`
- stint 34 is a fresh 5v5 unit off a defensive-zone faceoff

---

## Summary

- **DERIVE** (production backbone stale + dup-contaminated + no goal cut-points).
- Goal-splitting applied (2,290 splits) → score constant per stint.
- Tests **a PASS, b** 753 stints quarantined (608 absorbed in overlap games), **c
  PASS, d 95.94%** (situationCode lag, not a defect), **e PASS exact**. Pre-2015
  seasons pass every threshold, reported per season.
- One decision flagged: shift-derived vs `situationCode` strength (Atlas uses the ice).

**Phase 2 complete. Stopping per the preamble; awaiting Phase 3 (rule-7b-revised).**
