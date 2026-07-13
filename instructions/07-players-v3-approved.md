# 07 · Players v3 · APPROVED

Supersedes 07-players-index.md. Matches the approved rev 3 comp; where this doc
and older docs disagree, this doc wins. Assumes 00b and 00c have landed. Applies
to the existing players page component and route; do not change routing or nav.

## Language rule (applies site-wide, ratified here)
The phrase "assessed WAR" is retired from all UI. The column and value are "WAR";
reliability shrinkage is explained in plain words only where the confidence band
appears (see 5.4). Grep the frontend for "assessed" and update strings.

## Page anatomy

Nav, Well (00b/00c), footer as shipped.

### 1. Masthead (two rows)
Row one: title "Players" in Newsreader 24 left; right, baseline-aligned: lens
tabs "Rankings" (default) and "Usage and value" in the text-tab language, then
the season select (hairline, radius 2). Bottom border subtle, padding-bottom 14.
Row two (margin 16 0 6): left, position filters as text tabs: All, C, LW, RW, D,
G, then a 1px vertical divider, then "Rookies" as a toggleable filter of the
same style (it intersects the position filter, not exclusive). Right: team
select ("All teams", same select style) and "{n} qualified · How we measure"
in 12.5 muted with the blue Methods link (opens the methodology page or
popover). The qualified count always reflects the active filters. There is no
inline player search and no ⌘K hint on this page; the nav search is the single
search affordance.

### 2. Column sets (per lens and filter)
One table frame; the stat columns swap by context.
- Rankings lens, skater filters (All-skaters via C/LW/RW/D): GP, G, A, P, TOI,
  P/60, xGF%, GAR, WAR.
- Rankings lens, G: GP, SV%, GSAx, WAR (add GSAx/60 only if already served).
- Rankings lens, All (mixed skaters and goalies): the minimal value board: GP,
  TOI, GAR, WAR. Never show G/A/P in a mixed view.
- Usage and value lens: same anatomy with a deployment/contract set (TOI, PP
  share, zone starts, cap hit, surplus value). Finalize against fields actually
  served; do not invent columns without data, and drop gracefully per column.

### 3. Table anatomy
Header row: eyebrow-style labels, right-aligned over numeric columns, 1px
`--color-border-strong` beneath. Sortable: every stat header and WAR; the
active sort header renders ink with a 2px `--line-blue` underline and a ▾/▴
direction glyph; clicking toggles direction; default sort WAR descending.
**Emphasis follows sort**: the active sort column's values render
`--color-text-primary` weight 500; all other numerics are 13.5
`--color-text-secondary` tabular. (The comp's emphasized P column was a
demonstration of the treatment only.)

Row grid: `22px rank | 22px movement | 30px headshot |
minmax(0,1fr) player | ...stat columns 34-52px each | 86px WAR`, column-gap 12,
min-height 52, hairline bottom borders. The player column is the only flexible
column, so numerics cluster right against WAR by construction; preserve this
when adding or removing columns.
- Rank: tabular 13 muted. Re-numbers by the active sort (rank 1 is the top of
  whatever board is sorted).
- Movement: shown only when sorted by WAR descending; ▲n in `--line-blue`, ▼n
  in `--line-red`, 11px; unchanged rows show an en dash in `--color-border-strong`.
  Computed against the rank snapshot from 7 days prior (see Data).
- Headshot: 30px circle, 1px border, real assets, grayscale block fallback.
- Player: name 14.5 weight 500 (links to profile), second line 12 muted:
  position-group dot (site tokens: forwards teal, defense violet, goalies
  amber) + "C · EDM · {archetype}".
- TOI formats mm:ss; xGF% one decimal; GAR and WAR signed.
- WAR cell, right-aligned stack: value tabular 15 weight 500, then the
  micro-band: 64x10, hairline track, ±1 sd range as a 4px `#C9D6DC` bar, 6px
  ink point. No scale labels at this size; title attribute carries "±{sd}".
- Row interaction: clicking the row (or its chevron zone at far right if
  retained) expands the dossier card; the name link navigates instead
  (stop propagation). One row expanded at a time; expanding another collapses
  the first. Expansion animates height 160ms ease-out (sanctioned exception to
  the motion policy; instant under reduced motion). Hover: crease wash.
- Pagination: 25 rows, quiet secondary "Show more" centered beneath. Never
  infinite scroll.

### 4. Empty and loading
Loading: flat skeleton rows. A filter combination with zero results: one
Newsreader italic line ("No qualified players match these filters.") plus a
quiet "Clear filters" text button.

## 5. Expanded dossier card

A Panel (00c) spanning full table width beneath the row, padding 20px 24px,
margin 2px 0 12px. Contents in order:

