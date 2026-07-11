# Phase 0 — Environment, API audit, and schema contract

**Project:** Deployment Atlas (research repo, isolated under `NIR/research/deployment-atlas`)
**Seed:** `20260710` · **Rate limit:** ≤ 5 req/s · **Backoff:** base 2s, cap 60s, 5 retries on {429,500,502,503,504}
**User-Agent:** `deployment-atlas/0.1 (NHL deployment research; non-commercial; contact: repo owner via github)`
**Generated:** 2026-07-10 (machine-readable evidence: `reports/phase0_probe.json`; run metadata: `data/raw/run_meta.json`)

All findings below are read from **real cached payloads**. Where this document's
premises disagreed with a payload, the payload wins and the discrepancy is
recorded (§6). Nothing here is asserted from assumption.

---

## 0. What was built (tasks 0.1, 0.7)

- **Scaffold** per the preamble: `src/atlas/`, `tests/`, `data/raw|parquet/`, `reports/`, `Makefile`, `pyproject.toml`, project-local `.venv`. `make phase0` runs the audit; `make test` runs the suite.
- **Fetch stack** (`client.py`): cache-before-parse, ≤5 req/s rate limiter, exponential backoff (2s→60s, 5 retries, seeded jitter), resumable **manifest** (`data/raw/manifest.json`, atomic writes), and a non-raising `fetch_result` path so old-game 404s / empty bodies are recorded as *findings* rather than crashes.
- **Parsers** (`parse.py`): `parse_shifts(game_id)` and `parse_pbp(game_id)` return typed **polars** frames from cache (no network).
- **Tests**: 21 passing (`pytest -q`). Client (cache reuse, backoff schedule, 404 handling, rate-limit spacing), manifest (atomic round-trip, presence semantics), paths, and fixture-based parser invariants (row counts, non-negative durations, shift⊆boxscore).

### Isolation (standing `research/{project}` pattern)
- `data/` (raw JSON, Parquet, DuckDB) and `.venv/` are git-ignored both locally and via `NIR/.gitignore` rules (`research/*/data/`, `research/**/*.parquet`, `research/**/*.duckdb`, `research/*/.venv/`). Verified with `git check-ignore`.
- NIR's `pytest.ini` (`testpaths = tests`) and dbt (`dbt/`-relative paths) do **not** glob into `research/`; there is no `.github/` CI to exclude.
- The **only** tracked change outside `research/deployment-atlas/` is the `NIR/.gitignore` isolation block. Deleting the project folder + that block leaves the site untouched.

---

## 1. Fixtures fetched (task 0.2)

Every requested game was fetched (shifts + pbp + boxscore) and cached under `data/raw/{season}/{gameId}/`. **All returned HTTP 200** — including the oldest, but with an important empty-payload finding.

| gameId | season | type | shift rows (raw / **517**) | pbp plays | boxscore |
|---|---|---|---|---|---|
| 2023020204 | 2023-24 | reg | 694 / **689** | 320 | ✓ |
| 2023030411 | 2023-24 | playoff | 797 / **794** | 368 | ✓ |
| 2019020500 | 2019-20 | reg | 741 / **737** | 318 | ✓ |
| 2015020001 | 2015-16 | reg | 836 / **832** | 327 | ✓ |
| 2011020400 | 2011-12 | reg | 708 / **703** | 326 | ✓ |
| 2008020300 | 2008-09 | reg | **0 / 0** | 56 | ✓ |

**Finding:** `2008020300` shift payload is a 21-byte body with an empty `data: []` (HTTP 200, not a 404). Its pbp is sparse (56 plays, no `details` coordinate richness of the modern feed). Boxscore still populates. → Pre-2010 games can return **structurally valid but empty** shift charts; treat "empty shift list" as a first-class state, not an error.

Two extra games were fetched for verification and are also cached:
- `2023020145` (2023-11-02, **shootout** game) — for OT/SO marking (§3).
- score-by-date `2023-11-02` — used to locate the OT/SO game.

---

## 2. Observed schemas & field meanings

### 2a. Shift charts — `GET …/shiftcharts?cayenneExp=gameId={id}`

Envelope: `{ "data": [ …rows… ], "total": <int = len(data)> }`.

Each row (null rates measured on `2023020204`; **0%** unless noted):

