# UX conformance sweep (P5)

Page-by-page pass against the site-cohesion checklist. One row per page, one check per item.
No functional changes were made in this phase — only conformance fixes (titles, sentence case,
back-link labels, tabular figures) and the audit record below.

## Checklist items

1. `usePageTitle` set
2. FooterMeta present via PageLayout (no page opts out)
3. Back links / breadcrumbs use the parent-surface name, never "Back"
4. Entity rendering: players → name + position + team + tier chip; teams → logo + abbrev; canonical components
5. Sentence case on every heading, tab, and button
6. Colour: green/amber/red only for the confidence trio and documented valence
7. Responsive at 360 / 768 / 1280 — no horizontal scroll, tap targets ≥ 40px
8. Empty / loading / error state for every fetch
9. `tabular-nums` on any column of figures
10. Every model-number surface links a Learn method where one exists

**Legend:** ✓ pass · ✱ fixed this phase · ⚠ needs a browser pass (visual/responsive/a11y — no headless
browser available in this environment) · — n/a · † reference page, left unchanged by mandate (findings noted)

## Primary surfaces (audit order)

| Page | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| GameDetail | ✱ | ✓ | ✱ | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| TeamProfile | ✓ | ✓ | — | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ✓ |
| Playoffs | ✱ | ✓ | ✓ | ✓ | ✓ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| Studio · Build a trade | ✱ | ✓ | ✓ | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| Studio · Find a fit | ✱ | ✓ | ✓ | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| Studio · Trade history | ✱ | ✓ | ✓ | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| Studio · Line chemistry | ✱ | ✓ | ✓ | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| Studio · Roster moves | ✱ | ✓ | ✓ | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| Studio · Contracts | ✱ | ✓ | ✓ | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| Studio · Draft value | ✱ | ✓ | ✓ | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| Studio · Offseason forecast | ✱ | ✓ | ✓ | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| GamesExplorer | ✱ | ✓ | — | ✓ | ✓ | ✓ | ⚠ | ✓ | ✓ | — |
| ArchetypeExplorer | ✱ | ✓ | ✓ | ✓ | ✓ | ✓ | ⚠ | ✓ | ✓ | ⚠ |

## New surfaces (this initiative)

| Page | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Today | ✓ | ✓ | — | ✓ | ✓ | ✓ | ⚠ | ✓ | ✓ | ⚠ |
| Teams (Standings/Power/Deserved) | ✓ | ✓ | — | ✓ | ✱ | ✓ | ⚠ | ✓ | ✓ | ✓ |
| StudioHub | ✓ | ✓ | — | — | ✓ | ✓ | ⚠ | — | ✓ | — |
| Learn hub | ✓ | ✓ | — | — | ✓ | ✓ | ⚠ | — | — | — |
| Methods (index + doc) | ✓ | ✓ | ✓ | — | ✓ | ✓ | ⚠ | ✓ | ✓ | — |
| Writing (index + post) | ✓ | ✓ | ✓ | — | ✓ | ✓ | ⚠ | ✓ | — | — |

## Reference surfaces (unchanged by mandate)

| Page | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Players | † | ✓ | — | ✓ | † | ✓ | ⚠ | ✓ | ✓ | ✓ |
| PlayerProfile | † | ✓ | † | ✓ | † | ✓ | ⚠ | ✓ | ✓ | ✓ |

## Fixes applied in P5

- **Brand-token violation (item 1/5):** GamesExplorer and GameDetail hardcoded `document.title = 'NHL Intel - …'`. Replaced with `usePageTitle` → the title now derives from `BRAND_NAME`. This was the only place the old name still leaked.
- **`usePageTitle` (item 1):** added to GameDetail, Playoffs, ArchetypeExplorer, and all five Studio tool surfaces (the three shelled tools get their title from `StudioShell` via the active tab; Contracts/Draft/Offseason directly).
- **Back-link labels (item 3):** GameDetail's "Back to Games" / "← Back to Games" → "Games" / "← Games" (parent-surface name, no "Back"). PageCard title "Game Detail" → "Game detail".
- **Sentence case (item 5):** Teams "League Landscape/Table" → "League landscape/table"; TeamProfile "Season Snapshot/Trends", "Last 10 Results" → sentence case; TeamRadar axis labels "Chance Quality / Danger Generation / Danger Suppression / Zone Control" → sentence case.
- **Learn links (item 10):** the Teams power/deserved views now carry "Full method →" links to `/learn/methods/power-ratings` and `/learn/methods/reconciliation` (the P2 `LEARN_LINKS_PENDING` marker is retired).

## Open items / notes

