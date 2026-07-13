# 01 · Games ("Games Explorer") v3 · APPROVED

Supersedes 01-games-explorer.md and 01b-games-explorer-v2.md. Matches the two
approved comps (sparse slate / regular season night); where this doc and older
docs disagree, this doc wins. Assumes 00b and 00c have landed. Applies to the
existing games page component and route; do not change routing or the nav.

## Page anatomy

Nav, then the Well (per 00b/00c: `--color-bg-surface`, 1px subtle border, radius
24, padding 26px 32px 32px, `--container-max`, centered) on the canvas, then the
shared footer. No red rules; the only red on this page is the live indicator.

### 1. Masthead (one row; no eyebrow, no dek)
Left: the selected date as a serif title, Newsreader 24px, line-height 1.1,
weight 500 ("Tuesday, January 12"). Right, baseline-aligned on the same row: the
date strip. Below the row: 1px `--color-border-subtle`, padding-bottom 14.
Responsive: below 1080 the strip wraps to its own full-width row beneath the
title; below 700 the strip scrolls horizontally.

### 2. Date strip
Game dates only (dates with no games do not appear). Up to 7 visible items,
Archivo 13 weight 500 `--color-text-secondary`, gap 17. The selected date is
`--color-text-primary` with a 2px `--line-blue` underline (4px padding-bottom).
The current date renders its label as "Today · Jan 12" in place of the weekday.
Chevrons page the window by its visible width; the trailing calendar affordance
opens the existing date picker. When the selected date changes, the title,
sections, and rows swap with a 120ms opacity fade only. Deep offseason default:
if no games exist within the visible window of today, land on the most recent
played slate (not an empty today).

## 3. Slate states and the switch threshold

Let n = games on the selected date.
- n >= 4: **dense list** (section grammar + three row anatomies below).
- 1 <= n <= 3: **featured treatment** (featured tiles) plus the Recent results
  backfill.
- n = 0: empty line in Newsreader italic ("No games today.") with an inline link
  to the next or most recent slate ("Next slate: Thu, Jan 14"), plus the Recent
  results backfill.

## 4. Dense list (n >= 4)

### Section grammar
Sections in order, each with a module-header eyebrow carrying its count:
"In progress · 2", "Final · 2", "Tonight · 4". Empty sections are omitted. The
In progress eyebrow is prefixed by a 7px `--line-red` dot with a slow 2s pulse
(disabled under reduced motion); this is the page's only red. The first section
has no top rule; subsequent sections get 1px `--color-border-subtle`, padding-top
20, margin-top 22. Rows stack with gap 10. Sort inside sections: live by start
time, finals by end time descending, upcoming by start time.

