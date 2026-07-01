# Frontend Reference

> **Cleanup applied (branch `cleanup/safe-removals`).** The three orphaned components
> `visualizations/XGWormChart`, `visualizations/ShotPressureChart`, and `common/GoalTooltip`
> (plus their `.css`) were **deleted** (`a6a7c39`; `tsc --noEmit` passed after removal). Rows
> for them below describe their pre-cleanup state. `pages/DevComponents.tsx` was left in place
> (possible dev storybook). See CLEANUP_CANDIDATES.md for status.

Compiled reference for `frontend/`. Source of truth is the static-analysis inventory in
`_inventory/40_frontend.md` (evidence: ripgrep hits, import lines, and route elements captured
on 2026-07-01, branch `finalization`). This document organizes that inventory into prose and
tables. Deep per-feature traces (endpoint to mart to model) live in `FEATURE_MAP.md`; cleanup
tiering lives in `CLEANUP_CANDIDATES.md`. Line numbers are from the 2026-07-01 snapshot and may
drift; the working tree had uncommitted modifications at capture time.

## Hard rules (in force for this document)

1. **data/ingested objects are NEVER listed for deletion.** This document covers code and
   config only. "Orphaned" below means "no importer found in the mounted graph," never
   "delete."
2. **Puck tracking is retained by owner decision.** There are no puck-tracking components in
   the frontend. A `rg -ni "ppt|puck.?track"` sweep over `frontend/src` returns only
   `pages/GameDetail.tsx:472-474`, and that is a false positive (`ppTeam` = "power play team,"
   not puck tracking). This rule therefore does not intersect any orphan below.

Everything below is evidence-backed transcription, not re-investigation.

---

## 1. Overview

The frontend is **React + TypeScript + Vite**. `main.tsx` mounts only `<App/>` and imports
`utils/theme.ts`. Routing is a single **`BrowserRouter` in `App.tsx`**. All HTTP goes through
**one axios client**, `api/client.ts`, which exports the singleton `apiClient` with
`baseURL = VITE_API_BASE_URL || http://localhost:8000`; every `api/*.ts` module calls
`apiClient.get`/`apiClient.post` on it.

`App.tsx` mounts **21 `<Route>` elements** resolving to **18 distinct page components**. Three
of those routes are param variants of a single page (`TradeOutcomes`), so 19 page files exist
on disk and 18 are mounted (the lone unmounted page is `pages/DevComponents.tsx`). **11 pages
are lazy code-split** via `React.lazy` in `App.tsx:13-25`; the rest are eager imports. The only
`React.lazy` calls in the entire tree are those 11; every other `import(` hit is a compile-time
TypeScript type-only import inside `api/*.ts` and creates no runtime reachability. No dynamic
component import exists outside `App.tsx`, so the orphan analysis in Section 6 is not
undermined by hidden lazy loading.

---

## 2. Mounted routes

Router: `BrowserRouter` in `App.tsx`. All 21 `<Route>` elements:

| Route path | Page component | Import style |
|---|---|---|
| `/` | `GamesExplorer` | eager (`App.tsx:5`) |
| `/games/:gameId` | `GameDetail` | eager (`App.tsx:6`) |
| `/rankings` | `Rankings` | eager (`App.tsx:11`) |
| `/playoffs` | `Playoffs` | lazy (`App.tsx:25`) |
| `/teams` | `Teams` | eager (`App.tsx:7`) |
| `/teams/:teamId` | `TeamProfile` | eager (`App.tsx:8`) |
| `/players` | `Players` | eager (`App.tsx:9`) |
| `/players/:playerId` | `PlayerProfile` | eager (`App.tsx:10`) |
| `/tools` | `Tools` | lazy (`App.tsx:13`) |
| `/tools/offseason` | `Offseason` | lazy (`App.tsx:14`) |
| `/tools/lineup-lab` | `LineupLab` | lazy (`App.tsx:15`) |
| `/tools/trade-fit` | `TradeFit` | lazy (`App.tsx:16`) |
| `/tools/trade-builder` | `TradeBuilder` | lazy (`App.tsx:17`) |
| `/tools/contract-grader` | `ContractGrader` | lazy (`App.tsx:18`) |
| `/tools/roster-builder` | `RosterBuilder` | lazy (`App.tsx:19`) |
| `/tools/draft-value` | `DraftValue` | lazy (`App.tsx:20`) |
| `/tools/trade-outcomes` | `TradeOutcomes` | lazy (`App.tsx:21`) |
| `/tools/trade-outcomes/trade/:tradeId` | `TradeOutcomes` | same component, param route |
| `/tools/trade-outcomes/:kind/:id` | `TradeOutcomes` | same component, param route |
| `/learn/archetypes` | `ArchetypeExplorer` (page) | lazy (`App.tsx:23`) |

