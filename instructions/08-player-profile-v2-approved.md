# 08 · Player Profile v2 · APPROVED

Supersedes 08-player-profile.md. The Overview tab matches the approved comp
(mockup-player-profile-overview-v7.html; v1 through v6 are superseded
iterations). Impact, Trends, and Game log are specified here without comps and
follow the same grammar; where judgment is needed, follow the approved Overview
patterns. Assumes 00b and 00c have landed, plus the games and players handoffs.
Do not change routing except as noted in section 2.

## 0. System amendments ratified on this page (site-wide)

### 0.1 The annotation rail is retired
The margin-notes / footnotes column is removed everywhere, on this page and any
other page or doc that specifies it (team profile, game detail, archetype
explorer). Explanations become on-demand:
- Tooltip/popover terms: 1px dotted underline in `--color-text-muted` on the
  term (blue dotted for link-styled triggers like "How we know"). Popover: a
  Panel (00c) with 12.5px Newsreader body text, max width 320, dismiss on
  click-out and Escape, focus-trapped, openable by keyboard.
- Chart captions: one line, 11px muted, directly under a chart, only where the
  chart cannot be decoded without it. Captions are chart grammar, not notes.
No page may reintroduce a notes column or numbered footnotes.

### 0.2 One headline number
The reliability-shrunk WAR is the only headline WAR anywhere on the site. The
raw pre-shrinkage figure appears in exactly one place: the Impact tab, labeled
"before shrinkage" (see 4.2). This extends the "assessed WAR" language
retirement from the players handoff.

### 0.3 Reusable vocabulary introduced here
The career chart with role bands (3.2), the range-and-dot skill track (3.3),
the rolling percentile form chart (3.4), and role-scale wording (3.2) are
system components; Team Profile and Game Detail should reuse them rather than
invent parallels.

## 1. Header

Well (00b/00c) with nav and footer as shipped. Header band inside the Well:
- Left: 64px headshot (real asset; grayscale-initial fallback), name Newsreader
  34 line-height 1.05; meta line 13 secondary with position-group dot:
  "C · EDM · Age 28 · Shoots L · {tier} · {archetype}"; contract line 12.5
  muted: "$12.5M AAV through 2026-27 · UFA 2027 · surplus +$4.2M/yr ·
  Grade it →" with the surplus tabular in `--line-blue` weight 500 and the
  link opening the Contract Grader prefilled with this player. Fallbacks: no
  contract data, hide the line; surplus not served, omit that clause and file
  the TODO. Entry-level or 35+ flags may append as plain text if served.
- Right, right-aligned: eyebrow "WAR · {season}" where WAR is a tooltip term
  (0.1); the value in Newsreader 34 tabular; "1st of 479 forwards" 12 muted;
  the 84px micro confidence band (identical component to the players board:
  hairline track, ±1 sd range, ink point, 0 to +6 domain). This number and rank
  must always equal the player's current-season entry on the Players board.

## 2. Tabs

Overview · Impact · Trends · Game log, in the approved text-tab language under
the header. Route changes: "Receipts" renames to Impact; "Context" is removed
and its content redistributes (deployment to Overview and Impact per below);
"Shot Map" is removed as a tab and folds into Trends. Old URLs 301 to the new
tabs. There is no season select in the tabs row; season controls live on the
modules and tabs they scope (3.4, 5, 6). Tab state encodes in the URL.

## 3. Overview tab (approved comp)

Order: verdict, career chart, how he plays, this season, plays like. Sections
use the standard hairline-topped grammar.

### 3.1 Verdict
Full-width pull-quote: Newsreader italic 18, line-height 1.5, 2px `--line-blue`
left border, 16px padding-left. Content: the generated scouting summary
truncated to its first three sentences; "Full scouting report →" expands the
remainder in place (height animation per the players-page exception; instant
under reduced motion). If no verdict is served, the block is omitted entirely.

### 3.2 The career · WAR by season
Full-width chart, ~228px tall at desktop.
- Series: every career season's shrunk WAR, including partial seasons. Seasons
  under 20 GP render a smaller hollow dot with a tooltip noting games played;
  never silently drop a season.
- Y domain fixed enough to show the role bands: horizontal zones with washes
  alternating `#F2F7FA`-class tints and labels on the right edge in 11px
  eyebrow style. Skater-forward thresholds: Elite >= 3.0, 1st line >= 2.0,
  2nd line >= 1.0, 3rd line >= 0.3, Depth below. Position variants (labels and
  thresholds configurable server-side): defensemen use 1ST PAIR / 2ND PAIR /
  3RD PAIR / DEPTH; goalies use ELITE STARTER / STARTER / TANDEM / BACKUP.
  The zero line renders stronger than gridlines. Left axis: 0 / +2 / +4.
- Line: 1.5px ink with 3px ink dots; current season dot 4.5px `--line-blue`
  with its value labeled above in blue; career peak and rookie season values
  labeled in muted. X labels: every season in mono 11 (thin to every other
  below 900).
