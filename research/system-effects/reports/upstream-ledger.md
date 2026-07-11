# Upstream ledger — System Effects

Defects found in production or Atlas data during this project. Nothing here is fixed
mid-project; each carries evidence, affected consumers, and a proposed fix layer for a
later gated decision.

---

## UL-1 · `stg_games` / `stg_game_context` season mislabeling (production) — MEDIUM

**Found:** Phase 1 (inventory + date-map build).

**Evidence.** A block of 2015-16 games is labeled `season = '2024-25'`:
```
SELECT season, EXTRACT(YEAR FROM game_date) yr, COUNT(*) FROM stg_games WHERE season='2024-25' GROUP BY yr
  2015 -> 386,  2016 -> 61,  2024 -> 636,  2025 -> 805
```
`stg_game_context` inherits it (e.g. game_id `2015010082`, a 2015 **preseason** game, is
tagged `2024-25` with coaches `Bruce Boudreau` / `Patrick Roy`). Regular-season counts
per production season are consequently wrong: `stg_games` reports 2015-16 = 806 (true
1230) and 2024-25 = 1736 (true 1311). `game_date` itself is single-valued and correct per
`game_id` (0 games with conflicting dates), so the date is trustworthy — only the derived
`season` label is corrupt.

**Affected consumers.** Anything grouping `stg_games` / `stg_game_context` by `season`:
season-level marts, coach coverage-by-season, any "games this season" count. Likely a
season-derivation bug (inherited raw field vs. deriving from the `game_id` prefix /
`game_date`).

**Proposed fix layer.** Staging — derive `season` from the `game_id` season prefix (or
`game_date`) rather than the inherited payload field, then reconcile downstream counts.

**Immunity in this project.** System Effects anchors the game universe on the FROZEN Atlas
`games.parquet` (correct season labels) and attaches coaches/dates by `game_id` join, so the
mislabeling cannot leak into the regime ledger. No action needed here; recorded for production.

---

## UL-2 · `player_archetypes` was stale on the rebuilt backbone — RESOLVED (no action)

**Found:** Phase 0. **Resolved:** observed self-healed during Phase 1.

**Evidence.** `player_archetypes` (`fit_archetypes_v2.py`) reads the segment backbone
(`int_shift_segments`, `int_segment_context`, `int_on_ice_events`). Those were rebuilt
`2026-07-11 03:05`, but at Phase 0 `player_archetypes` had not been re-fit since
`2026-06-17` — stale-backbone-derived and stale. By `2026-07-11 14:06:58` the production
P4 recompute chain **re-fit it** (7,203 rows) on the deduped segments. Status: resolved.

**Note for this project.** Phase 3 will still derive its **own** archetype pools from the
frozen Atlas assets (position + Atlas-variant RAPM + context) — an **isolation** choice so
System Effects does not couple to a production table that re-fits/drifts, not a staleness
workaround. Recorded per product-owner request.

---

## UL-3 · Right-rail missing one coach for 2 games (source gap) — LOW

**Found:** Phase 1 backfill parse.

**Evidence.** Of 16,526 backfilled games, exactly 2 have a single null coach:
`2012020468` (2012-13, away coach null; home = Claude Noel) and `2012020484` (2012-13,
home coach null; away = Ron Rolston). The NHL right-rail `gameInfo` simply omits that one
team's `headCoach` for these games.

**Affected consumers.** The affected team-game rows drop out of their team's regime
coverage (reported as null products). Negligible: 2 of 38,298 team-games.

**Proposed fix layer.** Optional — backfill the two coaches from the HTML `RO{gg}.HTM`
roster report (documented fallback) if ever needed. Not worth a fetch now.