The three `TradeOutcomes` rows share one page file; the two param routes resolve to the same
component. The 11 lazy code-splits are Tools, Offseason, LineupLab, TradeFit, TradeBuilder,
ContractGrader, RosterBuilder, DraftValue, TradeOutcomes, ArchetypeExplorer, and Playoffs.

---

## 3. Mounted pages: renders, API calls, and data lineage

Each page below is reachable from a mounted route. "API" lists the api-layer modules the page
imports directly (child components make their own calls and are covered in Section 5). Lineage
summaries are intentionally short; the full endpoint-to-mart-to-model traces are in
`FEATURE_MAP.md`.

### GamesExplorer — route `/`
Date-strip games list and landing surface. Calls `api/games` (`getGameDates`,
`getGamesByDate`). Lineage: `/games/dates` and `/games/` back the schedule strip and per-date
game cards from the games serving layer. See `FEATURE_MAP.md`.

### GameDetail — route `/games/:gameId`
Single-game dashboard (timeline worm, KDE shot map, per-period and skater-impact tables).
Calls `api/games` and `api/goalies`. Lineage: the `/games/${id}/*` family (shots, goals,
pressure, winprob, special teams, goalie danger, shot quality, skater impact, team stats,
goaltending, context) feeds the dashboard panels. See `FEATURE_MAP.md`.

### Rankings — route `/rankings`
Power, deserved, and value ranking tables. Calls `api/rankings` (`getPowerRankings`,
`getDeservedStandings`, `getValueRankings`). Lineage: `/rankings/power`, `/rankings/deserved`,
`/rankings/value` from the rankings serving marts. See `FEATURE_MAP.md`.

### Playoffs — lazy route `/playoffs`
Playoff bracket predictor. Calls `api/playoffs` (`getPlayoffBracket`). Lineage:
`/playoffs/bracket`. See `FEATURE_MAP.md`.

### Teams — route `/teams`
Teams index / standings grid. Makes no direct api-layer calls; data arrives via child
components (standings/quick-jump). See `FEATURE_MAP.md`.

### TeamProfile — route `/teams/:teamId`
Team dashboard (identity, recent form, lines). Calls `api/teams`, `api/rankings`, `api/games`.
Lineage: `/teams/${id}` plus identity/trends/roster/streak/insights endpoints, blended with
rankings and game feeds. See `FEATURE_MAP.md`.

### Players — route `/players`
Players index / leaderboards. Calls `api/players`, `api/rankings`. Lineage: `/players/leaders`,
divergence/deployment boards, and rankings marts. See `FEATURE_MAP.md`.

### PlayerProfile — route `/players/:playerId`
Player dashboard (skill radar, shot map, percentile strip). Calls `api/labels`, `api/players`,
`api/goalies`. Lineage: `/players/${id}` detail plus radar/shot-quality/verdict/trajectory and
(for goalie profiles) `/goalies/${id}` endpoints; `api/labels` derives labels from the radar
payload with an in-module cache. See `FEATURE_MAP.md`.

