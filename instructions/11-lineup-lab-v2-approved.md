# 11 · Lineup Lab v2 · APPROVED

Supersedes BOTH 11-lineup-lab.md and 15-roster-builder.md: the two tools
merge into one workspace at Studio → Lineup Lab; the Roster Builder route
301s here and its name is retired. Comp: mockup-lineup-lab-v3.html (v1/v2
are superseded iterations). The old sub-modes (Forward trio / Defense pair /
Full unit) and the Line Builder / Team Builder lenses are gone; the card
covers all of them.

## 0. Amendment: grade colors (amends 12 v2 section 0)
Letter grades remain Newsreader serif site-wide and gain valence color:
A-range `--line-blue`, B ink, C `#46545E`, D and F `--line-red`. Applies
here, Player Fit, Contract Grader, and the Ledger. Exactly two grade sizes
exist on this page: 15px in unit headers and the units strip, 28px in the
open inspector. Nothing adjacent to a colored letter repeats its signal
(strip labels stay muted).

## 1. Shape of the tool
A workspace with three parts: the card (canvas), the bench (palette), and
the projection scoreboard (live score). Every action on the card re-renders
the scoreboard and the affected unit grades immediately; there is no submit
step and no separate results page.

## 2. Masthead and toolbar
Serif 24 "Lineup Lab" + dek; no lens tabs. Toolbar: team select chip (the
list includes "Blank sheet" at top), "Optimize placement", quiet Undo and
Reset, then Copy link and solid-ink Share card right. Below, one how-to line
referencing the actual affordance glyphs: drag the grip to move, tap the
chevron to inspect, the team select includes a blank sheet.
- Team selected: the card autofills that roster (current deployment).
- Blank sheet: an empty card; fill any slots in any order with any player;
  units grade as soon as they're full.
- Optimize placement rearranges ONLY the players currently on the card;
  it never adds or removes anyone. After running, moved cells carry the
  MOVED treatment and the move receipt summarizes ("Optimized: 4 moves ·
  roster +0.8 · Undo").

## 3. The projection scoreboard (one Panel)
Eyebrow "THE PROJECTION · {date}" + "How we project rosters" tooltip.
Content row: the delta vs the selected team's real roster (serif 32, THE
number; suppressed on a blank sheet with no baseline), projected points and
full-season range as standard figures, and the units strip right: one
column per unit (grade letter 15 over a mono unit label), each tappable to
scroll-and-inspect. Below an internal hairline: the move receipt left
("Last move: {player} to {slot} · {unit} 54→56% · roster +0.3 · Undo") and
right the honesty caption ("the change vs the real roster is the reliable
number") plus a collapsed "The work ▾" that expands to the component-value
and positional-strength rows (bar anatomy from the GAR composition, blue
positive / red negative, signed values). Undo history is a stack (multiple
undos); Reset restores the selected baseline.

## 4. The card
Named components:
- Player cell: 56px, grid `10px grip | content`; grip glyph in `#C9D6DC`;
  position + handedness mono 10 (goalies STARTER/BACKUP); name 13.5 w500
  ellipsized; WAR line 11.5 tabular: shrunk value colored by the player
  value rule + muted ± band. Identical for lines, pairs, goalies; all units
  share one 3-column grid so cell widths never vary by unit type. Empty
  slots are dashed cells ("+ Backup"). A moved player shows a blue border
  and a MOVED suffix on the badge until the next action.
- Unit header: eyebrow left; right cluster always in order: grade letter,
  "· {xGF}% xGF" 11.5 muted, inspect chevron. Goalies have no grade.
- Interactions: drag grip cell-to-cell to swap; drag from bench into any
  cell (replaced player returns to the bench top); tap chevron (or the
  strip letter) to inspect.

## 5. The unit inspector
Opens inline inside the unit's blue ring, beneath its cells; one unit
inspected at a time; ✕ closes. Row one: grade serif 28 (colored per 0) +
word; the 35-65 xGF track with a 50 tick and a dot colored by bucket; three
rate figures (xGF/60, xGA/60, net colored). Row two: up to three valence
receipt lines (generated, template fallbacks). Footer caption: the
real-minutes blend ("Blended with 212 real 5v5 minutes together, 46%
observed, weighted 61%"), a "Model inputs ▾" expand, and a pointer to
Better fits on the right. Units with zero shared minutes say "cold start ·
no shared minutes yet" in the blend slot.

## 6. The bench (right column, 300px)
Header + "drag onto the card" caption; league-wide search; source tabs
"{Team} spares {n}" / "League" (blank sheet shows League only). Rows: grip,
name + "pos · age" meta (league rows add team), WAR + band in the same
tabular style as cells. Always sorted by WAR; the bench never re-sorts
itself. Players dragged off the card land at the top of their tab.

## 7. Better fits (right column module, below the bench)
Eyebrow "BETTER FITS · {unit}" + "tap to swap" caption; scoped to the
inspected unit. Rows: name, "pos · team · over {incumbent}" meta, target
slot mono, projected "+{x} pp" in blue. Tapping swaps the player in,
re-grades, and writes the move receipt. Footer "All alternatives by slot →"
opens the full ranked list. With nothing inspected the module shows one
muted line: "Inspect a unit to see upgrades." Suggestions are same-caliber
by usage tier (existing model behavior) drawn league-wide, spares included.

## 8. Share and URL
Copy link encodes team/blank baseline and every slot assignment. The share
card is the scoreboard plus the card in compact form (names and grades, no
bench). Cross-team cards are the fun ones; the baseline line is omitted on
blank sheets.

## 9. Data
All existing: per-player shrunk WAR with bands, unit xGF projections and
grades, real shared-minutes blend, component and positional values, roster
delta and point projection, better-fit rankings. New: move-receipt deltas
(one recompute per action, already required for live grading) and grade
color thresholds shared with 12/14.

## 10. Mobile
Bench becomes a bottom sheet opened from a persistent "+ Bench" button;
scoreboard sticks compressed (delta + weakest unit) on scroll; cells go
full-width per unit row; drag falls back to tap-to-select, tap-to-place.

## 11. Acceptance
- One player-cell component and one unit-header component render every
  unit; pair and goalie cells are dimensionally identical to line cells.
- Grade colors follow section 0 in headers, strip, and inspector; only two
  grade sizes exist on the page.
- Every card action updates the scoreboard, unit grades, and move receipt
  in one frame; Undo reverses actions one at a time; Reset restores the
  baseline.
- Optimize placement never changes the player set; moved cells are marked;
  its receipt summarizes the move count and delta.
- Blank sheet: no delta shown; units grade when full; League is the only
  bench tab.
- Better fits scopes to the inspected unit, swaps in place, and shows the
  empty-state line otherwise; the bench never re-sorts.
- Share card and copy link round-trip the full card; Roster Builder URL
  301s; both themes AA; tsc and build green.
