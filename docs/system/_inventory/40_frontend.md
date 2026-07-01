# 40 — Frontend Inventory (React + TypeScript + Vite)

READ-ONLY static-analysis inventory of `frontend/` (mostly `frontend/src/`). Evidence is
ripgrep hits / import lines / route elements captured on 2026-07-01. Line numbers are as of
that snapshot and may drift.

## HARD RULES (in force for this document)

1. **data/ingested objects may NEVER be listed for deletion.** This file covers code/config
   only. Nothing here authorizes deleting ingested data; "orphaned" below means "no importer
   found in the mounted graph," never "delete."
2. **Puck tracking is retained by owner decision.** Any `ppt`/puck-tracking component is
   never orphaned-for-deletion. Verified: `rg -ni "ppt|puck.?track"` over `frontend/src`
   returns only `pages/GameDetail.tsx:472-474` — and that is a false positive (`ppTeam` =
   "power play team", not puck tracking). **There are no puck-tracking components in the
   frontend**, so this rule does not intersect any orphan below.

---

## 1. Mounted routes (`frontend/src/App.tsx`)

Router is `BrowserRouter` in `App.tsx`; `main.tsx` only mounts `<App/>`. All `<Route>`
elements:

| Route path | Page component | Import style |
|---|---|---|
| `/` | `GamesExplorer` | eager (`App.tsx:5`) |
| `/games/:gameId` | `GameDetail` | eager (`App.tsx:6`) |
| `/rankings` | `Rankings` | eager (`App.tsx:11`) |
| `/playoffs` | `Playoffs` | **lazy** (`App.tsx:25`) |
| `/teams` | `Teams` | eager (`App.tsx:7`) |
| `/teams/:teamId` | `TeamProfile` | eager (`App.tsx:8`) |
| `/players` | `Players` | eager (`App.tsx:9`) |
| `/players/:playerId` | `PlayerProfile` | eager (`App.tsx:10`) |
| `/tools` | `Tools` | **lazy** (`App.tsx:13`) |
| `/tools/offseason` | `Offseason` | **lazy** (`App.tsx:14`) |
| `/tools/lineup-lab` | `LineupLab` | **lazy** (`App.tsx:15`) |
| `/tools/trade-fit` | `TradeFit` | **lazy** (`App.tsx:16`) |
| `/tools/trade-builder` | `TradeBuilder` | **lazy** (`App.tsx:17`) |
| `/tools/contract-grader` | `ContractGrader` | **lazy** (`App.tsx:18`) |
| `/tools/roster-builder` | `RosterBuilder` | **lazy** (`App.tsx:19`) |
| `/tools/draft-value` | `DraftValue` | **lazy** (`App.tsx:20`) |
| `/tools/trade-outcomes` | `TradeOutcomes` | **lazy** (`App.tsx:21`) |
| `/tools/trade-outcomes/trade/:tradeId` | `TradeOutcomes` | same component, param route |
| `/tools/trade-outcomes/:kind/:id` | `TradeOutcomes` | same component, param route |
| `/learn/archetypes` | `ArchetypeExplorer` (page) | **lazy** (`App.tsx:23`) |

**19 page components exist; 18 are mounted.** The only unmounted page is
`pages/DevComponents.tsx` (see §5/§6).

---

## 2. Dynamic / lazy imports (so nothing is falsely orphaned)

`rg -n "lazy\(|import\("  frontend/src -g '*.tsx' -g '*.ts'`:

- **The only `React.lazy` code-splits are the 11 in `App.tsx:13–25`** (Tools, Offseason,
  LineupLab, TradeFit, TradeBuilder, ContractGrader, RosterBuilder, DraftValue,
  TradeOutcomes, ArchetypeExplorer, Playoffs). Each is quoted in §1 and **treated as
  reachable**.
- Every other `import(` hit is a **TypeScript type-only inline import** inside `api/*.ts`
  (e.g. `api/players.ts:127 Promise<import('./types').PlayerRadar>`,
  `api/goalies.ts:13`). These are compile-time types, **not** runtime code-splits and do not
  create reachability.
- No `React.lazy`, `loadable`, or dynamic `import()` of any **component** exists outside
  `App.tsx`. Therefore the orphan analysis in §6 is not undermined by hidden lazy loading.

---

## 3. API layer → backend endpoint join (`frontend/src/api/*`)

