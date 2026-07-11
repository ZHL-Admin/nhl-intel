# P4 consumer sweep — BLOCKER (STOP for a gate)

The P4 consumer sweep is paused on a hard failure that needs a ruling before I
touch a P1-committed model. **No consumer behavior was changed. No threshold was
tuned.** This is a stop-and-report per the standing boundary rules.

## What ran

Snapshotted the 9 headline downstream rating tables as `*_p4pre` (the "before"
for the ratings-diff dossier), then rebuilt the dbt subtree downstream of both
retrained sources:

`dbt run --select source:nhl_models.shot_xg+ source:nhl_models.player_impact+`
→ **PASS=24, ERROR=2, SKIP=4** (the 4 skips are downstream of the 2 errors).

- **Failed:** `mart_player_game_stats`, `mart_team_identity`
- **Error:** `Bad int64 value: ` (empty string cast to int64)

The models_ml recompute chain (compute_ratings → composite/gar/archetypes → …)
is **not started** — several of its jobs read these two marts, so running it now
would produce a half-consistent state.

## Root cause (fully diagnosed)

The failure is in the **`stg_shifts` view**, not in either retrained model:

- `int_shift_segments` and all P1 on-ice marts rebuilt fine because they select
  only `shift_start_seconds`/`shift_end_seconds`. The two failing marts are the
  only consumers that scan the view to completion in a way that evaluates the
  **`shift_end_seconds`** cast over every row.
- **1,129 shift rows** (across **174 games**, all **2019-20 regular season**,
  typeCode 517) carry an **empty `endTime`** (`""`) with `duration = "00:00"`.
  `shift_end_seconds` computes `cast(split(end_mmss,':')[offset(1)] as int64)`;
  for `end_mmss=""` that casts `''` → **`Bad int64 value`**.
- These are the **documented degenerate zero-duration 2019-20 records** the view
  already intends to drop via the outer `duration_seconds between 1 and 1200`
  filter. The bug is **cast ordering**: `parsed` evaluates the `shift_end_seconds`
  cast before the outer filter removes the rows.

**Provenance:** original JSON feed (no `_source` tag) — **not** the 563-game HTML
backfill (which touched 2025-26/2024-25/2013-14, not 2019-20), and **not** the
P1 dedup/period-5 change (those only *remove* rows and don't touch `endTime`).
It is a pre-existing latent defect, hidden while the scheduler was dormant
(ledger D8) so these two marts sat stale rather than rebuilding.

## Proposed fix (staging layer, zero data loss) — needs your gate

Add a well-formedness guard to the `parsed` CTE filter in `stg_shifts.sql`
(same layer and same class as the existing documented noise rules), so the cast
never sees an empty time component:

```sql
-- current (line 58):
where duration_mmss is not null and duration_mmss != ''
-- proposed:
where duration_mmss is not null and duration_mmss != ''
  and start_mmss like '%:%' and end_mmss like '%:%'
  and split(end_mmss, ':')[safe_offset(1)] != ''
  and split(start_mmss, ':')[safe_offset(1)] != ''
```

**Zero real-data loss:** every affected row has `duration = "00:00"`, so all 1,129
are already excluded downstream by `duration_seconds between 1 and 1200`. The
guard only prevents the cast from evaluating on rows the view already discards.

This is a new change to the P1-frozen `stg_shifts` (committed `9a98923`), so it
is gated. On approval I will apply it, re-run the 2 marts + 4 skipped models to
green, then resume the models_ml recompute chain and produce the ratings-diff
dossier.

## Resolution — guard applied, no-op assertion PASSED (2026-07-11)

The guard was applied to `stg_shifts.sql` (`parsed` CTE filter) and gated-approved
as staging-only. Acceptance test per the gate — **output must be unchanged**:

- **Pre-guard reference:** a `safe_cast` replica of the exact view logic (same
  filters), which equals the view's *intended* output (the erroring rows have
  `duration_seconds = 0` and are excluded by `between 1 and 1200` regardless).
- **Post-guard:** the rebuilt guarded view, materialized directly.
- **Metric:** per-season `count(*)`, `sum(duration_seconds)`, `sum(shift_end_seconds)`.

**Result: byte-identical across all 16 seasons** (2010-11 … 2025-26),
15,943,699 total rows. Zero rows changed. The guard is a proven no-op on output;
**the P1 per-game reconciliation stands without a full re-run.** (2019-20:
825,503 rows both sides — the 1,129 degenerate rows were already absent from the
intended output.)

## New ledger entry (proposed)

**D9 — 2019-20 empty-`endTime` degenerate shift rows break `stg_shifts` casts.**
1,129 rows / 174 games, typeCode 517, `duration 00:00`. Fix layer: dbt staging
(cast-ordering guard). Affected consumers: `mart_player_game_stats`,
`mart_team_identity` (both stale since the scheduler went off; every other
consumer avoided the `shift_end_seconds`/`duration_seconds` full scan).
