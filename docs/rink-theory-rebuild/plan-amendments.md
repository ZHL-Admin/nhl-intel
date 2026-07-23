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

## A6 — RATINGS & TOOLS are dropdowns (§2)

No nav item should lead to a page that is just more navigation. NOTES stays a
plain link; **RATINGS** and **TOOLS** are editorial dropdowns (white panel, 1px
hairline, subtle shadow, no icons):
- RATINGS → **Teams** (`/ratings`), **Players** (`/ratings/players`, new route).
- TOOLS → the four tools directly. `/tools` stays reachable by URL as a plain
  index, but the nav skips it.

New page `/ratings/players` (full table in Step 4): same editorial treatment as
the team table — RK, PLAYER, TEAM dot, POS, VALUE, CONTRACT SURPLUS, at most a
position filter; backed **entirely** by the dormant `/rankings/talent` +
`/rankings/surplus` read as-is (zero backend changes; cut any column the payload
can't support).

Old-path (Studio→tool) redirects are deferred to Step 5 (the tool-port step),
done comprehensively with param preservation. Until then the catch-all lands old
URLs on Home. (A premature partial set added in Step 2 was removed.)

## A7 — Legacy `src/pages` excluded from tsc (build hygiene)

The old dashboard pages live in `frontend/src/pages` and are the removed surface
(unreachable, tree-shaken out of the bundle by Vite). `frontend/tsconfig.json`
now excludes `src/pages` so those removed pages don't gate the new build. The
four KEPT tool sources still sit there as dormant salvage and re-enter the typed
build when ported into `src/rink` in Step 5. No source is deleted.

## A8 — Notes pipeline decisions (Step 3, §5)

- MDX via `@mdx-js/rollup` + `remark-frontmatter` + `remark-mdx-frontmatter`
  (frontmatter exposed as a named export). Figures imported via the `@figures`
  Vite alias.
- Drafts render in **dev only**; the production list, RSS, and navigation never
  treat a draft as published. Nothing publishes without an explicit
  `status: published` flip.
- `/rss.xml` generated at build (`scripts/gen-rss.mjs`, a `prebuild` step),
  published-only, valid-but-empty until the first publish.
- Figure data frozen inline per §5.3. The deserved-standings note cites the live
  dormant `GET /rankings/deserved` but ships a frozen 2025-26 snapshot.
- ShotMap/StripPlot relocated into `src/rink/figures/` (unmodified; ShotMap's one
  cross-dir import path updated for the move; reservation comments intact).
- Note 2 (rink bias): its primary artifact `artifacts/phase_value/arena_underrecording.csv`
  and `docs/phase-value/phase-value.md` are UNTRACKED (not on the rebuild branch);
  the exact values are frozen verbatim in the MDX citation comment with `[T]`
  (tracked-corroborated) / `[U]` (untracked-only) tags so provenance survives.
  `docs/phase-value/sprite-audit.md` and `docs/methodology/scorer-bias.md` ARE tracked.

## A9 — Seasonal Home rail (§3.1 amended)

The Home rail is seasonal, with an automatic, data-derived switch (no config flag):
**offseason** mode when the `/ratings` payload's `data_through` is more than 30 days
older than today; **in-season** otherwise. Switch logic lives in
`frontend/src/rink/home/Rail.tsx` (`isOffseason(data_through)`), with a dev-only
URL override (`?rail=inseason` / `?rail=offseason`) to capture either mode.

- **In-season:** POWER RATINGS (top 5) + LUCK WATCH — unchanged from Step 4.
- **Offseason:** PROJECTED 2026-27 (top 5 by `projected_rating` from
  `/tools/offseason`, read as-is — chose `projected_rating` = absolute projected
  strength over `delta`/`net_delta_war`, which measure offseason move impact /
  biggest movers, not strength; no footer link, as no board page exists) +
  CONTRACT WATCH (deterministic template: best/worst deal from `/rankings/surplus`
  read as-is, links to `/ratings/players`).
- FROM THE TOOLKIT: unchanged, year-round. Both modes styled identically per §6.

Frontend-only; no endpoint modified. **§4.2 append (standing rule):** the rail now
also consumes the dormant `GET /tools/offseason` (offseason mode) — read exactly
as it responds today.

## A10 — Tool port (Step 5)

The four kept tools are ported into the new shell **chrome-only**, unchanged
internally:
- Each new route wrapper (`src/rink/pages/tools/*`) lazy-loads the salvaged tool
  from `src/pages/*` and wraps it in the new `Shell` + `ShellContext.Provider
  value={true}` — the tool's own `PageLayout` collapses to a pass-through, so it
  renders inside the new TopBar/Footer instead of the old NavBar.
- Legacy design tokens/classes are loaded additively via `src/rink/legacy-tools.css`
  (the old `styles/*` layers) so the tool internals keep their look. Verified no
  shell regression (body/paper, rail, ratings shade/luck all unchanged) — token
  names don't collide and the layers are class-based.
- Rename **Trade Outcomes → Trade Ledger** (title); stale `eyebrow="Studio"` →
  `"Tool"` on all four; "Draft value"/"Contract grader" title-cased to match nav.
- **Compat fix (frontend only):** `DraftValue` requested `/draft/board?limit=250`
  but the endpoint caps at `le=100` → 422; changed to 100. Backend untouched.
- **Legacy redirects (A6 fulfilled):** `/studio/*` deep links redirect to the new
  tool homes, **param- and query-preserving** (e.g.
  `/studio/trades/history/trade/:id?season=…` → `/tools/trade-ledger/trade/:id?season=…`);
  removed Studio tools (build/fit/roster/offseason/hub) → the Tools shelf.
- Known residual (out of scope, chrome-only rebuild): some tools' internal copy
  links to removed tools (e.g. DraftValue → "Trade Builder"); those links resolve
  to the Tools shelf via the `/studio/*` redirect rather than 404.

## Ship-gate checklist (Step 8) — additions

Beyond the plan's §7 step-8 gate (≥3 published notes, /ratings reflects last run,
four tools work in the new shell), also confirm at ship:

- [ ] **Set a real `SITE_URL`** for the RSS build (`scripts/gen-rss.mjs`) — replaces
      the `https://rinktheory.example` placeholder in `<link>`, `<guid>`, and the
      `atom:link` self href. Set via the `SITE_URL` env at build time.
- [ ] **Fix stale copy that references removed tools** (TEXT-ONLY, authorized).
      The salvaged tools' internal copy links to surfaces that no longer exist
      (e.g. DraftValue body → "Trade Builder"; check the other three for similar).
      Repoint link labels/copy at surfaces that exist, or remove the link. No logic
      changes — that stays out of scope.