### Row anatomy A: live and final (shared grid)
Tile (00b treatment: `--color-bg-panel` fill, subtle border, radius 12). Grid:
`280px teams | 48px score | 100px status | minmax(0,1fr) worm | 128px right`,
column-gap 16, padding 9px 16px.
- Teams: two 22px lines, each: 20px team logo (real assets via the existing logo
  util; the comps' monogram circles are stand-ins only), name Archivo 13.5
  weight 500, record 11.5 muted ("26-12-4").
- Score: two right-aligned tabular 14.5 lines; leader/winner weight 500 ink, the
  other `--color-text-secondary`. Live ties render both secondary.
- Status: Spline Sans Mono 10.5 muted. Live: "2ND · 8:44" (period and clock).
  Final: "FINAL", or "FINAL · OT" / "FINAL · SO".
- Worm: the MiniWorm, full column width (this is deliberate; the wide track was
  an approved density fix), 28px tall, hairline midline in
  `--color-border-subtle`, single 1.5px stroke in the leading/winning team's
  `getTeamColor`, `--color-data-neutral` when tied, no fill.
- Right column: live rows show the win probability as a 56x4px two-segment
  team-color split bar (radius 2) plus "TOR 71%" tabular 12.5 weight 500
  secondary, favored team labeled. Final rows show a quiet blue "Recap" link
  with arrow instead.
- Interaction: the whole tile links to the game detail page; hover is the
  `--crease` wash.

### Row anatomy B: upcoming
Tile, height 50, padding 0 16. Grid:
`400px matchup | minmax(0,1fr) middle | 160px probability | 76px time`,
column-gap 16.
- Matchup, single line: away logo 20, name 13.5 weight 500, record 11.5 muted,
  "vs" in Spline Sans Mono 11 muted, then home logo, name, record.
- Middle column (this resolves the approved-with-note spacing item): two stacked
  12px lines, left-anchored so every row's middle text shares one left edge down
  the page (a floating centered line was the source of the odd feel). Line one:
  venue in `--color-text-secondary` ("Rogers Place, Edmonton"); line two: season
  series in `--color-text-muted` ("Season series 1-1", with the leader's abbrev
  when not tied). Fallbacks: venue missing, show series alone vertically
  centered; both missing, leave the column empty. If broadcast data is ever
  ingested it may replace line two; do not add a third line.
- Probability: the 56x4 team-color split bar plus "EDM 58%" as in anatomy A,
  from the pregame model.
- Time: tabular 13.5 weight 500, right-aligned, user's local zone ("9:00 PM").
  "TBD" in muted only when the API has no time.
- Whole tile links to the pregame/preview view of the game page.

## 5. Featured treatment (1 <= n <= 3)

Section eyebrow: "Tonight" plus context when available ("Tonight · Stanley Cup
Final"). Each game is a full-width featured tile, padding 18px 20px, flex
space-between:
- Left: matchup line at 16.5 weight 500 (logo, full team name, mono "vs", logo,
  name), then a 13px muted context line 7px below: playoff series context when
  applicable ("Game 5 · Carolina leads 3-1 · PNC Arena, Raleigh"), else venue
  plus season series.
- Right, right-aligned stack: start time in tabular 19 weight 500 ("8:00 PM ET";
  "Time TBD" muted fallback), then the split bar + favored percent, then a quiet
  blue "Pregame notes" link into the preview.
- Live and final games on a sparse slate use anatomy A rows, not featured tiles;
  featured is for upcoming games only. (A sparse live game may be revisited
  later; do not invent a featured-live variant now.)

## 6. Recent results backfill (n <= 3 only)

Below the slate, a hairline-topped section: eyebrow "Recent results", right link
"Full schedule" (opens the calendar/most recent slate). Up to 3 most recent
played games from prior dates, compact single-line tile rows, height 54, grid:
`50px date | 62px tag | minmax(0,1fr) matchup | 70px status | 150px+ worm`.
Date in mono 11 uppercase muted ("JUN 14"); tag shows the series game number
during a playoff series ("Game 4"), otherwise the column is omitted and the
matchup widens; matchup inline: dot-free (logo 20) abbrev 13.5 weight 500 with
winner's score weight 500 ink, loser secondary, middot separator; status mono
("FINAL", "FINAL · OT"); worm as anatomy A but at this row's width. Rows link to
recaps. During a playoff round between the same teams this section naturally
reads as the series history; keep the generic label.

## 7. Data dependencies
- Records with each team (standings source); venue and start times from the
  games feed; season series from the existing game-context staging data.
- Pregame win probability from the matchup preview endpoint; live win
  probability from the live model feed. If live probability is not served,
  live rows drop the split bar and show status only; file the backend TODO.
- Worm data from the existing xG timeline source that powers MiniWorm.

## 8. States, mobile, misc
- Loading: flat skeleton tiles matching row heights per section; no shimmer.
- Below 900: anatomy A hides the worm column; anatomy B hides the middle
  column. Below 640: anatomy A restacks (teams+scores full width, then a second
  line with status and probability/recap); anatomy B restacks to matchup line
  then time+probability line; featured tiles stack vertically (matchup block,
  then time/probability/link row).
- All numerals tabular. Team colors and logos only via the existing utils. No
  new tokens or fonts. The 120ms fade is the only motion besides the live pulse.

## 9. Acceptance
- Threshold verified: a 1-game date renders featured + backfill; an 8-game date
  renders the three-section dense list with no backfill; a 0-game date renders
  the empty line + backfill and the strip lands on a real slate by default.
- Masthead is one row at 1440 with the strip right-aligned; wraps below 1080;
  scrolls below 700.
- Upcoming middle column: left edges align across all rows; venue over series;
  fallbacks verified for missing venue and missing both.
- Exactly one red element per page (the live dot), pulsing only when a live
  section exists, static under reduced motion.
- Worms span their full column at 1440 and drop cleanly below 900; leader color
  and tied-neutral verified live.
- Split bars sum to 100 percent and match the labeled favorite; "TBD" only when
  no time exists.
- Keyboard order: masthead, strip dates, calendar, then tiles top to bottom;
  focus ring visible on tiles; both themes AA; tsc and build green.