### Tools — lazy route `/tools`
Tools hub landing. Links only, no api-layer calls.

### Offseason — lazy route `/tools/offseason`
Offseason WAR forecast board. Calls `api/offseason` (`getOffseasonBoard` →`/tools/offseason`,
`getTeamOffseason` → `/teams/${id}/offseason`). Renders the full `forecast/` component set
(Section 5). Lineage: offseason forecast serving layer / shared WAR projection. See
`FEATURE_MAP.md`.

### LineupLab — lazy route `/tools/lineup-lab`
Line-fit projection lab. Calls `api/tools` (`lineFit`, `lineFitSuggestions`, `getTeamLines`).
Lineage: `/tools/line-fit` family and `/teams/${id}/lines`. See `FEATURE_MAP.md`.

### TradeFit — lazy route `/tools/trade-fit`
Player-to-team fit finder. Calls `api/tools`, `api/players`, `api/teams`. Lineage:
`/tools/trade-fit` and `/tools/trade-fit/best-teams`, joined with player and team serving data.
See `FEATURE_MAP.md`.

### TradeBuilder — lazy route `/tools/trade-builder`
Two-team trade evaluator. Calls `api/assets`. Renders the `trade/` (singular) component set
(Section 5). Lineage: `/assets/search`, `/players/${id}/contract`, surplus/talent rankings, and
`POST /tools/trade-evaluate`. See `FEATURE_MAP.md`.

### ContractGrader — lazy route `/tools/contract-grader`
Contract value grader. Calls `api/assets`, `api/tools`. Lineage: `POST /tools/contract-grade`
plus contract lookups. See `FEATURE_MAP.md`.

### RosterBuilder — lazy route `/tools/roster-builder`
Roster suggest/evaluate builder. Calls `api/tools`, `api/teams`. Lineage: `POST
/tools/roster-suggest`, `POST /tools/roster-evaluate`, plus team serving data. See
`FEATURE_MAP.md`.

### DraftValue — lazy route `/tools/draft-value`
Draft pick-value curve and board. Calls `api/draft`. Lineage: `/draft/pick-value-curve`,
`/draft/theory-summary`, `/draft/board`, `/draft/player/${id}`. See `FEATURE_MAP.md`.

### TradeOutcomes — lazy route `/tools/trade-outcomes` (+2 param routes)
Trade-outcomes explorer (feed, dossier, search, value map, archetypes). Calls `api/trades`.
Renders the `trades/` (plural) component set (Section 5). Lineage: `/trades/board`,
`/trades/board/${id}`, `/traders/value-map`, `/traders/${kind}/${id}/dossier`,
`/trades/archetypes`, `/trades/thesis-summary`. See `FEATURE_MAP.md`.

### ArchetypeExplorer (page) — lazy route `/learn/archetypes`
Learn surface: archetype explainer. Calls `api/archetypes` (`getArchetypes` → `/archetypes`).
Note this is a distinct file from the `trades/ArchetypeExplorer.tsx` component (Section 7). See
`FEATURE_MAP.md`.

---

## 4. API layer → backend endpoint join

Transport: `api/client.ts` exports the single axios instance `apiClient`
(`baseURL = VITE_API_BASE_URL || http://localhost:8000`). Every module below calls
`apiClient.get`/`apiClient.post`; the quoted URL is the string passed to `apiClient`.

**`api/games.ts`**

