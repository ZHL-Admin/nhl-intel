# Shift-data HTML fallback — production ingestion report

Date: 2026-07-10
Scope: production ingestion only. No `research/` files modified, no history
re-backfilled, no dedup jobs or dbt models touched.

## Problem

The stats-REST shiftcharts endpoint
(`api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={id}`) returns an
EMPTY `data` array for a large share of 2024-25 / 2025-26 FINAL games (verified
live: 0 shift rows). The daily flow wrote those empties into
`nhl_raw.raw_shift_charts`. The proven recovery is the NHL HTML TOI reports,
which was validated byte-for-byte against the JSON feed during the 2026-07-10
backfill of 563 games. This change promotes that parser into production and wires
it as a live fallback so newly-final games self-heal each night.

## Files added

- `ingestion/shift_report_parser.py` — the HTML shift-report parser + fallback
  builder, copied and adapted from the research parser
  (`research/deployment-atlas/src/atlas/shift_report.py` +
  `backfill_shifts.py`). No import of `research/`. Public surface:
  - `parse_report(html)` → `list[ReportShift]` (OT/OT2/SO handling via
    `_period_number`).
  - `report_url(game_id, side)` — `www.nhl.com/scores/htmlreports/{season8}/T{H|V}{gg6}.HTM`.
  - `fetch_report(game_id, side)` — httpx GET with browser UA/referer +
    tenacity retry (matches `nhl_api.py` conventions).
  - `roster_from_pbp(pbp)` — resolves `(teamId, sweater) → (playerId, first,
    last)` and home/away team ids from that game's in-memory play-by-play
    `rosterSpots` (no extra network/BigQuery call).
  - `build_shift_elements(game_id, pbp, ...)` — normalizes to the raw_shift_charts
    517-row element shape and stamps the provenance marker.
  - `build_fallback_rows(game_ids, pbp_by_gid, ...)` — one `{id, game_id, data}`
    row per recoverable game; skips games with no in-memory pbp or that parse to
    zero shifts (never writes empties).
- `tests/test_shift_report_parser.py` — 8 tests. Hermetic: period mapping
  (OT/OT2/OT3/SO), mm:ss round-trip, URL builder, synthetic-HTML parse,
  sweater→player resolution + provenance marker + unresolved-sweater warning,
  and `build_fallback_rows` skip semantics. Network (`@pytest.mark.network`,
  skips offline): dual-source reconciliation for a regulation game (2025020001)
  and an OT game (2023020145), asserting the recovered
  `(teamId, playerId, period, start_second, end_second)` intervals equal the
  JSON 517 rows EXACTLY.

## Files changed

- `ingestion/loaders.py` — added `delete_rows_by_game_id(project, dataset,
  table, game_ids)`, the idempotency helper for delete-then-insert per game_id.
- `dags/nhl_daily.py`:
  - `ingest_nhl_data`: after the JSON shift-charts load, a fallback block detects
    FINAL games (boxscore `gameState` in `{FINAL, OFF}`) whose JSON shift response
    was empty, recovers shifts from the HTML reports, and delete-then-inserts the
    recovered row. JSON stays PRIMARY; the fallback fires ONLY on empty JSON.
    Errors are caught and logged non-fatally (the JSON rows are retained).
  - `check_shift_coverage` — new monitor task/function (see below).
  - Wired `ingest_task >> check_shift_coverage_task` (leaf, so a shift gap
    surfaces without blocking the nightly report).
- `pytest.ini` — registered the `network` marker.
- `requirements.txt` — added `beautifulsoup4` and `lxml` (the parser's deps;
  previously only present transitively).

## Provenance marker (chosen)

Each recovered shift ELEMENT carries `"_source": "html_shift_report"` inside the
serialized `data` JSON (field on the element, not a new table column). Rows from
the JSON feed have no `_source` key, so downstream:

- `json_extract_scalar(shift, '$._source')` = `NULL` → primary JSON feed;
- `... = 'html_shift_report'` → HTML fallback.

Chosen over a table column because (a) it is queryable per-shift with the exact
value the 2026-07-10 backfill already wrote, so all recovered rows (history +
nightly) are uniform, and (b) it needs no schema change to `raw_shift_charts`.

## Monitor + how the DAG surfaces failures