Transport: `api/client.ts` exports a single axios instance `apiClient`
(baseURL = `VITE_API_BASE_URL || http://localhost:8000`). All modules below call
`apiClient.get/post`. Quoted URL = the string passed to `apiClient`.

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
| `getPlayerVsOpponent` | GET | `/players/${playerId}/vs-opponent` (path built in call) |
| `getPlayerSituational` | GET | `/players/${playerId}/situational` (path built in call) |
| `getOverallLeaders` | GET | `/players/leaders` |
| `getArchetypeRanking` | GET | `/players/archetype-ranking` (path built in call) |
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
| `getTeamVsOpponent` | GET | `/teams/${teamId}/vs-opponent` (path built in call) |
| `getTeamDeployment` | GET | `/teams/${teamId}/deployment` (path built in call) |
| `getTeamSituational` | GET | `/teams/${teamId}/situational` (path built in call) |
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

## 4. Every page & component: renders / api / reachability

Reachability rule: reachable = imported (transitively) from a mounted route (§1) or a lazy
import (§2). "api endpoints" = endpoints reached via the api layer, by the file's own
`from '.../api/...'` imports (child components make their own calls, listed on their own row).
All import evidence from `rg -n "^import" ...` on 2026-07-01.

### Pages (`frontend/src/pages/`)

| File | Renders (1 line) | API (via api layer) | Reachable? |
|---|---|---|---|
| `GamesExplorer.tsx` | Date-strip games list / landing | `api/games` (dates, by-date) | ✅ route `/` |
| `GameDetail.tsx` | Single-game dashboard (worm, shot map, tables) | `api/games`, `api/goalies` | ✅ route `/games/:gameId` |
| `Rankings.tsx` | Power / deserved / value ranking tables | `api/rankings` | ✅ route `/rankings` |
| `Playoffs.tsx` | Playoff bracket predictor | `api/playoffs` | ✅ lazy route `/playoffs` |
| `Teams.tsx` | Teams index / standings grid | (child components) | ✅ route `/teams` |
| `TeamProfile.tsx` | Team dashboard (identity, form, lines) | `api/teams`, `api/rankings`, `api/games` | ✅ route `/teams/:teamId` |
| `Players.tsx` | Players index / leaderboards | `api/players`, `api/rankings` | ✅ route `/players` |
| `PlayerProfile.tsx` | Player dashboard (radar, shot map, strip) | `api/labels`, `api/players`, `api/goalies` | ✅ route `/players/:playerId` |
| `Tools.tsx` | Tools hub / landing | (links only) | ✅ lazy route `/tools` |
| `Offseason.tsx` | Offseason WAR forecast board | `api/offseason` | ✅ lazy route `/tools/offseason` |
| `LineupLab.tsx` | Line-fit projection lab | `api/tools` | ✅ lazy route `/tools/lineup-lab` |
| `TradeFit.tsx` | Player→team fit finder | `api/tools`, `api/players`, `api/teams` | ✅ lazy route `/tools/trade-fit` |
| `TradeBuilder.tsx` | Two-team trade evaluator | `api/assets` | ✅ lazy route `/tools/trade-builder` |
| `ContractGrader.tsx` | Contract value grader | `api/assets`, `api/tools` | ✅ lazy route `/tools/contract-grader` |
| `RosterBuilder.tsx` | Roster suggest/evaluate builder | `api/tools`, `api/teams` | ✅ lazy route `/tools/roster-builder` |
| `DraftValue.tsx` | Draft pick-value curve / board | `api/draft` | ✅ lazy route `/tools/draft-value` |
| `TradeOutcomes.tsx` | Trade-outcomes explorer (feed, dossier, search) | `api/trades` | ✅ lazy route `/tools/trade-outcomes` (+2 param routes) |
| `ArchetypeExplorer.tsx` (page) | Learn: archetype explainer | `api/archetypes` | ✅ lazy route `/learn/archetypes` |
| `DevComponents.tsx` | Internal component gallery / storybook | — | ❌ **ORPHANED** (see §6) |

### Components — `common/` (`frontend/src/components/common/`)

Most are presentational and reachable via a mounted page (directly or through the
`common/index.ts` barrel). API column filled only where the component imports the api layer.

