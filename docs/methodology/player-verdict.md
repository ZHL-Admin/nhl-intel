# Player Verdict (composed scouting read)

A per-player, two-horizon scouting read on the Player Profile, replacing the fixed per-archetype
descriptor. Gemini **narrates a deterministic payload** (it never computes); every figure it
references is verified against that payload before the read is stored or shown.

## Pipeline
```
models_ml/build_verdict_payload.py   deterministic two-horizon payload (no LLM)
models_ml/generate_verdicts.py       Gemini narration -> consistency checker -> nhl_models.player_verdict
backend GET /players/{id}/verdict     read-only; 404 -> profile falls back to the archetype descriptor
```

## Evidence payload (two horizons)
- **identity** (durable, multi-year): the archetype cluster is **modal across the three-season window**
  (NOT the latest season — a single off-season blip must not become the player's identity; ties break
  toward the more recent). It is surfaced as STYLE, never tier: `archetype.style` (how he plays, with
  any tier/quality tail stripped) and `archetype.family`; `archetype.cluster_label` is kept only for
  traceability and is **never** the identity noun (a style cluster can carry a tier word like
  "secondary" it does not mean — the noun comes from value, see below). `season_sensitive` is true only
  when no label holds a strict majority of the window or the family changes. `durable_traits` = the
  player's 3-year `player_impact` dimensions within position, selected as a **band** (every dim within
  `DURABLE_BAND` of the top dim and >= `DURABLE_FLOOR`, EV impact ordered ahead of special teams) so a
  spread of mid-high traits is described as a spread, not collapsed to one spike. `display_name`,
  `career_seasons`/`career_games`, `confidence` ∈ {high, medium, low} from career games
  (>= 250 high, >= 100 medium, else low) — the shrinkage that makes thin samples hedge.
- the identity **noun** is built from `current.overall.value_tier` (elite / high-end / middle-tier /
  depth / fringe, by overall percentile within pool) + family + durable traits — never the cluster name.
- **current** (this season): `overall` (production / play-driving / overall percentiles + agreement),
  `top_traits` / `watch_outs` (radar spokes by percentile, with honesty tag), `style`, `finishing`
  (actual vs expected SH%), `consistency`, and `deployment`.
- **deltas**: current vs the multi-year baseline (e.g. finishing below/above expected), only where it
  genuinely diverges.
- **horizon** (optional): a NEUTRAL note when current production and 3-year EV play-driving impact
  diverge by >= `HORIZON_GAP_PTS`. The two lenses measure different things; the prose may state this
  plainly but **never** as the model underrating or overrating anyone.

### Zone-usage gate (hard rule)
Zone deployment enters the payload **only** as `current.deployment.oz_start_pctile_edge` — the
**NHL Edge** OZ-start percentile (official, all situations, neutral in the denominator), labeled
"NHL Edge". The prompt forbids any other zone-start number. **PDO and live hot/cold are excluded**
(served separately, never baked into the weekly prose).

## Narration + consistency checker
Gemini returns `{ long, short, numbers_used: [{field, asserts}] }`. The checker resolves each
`field` (a dotted path into the payload) and compares the asserted number to the payload value
(within `CHECK_TOL`, normalising 0-1 vs 0-100). Any mismatch — including a **fabricated field not in
the payload** (e.g. an invented PDO) — fails the check; the verdict is regenerated once, then
dropped and never shown. (Mirrors the insight-engine consistency rule.)

The checker resolves both bracket (`durable_traits[0].pctile_3yr`) and dotted (`durable_traits.0...`)
index notation, so a correctly-cited list field is not falsely rejected. A second, non-numeric
`quality_check` also triggers regeneration: the long read must be <= `MAX_SENTENCES` (4), any zone-START
clause must carry "NHL Edge" and appear at most once, and no raw decimal/proportion may leak into prose.
Failing either check regenerates up to `MAX_REGEN_ATTEMPTS` times, then the verdict is dropped.

The full system prompt lives in `models_ml/generate_verdicts.py` (`SYSTEM_PROMPT`); it requires the read
to open with `display_name` (never the archetype label as a name) and to use pronouns thereafter.
Constants: `models_ml/config.VERDICT` (model: `gemini-2.5-flash-lite`).

## Cadence
- **Identity inputs** (player_impact 3yr, archetypes) recompute on their own slow clock; this job
  only reads them.
- **Written paragraph**: weekly, scoped to players who played in the last 7 days (`--weekly`).
- **Full regenerate**: `--full` on an archetype/radar refit or payload-schema change.
- **Live signals** (hot/cold, active streak): served from the marts at page load, never in the prose.

## Run
```
# inspect the deterministic payload
python -m models_ml.build_verdict_payload --player 8478402 --season 2025-26
# generate (needs LLM_API_KEY); --dry-run prints payloads without calling Gemini
python -m models_ml.generate_verdicts --players 8478402 8471675 --season 2025-26
python -m models_ml.generate_verdicts --weekly --season 2025-26     # weekly DAG cadence
python -m models_ml.generate_verdicts --full   --season 2025-26     # backfill / refit
```
Backfill is concurrent (`--concurrency`, default 8) and **checkpointed**: completed verdicts flush to
BigQuery every `PERSIST_BATCH` (40), so a crash or stop loses at most one partial batch. Re-run with
`--skip-existing` to resume — it skips players already written for the season and continues:
```
python -m models_ml.generate_verdicts --full --season 2025-26 --skip-existing --concurrency 8
```
Throughput note: on the **free** Gemini tier `gemini-2.5-flash-lite` throttles hard after an initial
burst (~1-4 players/min), so a full 678-player backfill takes hours; on an active **paid** tier it
finishes in minutes. If the backfill crawls, confirm billing is enabled on the API key's GCP project.

## Serving (make the wire live)
The backend serves from DuckDB, so after generating, export the table to the serving file (the export
needs the backend stopped):
```
python -m scripts.export_to_duckdb --only player_verdict
```

## Surfacing
`nhl_models.player_verdict` (player_id, season, long, short, numbers_used, identity_confidence,
model_version, generated_at, payload_hash). The Player Profile verdict band reads `long` via
`GET /players/{id}/verdict` (frontend `getPlayerVerdict`), **falling back to the archetype descriptor**
when no row exists yet; list surfaces keep their one-line archetype label. Reviewed prose was approved
2026-06; the full backfill is populating `player_verdict`, after which `export_to_duckdb` makes every
profile show its composed read (until then, un-backfilled players show the descriptor fallback).