| method | HTTP | URL |
|---|---|---|
| `getGameDates` | GET | `/games/dates` |
| `getGamesByDate` | GET | `/games/` (param `date`) |
| `getGameDetail` | GET | `/games/${gameId}` |
| `getGamePlayerStats` | GET | `/games/${gameId}/players` |
| `getGameShots` | GET | `/games/${gameId}/shots` |
| `getGameXGWorm` | GET | `/games/${gameId}/xgworm` |
| `getGameGoals` | GET | `/games/${gameId}/goals` |
| `getGamePressure` | GET | `/games/${gameId}/pressure` |
| `getGameWinProb` | GET | `/games/${gameId}/winprob` |
| `getGameSpecialTeams` | GET | `/games/${gameId}/specialteams` |
| `getGameGoalieDanger` | GET | `/games/${gameId}/goalie-danger` |
| `getGameShotQuality` | GET | `/games/${gameId}/shot-quality` |
| `getGameSkaterImpact` | GET | `/games/${gameId}/skater-impact` |
| `getGameTeamStats` | GET | `/games/${gameId}/teamstats` |
| `getGameGoaltending` | GET | `/games/${gameId}/goaltending` |
| `getTeamGames` | GET | `/games/` |
| `getGameContext` | GET | `/games/${gameId}/context` |
| `getGamePreview` | GET | `/games/${gameId}/preview` |

**`api/players.ts`**

| method | HTTP | URL |
|---|---|---|
| `getPlayerDetail` | GET | `/players/${playerId}` |
| `getPlayerTrends` | GET | `/players/${playerId}/trends` |
| `getPlayerGamelog` | GET | `/players/${playerId}/gamelog` |
| `getPlayerShots` | GET | `/players/${playerId}/shots` |
| `getPlayerVsOpponent` | GET | `/players/${playerId}/vs-opponent` |
| `getPlayerSituational` | GET | `/players/${playerId}/situational` |
| `getOverallLeaders` | GET | `/players/leaders` |
| `getArchetypeRanking` | GET | `/players/archetype-ranking` |
| `getPlayerReconciliation` | GET | `/players/${playerId}/reconciliation` |
| `getDivergenceBoard` | GET | `/players/divergence-board` |
| `getPlayerTrajectory` | GET | `/players/${playerId}/trajectory` |
| `getPlayerRadar` | GET | `/players/${playerId}/radar` |
| `getPlayerShotQuality` | GET | `/players/${playerId}/shot-quality` |
| `getPlayerVerdict` | GET | `/players/${playerId}/verdict` |
| `getPlayerSummary` | GET | `/players/${playerId}/summary` |
| `getPlayerPreview` | GET | `/players/${playerId}/preview` |
| `getPlayerValueNeighbors` | GET | `/players/${playerId}/value-neighbors` |
| `getDeploymentBoard` | GET | `/players/deployment-board` |
| `getPlayerDeployment` | GET | `/players/${playerId}/deployment` |

**`api/teams.ts`**

| method | HTTP | URL |
|---|---|---|
| `getTeamDetail` | GET | `/teams/${teamId}` |
| `getTeamTrends` | GET | `/teams/${teamId}/trends` |
| `getTeamRoster` | GET | `/teams/${teamId}/roster` |
| `getTeamVsOpponent` | GET | `/teams/${teamId}/vs-opponent` |
| `getTeamDeployment` | GET | `/teams/${teamId}/deployment` |
| `getTeamSituational` | GET | `/teams/${teamId}/situational` |
| `getTeamIdentity` | GET | `/teams/${teamId}/identity` |
| `getStyleMap` | GET | `/teams/style-map` |
| `getTeamStreak` | GET | `/teams/${teamId}/streak` |
| `getStandings` | GET | `/teams/standings` |
| `getTeamInsights` | GET | `/teams/${teamId}/insights` |

**`api/goalies.ts`**

| method | HTTP | URL |
|---|---|---|
| `getGoalieSeason` | GET | `/goalies/${goalieId}` |
| `getGoalieRadar` | GET | `/goalies/${goalieId}/radar` |
| `getGoaliePreview` | GET | `/goalies/${goalieId}/preview` |

**`api/rankings.ts`**

| method | HTTP | URL |
|---|---|---|
| `getPowerRankings` | GET | `/rankings/power` |
| `getDeservedStandings` | GET | `/rankings/deserved` |
| `getValueRankings` | GET | `/rankings/value` |