- Header row: eyebrow "The career · WAR by season" left; right: confidence
  dot-chip ("High confidence") and the "How we know" tooltip trigger.
- Footer row: left, the generated one-line reading in Newsreader italic 14
  (omit if not served; a static template like "{n} seasons at {tier} level" is
  the fallback); right, the draft line: "Drafted 1st overall, 2015 ·
  +27.8 WAR vs 7.6 expected at the slot · Draft value →" linking to Draft
  Value prefilled. Undrafted players: "Undrafted · signed {year}" and no link.
- Hover on any dot shows season, WAR, GP, team in a tooltip.

### 3.3 How he plays
- Header: eyebrow left; right, season pills (text-tab style) for the last four
  seasons with a leading chevron for older seasons; current season selected by
  default. Selecting a pill moves the skill dots and printed values with a
  120ms fade and updates the URL.
- Intro row: archetype sentence 14 ("A North-South forward: ...") left; legend
  "Band = career range · dot = selected season" 11 muted right.
- Two-column grid (1fr 1fr, 56px gap). Left column group: "With the puck"
  (skater offense skills as served, e.g. skating, playmaking, shot volume,
  rush, finishing, shot danger, cycle). Right column groups: "Special teams",
  "Away from the puck", then the "Deployment" block. Group headers are 11px
  eyebrows in `--color-border-strong` tone. Skill taxonomy and grouping adapt
  per position from served axes; goalies get goalie axes (e.g. high-danger
  saves, rebound control, puck handling) under sensible groups.
- Skill row: grid `112px label | flexible track | 30px value`, height 26.
  Track: hairline; career range as a 3px `#D9E4E9` bar from career-min to
  career-max percentile; selected season as a 7px ink dot. Value: the selected
  season's percentile, 12.5 weight 500, colored by the value-color rule
  (>= 90 `--line-blue`, <= 25 `--line-red`, else ink). If per-season
  percentiles are not served, render single-dot without the range and file the
  TODO; never fabricate a range.