### 5.1 Header row
Left: 36px headshot, name 16 weight 500, one meta line 12 muted: "C · EDM ·
Age 28 · Shoots L · {tier} · {archetype} · {usage descriptor}". Right: actions:
primary ink button "View full profile" (navigates) and secondary hairline
button "Compare with..." (see 6.2). Buttons radius 2, height 32.

### 5.2 Verdict
Margin-top 16. The served verdict sentence as the site's pull-quote: Newsreader
italic 16, line-height 1.45, 2px `--line-blue` left border, 14px padding-left.
If no verdict is served for a player, omit the block entirely.

### 5.3 Two-column body (grid 1fr 1fr, gap 38, margin-top 26)
The 26px top margin is deliberate (approved spacing note); do not shrink it.

Left column, "Where the value comes from · GAR":
- One row per served GAR component (label 13 secondary, 4px bar from zero,
  value tabular 12.5 weight 500). Bars scale to the largest absolute component;
  positive fills `--line-blue`, negative fills `--line-red` with the value in
  red. Skater components as served (even-strength offense, power play,
  even-strength defense, penalties, faceoffs, etc.); goalie cards use the
  goalie decomposition (GSAx-based components) with the same anatomy.
- Total line, 13 secondary tabular: "Total +31.0 GAR → +3.6 WAR after
  reliability shrinkage".
- Percentile pair (margin-top 16): "Production" and "Play-driving" as the
  standard gauge (hairline track, blue dot, tabular value), side by side.
- Data dependency: if per-component GAR is not served, render the total line
  and percentile pair only and file the backend TODO; never fabricate a split.

Right column:
- "Confidence range · ±1 sd": the full band at column width: hairline track,
  zero tick with mono "0" label, "+6" at the right end (fixed 0 to +6 domain,
  matching the row micro-bands), ±1 sd range bar, 8px ink point. Caption
  beneath, 11.5 muted, two lines max, plain language: "WAR is shrunk toward
  league average until the sample earns it. A wider band means a softer rank;
  when two bands overlap, the order between them is soft."
- "Season by season" (margin-top 20): the last five seasons as small vertical
  bars (9px wide, heights proportional on a shared scale), value tabular 11.5
  above, season in mono 11 beneath; past seasons `#C9D6DC`, current season
  `--line-blue` with its value in ink weight 500. Fewer than five seasons:
  render what exists, left-aligned.
- Both columns should bottom out within ~24px of each other for a typical
  skater; tune internal margins, not content, if they drift.

### 5.4 What is deliberately absent
No radar (relocated to the full profile page), no season-stats table (now in
the row), no pill chips anywhere in the card.

## 6. Behaviors

### 6.1 Shareable state
Lens, position filter, Rookies, team, season, sort key and direction, and the
expanded player id all encode into query params; loading a URL restores the
exact view; back/forward navigates state. Titles update ("Players · C ·
sorted by G") for share previews.

### 6.2 Compare
Preserve the existing compare flow behind "Compare with..." (player picker into
the current comparison view), restyled to system. Fast-follow, optional, behind
its own flag: a multi-select compare tray (selecting players from cards
accumulates 2-3 into a bottom bar with a primary Compare action). Do not build
the tray in this pass if no comparison route exists; file the TODO.

## 7. Data dependencies
Rank movement requires a nightly rank-snapshot table (hide the column plus TODO
if absent). Per-component GAR per 5.3. WAR-by-season history for the trend.
Rookie flag for the filter. TOI, xGF%, SV%, GSAx from served stats. Verdict
sentences and percentiles as currently served.

## 8. Mobile
Below 900: columns reduce to GP, G, A, P, WAR (goalies: GP, SV%, WAR);
movement hidden; team select collapses into a filters sheet with the position
tabs. Below 640: columns reduce to P and WAR (goalies: GSAx and WAR); the
expanded card stacks to one column in the order header, verdict, composition,
confidence, trend, actions. Filters scroll horizontally.

## 9. Acceptance
- Sorting: every header sorts, direction toggles, rank re-numbers, emphasis
  follows the active column, WAR-desc shows movement and other sorts hide it.
- Column sets verified in all five contexts (skater filters, G, All-mixed,
  Usage lens, mobile reductions); G/A/P never appear in a mixed view.
- Micro-band and card band share the 0 to +6 domain; a goalie's wide band and
  a star skater's tight band spot-checked against served sd.
- Card: columns bottom-align within tolerance for a typical skater; goalie
  decomposition renders; missing-component and missing-verdict fallbacks
  verified; the 26px verdict-to-body gap present.
- No "assessed" strings remain in the UI; no pills; one search affordance.
- URL round-trip restores lens, filters, sort, and expanded row exactly.
- Keyboard: filters, headers (sort on Enter), rows (expand on Enter), card
  actions all reachable in order; focus visible; both themes AA; tsc and
  build green.