**`api/playoffs.ts`**

| method | HTTP | URL |
|---|---|---|
| `getPlayoffBracket` | GET | `/playoffs/bracket` |

**`api/archetypes.ts`**

| method | HTTP | URL |
|---|---|---|
| `getArchetypes` | GET | `/archetypes` |

**`api/draft.ts`**

| method | HTTP | URL |
|---|---|---|
| `getPickValueCurve` | GET | `/draft/pick-value-curve` |
| `getDraftTheorySummary` | GET | `/draft/theory-summary` |
| `getDraftBoard` | GET | `/draft/board` |
| `getPlayerDraft` | GET | `/draft/player/${playerId}` |

**`api/offseason.ts`**

| method | HTTP | URL |
|---|---|---|
| `getOffseasonBoard` | GET | `/tools/offseason` |
| `getTeamOffseason` | GET | `/teams/${teamId}/offseason` |

**`api/assets.ts`**

| method | HTTP | URL |
|---|---|---|
| `searchAssets` | GET | `/assets/search` |
| `getPlayerContract` | GET | `/players/${playerId}/contract` |
| `gradeContract` | POST | `/tools/contract-grade` |
| `getSurplusRankings` | GET | `/rankings/surplus` |
| `getTalentRankings` | GET | `/rankings/talent` |
| `evaluateTrade` | POST | `/tools/trade-evaluate` |

**`api/tools.ts`**

| method | HTTP | URL |
|---|---|---|
| `rosterSuggest` | POST | `/tools/roster-suggest` |
| `rosterEvaluate` | POST | `/tools/roster-evaluate` |
| `searchPlayers` | GET | `/players/search` |
| `lineFit` | POST | `/tools/line-fit` |
| `lineFitSuggestions` | POST | `/tools/line-fit/suggestions` |
| `getTeamLines` | GET | `/teams/${teamId}/lines` |
| `tradeFit` | POST | `/tools/trade-fit` |
| `bestTeamFits` | GET | `/tools/trade-fit/best-teams` |

**`api/trades.ts`**

| method | HTTP | URL |
|---|---|---|
| `getTradeBoard` | GET | `/trades/board` |
| `getBoardItem` | GET | `/trades/board/${tradeId}` |
| `getValueMap` | GET | `/traders/value-map` |
| `getDossier` | GET | `/traders/${kind}/${id}/dossier` |
| `getArchetypes` | GET | `/trades/archetypes` |
| `getThesisSummary` | GET | `/trades/thesis-summary` |

**`api/labels.ts`** — no HTTP of its own. `playerLabelsFromRadar` is pure; `getPlayerLabels`
composes `getPlayerRadar` (`/players/${id}/radar`) with an in-module cache.

**`api/types.ts`** — types only, no runtime.

---

## 5. Component inventory by directory (with reachability)

Reachability rule: reachable = imported (transitively) from a mounted route (Section 2) or one
of the 11 lazy imports. The API column is filled only where the component itself imports the
api layer.

### `common/`

Most are presentational and reach a mounted page directly or through the `common/index.ts`
barrel.

| File | Renders | API | Reachable? |
|---|---|---|---|
| `NavBar.tsx` | Top nav + player quick-search | `api/tools` (`searchPlayers`) | Yes |
| `PageLayout.tsx` / `PageHeader.tsx` / `PageCard.tsx` | Page shell / header / card wrappers | — | Yes |
| `ErrorBoundary.tsx` | React error boundary (used in `App.tsx`) | — | Yes |
| `SkeletonLoader.tsx` | Loading skeletons | — | Yes |
| `PlayerPicker.tsx` | Player autocomplete picker | `api/tools` (`searchPlayers`) | Yes |
| `PlayerExplorer.tsx` | Player search + explore panel | `api/tools`, `api/teams` | Yes |
| `LineSwapWidget.tsx` | Line-swap what-if widget | `api/tools` | Yes |
| `MatchupPreviewCard.tsx` | Game matchup preview card | `api/games` (preview) | Yes |
| `GoalTooltip.tsx` | HTML tooltip for goal events | — | Transitively orphaned (Section 6) |
| Presentational primitives (see below) | Badges, bars, ladders, cards, radars, chart shells, toggles | — | Yes (>=1 importer) |

