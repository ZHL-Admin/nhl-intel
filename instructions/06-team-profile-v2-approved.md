# 06 · Team Profile v2 · APPROVED

Supersedes 06-team-profile.md. The Overview tab matches the approved comp
(mockup-team-profile-overview-v2.html; v1 is a superseded iteration).
Performance, Roster, and Games are specified here without comps and follow the
same grammar; where judgment is needed, follow the approved Overview and the
player-profile handoff (08 v2) patterns. Assumes 00b, 00c, and the 08 v2
system amendments (rail retired, tooltip pattern, one-number rule, value-color
rule) have landed.

## 0. Amendments and new components ratified on this page

### 0.1 League-distribution row (new system component)
For team-context metrics, the comparison is the other 31 teams, not the team's
own history. Row anatomy: `130px label | flexible strip | 38px value`, height
27. Strip: a faint baseline hairline; the other 31 teams as 1.5x8px ticks in
`#D9E4E9` at their actual percentile positions (computed from the league table,
never decorative); this team as a 7px ink dot. Printed value is the league
rank ("26th"), tabular 12.5 weight 500. Hovering a tick names that team.

### 0.2 Team rank coloring
The value-color rule translated to a 32-team league: ranks 1 through 6 render
`--line-blue`, ranks 25 through 32 render `--line-red`, all else ink. Applies
to ranks and rank-like values only, never raw stats.

### 0.3 Insight valence dots (amends 08 v2 section 3.4)
Insight-line lead dots follow valence: `--line-red` for negative findings,
`--line-blue` for positive or neutral. This applies retroactively to the
player-profile insights; update that component when building this page.

## 1. Header

Well, nav, footer as shipped.
- Left: 64px team logo (real asset; team-color monogram circle is the comp
  stand-in), name Newsreader 34; meta line 13 secondary with a team-color dot:
  "Atlantic · Eastern · 41-31-10 · 92 PTS · 6th in division"; cap line 12.5
  muted: "Cap space $8.4M · $79.1M committed · 7 picks in 2026 · Offseason
  plan →" with cap space tabular blue weight 500 and the link opening the
  Offseason tool scoped to this team. Fallbacks: cap data missing, hide the
  line plus TODO.
- Right, right-aligned, exactly four elements: eyebrow "Power rating ·
  {season}" where Power rating is a tooltip term (definition and the net
  goals-per-game unit live in the tooltip, not the layout); the value in
  Newsreader 34 tabular; one 12px muted context line combining rank and
  stakes: in season "23rd of 32 · Playoff odds 12%" with the odds linking to
  Playoffs, after the season "23rd of 32 · 8 back of the cut"; the 84px micro
  confidence band (±1 sd of the rating).

## 2. Tabs