| File | Renders (1 line) | API | Reachable? |
|---|---|---|---|
| `NavBar.tsx` | Top nav + player quick-search | `api/tools` (searchPlayers) | ✅ |
| `PageLayout.tsx` / `PageHeader.tsx` / `PageCard.tsx` | Page shell / header / card wrappers | — | ✅ |
| `ErrorBoundary.tsx` | React error boundary (used in `App.tsx`) | — | ✅ |
| `SkeletonLoader.tsx` / `GameCardSkeleton`* | Loading skeletons | — | ✅ |
| `PlayerPicker.tsx` | Player autocomplete picker | `api/tools` (searchPlayers) | ✅ |
| `PlayerExplorer.tsx` | Player search + explore panel | `api/tools`, `api/teams` | ✅ |
| `LineSwapWidget.tsx` | Line-swap what-if widget | `api/tools` | ✅ |
| `MatchupPreviewCard.tsx` | Game matchup preview card | `api/games` (preview) | ✅ |
| `GoalTooltip.tsx` | HTML tooltip for goal events | — | ⚠️ **transitively ORPHANED** (only importers are the two orphaned charts — see §6) |
| `Badge`, `UncertaintyBand`, `PlayerAvatar`, `ChartPanel`, `ComparisonRow`, `ComponentStackBar`, `PercentileBarList`, `StreakDoctorCard`, `StandingsLadder`, `PlayerValueLadder`, `InsightCard`, `DateStrip`, `IdentityHeader`, `MiniWorm`, `PodiumCards`, `PossessionBar`, `StatCard`, `TabNav`, `Tabs`, `ThemeToggle`, `TimelineList`, `Tooltip`, `XGBreakdown`, `ToggleSwitch`, `FormStrip`, `PlayerCard`, `ImpactValuePanel`, `OverallSummary`, `Select`, `LineProjection`, `TeamQuickJump` | Presentational primitives (badges, bars, ladders, cards, radars, chart shells, toggles) | — | ✅ (≥1 importer; exported via `common/index.ts` and consumed by mounted pages) |

`*` `GameCardSkeleton.tsx` lives in `components/games/`, listed here for grouping.

### Components — `forecast/` (all imported by `pages/Offseason.tsx:10–16`, route `/tools/offseason`)

| File | Renders | API | Reachable? |
|---|---|---|---|
| `ForecastHeroStats.tsx` | Offseason hero stat band | — | ✅ (`Offseason.tsx:10`) |
| `LeagueRail.tsx` | League-wide forecast rail | — | ✅ (`:11`) |
| `MoveLedger.tsx` | Roster-move ledger | — | ✅ (`:12`) |
| `ComponentBars.tsx` | WAR component bars | — | ✅ (`:13`) |
| `ProjectedLineup.tsx` | Projected lineup grid | — | ✅ (`:14`) |
| `OffseasonLeagueTable.tsx` | League forecast table | — | ✅ (`:15`) |
| `QuietState.tsx` | Empty/quiet-state placeholder | — | ✅ (`:16`) |

### Components — `games/`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `GameCard.tsx` | Game summary card (games list) | — | ✅ (used by GamesExplorer/Teams) |
| `GameCardSkeleton.tsx` | Game card skeleton | — | ✅ |
| `GameOfTheNight.tsx` | Featured game hero | `api/games` | ✅ (GamesExplorer) |

### Components — `players/`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `DeploymentBoard.tsx` | Deployment leaderboard | `api/players` | ✅ |
| `PlayerDraftLine.tsx` | Draft-pedigree line | `api/draft` | ✅ |
| `PlayerRowExpansion.tsx` | Expandable player row (radar/labels) | `api/players`, `api/goalies`, `api/labels` | ✅ |

### Components — `teams/`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `TeamIdentityTab.tsx` | Team identity tab | `api/teams` | ✅ (TeamProfile) |
| `TeamFormTab.tsx` | Team recent-form tab | `api/teams` | ✅ (TeamProfile) |
| `LineBoard.tsx` | Team line combinations | `api/tools` (getTeamLines) | ✅ |
| `StyleMapChart.tsx` | Team style-map scatter | `api/teams` (style-map) | ✅ |
| `TeamRadar.tsx` | Team radar chart | — | ✅ |

### Components — `visualizations/`