| field | type | meaning |
|---|---|---|
| `id` | int | unique row id (shift or goal-marker) |
| `playerId` | int | **NHL player id — join key** to `rosterSpots` and boxscore |
| `teamId` / `teamAbbrev` / `teamName` | int/str/str | player's team |
| `period` | int | 1–3 reg, **4 = OT, 5 = SO** (see §3) |
| `startTime` | str `MM:SS` | game clock **elapsed in period** at shift start |
| `endTime` | str `MM:SS` | game clock elapsed in period at shift end |
| `duration` | str `MM:SS` \| null | shift length; **null only on goal-marker rows** (0.72% of all rows; 0% of `517` rows) |
| `typeCode` | int | **517 = player shift**, **505 = embedded goal marker** |
| `detailCode` | int | `0` on shifts; `801/802/803` on goal markers |
| `eventNumber` | int | on `505` rows, links to the goal's event |
| `shiftNumber` | int | per-player sequential shift index; **0 on goal-marker rows** |
| `hexValue` | str | team jersey hex colour |
| `firstName` / `lastName` | str | player name |
| `gameId` | int | game id |
| `eventDescription` | str \| null | **null on all `517` shift rows**; on `505` rows carries strength (`EVG`,`PPG`,`EN`,…) |
| `eventDetails` | str \| null | null on `517`; on `505` rows carries scorer/assist names |

Representative rows (from `2023020204`):
```
517 shift : {playerId 8473446, period 1, start 02:42, end 03:29, duration 00:47,
             shiftNumber 1, detailCode 0, eventDescription null}
505 marker: {playerId 8475784, period 2, start 19:02, end 19:02, duration null,
             shiftNumber 0, detailCode 803, eventDescription "EVG",
             eventDetails "JJ Peterka"}   ← a goal, not a shift
```

### 2b. Play-by-play — `GET …/gamecenter/{id}/play-by-play`

Top-level keys: `id, season, gameType, limitedScoring, gameDate, venue, venueLocation, startTimeUTC, easternUTCOffset, venueUTCOffset, tvBroadcasts, gameState, gameScheduleState, periodDescriptor, awayTeam, homeTeam, shootoutInUse, otInUse, clock, displayPeriod, maxPeriods, gameOutcome, plays, rosterSpots, regPeriods, summary`.

- `gameType` is an **integer** in the body: `2` regular, `3` playoff (the id string uses `02`/`03`; §6).
- **`plays[]`** element: `eventId, sortOrder, periodDescriptor{number,periodType,maxRegulationPeriods}, timeInPeriod "MM:SS", timeRemaining "MM:SS", situationCode, homeTeamDefendingSide (left|right), typeCode (int), typeDescKey (str), details (dict), pptReplayUrl`.
  - **Chronology:** order by `sortOrder`.
  - **Coordinates live in `details`:** `xCoord` (≈ ±100, length axis), `yCoord` (≈ ±42, width), `zoneCode` (`O`/`D`/`N`). `homeTeamDefendingSide` gives the side needed to normalize coordinates to attacking direction.
  - **No on-ice skater lists anywhere in a play** (verified: zero integer-list fields across all 320 plays). → **This is the reason the project exists**; on-ice state must be reconstructed from shift charts.
- Event types seen (`typeDescKey`, count in `2023020204`): faceoff 55, shot-on-goal 55, hit 51, blocked-shot 44, stoppage 40, missed-shot 31, giveaway 12, penalty 8, takeaway 8, goal 5, delayed-penalty 4, period-start 3, period-end 3, game-end 1 (playoff/OT/SO games add `shootout-complete`, `delayed-penalty`, etc.).
- **`details` keys per event type** (recorded in probe): e.g. `shot-on-goal → shootingPlayerId, goalieInNetId, shotType, xCoord, yCoord, zoneCode, eventOwnerTeamId, homeSOG, awaySOG`; `faceoff → winningPlayerId, losingPlayerId, zoneCode, coords`; `hit → hittingPlayerId, hitteePlayerId`; `goal → scoringPlayerId, assist1PlayerId, goalieInNetId, homeScore, awayScore`.
- **`rosterSpots[]`** (40 entries): `teamId, playerId, firstName{default}, lastName{default}, sweaterNumber, positionCode (C/L/R/D/G), headshot` — the per-game id→name→position→team map.

**Penalties (task 0.4).** A `penalty` play encodes everything in `details` + the play's clock:
`committedByPlayerId`, `drawnByPlayerId`, `eventOwnerTeamId` (**penalized team**), `descKey` (e.g. `tripping`), `typeCode` (`MIN`/`MAJ`/`BEN`/…), `duration` (**integer minutes**, e.g. `2`), `xCoord/yCoord/zoneCode`. **Start time** = the play's `timeInPeriod` + `period`. **Expiry is not given** — it must be derived (`start + duration`) during reconstruction.