Overview · Performance · Roster · Games. Route changes: Identity is removed
(its content lives in Overview's How they play); "Performance / Trends"
renames to Performance; Lines becomes a lens inside Roster; Depth chart
renames to Roster; Games is new. Old URLs 301. No season select in the tabs
row; season controls sit on the modules and tabs they scope.

## 3. Overview tab (approved comp)

Order: verdict, this season, how they play, who drives it, the era.

### 3.1 Verdict
The generated team blurb as the standard pull-quote (serif italic 18, blue
left border), three sentences max, "Full team report →" expands in place.
Omit if not served.

### 3.2 This season (the lead section)
- Header: eyebrow + season select (scopes this section) left; "Why the
  rating → Performance" right.
- Figures row: six figures (value 24, rank beneath colored per 0.2): PTS,
  GF/GP, GA/GP, xGF%, HDCA/60, PP%. Adjust the set only if a served metric is
  missing; six figures, always judged.
- Two-column body: `minmax(0,1fr) 392px`, gap 48.
  Left: the team form chart: rolling 10-game power-rating percentile among
  teams, same anatomy as the player form component (25/50/75 gridlines, 50
  line stronger, blue fill above and red below clipped exactly at the line,
  endpoint dot and rank-percentile label colored by bucket; the comp's fills
  and tick positions are hand-approximated). The full legend/caption sits
  below the chart in one 11px muted line (metric, window, average line,
  color meaning, date span). Below the caption, a hairline, then the insight
  lines (valence dots per 0.3): the slump diagnosis and one steadying fact,
  as served; omit gracefully.
  Right: "The division" mini table: eyebrow + "Full standings →"; eight rows
  (`20px rank | 20px logo | name | 44px PTS | 36px GP`, height 33, hairline
  separators); the playoff cut as a dashed rule with a right-aligned mono
  "CUT" label; this team's row highlighted (`#F2F7FA` wash, weight 600); every
  row links to that team's profile. In season the table is live standings;
  the section may swap GP for a points-pace column only if served.
- In-season addition: a slim "Next up" line above the figures reusing the
  games page upcoming anatomy in compact form (opponent with logo and record,
  venue, time, split bar with favored percent), linking to the pregame view.
  Absent after the season.

### 3.3 How they play
- Header: eyebrow + season pills (last four seasons, chevron for older).
- Intro row: generated archetype sentence 14 left; legend right: "Ticks = all
  32 teams · dot = {team} · value = league rank".
- Two-column grid (1fr 1fr, gap 56). Left group "With the puck" (rush attack,
  zone entries, possession, cycle offense, finishing, chance quality). Right
  groups "Without the puck" (forecheck pressure, shot suppression, danger
  suppression), "Special teams" (power play, penalty kill), then "How they're
  built": a two-line generated roster-shape note (age and depth structure).
  Metric set follows served identity axes; keep six/five-plus-note balance.
- Every row is the league-distribution component (0.1) with rank coloring
  (0.2). Pills move the dot, the tick field, and the rank together (the
  distribution is per-season). Caption: "Rank among 32 teams · selected
  season".

### 3.4 Who drives it
Eyebrow + "Full roster →" (opens the Roster tab). A 3-column grid of six
Tiles (00b), each: 36px headshot, name 14 weight 500, "pos · age" muted;
second row: stat line tabular 12.5 secondary (skaters "82 GP · 31-49-80";
goalies "46 GS · .893 · -8.9 GSAx") and the WAR value 13.5 colored by the
player value rule. Selection: top five skaters by WAR plus the primary goalie
(most starts) regardless of sign; the honest negative card is a feature, not
a bug. Whole tile links to the player profile. Injured players carry a small
muted "IR" suffix.

### 3.5 The era (closing section)
Full-width chart, same anatomy as the player career chart: the last ten
seasons of power rating; y bands in franchise words with labels on the right
edge: CONTENDER (>= +0.45), PLAYOFF TEAM (>= +0.10), BUBBLE (>= -0.25),
REBUILD (below); thresholds configurable server-side; alternating band
washes; zero line stronger; ink line and dots, current season blue and
labeled, series minimum and best season labeled muted; mono season x labels.
Header: eyebrow + "How we rate teams" tooltip. Footer: generated reading line
in serif italic left (template fallback), "Last playoff appearance: {year} ·
Playoffs →" right (or "In the playoffs · Playoffs →" when applicable).

## 4. Performance tab (specified, no comp)

Question: why is the rating what it is, and how has the season really gone.
Sections in order; season select in the toolbar.

### 4.1 Where the rating comes from
Composition rows in the GAR-composition anatomy: 5v5 play, finishing,
goaltending, special teams as served component values (goals per game),
positive bars blue and negative red, values signed tabular; total line
"Total -0.19 net goals per game · 23rd of 32". "Full rankings →" links to
the rankings page.

### 4.2 Results versus the underlying game
Two paired gap charts reusing the player goals-versus-expected grammar:
cumulative GF versus xGF, and cumulative GA versus xGA (solid observed,
dashed expected, gap shaded blue where favorable and red where not), each
with a one-line worded delta. Together these answer "lucky or good" for both
ends of the ice.

### 4.3 Form, full size
The rolling power-rating percentile chart at full width and height, points
hoverable and clicking through to game recaps.

### 4.4 Situational profile
A compact hairline table: rows 5v5, power play, penalty kill; columns xGF/60,
xGA/60, GF/60, GA/60, each cell with its league rank in muted, rank-colored
per 0.2. Only served situations render.

### 4.5 Goaltending
One league-distribution row for team GSAx, then a small table of the team's
goalies: GS, SV%, GSAx, WAR, rank-colored, linking to profiles.

## 5. Roster tab (specified, no comp)

Question: who is on this team and how do they fit. Two lenses in the players
page lens language: "Depth chart" (default) and "Lines".

### 5.1 Depth chart lens
Positional grid of compact player cells: forwards as four rows of LW/C/RW,
defense as three pair rows, goalies as two cells; cell content: name 13.5
weight 500 linking to the profile, second line muted "AAV · WAR" with the WAR
colored by the player rule. Ordering within a column by TOI role. Injured and
scratched players in a trailing muted group. A footer line totals it: "Cap
committed $79.1M · space $8.4M · Offseason plan →". Data comes from the
existing depth chart source; cells degrade to name-only if contract or WAR is
unserved.

### 5.2 Lines lens
The existing line-combination content restyled to hairline rows: unit (three
or two names), TOI together, actual xGF%, projected xGF% (the chemistry
model), and the delta between them colored blue/red. A "How chemistry works"
tooltip carries the old footnote explanation. Rows link nowhere in v1; a
Lineup Lab link sits at the section end ("Experiment with these lines →").

## 6. Games tab (specified, no comp)

Question: the record and what is next. Season select in the toolbar; optional
Home/Away filter as text tabs.
- In season, an "Upcoming" section first: the games page anatomy B rows
  (opponent with logo and record, venue and series middle column, split bar
  and time), linking to pregame views.
- "Results": played games newest first with month divider eyebrows, reusing
  the games page compact played row plus a leading result column: `34px W/L |
  50px date | matchup | 70px status | worm`, W in ink weight 500 and L in
  secondary, score inline in the matchup, worm in the winner's color; rows
  link to recaps. 25 rows then "Show more".
- After the season this tab is Results only, with the header noting the
  final record.

## 7. Data dependencies
Power rating by season (ten years) with band thresholds. Per-metric values
for all 32 teams per season (drives every distribution strip; this is the
league table, not new modeling). Rolling team power-rating percentile series.
Rating components (4.1). Cumulative xG for and against (4.2). Situational
rates with ranks (4.4). Goalie table (4.5). Cap space, commitments, and pick
count (header, 5.1). Playoff odds in season (header). Line chemistry
projections (5.2). Generated text with omit-or-template fallbacks: team
blurb, archetype sentence, built note, era reading line, insights. Per-player
WAR and stat lines already exist.

## 8. Mobile
Below 900: header stacks; This season becomes figures, form, insights, then
the division; How they play single column; Who drives it two columns; the era
compresses like the player career chart; depth chart scrolls horizontally by
position group. Below 640: figures wrap 3x2; division rows drop GP; cards
single column; tabs scroll.

## 9. Acceptance
- Distribution strips: tick positions match the served league table for the
  selected season (spot-check three metrics against the rankings page); pills
  move ticks, dot, and rank together; hover names teams.
- Rank coloring: 1-6 blue and 25-32 red verified on both a strip value and a
  figure rank; never applied to raw values.
- Header: exactly four elements on the right; the stakes line switches
  between odds (in season) and cut gap (after) correctly; cap line hides
  cleanly without data.
- This season: the division cut line sits after the correct seed; this team's
  row highlighted and all rows navigate; the form endpoint label and color
  match the final rolling value; insight dots follow valence (and the player
  profile insight component is updated to match).
- Who drives it: top five skaters by WAR plus the most-started goalie; a
  negative goalie card renders red and still links; IR suffix verified.
- The era: bands and labels render from configurable thresholds; a team
  currently in the playoffs shows the alternate footer.
- Tabs: Identity and Lines URLs redirect; Lines lens renders inside Roster;
  Games shows upcoming plus results in season and results only after.
- Both themes AA; tsc and build green.