| File | Renders | API | Reachable? |
|---|---|---|---|
| `GameTimelineStack.tsx` | Stacked game-timeline (worm+pressure+winprob) | `api/games` | ✅ (`GameDetail.tsx:7`) |
| `ShotMapKDE.tsx` | KDE shot heatmap (game shots) | `api/games` (getGameShots) | ✅ (`GameDetail.tsx:8`) |
| `PeriodBreakdownTable.tsx` | Per-period breakdown table | — | ✅ (`GameDetail.tsx:9`) |
| `RollingContextPanel.tsx` | Rolling team-trend panel | `api/teams` (trends) | ✅ (`GameDetail.tsx:10`) |
| `ShotMap.tsx` | SVG shot map (player shots) | — (props-fed) | ✅ (`PlayerProfile.tsx:7`) |
| `StripPlot.tsx` | Percentile strip plot | — | ✅ (`PlayerProfile.tsx:8`) |
| `SkillRadar.tsx` | Skill radar | — (props-fed) | ✅ (`PlayerProfile.tsx:9`, `ArchetypeExplorer.tsx:14`, `PlayerRowExpansion.tsx:12`) |
| `XGWormChart.tsx` | Standalone xG worm chart | `api/games` (xgworm, goals) | ❌ **ORPHANED** (see §6) |
| `ShotPressureChart.tsx` | Standalone shot-pressure chart | `api/games` | ❌ **ORPHANED** (see §6) |

### Components — `trade/` (feeds `pages/TradeBuilder.tsx`, route `/tools/trade-builder`)

| File | Renders | API | Reachable? |
|---|---|---|---|
| `TradeTeamPanel.tsx` | One team's side of a trade | — | ✅ (`TradeBuilder.tsx:15`) |
| `TradeSetup.tsx` | Trade setup / team selectors | `api/assets` | ✅ (`TradeBuilder.tsx:16`) |
| `TradeVerdict.tsx` (`TradeSummaryBand`, `Domains`) | Trade verdict band | — | ✅ (`TradeBuilder.tsx:17`) |
| `AssetPicker.tsx` | Asset (player/pick) picker | `api/assets` | ✅ (via `TradeTeamPanel.tsx:11`) |

### Components — `trades/` (feeds `pages/TradeOutcomes.tsx`, route `/tools/trade-outcomes`)

| File | Renders | API | Reachable? |
|---|---|---|---|
| `TradesLanding.tsx` | Trade-outcomes landing | — | ✅ (`TradeOutcomes.tsx:13`) |
| `TeamsGms.tsx` | Teams/GMs value-map view | `api/trades` | ✅ (`TradeOutcomes.tsx:14`) |
| `ArchetypeExplorer.tsx` (trades) | Trade-archetype explorer | `api/trades` | ✅ (`TradeOutcomes.tsx:15`) |
| `TraderDossier.tsx` | Per-trader dossier | `api/trades` | ✅ (`TradeOutcomes.tsx:16`) |
| `TradeBalanceCard.tsx` | Trade balance/tilt card | `api/trades` | ✅ (`TradeOutcomes.tsx:17`) |
| `TradeSearch.tsx` | Trade search box | `api/trades`, `api/tools` | ✅ (`TradeOutcomes.tsx:18`) |
| `ValueMap.tsx` | Value-map scatter | `api/trades` | ✅ (via `TeamsGms.tsx:12`) |
| `TradesFeed.tsx` | Trade feed list | `api/trades` | ✅ (via `TradesLanding.tsx:8`) |
| `Tilt.tsx` | Small tilt/balance meter | — | ✅ (via `TradeBalanceCard.tsx:13`, `TradesFeed.tsx:11`, `TraderDossier.tsx:17`, `TeamsGms.tsx:13`, `ArchetypeExplorer.tsx:11`) |

> Deleted-in-working-tree (git status M/D): `components/trades/Leaderboards.tsx` and
> `components/trades/Overview.tsx` are marked deleted in the current branch and no longer on
> disk — not counted above.

### utils / config (not components; reachability noted for completeness)

`utils/theme.ts` (imported by `main.tsx`), `utils/format.ts`, `utils/teams.ts`,
`utils/radar.ts`, `utils/forecastFormat.ts`, `config/metrics.ts` — all imported by reachable
pages/components (helpers). Not audited line-by-line here.

---

## 5. Forced resolution of the three duplication smells

### 5a. `components/trade/` vs `components/trades/` — **NOT a superseded duplicate; both live**
Deciding imports:
- `components/trade/*` (AssetPicker, TradeSetup, TradeTeamPanel, TradeVerdict) is imported
  **only** by `pages/TradeBuilder.tsx:15–17` → mounted route **`/tools/trade-builder`**
  (the two-team trade evaluator).