- Deployment block (right column, below skills): 7px stacked zone-start bar
  (OZ `--line-blue`, NZ `#C9D6DC`, DZ `#8A99A3`, max-width 340), caption line
  with the split and the plain-language read ("offense-first, 95th pctile zone
  starts"), then one inline row: TOI with rank, PP usage word, PK usage word.
- Section caption: "Percentile within forwards · printed value is the selected
  season" (position noun adapts).

### 3.4 This season
- Header: eyebrow + the season select (this is the only season control on the
  Overview; it scopes this section only) left; "Why the model believes it →
  Impact" link right.
- Figures row: six figures, value 24 weight 500 tabular, eyebrow above, rank
  below colored by the value-color rule. Skaters: GP, P, G, A, TOI/GP, xGF%.
  Goalies: GP, W, SV%, GSAx, HD SV% (if served), SO.
- Form chart (left, flexible) beside is-it-real (right, 392px):
  Form = rolling 10-game impact-score percentile among skaters. Axis gridlines
  at 25/50/75 with values labeled; the 50 line stronger and labeled "LEAGUE
  AVG"; regions between the line and the 50 line filled `--line-blue` at 8%
  above and `--line-red` at 8% below, clipped exactly at the average line (the
  comp's regions are hand-approximated); 1.5px ink line; endpoint dot in blue
  with its percentile labeled ("78TH"); mono month labels at the x extremes.
  Caption: "Impact percentile among skaters, rolling 10 games · blue above
  league average, red below" plus "Full form → Trends" right. Goalie variant:
  rolling GSAx percentile among goalies. Guard: under 15 GP in the selected
  season, replace the chart with one muted line "Not enough games yet." Per-
  game impact scores come from existing game-level data; the rolling series is
  computed, not new pipeline.
- Is it real: up to two served insight lines (7px blue dot, bold lead phrase,
  one sentence). Omit the column gracefully if none are served.

### 3.5 Plays like
Closing strip: eyebrow + "How similarity works" tooltip right; four
comparables inline (28px headshot, name 13.5 weight 500 linking to their
profile, "pos · team · {similarity}%" beneath). Hidden entirely if similarity
is not served.

## 4. Impact tab (specified, no comp)

Question: why does the model say that number. Sections in order:

### 4.1 Where the value comes from
The composition chart exactly as approved on the players board card: one row
per served GAR component, 4px bars from zero scaled to the largest absolute
component, positives blue, negatives red with red values; total line
"Total +31.0 GAR → +3.6 WAR after reliability shrinkage". Goalies use the
goalie decomposition. If components are unserved, total line only plus TODO.

### 4.2 The number, before and after
The raw-versus-shrunk story, the only home of the raw figure: two figures side
by side ("+5.2 before shrinkage" muted, "+3.6 WAR" ink weight 500), then the
full confidence band at width (0 to +6 domain, zero tick, sd range, ink point,
scale labels) with the approved plain-language caption about shrinkage and
soft ordering. A "How shrinkage works" tooltip term links the method.

### 4.3 Production and play-driving
The two standard gauges (Production percentile, Play-driving percentile) plus
the agreement sentence rendered as plain text with a blue dot ("Value and
play-driving agree..."), sourced from the served verdict components.

### 4.4 Play-driving detail
Per-situation impact as bar rows (EV offense, EV defense, power play, penalty
kill as served RAPM/on-off values), shown twice: selected season and 3-year,
as two dots on shared tracks reusing the range-and-dot grammar (labeled
legend). Only render situations actually served.

### 4.5 Deployment detail (absorbs old Context content)
The full deployment table: TOI by situation (EV/PP/PK), zone-start split with
the stacked bar, quality-of-competition and quality-of-teammates if served,
plus most-common linemates (top 3 with TOI together) if served. Anything
unserved is omitted without placeholder.

## 5. Trends tab (specified, no comp)

Question: how is he trending, short and long term. Toolbar: season select plus
a range control (Season / Last 25 / Career) where applicable.

### 5.1 Form, full size
The rolling impact percentile chart at full width and greater height, same
anatomy as 3.4, with hoverable points (each resolves to a game; clicking opens
that game's detail).

### 5.2 Finishing: goals versus expected
Cumulative goals and cumulative xG as two lines (ink and dashed muted,
following the solid-observed dashed-expected law), the gap between them shaded
blue where goals lead and red where they trail; caption states the delta in
words ("+6.2 goals above expected"). This is the "is it real" module expanded.

### 5.3 Rolling rates
Two small multiples on one row: rolling 25-game P/60 and rolling 25-game
ixG/60, each with its season-average hairline. Goalie variants: rolling SV%
and rolling GSAx/60.

### 5.4 Shot map (folded in per the approved tab decision)
Half-rink shot map for the selected season: attempt locations rendered as
density hexes or dots colored by frequency versus league (diverging blue/red),
with a toggle for goals-only. This module may use the literal rink outline
(the reserved 24px rink-radius frame applies here legitimately). Season pills
above; goalie variant is a save/against map. If coordinate data is unserved,
the module is omitted and the tab shows 5.1 through 5.3 only.

## 6. Game log tab (specified, no comp)

Question: the record. Season select in the toolbar; default current season,
newest first.
- Table anatomy per the players-board grammar (hairline rows, eyebrow headers,
  right-aligned numerics, tabular): Date (mono), Opp (logo + abbrev, home/away
  tick), Result ("W 5-2" with W/L in ink weight 500, links to game detail),
  TOI, G, A, P, S, xG, Impact (the per-game impact score, value colored by
  percentile bucket per the value-color rule). Goalies: Date, Opp, Result,
  Decision, SA, SV, SV%, GSAx, Impact.
- No sorting in v1; chronological only. 25 rows with "Show more".
- A thin month divider row groups games ("MARCH" eyebrow rows).
- Below 640: Date, Opp, Result, P (or SV%), Impact.

## 7. Data dependencies (consolidated)
Career shrunk-WAR series per season with GP (partial-season flag). Role-band
thresholds and labels per position. Per-skill percentiles per season plus
career min/max per skill. Per-game impact scores (rolling form, game log
column). Similarity comps with scores. Contract terms plus surplus per year.
Generated text: verdict (3.1), career reading line (3.2), is-it-real insights
(3.4), agreement sentence (4.3), each with omit-or-template fallbacks and
never fabricated client-side. GAR components (4.1), RAPM by situation (4.4),
deployment and linemate data (4.5), shot coordinates (5.4), draft expected
value (3.2). File a TODO for each unserved item; the specs above define the
degraded rendering.

## 8. Mobile
Below 900: header stacks (identity, then the number block left-aligned);
career chart compresses with every-other x labels and right band labels moving
to an inline legend; How he plays becomes one column (skills, then role
groups, then deployment); This season figures wrap 3x2. Below 640: tabs
scroll horizontally; skill tracks keep the 112px label but tighten gaps;
Plays like wraps to two per row. Tooltips become tap-to-open popovers.

## 9. Acceptance
- One-number rule: the header value equals the Players board entry for the
  same season; the string "+5.2" (raw) appears nowhere outside Impact 4.2 and
  is labeled "before shrinkage" there; no "assessed" strings anywhere.
- Rail retirement: the old footnote/notes component is deleted, not hidden;
  every explanatory need on the page resolves to a tooltip term or a one-line
  caption; popovers are keyboard-accessible.
- Career chart: full career renders including a sub-20-GP season as a hollow
  dot; role bands and labels verified for a forward, a defenseman, and a
  goalie; undrafted footer variant verified.
- Skill section: pills move dots and values with URL state; range never
  exceeds track; single-dot degraded mode verified; position taxonomies load
  from served axes.
- Form chart: fills clip exactly at the average line; endpoint label matches
  the final rolling value; goalie GSAx variant renders; the under-15-GP guard
  shows the empty line; points on Trends resolve to games.
- Tabs: old Receipts/Context/Shot Map URLs redirect; season selects exist only
  on This season, Trends, and Game log.
- Value-color rule applied to ranks, percentiles, and impact buckets only,
  never to raw stat values; both themes AA; tsc and build green.
