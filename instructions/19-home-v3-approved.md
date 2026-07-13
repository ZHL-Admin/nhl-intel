# 19 · Home ("Today") v3 · APPROVED

Supersedes 19-home-today-v2.md. Matches the approved rev 3 comp exactly; where
this doc and older docs disagree, this doc wins. Assumes 00b and 00c have landed.
Applies to the existing Today/home page component and route; do not change routing
or the nav. Offseason state only for now (see Phases, bottom).

## Page anatomy, top to bottom

Everything below the nav sits on the canvas (`--color-bg-base`) inside the Well
(`--color-bg-surface`, 1px `--color-border-subtle`, radius 24, padding 28px 32px
32px, max-width `--container-max`, centered), followed by the footer on the canvas.

### 1. Context strip (00c variant; no Sheet title on this page)
Left: the human date, "Tuesday, July 7", Archivo 13.5 weight 500,
`--color-text-primary`. Right: the phase line, 13px `--color-text-muted`:
"Free agency · Day {n} · {d} days to opening night". Day count from July 1 of the
current year; days-to-opening from the first scheduled game date in the games API.
Baseline aligned, padding-bottom 14, border-bottom 1px `--color-border-subtle`,
margin-bottom 24. No red rule (00c).

### 2. The single grid (structural law for this page)
One grid wrapper holds the rest of the Well content above the Studio band:
`grid-template-columns: minmax(0,1fr) 324px; gap: 40px`. The main column and the
rail live inside it. Nothing on this page may introduce a second column structure;
every vertical seam on the page is this grid's seam. (This is the balance fix the
approval ratified; treat it as an invariant, not a default.)

## Main column

### 3. The Lead
Eyebrow "The lead". Headline: Newsreader 37px, line-height 1.15, weight 500,
max-width 620px, target two lines or fewer at column width. Dek: Archivo 15px,
line-height 1.55, `--color-text-secondary`, max-width 600px, one to two sentences.
Link: quiet blue text link with a small arrow icon ("Read the breakdown").
Source: the daily insight/report feed if an endpoint exists; otherwise derive
client-side from the largest single-day move on the offseason board and file a
backend TODO for a served lead. The Lead links to the page that substantiates it
and never duplicates a rail module's full content.

### 4. Divider
1px `--color-border-subtle`, margin-top 26, padding-top 22, main column only.

### 5. The Ledger
Module header: eyebrow "The ledger · This week's moves" left, quiet blue link
"All moves" right, margin-bottom 11.

Table (not a Panel; hairline Gamesheet in the main column):
- Column grid: `50px date | minmax(0,1fr) player | 66px to | 122px terms |
  96px verdict`, column-gap 12. Verdict column right-aligned.
- Header cells in eyebrow style, padding-bottom 6, bottom border 1px
  `--color-border-strong`. Labels: Date, Player, To, Terms, Verdict.
- Rows: min-height 47, bottom border `--color-border-subtle`, 8 most recent moves.
- Cells: date in Spline Sans Mono 11 uppercase muted ("JUL 7"); player name
  Archivo 15 weight 500 with position inline in 12px muted; team as a 9px
  `getTeamColor` dot plus abbrev 13 weight 500; terms tabular 13.5
  ("6 yr · $7.0M"), trades render "Trade · {asset}" in `--color-text-secondary`;
  verdict for signings is a 27px circle, 1px `--color-border-strong`, letter in
  Newsreader 14.5 weight 500 (must render 1 and 2 character grades: A, B+, C-);
  verdict for trades is eyebrow-style text in `--color-text-secondary`
  ("Edge DET"), no glyph.
- Footer row: padding-top 12, top border 1px `--color-border-strong`, quiet blue
  link "All {n} moves this offseason" with arrow, where n comes from the API.
- Interaction: row hover is the `--crease` wash; the row links to the graded
  detail (prefilled Contract Grader for signings, trade dossier for trades); the
  player name is a nested link to the player profile (stop propagation).
- Data: the roster-moves feed, newest first. Verdicts must be precomputed
  server-side; if a move has no grade, render the row with an empty verdict
  cell (blank, not a fake) and file the backend TODO "grade on write in the
  offseason DAG". Never compute or invent grades client-side.

## Rail (side column)

Flex column, gap 14. Every module is a Panel (00c). Order is fixed:

