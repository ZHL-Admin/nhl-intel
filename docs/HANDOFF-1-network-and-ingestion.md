# Handoff 1: Network access and NHL API ingestion environment

**Provide this when Claude Code reports it cannot reach the NHL API (Phase 1 prompts 1.1 through 1.4, and the daily DAG).**

## The situation
Ingestion code targets two public, unauthenticated NHL hosts:
- `https://api-web.nhle.com` (schedule, gamecenter pbp/boxscore/landing/right-rail, edge, ppt-replay, partner-game, standings, glossary)
- `https://api.nhle.com` (stats REST: shiftcharts, skater/goalie reports with cayenneExp paging)

No API keys exist or are needed. The only requirement is outbound HTTPS from wherever the ingestion scripts run.

## Operating rule for Claude Code
You may not be able to reach these hosts from your sandbox. That is fine and expected. The division of labor is:

1. **You write and fully wire the code** (ingestion functions, raw-table loaders, DAG tasks, backfill flags, dbt staging models) exactly as specified in the prompt.
2. **You also write a runnable smoke script** for each new surface at `scripts/smoke_ingest_<surface>.py` that: fetches ONE real example (one game's shift chart, one player's Edge detail, etc.), prints the top-level keys and 30 lines of pretty JSON, and exits nonzero on any HTTP or parse failure. No BigQuery writes in smoke scripts.
3. **You hand me the exact commands to run.** I will run them on my machine (which has open network and the GCP service account) and paste the output back to you. Treat my pasted output as the ground truth for schema decisions (field names, types, undocumented parameters).
4. **Never substitute imagined payloads for real ones.** If a schema decision depends on a payload you haven't seen, stop at the smoke script and ask me to run it. The findings docs (EDGE_FINDINGS.md, STATSREST_FINDINGS.md, PPT_REPLAY_FINDINGS.md) get written only from real pasted output.

## What I will run, in order, when you hand me commands
```bash
# from repo root, venv active, .env loaded
python scripts/smoke_ingest_shiftcharts.py --game-id 2025020500
python scripts/smoke_ingest_edge.py --player-id 8478402 --season 20252026
python scripts/smoke_ingest_statsrest.py --season 20252026
python scripts/smoke_ingest_landing.py --game-id 2025020500
python scripts/smoke_ingest_partner_odds.py
python scripts/explore_ppt_replay.py
# then the real loads
python backfill_historical.py --season 2025-26 --tables shiftcharts
python scripts/refresh_edge.py
python scripts/backfill_edge.py
```
Known-good test IDs you can hardcode as defaults: game `2025020500` (any regular-season 2025-26 game id of form 2025020001-2025021312 works), player `8478402` (Connor McDavid), team id `10` (Toronto). If an ID 404s I will substitute a valid one and tell you.

## Rate limiting and politeness (bake into the code, not the docs)
- Reuse the existing tenacity retry pattern (3 attempts, exponential 2-10s) for every new function.
- Backfill concurrency: keep the existing async semaphore; cap at 5 concurrent requests against api.nhle.com (the stats REST host is the more sensitive one) and 10 against api-web.nhle.com.
- Add a `--sleep-ms` flag (default 100) between sequential requests in refresh/backfill scripts.
- All raw responses land unmodified (existing loader pattern); transformation happens only in dbt.

## Failure protocol
If I paste output showing an endpoint is dead, moved, or shaped differently than the plan assumed: update the plan's assumption in the relevant FINDINGS doc, adapt the staging model to the real shape, and note the deviation in the commit message. The blueprint allows features to die when the API can't support them; it does not allow pretending.