- **Item 7 (responsive + a11y) is ⚠ everywhere:** no headless browser is available in this environment, so 360/768/1280 layout, horizontal-scroll, and tap-target checks were reasoned about statically (mobile breakpoints exist for the new surfaces) but not visually confirmed. This is the one checklist dimension that needs a manual browser pass before sign-off.
- **Item 10 ⚠ on the tool pages:** each tool surfaces model numbers but does not yet link a Learn method doc. A follow-up can add a "How we measure" link per tool (e.g. Contracts → `/learn/methods/contract-surplus`, Draft → `/learn/methods/draft-value`); left out of P5 because it is arguably a functional addition, not a conformance fix.
- **Reference-page findings (not fixed — pages are "unchanged" by mandate):** Players has a "Player Rankings" tab and PlayerProfile has "Game Log", "Shot Map", "Performance Trends", "Career Trajectory", "Shot Locations" — all Title Case. These are genuine sentence-case findings on the reference surfaces; per the standing "Players index / PlayerProfile unchanged" rule they were left as-is and are recorded here for a future owner decision.
- **`DevComponents.tsx`** is a dev-only sandbox (unrouted) and was excluded from the sweep.

---

# The Sheet Design System conformance (DS4)

The ten laws + §11 accessibility, audited across the system after DS0–DS3. Status is at the
**token/component** level (the tokens and shared components propagate to every page), plus
page-specific notes. Same legend: ✓ pass · ✱ fixed in DS0–DS4 · ⚠ needs a browser pass · † reference
page left unchanged.

## The ten laws

| # | Law | Status | Evidence / notes |
|---|---|---|---|
| 1 | One page, one card | ✓ | PageCard is the single card; ChartPanel auto-flattens inside it; Studio shells are chrome, not cards. |
| 2 | Ink is interactive, Ice is data | ✱ | Fixed the ink-as-data violations: AssessmentBand histogram (ink→ice), SkillRadar polygon (ink→ice). Data families resolve to the ice/cat/div/seq ramps; accent (ink) is reserved for interaction + the R6 total tick (a marker, per spec). |
| 3 | Colour means one thing | ✱ | TierBadge de-coloured (was green/amber tier-by-colour → border-strong only). Confidence = success/warning/muted; valence = success/danger; categorical = cat-1..6. No overlap. |
| 4 | Every model number shows uncertainty or links its method | ✓ / ⚠ | Intervals/bands are the ±1sd convention; Teams power/deserved link Learn methods (DS0/P4). Per-chart "how we measure" links on the tool charts remain ⚠ (deferred with the recharts anatomy). |
| 5 | Serif speaks, sans works, mono measures | ✱ | Three roles wired (Fontsource). Display serif applied to page mastheads, team name/verdict, assessment headline, article body (DS2). Mono for ticks/ranks/overlines. |
| 6 | Sentence case everywhere (mono overline excepted) | ✱ | Swept in P5 + DS; overline is the only uppercase (ChartFrame kicker, region titles, ChartPanel section number). Reference-page Title-Case findings recorded, not fixed. |
| 7 | Hairlines over shadows | ✱ | shadow-md/xl retired from new work; MoreSheet xl→lg. Overlays use shadow-lg, PageCard/tooltips shadow-sm. Legacy shadow-md call sites remain ⚠ (audit in a visual pass). |
| 8 | Direct labels over legends | ⚠ | New charts favour direct labels; the RatingsViews on-demand 4-component power legend (a legend under 5 series) is the one known exception, left for a visual call. |
| 9 | Numbers tabular, signed, §5.4 formatted | ✱ | Global `tabular-nums` on td/.num/[data-num]; `fmt.*` namespace built and adopted on Today. Full legacy `toFixed` reduction is the ⚠ remainder. |
| 10 | Motion functional 120–240ms, honours reduced-motion | ✓ | Motion tokens defined; global `prefers-reduced-motion` guard added in index.css. |

## §11 accessibility

| Item | Status | Notes |
|---|---|---|
| Text contrast 4.5:1 (all three text tokens, both themes) | ✱ / ⚠ | text-secondary/muted darkened in DS0 to hit the target; not yet re-measured with a contrast tool (⚠). |
| Universal focus treatment (2px ring, offset 2, never removed) | ✱ | Global `:focus-visible` rule in index.css using `--focus-ring`. |
| Hit targets ≥ 40px on touch | ⚠ | BottomTabBar/rows sized for it; needs a 360px device check. |
| Charts role="img" + dek-mirroring aria-label | ✱ / ⚠ | ChartFrame sets it; existing SVG charts have partial role="img" — full sweep ⚠. |
| Live regions (score updates aria-live) | ⚠ | Not yet added to Today/Games score strips. |
| Reduced motion honoured | ✓ | Global guard. |

## Deferred (carried past DS4, need a visual/browser loop)

- **Ad-hoc button/input/overlay conformance** (§7.1/7.2/7.7) — no shared Button/Input components exist; the styles are scattered. Best done on the `/dev/components` gallery with eyes.
- **Recharts per-chart anatomy** — individual deks, source lines, mono axis-tick formatting, and the "how we measure" links on the page-embedded recharts charts (DraftValue, ContractGrader, TeamProfile, TraderDossier, ValueMap).
- **Full `toFixed` reduction** to chart internals across legacy pages (law 9 tail).
- **Legacy `shadow-md` call sites** (law 7 tail).
- **Live regions**, **contrast re-measurement**, **hit-target/360px audit**, and **full chart aria sweep** (§11 ⚠ items) — all require a running browser.
- **Reference pages** (Players, PlayerProfile) — Title-Case + vertical-gridline findings recorded; left unchanged by mandate.
