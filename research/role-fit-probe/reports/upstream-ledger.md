# Upstream ledger — role-fit-probe

Defects/gaps found in production or frozen-data during this probe. Nothing here is fixed mid-probe;
each carries evidence, affected consumers, and a proposed fix layer for a later gated decision.

---

## UL-P1 (Step 0b, HIGH) — the Atlas `events.parquet` under-projects `stg_play_by_play`, dropping 6 player-attribution columns

**Finding.** The frozen Atlas `events.parquet` attributes an individual player only to shot-family
events (shooter/scorer/assist). Hits, takeaways, giveaways, blocked-shots (blocker), and penalties
show **0% player attribution** — but this is an **ingestion projection artifact, not a data-truth.**
The upstream production staging model **`stg_play_by_play` parses and exposes** all of these player
ids directly from `raw_play_by_play.details`:

| event | player id(s) in `stg_play_by_play` | in `events.parquet`? |
|---|---|---|
| hit | `hitting_player_id`, `hittee_player_id` | **dropped** |
| takeaway / giveaway | `player_id` (generic details.playerId) | **dropped** |
| blocked-shot | `blocking_player_id` (the blocker) | **dropped** (only the shooter was kept) |
| penalty | `committed_by_player_id`, `drawn_by_player_id` | **dropped** |
| shot / goal / assist | `shooting_/scoring_/assist1_/assist2_player_id` | kept |

**Evidence (code, no fetch).**
- `dbt/models/staging/stg_play_by_play.sql` selects `hittingPlayerId`, `hitteePlayerId`,
  `blockingPlayerId`, `committedByPlayerId`, `drawnByPlayerId`, and `playerId` from
  `raw_play_by_play.details` (lines ~38-47).
- `research/deployment-atlas/src/atlas/sources.py::materialize_events` SELECT keeps only
  `shooting_player_id, scoring_player_id, goalie_in_net_id, assist1_player_id, assist2_player_id,
  event_owner_team_id` — the six columns above are never selected. `EVENT_COLUMNS` mirrors that.
- Production already consumes the dropped fields: `int_shot_attempts.sql` uses `blocking_player_id`;
  the pipeline exposes per-player faceoffs via a **separate** source `stg_statsrest_faceoffs`
  (`mart_player_faceoff_zones`) — faceoff winner/loser is NOT in the pbp stream (winning/losingPlayerId
  are not parsed), but per-player per-zone faceoff W/L is available at season grain from stats-REST.

**Affected consumers.** Any player-level role/action model built on the frozen `events.parquet`
(this probe's Link 1; the flat "shot-only" ceiling in §0). Not a correctness bug in existing shot
metrics — a coverage gap for possession/defensive/discipline attribution.

**Recovery (report only — the probe does not fetch).** This is a **re-projection, not a re-fetch**:
the raw data is already ingested in BigQuery (`raw_play_by_play` → `stg_play_by_play`). Adding the six
columns to `materialize_events`'s SELECT (and joining `stg_statsrest_faceoffs` for faceoffs) recovers
individual attribution for **hits, takeaways, giveaways, shot-blocks, penalties, and faceoffs** with
no external API call. A true re-fetch would only be needed to backfill any games missing from
`raw_play_by_play` (the known 2-game pbp gap already handled by `api:gap_fetch`).

**Proposed fix layer.** Either (a) a probe-local enriched events table built by a targeted production
read of `stg_play_by_play`, or (b) a new/extended Atlas events materialization widening the SELECT.

**Status — RESOLVED probe-side (owner authorized the read).** `src/rolefit/enrich.py` executed a
one-time, read-only pull of the six columns (keyed by game_id, event_id) from
`nhl_staging.stg_play_by_play`, plus per-player per-zone faceoffs from `nhl_staging.stg_statsrest_
faceoffs`, into probe-local parquet. **No production table was written; frozen Atlas assets
untouched.** Source population confirmed ~100%: hits 965,087 (hitter+hittee), blocks 612,049,
giveaways 398,846, takeaways 276,783, penalties committed 160,712 / drawn 150,040.

Provenance (`data/parquet/enriched/MANIFEST.json`), pulled 2026-07-13 11:47:35, project
`nhl-intel-498216`:
- `event_players.parquet` — 6,545,861 rows, sha256 `078a0dda56ca1b37…`
- `faceoffs.parquet` — 14,231 rows, sha256 `d019cc24e5db8b86…`

**Production fix still deferred/gated:** widening the Atlas/production `materialize_events` SELECT is
a later production decision. Standing flag: any future project wanting two-way events must not
re-derive from the frozen Atlas `events.parquet` as-is (it is offense-only where the raw data is
two-way). See probe.md §1b for the two-way role-space re-gate built on this recovery.

---

## UL-P2 (Link 1 re-gate, MEDIUM) — the shot 5v5 filter silently dropped pre-2015; original §1 was 2015-16+ only

**Finding.** `events.is_primary_scope = (season_start_year >= 2015)` (Atlas modeling floor 2015-16;
pre-2015 admitted but integrity-pending). The role-profile shot extractor filters on
`is_primary_scope`, so **pre-2015 shot features are empty** — their rate axes come out 0/null, whose
within-(position,season) z-score is 0/0 = NaN, which the PCA `drop_nulls` then removes. Net effect:
the original Link 1 (§1) **silently ran on the 2015-16 → 2025-26 window (11 seasons), not 16**, while
the report labelled it 16-season. The verdict is unaffected (re-running explicitly scoped to
2015-16+ reproduces §1 exactly: F PC1 0.64/0.66, D PC2 0.77/0.72, PASS 5/8), but the scope label was
wrong.

**Resolution (probe-side).** The probe is now **explicitly scoped to the integrity-validated primary
window 2015-16 → 2025-26**; pre-2015 is broken out by exclusion (consistent with the program's
"pre-2015 admitted but always broken out" rule and the Atlas modeling floor). Profile builders default
to `SEASONS_PRIMARY`; the pre-2015 garbage profiles were removed. §1's numbers stand (they were always
2015-16+); the label is corrected in §1b. Not a production defect — a probe scoping/labelling fix.