The presentational-primitives group covers: `Badge`, `UncertaintyBand`, `PlayerAvatar`,
`ChartPanel`, `ComparisonRow`, `ComponentStackBar`, `PercentileBarList`, `StreakDoctorCard`,
`StandingsLadder`, `PlayerValueLadder`, `InsightCard`, `DateStrip`, `IdentityHeader`,
`MiniWorm`, `PodiumCards`, `PossessionBar`, `StatCard`, `TabNav`, `Tabs`, `ThemeToggle`,
`TimelineList`, `Tooltip`, `XGBreakdown`, `ToggleSwitch`, `FormStrip`, `PlayerCard`,
`ImpactValuePanel`, `OverallSummary`, `Select`, `LineProjection`, `TeamQuickJump`. Each has at
least one importer and is re-exported by `common/index.ts` and consumed by mounted pages. See
the barrel-export caveat in Section 7.

### `forecast/` — all imported by `pages/Offseason.tsx:10-16`, route `/tools/offseason`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `ForecastHeroStats.tsx` | Offseason hero stat band | — | Yes (`Offseason.tsx:10`) |
| `LeagueRail.tsx` | League-wide forecast rail | — | Yes (`:11`) |
| `MoveLedger.tsx` | Roster-move ledger | — | Yes (`:12`) |
| `ComponentBars.tsx` | WAR component bars | — | Yes (`:13`) |
| `ProjectedLineup.tsx` | Projected lineup grid | — | Yes (`:14`) |
| `OffseasonLeagueTable.tsx` | League forecast table | — | Yes (`:15`) |
| `QuietState.tsx` | Empty/quiet-state placeholder | — | Yes (`:16`) |

### `games/`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `GameCard.tsx` | Game summary card (games list) | — | Yes (GamesExplorer / Teams) |
| `GameCardSkeleton.tsx` | Game card skeleton | — | Yes |
| `GameOfTheNight.tsx` | Featured game hero | `api/games` | Yes (GamesExplorer) |

### `players/`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `DeploymentBoard.tsx` | Deployment leaderboard | `api/players` | Yes |
| `PlayerDraftLine.tsx` | Draft-pedigree line | `api/draft` | Yes |
| `PlayerRowExpansion.tsx` | Expandable player row (radar/labels) | `api/players`, `api/goalies`, `api/labels` | Yes |

### `teams/`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `TeamIdentityTab.tsx` | Team identity tab | `api/teams` | Yes (TeamProfile) |
| `TeamFormTab.tsx` | Team recent-form tab | `api/teams` | Yes (TeamProfile) |
| `LineBoard.tsx` | Team line combinations | `api/tools` (`getTeamLines`) | Yes |
| `StyleMapChart.tsx` | Team style-map scatter | `api/teams` (style-map) | Yes |
| `TeamRadar.tsx` | Team radar chart | — | Yes |

