# 14 · Contract Grader v2 · APPROVED

Supersedes 14-contract-grader.md. Comps: mockup-contract-grader.html (Grade
a contract, with The Work expanded) and mockup-contract-grader-market.html
(The Market). mockup-contract-grader-leaderboards.html is a superseded
iteration. Masthead per the Studio pattern: serif 24 title + dek, lens tabs
right: "Grade a contract" (default) · "The market" (renamed from
Leaderboards; old URL 301s). Grades follow the valence-color amendment
(11 v2 section 0). No green, no red rule, no boxed stat tiles anywhere.

## 1. Grade a contract

### 1.1 The deal panel (left, 320px)
Mode text-tabs: "Actual deal" (default; AAV and term lock to the signed
contract) and "Hypothetical" (both fields free). Player chip with headshot,
name, "pos · age · team", and a "Change ▾" combobox. Projection line
("Projected 2.9 WAR now, aging to ~2.8 by 2026-27"). AAV field with "% of
cap" beside it; term stepper with "expires {year} · ages {a-b} across the
term" beneath. Footer caption states the interaction model: the grade
updates as you change the numbers; there is no submit step. Deep links from
player profiles ("Grade it →") land here with the player and actual deal
loaded.

### 1.2 The scoreboard (one Panel)
Eyebrow "THE GRADE · {date} · {actual contract | hypothetical}"; right:
confidence dot-chip + "How we grade contracts" tooltip (method, PV
definition, band meaning). Body: grade letter Newsreader 44, valence-
colored, beside the verdict sentence: word first ("A steal." / "Fair." /
"An overpay." / "An albatross."), the percentage framing, and the surplus
embedded mid-sentence, colored. Below the hairline, four receipt lines in
two columns with valence dots; the wide-band caveat always present with a
neutral dot. Generated with template fallbacks built from the figures.

### 1.3 Figures row
Four judged figures, no boxes: Surplus PV (colored, "± band · % vs cost"
caption; tooltip term), Fair AAV this term (tooltip; caption is the gap to
the cap hit), Cap hit ("yrs · % of cap"), Fair AAV today (tooltip;
"point-in-time, this season"). Confidence lives only in the chip.

### 1.4 Paid vs worth chart
Existing chart, system inks: solid ink line = the flat cap hit (the
contractual fact); dashed blue line = projected fair value with its
`#D9E4E9` confidence ribbon (solid observed / dashed projected grammar);
blue fill at 8% where fair exceeds cap, red fill where cap exceeds fair;
NOW as a mono label on a hairline; season and age x labels in mono; $ / %
of cap as text-tabs. One caption line explains all four marks.

### 1.5 The work (collapsible, default expanded)
Three parts. (a) Where the surplus comes from: composition bars for Player
value and Cap growth summing to the surplus, plus the flat-cap caveat
caption. (b) Aging: two or three generated sentences naming the curve for
this position and the WAR slide across the term. (c) Closest market
comparables: a table of the four nearest deals by projection, position,
and age at signing: name + "pos · team · signed {year}", deal (AAV × yrs),
projection at signing, grade letter colored, surplus restated in today's
dollars; rows open that deal in the grader. Caption states the matching
basis. Comps are a served endpoint (confirmed); if a deal has fewer than
four sane comps, show what exists.

## 2. The Market

### 2.1 Filters and quick views
Quick views as text-tabs: All contracts · Steals (A grades) · Albatrosses
(D and F) · Expiring 2026 (final year). Then position tabs (All C W D G),
team select, player search. Baseline population: active contracts, min $1M
AAV, count shown in the footer. All state URL-encoded.

### 2.2 The table
Players-board rules apply: sortable columns with emphasis following the
sort (active column values 13.5 weight 500 colored; others 13 secondary);
header shows the sort arrow. Columns: Player (name + "pos · team · age"),
Grade (serif colored), AAV, Yrs, Expires, Fair AAV (tooltip term), Surplus
PV (default sort; value colored + a 64px micro-band on a fixed ±$10M
domain with a center tick, dot colored by sign). 25 rows then "Show more".

### 2.3 The expanded row
One row expands at a time (players-board dossier pattern), on a `#F7FAFB`
wash. Left: the verdict sentence (word-first, surplus embedded), two or
three valence receipts (aging, per-season shape, and the nearest comp
inline with its colored grade), then quick actions as buttons: "Open in
the grader →" (primary), "Player profile", "Build a trade around it"
(opens Trade Builder with the player pre-added to his team's side).
Right: the paid-vs-worth chart in miniature (330px) with the same grammar
and a one-line fill caption. Everything is served by the same endpoint as
the grader; nothing is recomputed differently.

## 3. Share and URL
Grader: Copy link encodes player, mode, AAV, term; share card = the
scoreboard plus the figures row. Market: URL encodes view, filters, sort,
and an expanded row id.

## 4. Data
Existing: fair AAV curves, surplus PV with bands, grades, aging
projections, cap-growth assumption. Confirmed new endpoint: nearest
comparables (projection, position, age at signing; surplus restated to
present dollars). Generated text: verdict sentences, receipts, aging
paragraph, with template fallbacks from the figures.

## 5. Mobile
Grader: deal panel stacks above the scoreboard; figures wrap 2x2; chart
compresses; The Work sections stack. Market: table drops Fair AAV and
Expires below 720 (both appear in the expanded row); expansion stacks
chart under text; filters scroll.

## 6. Acceptance
- Live recompute: changing AAV or term updates grade, sentence, receipts,
  figures, and chart with no submit; Actual mode locks fields.
- Coherence: surplus PV for a player matches the profile contract line,
  The Market row, and Trade Builder's "vs market" for the same date
  (single source; spot-check three players).
- Grade colors per the amendment in the scoreboard, comps, and Market
  rows; the two grade sizes rule holds per page.
- Chart: red fill renders when fair is below cap (verify on an albatross);
  ribbon follows the dashed line only.
- Comps: rows open the grader preloaded; degraded state below four comps.
- Market: quick-view definitions as specced; emphasis follows sort; band
  domain fixed at ±$10M; one expansion at a time; actions route correctly
  including the Trade Builder pre-add.
- Leaderboards URL 301s to The Market; both themes AA; tsc and build
  green.
