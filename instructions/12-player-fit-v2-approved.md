# 12 · Player Fit v2 · APPROVED

Supersedes 12-trade-fit.md. Comp: mockup-player-fit.html. Page lives at
Studio → Trades as the "Player fit" lens beside Build trade and Trade
history; masthead identical to 13 v2 (serif 24 title, lens tabs right, old
breadcrumb/eyebrow/dek removed).

## 0. Amendment ratified on this page
Green is retired from the product. Grades, positive states, and success
indicators render in ink or `--line-blue` per the value-color rule; the old
green grade boxes and green progress bars are gone. Letter grades everywhere
(here, Contract Grader, the Ledger) are Newsreader serif in ink.

## 1. Toolbar (the tool itself)
The pairing is a persistent control row, not a wizard: player select chip
(headshot, name) → arrow → team select chip (logo, name), each a combobox
with search; changing either re-scores immediately (no Score button). Right:
"Copy link" + solid-ink "Share card". URL encodes the pairing; deep links
restore it.

## 2. The scoreboard (one Panel, the only elevated object)
- Eyebrow row: "THE FIT · {date}" left; blue dotted "How we score fit"
  tooltip right (method, component weights, and the estimate caveats live
  here).
- Grid `1fr 170px`. Left: identity line (44px headshot, name 16.5, meta
  "C · 30 · Colorado · {archetype}", arrow, destination logo + team), then
  the generated verdict trimmed to two sentences max, 13.5 secondary.
  Right, right-aligned: eyebrow "Fit grade", the letter Newsreader 44 ink,
  beneath it "92 / 100 · {word}" (word from grade: strong / good / fair /
  poor fit).
- Below an internal hairline, four receipt lines in two columns (valence
  dots; the quality caveat always present with a neutral `#8A99A3` dot:
  "Quality travels: ... fit measures need, not talent"). Generated with
  template fallbacks from the work components.

## 3. Where he lands on the roster (the evidence)
The need-gap row, a variant of the track grammar: `158px label | track |
92px word`, height 32. Track: baseline hairline; hollow 8px dot (1.5px
`#8A99A3` border, white fill) at the team's current league percentile in
that area; solid ink dot at the player's percentile; a `#B9C7CD` connector
between them. Verdict word right: "Fills it" blue when a low team dot meets
a high player dot, "Helps" ink, "Covered" and "Low need" muted; thresholds
configurable. Five areas (finishing, even-strength offense and defense,
power play, penalty kill) split across two columns; the second column ends
with the fixed explainer line "The gap is the argument...". Legend in the
section header: "Hollow dot = {team} today · ink dot = {player} · percentile
within the league". Goalie subjects swap areas for goalie-relevant ones.

## 4. The work (collapsible, default expanded)
Rows `220px | 1fr | 130px`: component name with its weight in muted mono
("Need fit 55%", EST badge where estimated), the existing plain caption
center, word rating right (Strong / Excellent / Elite scale, word first, no
bars). Quality floor is a tooltip term carrying the ± WAR detail. Footer:
the unchanged disclaimer ("Fit and quality are separate... weigh those
yourself").

## 5. Around the league (closing strip)
Four Tiles: the three best fits (logo, team, serif grade letter 22, one-line
generated reason) plus the weakest fit on a white dashed-border Tile, grade
in secondary, reason honest ("a center logjam and low need where he's
strongest"). Header caption: "Talent is the same everywhere; the differences
are need and style · tap to re-score". Tapping swaps the destination select
and re-scores in place.

## 6. Empty and partial states
No wizard boxes, no red rule. With nothing selected: toolbar selects empty,
then a "Recent & notable" grid of tappable player Tiles (headshot, name,
pos · team, archetype, WAR) that fill the player select; a full search field
above it. Player chosen but no team: the grid swaps to the 32-team pill
grid. The scoreboard area shows one muted line until both selects fill
("Pick a player and a destination for a verdict"). Score-another is just
changing a select.

## 7. Share card
The scoreboard verbatim: pairing, grade, sentence, receipts, wordmark
footer. Copy link restores state per section 1.

## 8. Data
All served today: fit grade and components with weights, team and player
area percentiles (the gap rows are the existing need/strength data
re-plotted), best-fit rankings; add the single weakest fit to that endpoint.
Generated: verdict sentence, receipts, tile reasons, with template
fallbacks.

## 9. Mobile
Scoreboard stacks (identity, sentence, grade, receipts single column); gap
rows single column; work rows wrap caption under name; tiles two-up. Selects
stack full width.

## 10. Acceptance
- Changing either select re-scores without navigation; URL round-trips.
- No green anywhere on the page; grades serif ink; verdict words match
  configured thresholds on gap rows.
- Quality-caveat receipt always renders with the neutral dot.
- Gap rows plot served percentiles exactly (spot-check against the team
  profile's How they play and the player's percentile gauges).
- Weakest-fit tile renders dashed and re-scores like the others.
- Empty and partial states per section 6; share card matches the
  scoreboard; both themes AA; tsc and build green.