### `visualizations/`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `GameTimelineStack.tsx` | Stacked game timeline (worm + pressure + winprob) | `api/games` | Yes (`GameDetail.tsx:7`) |
| `ShotMapKDE.tsx` | KDE shot heatmap (game shots) | `api/games` (`getGameShots`) | Yes (`GameDetail.tsx:8`) |
| `PeriodBreakdownTable.tsx` | Per-period breakdown table | — | Yes (`GameDetail.tsx:9`) |
| `RollingContextPanel.tsx` | Rolling team-trend panel | `api/teams` (trends) | Yes (`GameDetail.tsx:10`) |
| `ShotMap.tsx` | SVG shot map (player shots) | — (props-fed) | Yes (`PlayerProfile.tsx:7`) |
| `StripPlot.tsx` | Percentile strip plot | — | Yes (`PlayerProfile.tsx:8`) |
| `SkillRadar.tsx` | Skill radar | — (props-fed) | Yes (`PlayerProfile.tsx:9`, `ArchetypeExplorer.tsx:14`, `PlayerRowExpansion.tsx:12`) |
| `XGWormChart.tsx` | Standalone xG worm chart | `api/games` (xgworm, goals) | Orphaned (Section 6) |
| `ShotPressureChart.tsx` | Standalone shot-pressure chart | `api/games` | Orphaned (Section 6) |

### `trade/` (singular) — feeds `pages/TradeBuilder.tsx`, route `/tools/trade-builder`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `TradeTeamPanel.tsx` | One team's side of a trade | — | Yes (`TradeBuilder.tsx:15`) |
| `TradeSetup.tsx` | Trade setup / team selectors | `api/assets` | Yes (`TradeBuilder.tsx:16`) |
| `TradeVerdict.tsx` (`TradeSummaryBand`, `Domains`) | Trade verdict band | — | Yes (`TradeBuilder.tsx:17`) |
| `AssetPicker.tsx` | Asset (player/pick) picker | `api/assets` | Yes (via `TradeTeamPanel.tsx:11`) |

### `trades/` (plural) — feeds `pages/TradeOutcomes.tsx`, route `/tools/trade-outcomes`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `TradesLanding.tsx` | Trade-outcomes landing | — | Yes (`TradeOutcomes.tsx:13`) |
| `TeamsGms.tsx` | Teams/GMs value-map view | `api/trades` | Yes (`TradeOutcomes.tsx:14`) |
| `ArchetypeExplorer.tsx` (trades) | Trade-archetype explorer | `api/trades` | Yes (`TradeOutcomes.tsx:15`) |
| `TraderDossier.tsx` | Per-trader dossier | `api/trades` | Yes (`TradeOutcomes.tsx:16`) |
| `TradeBalanceCard.tsx` | Trade balance / tilt card | `api/trades` | Yes (`TradeOutcomes.tsx:17`) |
| `TradeSearch.tsx` | Trade search box | `api/trades`, `api/tools` | Yes (`TradeOutcomes.tsx:18`) |
| `ValueMap.tsx` | Value-map scatter | `api/trades` | Yes (via `TeamsGms.tsx:12`) |
| `TradesFeed.tsx` | Trade feed list | `api/trades` | Yes (via `TradesLanding.tsx:8`) |
| `Tilt.tsx` | Small tilt/balance meter | — | Yes (via `TradeBalanceCard.tsx:13`, `TradesFeed.tsx:11`, `TraderDossier.tsx:17`, `TeamsGms.tsx:13`, `ArchetypeExplorer.tsx:11`) |

Note: `components/trades/Leaderboards.tsx` and `components/trades/Overview.tsx` are marked
deleted (git status D) on branch `finalization` and no longer on disk; they are not counted
above.

### `utils/` and `config/` (helpers, not components)

`utils/theme.ts` (imported by `main.tsx`), `utils/format.ts`, `utils/teams.ts`,
`utils/radar.ts`, `utils/forecastFormat.ts`, and `config/metrics.ts` are all imported by
reachable pages/components. Not audited line-by-line.

---

## 6. Orphans (zero importers from the mounted graph)

These are "no importer found," **not** deletion directives; `CLEANUP_CANDIDATES.md` tiers them.
None are data/ingested objects and none are puck-tracking, so both hard rules are satisfied.

