# RINK THEORY rebuild — plan amendments

Amendments to the "RINK THEORY - Rebuild Plan" (plan of record). Recorded as the
owner approves corrections during the build. The plan itself is unchanged; this
file is the authoritative delta.

## A1 — Display/heading font (§6)

Use **Newsreader Variable** as the display/heading (and body) serif, overriding
the plan's Playfair Display / Source Serif Pro roles. Newsreader is already
self-hosted (`@fontsource-variable/newsreader`, `opsz` axis → display cut at
large sizes, text cut at small). Mono = Spline Sans Mono; UI = Archivo. No new
font dependencies. (Also overrides any font shown in the v2 mockups.)

## A2 — Ratings freshness stamp (§3.4, §4.2)

`GET /ratings` exposes recency as **`data_through`** = `MAX(game_date)` from
`team_ratings`. The page/rail label reads **"DATA THROUGH `<date>`"**, not
"LAST RUN" — `MAX(game_date)` is data recency, not a job run time. (The v2
Ratings mockup literally shows "LAST RUN …"; this amendment overrides it.)
Build `/ratings` as a thin new endpoint that merges the existing
`/rankings/power` (rating + four `contrib_*` components) and `/rankings/deserved`
(`luck_delta`) queries.

## A3 — §4.2 "actively consumed" endpoint list is amended

Recon confirmed the four kept tools depend on endpoints beyond those the plan's
§4.2 named. All already exist and are registered (backend stays add-only; nothing
is unregistered). Append to the "actively consumed" list:

- `GET /players/search` — player pickers (Lineup Lab, Contract Grader)
- `GET /teams/{team_id}/lines` — Lineup Lab (current team lines)
- `GET /players/{player_id}/contract` — Draft Value, Contract Grader
- `GET /rankings/surplus` — Contract Grader (surplus/efficiency board)
- `GET /rankings/talent` — Contract Grader (talent board)
- Trade Ledger detail/summary routes: `GET /trades/board`, `/trades/board/{trade_id}`,
  `/trades/thesis-summary`, `/trades/archetypes`, `/traders/value-map`,
  `/traders/{kind}/{entity_id}/dossier`
- Draft Value detail/summary routes: `GET /draft/pick-value-curve`,
  `/draft/theory-summary`, `/draft/board`, `/draft/player/{player_id}`
- Contract Grader: `POST /tools/contract-grade`, `GET /assets/search`

**Standing rule:** any further backend dependency a tool port surfaces during
Step 5 is **appended to this list, not treated as scope creep**. The backend
remains **add-only** regardless — the only authorized new endpoint is `GET
/ratings`; existing dormant routes stay registered and functional.

## A4 — Figure-kit orphans (§4.3/§5.3)

`ShotMap` and `StripPlot` (`frontend/src/components/visualizations/`) are carried
into the figure kit **unmodified**, each with a header comment noting it has no
live importer and exists for future note figures. They are not deleted during
teardown. Physical relocation into the `figures/` kit happens when the kit is
scaffolded in Step 3.

## A5 — Nav has no Search in v1 (§2)

Nav is **NOTES · RATINGS · TOOLS**. The v2 mockups show a "SEARCH" item; the plan
of record (§2, "no search in v1") overrides. Search becomes a new idea with an
obvious home if/when needed.