- `components/trades/*` (TradesLanding, TeamsGms, ArchetypeExplorer, TraderDossier,
  TradeBalanceCard, TradeSearch, + transitive ValueMap/TradesFeed/Tilt) is imported **only**
  by `pages/TradeOutcomes.tsx:13–18` → mounted route **`/tools/trade-outcomes`** (the
  historical trade-outcomes explorer).
- `rg "components/trade/"` and `rg "components/trades/"` show **zero cross-imports** between
  the two directories. They are two distinct, both-reachable features — singular `trade/`
  serves Trade Builder, plural `trades/` serves Trade Outcomes. **Neither directory is
  orphaned or superseded.** (Naming is a collision hazard, not dead code.)

### 5b. `ShotMap.tsx` vs `ShotMapKDE.tsx` — **both imported; different pages, not superseded**
- `ShotMapKDE` ← `pages/GameDetail.tsx:8` (`import ShotMapKDE from '../components/visualizations/ShotMapKDE'`), rendered at `GameDetail.tsx:1079` — **game** shot heatmap.
- `ShotMap` ← `pages/PlayerProfile.tsx:7` (`import ShotMap from '../components/visualizations/ShotMap'`), rendered at `PlayerProfile.tsx:1326` — **player** shot map.
- Both are reachable from mounted routes; each serves a different surface (game vs player).
  **Neither is orphaned.** They are functional siblings, not a superseded pair.

### 5c. `pages/DevComponents.tsx` — **NOT mounted, zero importers → orphaned**
- Not referenced in `App.tsx` routes (§1).
- `rg -n "DevComponents" frontend/src` returns a single hit: its own definition
  `pages/DevComponents.tsx:45:export default function DevComponents()`. **No importer, no
  route.** Orphaned (see §6).

---

## 6. Orphan list (zero importers from the mounted graph — evidence attached)

These are "no importer found," **not** deletion directives (Phase E tiers them). None are
data/ingested objects; none are puck-tracking (HARD RULES §1–2 satisfied).

| File | Zero-importer evidence | Notes |
|---|---|---|
| `pages/DevComponents.tsx` | `rg -n "DevComponents" frontend/src` → only self `:45 export default function DevComponents()`; absent from `App.tsx` routes | Internal component gallery; never mounted |
| `components/visualizations/XGWormChart.tsx` | `rg -n "^import" ... \| rg XGWormChart` → only its own imports (`XGWormChart.tsx:1–7`); no `import ... from '.../XGWormChart'` anywhere; importer-count sweep = 0 | Standalone worm chart; `GameDetail` uses `GameTimelineStack` instead |
| `components/visualizations/ShotPressureChart.tsx` | `rg -n "ShotPressureChart" ...` → only self (`:6 import './ShotPressureChart.css'`); no external importer; importer-count sweep = 0 | Standalone pressure chart; superseded by `GameTimelineStack` (which folds pressure in) |
| `components/common/GoalTooltip.tsx` | Importers are **only** `XGWormChart.tsx:4` and `ShotPressureChart.tsx:3` — both themselves orphaned; **not** in `common/index.ts` barrel | **Transitively orphaned** (reachable only through the two orphaned charts). Flagged ⚠️, not ❌, because it becomes live again if either chart is re-mounted |

**Orphan cluster summary:** `XGWormChart` + `ShotPressureChart` are a mutually-independent
dead pair; `GoalTooltip` is dead solely because those two are its only consumers.
`DevComponents` is an independent unmounted dev page.

---

## Uncertainty / caveats (explicit)

- **Barrel-exported-but-unused risk not exhaustively cleared.** The `common/index.ts` barrel
  re-exports ~46 components; the automated importer-count sweep counts the barrel itself as an
  importer, so a common component that is re-exported by the barrel yet never destructured
  from `'../common'` by any mounted file would show count ≥ 1 and **would not surface as an
  orphan here.** I did not trace every named import out of the barrel across all 168 files.
  The common-primitives row in §4 is marked ✅ on the basis of ≥1 importer, not per-symbol
  consumption. If Phase E needs certainty on individual common primitives, a per-symbol
  `rg "\b<Name>\b"` from the mounted graph is required. All non-common components (games,
  teams, players, forecast, visualizations, trade, trades, pages) were resolved by direct
  import evidence and are not subject to this caveat.
- Route-param variants of `TradeOutcomes` (`/tools/trade-outcomes/...`) resolve to the same
  component; no separate page file.
- Line numbers are from the 2026-07-01 snapshot on branch `finalization`; the working tree has
  uncommitted modifications (git status) that may shift them.
