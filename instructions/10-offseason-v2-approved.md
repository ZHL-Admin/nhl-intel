# 10 · Offseason Forecast v2 · APPROVED

Supersedes 10-offseason.md. Comp: mockup-offseason-v3.html (the league
table with Detroit's dossier and Cossa's decision expanded).
mockup-offseason.html, -v2, and -league are superseded iterations. The
page keeps its name and URL; the League/Team lens tabs are retired in
favor of one league view with expandable team dossiers (old Team-lens
URLs 301 to `?team={abbr}`, which auto-expands and scrolls to the team).
Deep links from the team profile ("Offseason plan →") land the same way.

## 1. The league table
Masthead: serif 24 "Offseason forecast" + dek "Projected standings for
{season}, and the summer's open decisions, priced". Toolbar: "Jump to a
team" select (expands that row), an update line ("Updated daily as moves
land · {n} signings logged yesterday"), Copy link, Share card.

Players-board table rules (07 v3): sortable columns, emphasis follows
sort. Columns: rank (projected order), Team (logo, name, meta "{last
season rank} last season · {n} spots open"; last-season rank colored by
the team-rank rule; the meta absorbs the old chart's unresolved-spots
footnote), Projected points (default sort desc), From moves (points,
colored by sign, near-zero stays secondary), Moves (count logged), Net
WAR (signed, colored), Effective space (colored; tooltip carries the
formula). All 32 rows; 16 shown then "Show all". Footer captions: the
effective-space definition ("cap space after projected RFA awards and
league-minimum fills"), the nightly-update note, and "tap a team to open
its summer".

## 2. The team dossier (row expansion, one at a time)
The expansion sits on a `#F7FAFB` wash; each section is a distinct white
card (`#FFFFFF`, 1px `#E7EEF1`, radius 12) so the sections read as
separate objects, not one run-on region. Order:

### 2.1 The summary (card)
Header row: eyebrow left; right, two links: "Open the projected roster
in Lineup Lab →" (carries the projected depth chart; this replaces the
old Projected Lineup section) and "Team profile" (which now owns the old
Where the Strength Lives content). Figures row: Projected points (caption
"80% range {a}-{b}"), From moves (points, colored, one-line caption),
League rank ("of 32 · was {n} last season"), Moves logged (caption
"{i} in · {o} out"; tapping the figure expands the full in/out ledger
inline: each move with its signed projected-WAR effect and band, i.e. the
old What Moved The Number rows), Effective space (colored; caption
"{raw} raw · the RFA awards eat it" or equivalent). Below a hairline: two
or three valence receipt lines summarizing the summer.

### 2.2 The decisions (card)
Quick-view text-tabs All · RFAs · UFAs; the Grader-attribution caption
right. Players-board table: Player (name + "pos · age"), Last season
(mono stat line: skaters "GP · G-A-P", goalies "GP · SV% · GAA"), WAR
(default sort desc; signed value colored by the player value rule + 60px
band on a fixed ±3 domain), Contract (status chip RFA/UFA/ARB + expiring
AAV), Projected (the award: "$x × ny", served by the Contract Grader),
The call (word: Re-sign blue / Toss-up ink / Walk red; rule: sign of the
projected surplus at the projected award, with a dead band around zero
for toss-ups; the rule is stated in the footer caption).

Player expansion (nested, one at a time): a wash card inside the white
section card. Contents: a verdict sentence, then a two-branch grid:
"IF THEY RE-SIGN · {terms}" and "IF THEY WALK", each with two valence
receipt lines pricing the branch in forecast points, the contract grade
and surplus (sign side), space consequences, and the honest caveat where
one exists (e.g. goalie-development noise, neutral dot). The stopgap
assumption behind the walk branch (league-average replacement at the
position) is documented in the Call tooltip. Actions: "Grade a number →"
(Contract Grader, hypothetical mode, player preloaded), "Player
profile", "Find a replacement" (scrolls to Best available fits filtered
to the position).

### 2.3 The holes and best available fits (card)
Two-column grid. Left, THE HOLES: up to three need rows (title + one
explanatory line), sourced from the depth chart and how-they-play
percentiles. Right, BEST AVAILABLE FITS: four Tiles on wash (name, fit
grade letter valence-colored, one-line reason; the top fit's reason may
price itself in forecast points), the free-agent pool scored by Player
Fit for this team; tapping a tile opens Player Fit with the pairing
loaded. Beneath the tiles: "Build a trade instead →" (Trade Builder with
the team preloaded) plus a muted rationale clause. The former Assets
section is deleted; pick leverage appears as a summary receipt when it
matters.

## 3. Deliberate cuts from the current page
- The league bar chart is replaced by the table (rank and colored
  From-moves carry the same reading).
- Projected Lineup: replaced by the Lineup Lab link (single owner of
  depth-chart rendering).
- Where the Strength Lives: replaced by the Team profile link.
- The Verdict paragraph: its content is distributed to the summary
  receipts; no prose block in the dossier.
- The moves ledger survives behind the Moves-logged figure (2.1).

## 4. Data
Existing: nightly forecast (points, ranges, ranks), per-move WAR effects
with bands, cap sheet, stats lines. New: effective space (Grader awards
plus league-minimum fills), the Call thresholds, two-branch forecast
deltas (roster with and without the player, stopgap-adjusted), and the
batch Player Fit scoring of the FA pool per team (cacheable nightly; the
pool is small). Generated text: summary receipts, decision verdicts,
branch lines, hole explanations, all with template fallbacks.

## 5. Seasonal behavior
The page always shows the next summer. During the season the decisions
list holds upcoming expiries and the forecast tracks the current roster;
the header label rolls to the new offseason when the league year turns
on Jul 1. The update line always names the latest logged activity.

## 6. Share and URL
URL encodes sort, expanded team, and expanded player. Share card: with a
team open, the summary card plus the top of the decisions table; with
none open, the top five rows of the forecast.

## 7. Mobile
Table drops Moves and Net WAR below 720 (both live in the summary);
dossier cards stack full-width; decisions drop the stats column; the
two-branch grid stacks; fits go 2x2 to 1-column.

## 8. Acceptance
- Expansion hierarchy: wash container, white section cards, nested
  player expansion on wash; one team and one player open at a time.
- Sort emphasis follows the players-board rules in both tables; WAR band
  domain fixed at ±3; league default sort is Projected points desc.
- Coherence: the Projected column equals the Contract Grader's
  hypothetical output for the same player and date; effective space
  recomputes when a decision resolves; the Call's sign matches the
  two-branch point deltas; fit grades match Player Fit; the Lineup Lab
  link opens the projected roster, not the current one.
- The moves ledger expands from the Moves figure and its per-move
  effects sum to the Net WAR column.
- Team-lens URLs 301 to `?team=`; deep links auto-expand and scroll.
- Nightly ingestion updates points, From moves, Moves, Net WAR, and the
  update line together; both themes AA; tsc and build green.
