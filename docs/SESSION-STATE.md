# Session state — finalization plan progress

Working branch: **`finalization`** (10 commits ahead of the redesign work).
Last updated at the end of the shift-foundation + Edge-ingestion session.

## Done & validated (committed)
- **Phase 0** — proxy relabeling (`zone_entry_proxy_*`), model-layer conventions
  (`models_ml/`, `insight_engine/`, `docs/methodology/`, `frontend/src/config/metrics.ts`),
  dbt vars, README + Makefile. dbt compile + pytest + frontend build all green.
- **Phase 1.1 — shift charts (COMPLETE)**
  - Ingestion: `get_shift_charts`, loader `raw_shift_charts`, `scripts/ingest_shifts.py`,
    `backfill_historical.py --tables {boxscore,pbp,shiftcharts}` (resumable shift-only path),
    daily DAG wired, `scripts/smoke_ingest_shiftcharts.py`.
  - **Full history backfilled: ~13,850 games, 2015-16→2025-26, 0 failures.**
  - Models: `stg_shifts` → `int_shift_segments` (53.1M rows) → `int_segment_context`
    (4.5M) → `int_on_ice_events` (4.3M), all materialized as tables.
  - **Validated: 81,762 goals at 99.95% on-ice attribution; ~48 5v5 min/game every season.**
  - Key corrections to the plan: typeCode **517 = real shifts, 505 = goal annotations**
    (plan had it backwards); event→segment uses **(start, end]** (goals carry the
    shift-end timestamp); excluded 0.01% degenerate/corrupt durations.
- **Phase 1.2 — Edge ingestion layer (DONE; staging/marts NOT yet)**
  - **Real endpoint family discovered** (plan's `/v1/edge/skater-detail` was dead):
    `/v1/edge/{entity}-{report}/{id}/{season}/{gameType}`. Reports: skater
    skating-speed-detail / skating-distance-detail / shot-speed-detail /
    shot-location-detail / **zone-time** (no `-detail` suffix); goalie
    save-percentage-detail; team shot-location-detail. See `scripts/EDGE_FINDINGS.md`
    + saved payloads in `scripts/edge_samples/` (gitignored).
  - `get_edge_skater/goalie/team`, `scripts/explore_edge.py`, `scripts/refresh_edge.py`
    (resumable, `make edge-refresh SEASON=...`), `raw_edge_*` sources + loader.
  - Only a 15-entity sample ingested so far (2024-25) — run a full refresh per season.

- **Phase 1.3 — non-Edge API surfaces (CODE COMPLETE; full backfills pending)**
  - **All 5 surfaces probed live** (`scripts/STATSREST_FINDINGS.md`): faceoffs use
    `skater/faceoffwins` (zone + ev/pp/sh splits, paged); landing carries per-goal
    `highlightClipSharingUrl` + `pptReplayUrl` (the latter is real — note for 1.4);
    right-rail carries scratches/coaches/seasonSeries/teamGameStats; glossary lives on
    the **stats-REST host** (`/stats/rest/en/glossary`; api-web `/v1/glossary` is 404);
    standings-by-date gives ranks + l10 (offseason dates return 0 rows).
  - Ingestion: `get_skater_faceoffs/get_game_landing/get_game_right_rail/get_partner_odds/
    get_glossary/get_standings_by_date`; loader serialize-field + game_id-injection rules;
    `raw_*` sources. Refresh scripts (resumable, repo precedent = per-surface like Edge):
    `refresh_statsrest_faceoffs.py`, `refresh_game_context.py`, `refresh_standings.py`,
    `refresh_partner_odds.py`, `ingest_glossary.py`. Smoke tests for all 5 (all green).
  - Staging: `stg_statsrest_faceoffs`, `stg_standings`, `stg_game_context`,
    `stg_partner_odds` (de-vig; **INTERNAL ONLY**, no API/UI). Mart: `mart_player_faceoff_zones`.
    dbt build PASS=13. Validated: Crosby/Hischier/Larkin top faceoff vol, zone sums consistent;
    G4 context = 8 goals all w/ links, scratches/series/last10 parsed.
  - Backend: `GET /games/{id}/context` (joins last-10 from `stg_standings` as-of game date).
    Frontend: GameDetail Overview gets a **Matchup context** card (series/last-10/scratches via
    ComparisonRow) + scoring-timeline rows link to highlight video (`target=_blank`). `npm run build` green.
  - DAG: landing/right-rail/standings/partner-odds added to daily `ingest_nhl_data`;
    new weekly `refresh_weekly_aux` task (faceoffs + glossary, Monday-gated).
  - **NOT done:** `partner_odds` de-vig path is PENDING in-season payload (offseason → games=[]);
    full landing/right-rail backfill for current+prev season (run `refresh_game_context --season`);
    daily standings backfill (have weekly sample); `backfill_historical.py` intentionally NOT
    touched (per Edge precedent, new surfaces use their own refresh scripts).

## Next up (fresh-context work)
1. **Phase 1.2 finish — Edge staging/marts/backend.** `stg_edge_skaters/goalies/teams`
   (parse the 5 report shapes from `edge_samples/`), `mart_edge_player_profile` /
   `mart_edge_team_profile`, `GET /players/{id}/edge` + `/teams/{id}/edge`,
   `backfill_edge.py`, DAG weekly task. Zone-time gives oz/nz/dz + zone starts by strength.
2. **Phase 1.3 operational runs** — `refresh_game_context --season 2025-26` then `2024-25`;
   `refresh_standings --season 2025-26/2024-25` (daily cadence); confirm partner-odds parse
   once games return in-season (verify the american-odds JSON path in stg_partner_odds).
3. **Phase 1.4** — ppt-replay spike (note: `pptReplayUrl` JSON sprites exist per goal in
   landing, e.g. `wsr.nhle.com/sprites/{season}/{game}/ev{eventId}.json`) + backfill floor to 2010-11.
4. **Incremental refactor (important):** make `int_shift_segments`/`int_segment_context`/
   `int_on_ice_events` incremental by game so the nightly run doesn't rescan 11 seasons
   (the monolithic build is ~17 min and needs the raised timeout below).

## Environment gotchas (bit us this session)
- Use the project venv or `pip install -U "google-cloud-bigquery>=3.20"` — older versions
  fail with `_blocking_poll() got an unexpected keyword argument 'retry'`. Pinned in requirements.
- dbt: always `--target dev` locally; the segmentation rebuild needs
  `timeout_seconds` raised in `dbt/profiles.yml` (set to 1800 locally; default 300 times out).
  profiles.yml is gitignored — set this in any new environment.
- Always `set -a; source .env; set +a` and export `GOOGLE_APPLICATION_CREDENTIALS` first.

## Resume commands
```bash
# env
cd /Users/codytownsend/Desktop/nhl/NIR && set -a && source .env && set +a
export GOOGLE_APPLICATION_CREDENTIALS=$PWD/secrets/nhl-intel-sa.json
# full Edge refresh for a season (when ready to populate beyond the sample)
python -m scripts.refresh_edge --season 2025-26
# explore real Edge payloads (already saved under scripts/edge_samples/)
python scripts/explore_edge.py --season 20242025
```

## Operating model (from docs/HANDOFF-*.md)
I write code + `scripts/smoke_ingest_*` per surface; long backfills/training run in the
background (I have network + BigQuery access here). Model jobs get `--dry-run/--sample/--resume`
+ a pasteable report. Archetype naming (Phase 4.2) is the one human-in-the-loop step.
No placeholders/mock data — features die or are labeled proxies when the API can't support them.
