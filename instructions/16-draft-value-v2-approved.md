# 16 · Draft Value v2 · APPROVED

Supersedes 16-draft-value.md. No comps: the board follows the approved
players-board and Market anatomies (07 v3, 14 v2); the pick-lookup module
and the essay are specified here and fall under the standing first-build
screenshot review. The page splits in two:
- The TOOL stays at Studio → Draft Value: a pick lookup plus the steals-
  and-busts board.
- The RESEARCH moves to Writing as an essay ("What a draft pick is really
  worth"); the old page's two headline sections, the full-size figure, the
  bust-rate table, and the methodology footnote are its content. The tool
  and essay cross-link; nothing is deleted, only rehomed.

## 1. The tool page

### 1.1 Masthead and toolbar
Serif 24 "Draft Value" + dek "What a pick is worth, and who beat their
slot". No lens tabs. Toolbar right: "Read the research →" (the essay) and
Copy link.

### 1.2 The pick lookup (one Panel)
- Left: a pick stepper/select (1-224) showing "Pick #14 · Round 1" with
  prev/next; changing it recomputes live (no submit).
- Figures row for the selected slot, judged-figures anatomy: Expected WAR
  (7-year, the curve's value; tooltip carries the fit method), Middle 80%
  (the outcome range, "0.4 to 11.2"), Never plays (%), Becomes a regular
  (%). Rates come from the slot's historical bucket.
- Equivalence lines, generated with template fallbacks, two max:
  "Worth about #28 and #45 combined" (solver: nearest pick pair summing to
  the expected value) and "The drop to #{next round marker} costs
  -{x} WAR".
- Right: the curve in miniature (~340px): fitted line solid ink, sparse-
  tail extrapolation dashed (solid observed / dashed projected grammar),
  middle-80% band `#D9E4E9`, log x with mono tick labels (1, 2, 5, 10, 31,
  62, 124, 217), the selected pick as a blue dot with its value labeled.
  No outlier annotations here; those belong to the essay figure.
- Footer caption: "This curve prices every draft-pick asset in the Trade
  Builder" with a link. Single source is an acceptance item.

### 1.3 The board (steals and busts)
Players-board rules (07 v3) apply wholesale.
- Quick views as text-tabs: Steals · Busts · All. Filters: class select
  ("Classes 2010-2018" default, individual classes selectable), position
  tabs (All F D G), team select (drafting team), player search. State
  URL-encoded.
- Columns: Player (name + "class · team · pos"), Pick (mono "#58"),
  Realized (7-year WAR), Slot exp. (tooltip term), vs Slot (default sort
  desc; signed value colored by the player value rule + a 64px micro-band
  on a fixed ±20 domain with center tick). Emphasis follows sort; Busts
  view defaults vs Slot ascending. 25 rows, then Show more.
- Expanded row (one at a time, `#F7FAFB` wash): a generated verdict
  sentence ("Went #58 in 2011; produced like a top-three pick."), the
  inverse-lookup figure "Performed like pick #{n}" (computed by mapping
  realized WAR back through the curve), a small paired band showing slot
  expectation vs realized on the same scale, and quick actions: "Player
  profile →" (primary) and, when an active contract exists, "Grade his
  deal →" (Contract Grader preloaded). Goalie rows carry the essay's
  "goalie value is cruder" caveat as a muted suffix.

## 2. The essay (Writing)
Title "What a draft pick is really worth", filed under Writing with a
Methods cross-link; the Draft Value tool links to it and the essay's
figures link back ("Look up any pick →").
- Content mapping from the old page, in order: headline one ("A top-five
  pick is worth roughly 5.1 WAR; by the third round, essentially
  replacement level") with the full-size curve as Fig. 1: system inks as
  in 1.2 plus the editorial annotations (the cliff note, "round 2
  flattens", Yakupov as a red outlier dot, Andersen blue), serif italic
  annotation voice, mono fig caption. Headline two ("43% of all picks
  never play an NHL game...") with its prose (the mean-vs-median honesty
  paragraph survives verbatim) and the pick-range table restyled to
  hairline rows (editorial tables are prose furniture, not the board
  component). The methodology footnote becomes the essay's closing
  paragraph with the Methods link.
- Prose per system rules: no bullets, serif display, pull-quote treatment
  available for the two headlines.
- The old page URL keeps the tool; an in-page anchor that previously
  pointed at the research 301s to the essay.

## 3. Data
Existing: the fitted curve with percentile bands, per-slot bucket rates,
per-player realized vs slot (2010-2018 classes). New but derived: the
equivalence solver and the inverse lookup ("performed like pick #n"),
both pure functions of the served curve; never-play and regular rates per
individual slot (currently bucketed; serve the bucket value if per-slot
is noisy). Generated verdict sentences with template fallbacks.

## 4. Mobile
Lookup stacks (stepper, figures 2x2, mini curve full width); board drops
Slot exp. below 720 (it appears in the expanded row); expansion stacks;
essay is already linear.

## 5. Acceptance
- One curve, three consumers: the lookup figures, the Trade Builder's
  pick-asset values, and the board's slot expectations all read the same
  served function (spot-check pick #14 across all three).
- Lookup recomputes live; equivalences re-solve on every pick; the mini
  curve dot tracks the stepper.
- Board: quick-view sort defaults as specced; emphasis follows sort;
  band domain fixed at ±20; expansion one-at-a-time; the Contract Grader
  action appears only with an active deal; inverse-lookup figure matches
  the curve.
- Essay: live at Writing with both cross-links; the research sections,
  figure annotations, table, and methodology text all present; old
  anchors redirect; no research content remains on the tool page.
- Goalie caveat renders on goalie rows; both themes AA; tsc and build
  green.