DAG failure-surfacing today: there is NO alert/`on_failure_callback` anywhere in
`dags/`. The only mechanism is Airflow task failure plus `"email_on_failure":
True` in `default_args` (with `retries: 2`).

`check_shift_coverage` counts FINAL games (latest boxscore `gameState` in
`{FINAL, OFF}`, ingested in the last 3 days) whose latest `raw_shift_charts` row
is still an empty array after JSON + HTML fallback. It logs a loud line and
RAISES `RuntimeError` when any remain — which marks the task failed and emails
via the existing mechanism (per the brief, a loud log + raised exception is the
accepted mechanism given there is no alert callback). Zero uncovered games = pass.

## Verification (dry-run; production untouched)

### 5-game reconciliation — HTML fallback vs research backfill parquet
Games previously empty in the JSON feed; recovered elements passed through the
same stg_shifts transform (517-only, dedup on (player,start,end), duration
1..1200) and compared to `research/deployment-atlas/data/parquet/shifts.parquet`:

| game       | html_rows | pq_rows | html_TOI_s | pq_TOI_s | match |
|------------|-----------|---------|------------|----------|-------|
| 2025020814 | 772       | 772     | 42677      | 42677    | OK    |
| 2025020303 | 753       | 753     | 42039      | 42039    | OK    |
| 2025020100 | 762       | 762     | 42554      | 42554    | OK    |
| 2025020400 | 705       | 705     | 42915      | 42915    | OK    |
| 2025020700 | 704       | 704     | 43518      | 43518    | OK    |

All 5 match on both row count and TOI sum; zero unresolved-sweater warnings.
(Unit tests additionally reconcile the raw intervals byte-for-byte against the
live JSON 517 rows for 2025020001 and the OT game 2023020145.)

### Healthy-game no-fire (JSON path untouched)
Three JSON-healthy FINAL games — the empty-final gate does NOT fire:

| game       | json_rows | fallback_fires |
|------------|-----------|----------------|
| 2025020200 | 732       | False          |
| 2025020500 | 769       | False          |
| 2025020600 | 811       | False          |

The fallback block only inspects games whose JSON `data` is empty, so the JSON
load path is byte-for-byte unchanged for healthy games.

### Idempotency (temp table `nhl_raw._tmp_shift_fallback_verify`, then dropped)
Seeded an empty JSON-path row per game, then ran the fallback (delete-then-insert
via `delete_rows_by_game_id` + serialized load) twice:

```
seed(empty):                 rows-per-game={2025020303: 1, 2025020814: 1}
after fallback run #1:        rows-per-game={2025020303: 1, 2025020814: 1}
after fallback run #2 (rerun):rows-per-game={2025020303: 1, 2025020814: 1}
game 2025020814: final_rows=1 shifts=772 _source=html_shift_report
game 2025020303: final_rows=1 shifts=753 _source=html_shift_report
```

Exactly one row per game after two runs; the surviving row is the HTML data with
the provenance marker. Temp table dropped; production `raw_shift_charts`
untouched.

### Tests
`pytest tests/test_shift_report_parser.py` → 8 passed (incl. both live
reconciliation tests). Full targeted run with `test_api.py` → 9 passed.

## Integration notes / awkwardness

- Roster resolution reuses the play-by-play payloads the daily flow already
  fetches in memory (`play_by_plays`), so the fallback needs no extra
  network/BigQuery round-trip — cleaner than the research backfill's BigQuery
  `game_rosters` query, which existed because the backfill ran standalone.
- FINAL detection comes from the boxscore `gameState` (`{FINAL, OFF}`) already
  fetched earlier in the same task; no new fetch.
- The JSON path still writes empty rows for empty-final games (unchanged); the
  fallback then delete-then-inserts, removing those same-day empties. This keeps
  the JSON path provably untouched (the fallback is purely additive) at the cost
  of a transient empty row within the run — acceptable and idempotent.
- `raw_shift_charts` serializes only the `data` field (keyed by table_id in
  `loaders.py`), so the fallback rows ride the exact same `load_json_to_bigquery`
  serialization as the JSON path; no schema divergence.
- The daily task is a single large `ingest_nhl_data` function; the fallback slots
  in after the shift-charts load rather than as its own task. A separate task
  would need the in-memory pbp/boxscore state re-fetched or passed via XCom, so
  inline was the lower-risk choice.