| File | Zero-importer evidence | Notes |
|---|---|---|
| `pages/DevComponents.tsx` | `rg -n "DevComponents" frontend/src` returns only its own definition (`:45 export default function DevComponents()`); absent from `App.tsx` routes | Internal component gallery / storybook; never mounted |
| `components/visualizations/XGWormChart.tsx` | No `import ... from '.../XGWormChart'` anywhere; only its own imports (`:1-7`); importer-count sweep = 0 | Standalone worm chart; `GameDetail` uses `GameTimelineStack` instead |
| `components/visualizations/ShotPressureChart.tsx` | `rg -n "ShotPressureChart"` returns only self (`:6 import './ShotPressureChart.css'`); no external importer; importer-count sweep = 0 | Standalone pressure chart; superseded by `GameTimelineStack` (which folds pressure in) |
| `components/common/GoalTooltip.tsx` | Only importers are `XGWormChart.tsx:4` and `ShotPressureChart.tsx:3`, both themselves orphaned; not in the `common/index.ts` barrel | **Transitively orphaned** — reachable only through the two orphaned charts; becomes live again if either chart is re-mounted |

Orphan cluster summary: `XGWormChart` and `ShotPressureChart` are a mutually-independent dead
pair; `GoalTooltip` is dead solely because those two charts are its only consumers.
`DevComponents` is an independent unmounted dev page.

---

## 7. Duplication resolution

Three naming/duplication smells were resolved by import evidence. None is dead code.

### `trade/` (singular) vs `trades/` (plural) — both live, different routes
`components/trade/*` (AssetPicker, TradeSetup, TradeTeamPanel, TradeVerdict) is imported **only**
by `pages/TradeBuilder.tsx:15-17`, mounted route `/tools/trade-builder` (the two-team trade
evaluator). `components/trades/*` (TradesLanding, TeamsGms, ArchetypeExplorer, TraderDossier,
TradeBalanceCard, TradeSearch, plus transitive ValueMap/TradesFeed/Tilt) is imported **only** by
`pages/TradeOutcomes.tsx:13-18`, mounted route `/tools/trade-outcomes` (the historical
trade-outcomes explorer). `rg "components/trade/"` and `rg "components/trades/"` show zero
cross-imports. Two distinct, both-reachable features: singular `trade/` serves Trade Builder,
plural `trades/` serves Trade Outcomes. Naming is a collision hazard, not dead code.

### `ShotMap.tsx` vs `ShotMapKDE.tsx` — both live, different surfaces
`ShotMapKDE` is imported by `pages/GameDetail.tsx:8` and rendered at `GameDetail.tsx:1079` (the
**game** shot heatmap). `ShotMap` is imported by `pages/PlayerProfile.tsx:7` and rendered at
`PlayerProfile.tsx:1326` (the **player** shot map). Both are reachable from mounted routes and
serve different surfaces. Functional siblings, not a superseded pair.

### Two `ArchetypeExplorer` files
`pages/ArchetypeExplorer.tsx` is the Learn page mounted at `/learn/archetypes`;
`components/trades/ArchetypeExplorer.tsx` is the trade-archetype component used by
`TradeOutcomes`. Distinct files, both reachable.

### Barrel-export caveat (carried from the inventory)
The `common/index.ts` barrel re-exports roughly 46 components. The automated importer-count
sweep counts the barrel itself as an importer, so a common component re-exported by the barrel
but never actually destructured from `'../common'` by any mounted file would still show count
>= 1 and would not surface as an orphan. Per-symbol consumption of the common primitives was
**not** exhaustively cleared; the primitives row in Section 5 is marked reachable on the basis
of at least one importer, not per-symbol usage. Certainty on an individual common primitive
requires a per-symbol `rg "\b<Name>\b"` sweep from the mounted graph. All non-common components
(games, teams, players, forecast, visualizations, trade, trades, pages) were resolved by direct
import evidence and are not subject to this caveat.

### Additional caveats
The three `TradeOutcomes` param routes resolve to the same page file (no separate component).
Line numbers are from the 2026-07-01 snapshot on branch `finalization`; uncommitted working-tree
modifications may shift them.