**Goalie pulls / empty net (task 0.4).** There is **no explicit goalie-pull event**. Empty-net / pulled-goalie state is recovered two ways, both verified:
1. `situationCode` — the pulled team's goalie digit flips to `0` (see §2d).
2. On a goal, `details.goalieInNetId` is **null** when scored into an empty net.

### 2c. Boxscore — `GET …/gamecenter/{id}/boxscore` (task 0.5)

- **Per-player TOI location:** `playerByGameStats.<awayTeam|homeTeam>.<forwards|defense|goalies>[].toi`.
- **TOI format:** string `"MM:SS"` (skater sample `"11:11"`; goalie sample `"00:00"` = dressed backup who didn't play). Shape per team: 12 forwards / 6 defense / 2 goalies.
- Skater keys: `playerId, name, position, sweaterNumber, goals, assists, points, plusMinus, pim, hits, powerPlayGoals, sog, faceoffWinningPctg, toi, blockedShots, shifts, giveaways, takeaways`. The `shifts` count is a useful cross-check for shift reconstruction.
- Goalie keys: `…, toi, evenStrengthShotsAgainst, powerPlayShotsAgainst, shorthandedShotsAgainst, saves, shotsAgainst, starter, decision, …`.

### 2d. `situationCode` format — verified against an empty-net goal (task 0.4)

4-character string, one digit per slot: **`[awayGoalieOnIce][awaySkaters][homeSkaters][homeGoalieOnIce]`**.

`2023020204` had **no** empty-net goal (all 5 goals `goalieInNetId`≠null), so verification used **`2023030411`**: its 3rd goal was scored by **FLA (home, id 13)** into **EDM's (away)** empty net —
```
situationCode "0651", goalieInNetId null, eventOwnerTeamId 13(home)
→ away goalie 0 (pulled) · away skaters 6 · home skaters 5 · home goalie 1
```
which matches the observed distribution:

| code | meaning | count (2023020204) |
|---|---|---|
| `1551` | 5v5, both goalies in | 206 |
| `1541` | away 5 v home 4 → away PP / home PK | 47 |
| `1451` | away 4 v home 5 → home PP / away PK | 36 |
| `0651` | away goalie pulled, 6v5 (empty away net) | 20 |
| `1441` | 4v4 | 11 |

(The 20 `0651` events in `2023020204` are the trailing away team pulling its goalie late in period 3 — times 18:20–18:30 — no goal resulted.)

---

## 3. Time semantics (period clock, lengths, OT/SO) — task 0.3/0.4 confirmed

- **All `MM:SS` times are the in-period game clock.** Shift `startTime/endTime` and pbp `timeInPeriod` count **up** from `00:00`; pbp `timeRemaining` counts **down** from `20:00` (verified: first play `timeInPeriod 00:00` ↔ `timeRemaining 20:00`).
- **Regulation period length = 20:00 = 1200 s**, 3 periods. Parser exposes period-relative `start_s/end_s/duration_s` and an absolute `game_elapsed_start_s = (period-1)·1200 + start_s`.
- **OT & shootout — directly verified on `2023020145` (a shootout game):**
  - **OT shifts** appear as normal rows with **`period = 4`, `typeCode 517`** on the OT clock (example: `start 02:25 → end 04:02`, duration `01:37`). 43 such rows.
  - pbp `periodDescriptor` shows **`(4,"OT")` and `(5,"SO")`** — `periodType` is the authoritative OT/SO marker, not the period number alone.
  - **The shootout produces pbp events** (`period 5`, `periodType SO`: `period-start, shot-on-goal, goal, shootout-complete, period-end, game-end`) **but zero shift rows** (shift periods top out at 4). → Shootouts contribute no on-ice time.
- **Caveat carried to reconstruction:** regular-season OT is **5:00**, not 20:00 (playoff OT *is* full 20:00 periods 4,5,…). `game_elapsed_start_s`'s `(period-1)·1200` start offset is correct because periods 1–3 are always 1200 s; but any logic that assumes OT *length* = 1200 s would be wrong for regular-season OT. None of the six required fixtures reached OT (all max period 3), so this is flagged, not yet exercised.

---

## 4. `typeCode` filtering rule adopted (task 0.3)

**Keep `typeCode == 517`; drop `505`.** (`SHIFT_TYPECODE_SHIFT = 517` in `config.py`, applied in `parse_shifts`.)

Evidence the `505` rows are goal markers, not shifts — every `505` row has: `duration = null`, `shiftNumber = 0`, `startTime == endTime`, non-null `eventDescription` (`EVG`/`PPG`/`EN`), `eventDetails` = scorer/assists, and `detailCode ∈ {801,802,803}`. Their `playerId` is the **scorer**, and the goal is already fully represented in pbp. Counts: `2023020204` → 689×`517` + 5×`505`; `2023030411` → 794×`517` + 3×`505`.

**Goalies in shifts (task 0.3):** yes — goalies appear as `517` shift rows (2 per game in both audited fixtures; cross-checked against `rosterSpots.positionCode == "G"`). They must be excluded when counting *skaters* for strength states.

---

## 5. Earliest usable season (task 0.6)

**Earliest usable season with shift data: `2010-11`.** Probe = one mid-season game (`{season}020500`) per season, walking backward from 2010-11, stopping after **two consecutive** empty/failed seasons.

| season | gameId probed | HTTP | shift rows (517) | usable |
|---|---|---|---|---|
| 2010-11 | 2010020500 | 200 | 793 | ✅ |
| 2009-10 | 2009020500 | 200 | **0** | ❌ |
| 2008-09 | 2008020500 | 200 | **0** | ❌ (2nd consecutive → stop) |

Corroborated by the required fixtures: `2011020400` returns 703 shift rows, while `2008020300` returns 0. The `shiftcharts` endpoint responds `200` for pre-2010 games but with empty `data`, so **usability = "≥1 `517` row", not HTTP status.**

---

## 6. Assumptions in the brief that don't hold — and what exists instead

1. **`gameType` "02"/"03" strings vs integers.** The id *string* embeds `02`/`03`, but every payload body exposes `gameType` as an **integer** (`2`/`3`). Parse the id positionally; expect ints in bodies.
2. **Preseason (`01`) exists and isn't mentioned.** Club schedules return `gameType 1` games (8 for TOR/2023-24) alongside `2` (82) and `3`. Any enumeration must filter to `02` (and `03`) or it will ingest preseason.
3. **"pbp gives who was on the ice" — it does not.** Plays carry event participants (shooter, goalie, hitter…) but **no on-ice skater roster**. Confirmed empty across all plays. On-ice state comes only from shift charts.
4. **Shift feed is not purely shifts.** `shiftcharts.data` interleaves **goal-marker rows (`505`)** with real shifts (`517`); naïvely counting rows over-counts. Filter adopted in §4.
5. **`situationCode` was undocumented in the brief.** Format decoded and verified in §2d.
6. **"Old games error/return empty" generalized:** old games return **HTTP 200 with empty `data`**, not 404 — empty shift lists are the real signal (§1, §5).
7. **Goalie pulls have no event.** Inferred from `situationCode` / `goalieInNetId` (§2d), not an explicit play.
8. **Schedule vs gamecenter `gameState` vocab differ** (`FINAL`/`FUT` in schedule; `OFF`/`LIVE`/`FUT` in gamecenter & score). Normalize when enumerating completed games.

---

## 7. Row counts per fixture after parsing (task 0.7 deliverable)

`parse_shifts` (517-filtered) and `parse_pbp`, from cache; **0 negative durations** across all:

| gameId | parsed shifts (rows) | parsed pbp (rows) | negative durations |
|---|---|---|---|
| 2023020204 | 689 | 320 | 0 |
| 2023030411 | 794 | 368 | 0 |
| 2019020500 | 737 | 318 | 0 |
| 2015020001 | 832 | 327 | 0 |
| 2011020400 | 703 | 326 | 0 |
| 2008020300 | **0** | 56 | 0 |

Parser invariants asserted in `tests/test_parse.py`: exact shift/pbp counts for `2023020204`; non-negative durations for all; **every shift `playerId` present in the boxscore** (both audited games); typed dtypes.

---

## Open items flagged for Phase 1 (not acted on — awaiting go-ahead)

1. **Regular-season OT length (5:00)** vs the 1200 s absolute-time assumption — needs handling when a game reaches period 4 (playoff OT is fine).
2. **Pre-2010 coverage** — if the corpus must reach before 2010-11, the modern `shiftcharts` endpoint is insufficient; an alternative source (HTML report scraping) would be required. Recommend scoping the corpus to **2010-11 →** unless earlier is essential.
3. **`situationCode` for 3-goalie edge cases / penalty-shot** not seen in samples; revisit if encountered.

**Phase 0 complete. Stopping here per the preamble; awaiting instruction to begin Phase 1.**