### 6. Offseason board (movers)
Header: eyebrow "Offseason board", link "Full board".
Rows: grid `52px label | minmax(0,1fr) track | 38px value`, gap 8, height 28.
Label: 9px team dot + abbrev 13 weight 500. Value: tabular 12.5, right-aligned,
`--line-blue` for risers, `--line-red` for fallers, signed ("+3.5").
Track: shared fixed domain of ±4.0 WAR across all rows; 3px bars fill from the
center; risers rightward in `--line-blue`, fallers leftward in `--line-red`.
Unresolved forecast portion renders as a dashed extension (3px dashed border) of
the same color. One 1px `--color-border` vertical zero line spans all rows inside
the track column, pixel-aligned at every width. Content: top 3 risers then top 2
fallers by absolute change. Legend under the rows, eyebrow 11:
"Dashed = unresolved spots".

### 7. Still available
Header: eyebrow "Still available", link "All free agents".
Four rows, min-height 31, hairline tops between rows: player name 13.5 weight 500
with position and age inline 12px muted ("LW · 27"); right side "proj $7.1M" in
tabular 13 `--color-text-secondary`. Rows link to player profiles.
Data: top remaining UFAs ranked by projected value. Projected AAV comes from the
contract model; if projected AAV is not served yet, show projected WAR instead
and file the backend TODO; if neither, omit the right column rather than fake it.

### 8. End of season board
Header: eyebrow "End of season board", link "Rankings".
Five rows: grid `14px rank | 9px dot | 1fr team | 40px rating`, row height 29.
Rank tabular muted; abbrev weight 500 with city name inline secondary; rating
tabular weight 500 right-aligned. Rows link to team profiles. Rename the module
"Power board" automatically once the new season's ratings begin updating.

### 9. Featured
Eyebrow "Featured"; title Newsreader 16.5 line-height 1.3; dek 12.5 secondary,
one line; quiet blue "Read" link with arrow. Source from Learn (the archetypes
explainer) until editorial writing exists; structure so a future content source
drops in without layout change.

## Below the grid

### 10. Studio band
Full Well width. Top border `--color-border-subtle`, margin-top 26, padding-top
20. Header: eyebrow "From the Studio", link "All tools". Three equal columns,
gap 32, each fully clickable to its tool: name in Newsreader 17; dek 12.5
secondary, one line; contract line in Spline Sans Mono 11 muted
("player + terms → grade"). Offseason pinning: Contracts, Trades, Lineups. The
pinned set is a config array so the season state can rotate it.

### 11. Footer
On the canvas below the Well (per 00b, already shipped): container width,
margin-top 20, padding 16px 24px 22px, top border 1px `--color-border`. Left:
14px logo dot, "Rink Theory" 13 weight 500, "· Hockey that shows its work." 13
muted. Right: Spline Sans Mono 11 uppercase muted "DATA THROUGH {date} · UPDATED
NIGHTLY", then Methods and Writing links 12.5 secondary. Verify its left and
right edges align with the Well's outer edges.

## States and behavior
- Phase detection: a small utility returning `season` when any game is scheduled
  within the next 7 days, else `offseason`, derived from the games dates API at
  load. This page ships the offseason layout only; the season branch renders the
  same page for now behind a clearly marked TODO. The season layout gets its own
  mockup-approval pass before it is built.
- Loading: flat `--color-bg-elevated` skeleton blocks matching each module's
  silhouette; no shimmer.
- Empty ledger (no moves in 7 days): one Newsreader italic line ("Quiet week.
  Last move Jun 28.") plus the "All moves" link; keep the rail as normal.
- Mobile: below 900 the grid stacks in order: context strip, Lead, Ledger, then
  the four Panels, then the Studio band (single column). Below 640 the Ledger
  restacks each row to two lines: line one is player plus verdict right; line two
  is date, team, terms in muted 12px. The Studio band stacks to one column.
- All numerals `tabular-nums`. Team colors only via `getTeamColor`. No new fonts,
  no hardcoded colors outside `getTeamColor` and the tokens.

## Acceptance
- One vertical seam: the rail's left edge is at an identical x from the movers
  panel through Featured, and no element introduces a second column split.
- No red horizontal rules on this page; the context strip and all dividers are
  neutral (00c applied globally).
- Ledger renders 1 and 2 character grades in the circles; a graded signing, an
  ungraded signing (blank verdict), and a trade (text verdict) all verified.
- Movers bars share the ±4.0 domain and one pixel-aligned zero line; at least one
  dashed unresolved segment verified against real data.
- Panels are visually identical in treatment; main column and rail bottoms land
  within roughly 100px of each other at 1440x900 with 8 ledger rows.
- Keyboard order: context strip, Lead link, Ledger rows, rail panels top to
  bottom, Studio cells, footer links; focus visible throughout.
- Both themes AA including `--color-bg-panel`; tsc and production build green.
