# 13 · Trade Builder v2 · APPROVED

Supersedes 13-trade-builder.md. Comp: mockup-trade-builder-v2.html (v1 is a
superseded iteration). Assumes all prior system amendments (rail retired, red
rule and red center line retired, tooltip pattern, valence dots, value-color
rule).

## 1. Masthead and toolbar
Title row inside the Well: "Trade Builder" Newsreader 24 left; sub-lens text
tabs right: Build trade (default) · Player fit · Trade history. The old
breadcrumb, STUDIO eyebrow, display-size title, and dek are removed. Toolbar
row below: eyebrow count "2 TEAMS · 3 ASSETS" + "+ Add team" + quiet "Reset"
left; "Copy link" + solid-ink "Share card" right. Buttons radius 2, height 30.

## 2. The scoreboard (the verdict, one Panel)
A single Panel, roughly 200px, the only elevated object on the page. It sits
above the pieces and re-renders live as assets change.
- Eyebrow row: "THE VERDICT · {date}" left; right: confidence dot-chip
  ("Medium confidence"; dot muted for low/medium, ink for high) and a blue
  dotted "How we judge trades" tooltip carrying the method, including how the
  tilt is computed if it is derived rather than a direct model output. The
  tilt and the home Ledger's "Edge {TEAM}" language must share one source.
- Two-team layout: grid `1fr 300px 1fr`. Left: logo 24, team name 14.5, role
  phrase in serif italic 14 secondary (generated: "Wins now", "Retools for
  the future"). Center: the balance meter: hairline track, quarter ticks,
  stronger center tick, one 9px ink dot placed by the tilt; one 12px worded
  label beneath ("Nearly even · slight edge Carolina"). Right: mirrored team
  block, right-aligned.
- Below an internal hairline: receipt lines in one column per team (three
  per side, valence dots blue/red for that team's perspective, bold two-to-
  four-word lead, number embedded mid-sentence, one line each). Generated
  with template fallbacks from the four work metrics; a cap violation is
  always one of the three.
- Three-plus teams: the flanking grid and meter do not scale, so the
  scoreboard becomes stacked team rows, one per team: `24px logo | team +
  serif role phrase (240px) | net-edge micro-bar | receipt lines (1fr)`.
  The micro-bar is a zero-centered signed bar (anatomy of the GAR
  composition bars): blue right of zero for net value gained, red left for
  given up, all rows sharing one scale, with the signed value printed
  ("+$3.1M eq"). Rows sort by net edge, best first. The worded label moves
  into each row's bar cell ("Comes out ahead", "About even", "Gives up the
  most"). Receipt lines drop to two per team. Eyebrow row is unchanged.
  This layout activates at N >= 3; removing back to two teams restores the
  meter.

## 3. The pieces (the workspace)
Two team columns on the plain page divided by a 1px hairline (the red center
line is gone); at three-plus teams, columns wrap two per row.
- Column header: logo, team, remove ✕. Source text-tabs with muted counts
  (Players · Prospects · Draft picks), then a search field scoped to that
  team, then a "{TEAM} SENDS" eyebrow.
- Asset cards are Tiles: 36px headshot (pick cards use a mono year badge),
  name 14.5, meta line muted ("C · 29 · to Carolina"; destination is a
  select when three-plus teams). Figure row: "WAR, term" (tooltip: projected
  WAR over remaining term, with range) · "vs market" (tooltip: surplus value,
  renamed from surplus everywhere on this page) · "Cap $8.7M · 6y" ·
  retention select right ("None ▾", options 25% and 50%; retained salary
  restyles the cap figure and recomputes everything). Values colored by the
  value rule.

## 4. The work (the appendix)
Collapsible section, default expanded, "Hide ▴" toggle; state remembered.
One shared table: `metric+caption (1fr) | one 104px right-aligned value
column per team | 250px context`. Rows:
- Talent ("WAR gained or lost, next season"): signed values colored;
  context = history strip.
- Price vs market (tooltip term; "surplus value exchanged, per year"):
  signed dollars colored; history strip.
- Fit (tooltip term; "how incoming players slot into lineup need"): word
  first (Strong / Good / Fair / Poor mapped from the fit score, thresholds
  configurable) with the number muted beside it; context = one generated
  sentence naming who fills what.
- Cap (APPROX mono badge; "projected against this season's ceiling"):
  "Under $1.2M" ink / "Over $8.8M" red; context = the before-and-after
  arithmetic per team.
History strips reuse the league-distribution row anatomy: ticks are real
trades from the Trade Outcomes dataset positioned by magnitude percentile,
dot is this trade, caption "A bigger talent swing than 84% of trades".
Footer line: present value as a tooltip term plus the strip explanation;
this replaces the old footnote paragraph entirely.

## 5. Empty state
Same masthead and toolbar (count reads "0 TEAMS · 0 ASSETS"; Reset hidden).
No red rule. Two side-selection Tiles ("Side A · choose a team" / "Side B"),
the 32-team pill grid beneath (pills radius 2, logo + abbrev), then a
hairline, then the start-from-a-player search with "load an example →"
right. Choosing a team collapses the picker into that side's column;
the scoreboard appears only once both sides hold at least one asset,
before which its space shows a single muted line ("Add assets to both
sides for a verdict").

## 6. Share card and URL
Copy link encodes teams, assets, and retention in the URL (shareable,
restorable). Share card renders the scoreboard exactly: verdict eyebrow and
date, meter or stacked rows, role phrases, receipts, plus one generated
prose sentence at the top (the only place the old verdict paragraph
survives) and the wordmark footer.

## 7. Data and dependencies
Per-asset projected WAR over term with range, surplus (market gap), cap
figures, retention math: all existing. Tilt: model output or documented
derivation shared with the Ledger. Fit scores with word thresholds. Trade
history magnitude percentiles (computed from Trade Outcomes; never
decorative). Generated role phrases, receipts, and fit sentences with
template fallbacks.

## 8. Mobile
Scoreboard: teams stack, meter full width between them, receipts single
column. Pieces: columns stack, per-team; the scoreboard collapses to a
sticky one-line summary bar (tilt label + confidence) while scrolled past.
The work scrolls horizontally beyond two teams.

## 9. Acceptance
- Scoreboard updates live on add/remove/retention; N >= 3 swaps to stacked
  rows sorted by edge and back again; micro-bars share one scale.
- Receipt lines: three per side (two at N >= 3), valence dots correct per
  perspective; cap violations always surface.
- Work table: fit words match configured thresholds; strips positioned from
  real Trade Outcomes percentiles; PV footnote paragraph removed for the
  tooltip.
- Empty state carries no red rule; verdict placeholder line until both
  sides have assets.
- Copy link restores full state; share card matches the scoreboard plus the
  prose line.
- Renames verified everywhere on the page: cost-efficiency to Price vs
  market, surplus to vs market on asset cards.
- Both themes AA; tsc and build green.
