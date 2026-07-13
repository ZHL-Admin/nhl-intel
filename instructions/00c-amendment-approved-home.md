# 00c · System amendment: ratified by the approved Home comp

Amends 00 and 00b. Run before 19-home-v3. These changes are global; the home page
depends on them but they apply site-wide.

## 1. The red rule is removed, everywhere
The Sheet's 1px red rule is deleted as a concept. The Sheet keeps its divider, now
1px `--color-border-subtle`, full Well width. Remove the rule from the Sheet
component and verify no page renders a red horizontal rule. `--line-red` keeps only
its functional roles: negative and below-expected in data, live indicators, and
destructive actions. Where the docs justify visual elements as rink imagery
("center line", "faceoff dot", "crossing the blue line"), treat that language as
retired; the palette and the blue/red data convention stay because they are
functional conventions, not costume. No element may exist on a page purely to
evoke a rink.

## 2. Panel (new primitive)
A quiet grouped-module container for side rails and similar secondary regions.
- Token: `--color-bg-panel`, light `#F7FAFB`, dark: reuse `--color-bg-elevated`.
- Style: background `--color-bg-panel`, 1px `--color-border-subtle`, radius 12px,
  padding 15px 17px. No shadow. Not nestable; no Panel inside a Panel or Tile.
- Distinct from Tiles (00b): Tiles are single tappable objects; Panels group a
  module (header, rows, footer link) whose rows may be individually interactive.
- Internal conventions: module header row (eyebrow left, quiet blue link right,
  margin-bottom 11), rows separated by `--color-border-subtle` hairlines.

## 3. Context strip (Sheet variant for utility mastheads)
A slim single-line replacement for the eyebrow/title/dek Sheet on pages where a
large title wastes space (currently: Home only). Left: primary context in Archivo
13.5 weight 500 ink. Right: secondary context in 13 muted. Baseline aligned,
padding-bottom 14, bottom border 1px `--color-border-subtle`. Other pages keep the
standard Sheet (with the neutral rule per item 1).

## 4. Verdict rendering note
The home Ledger renders trade verdicts as eyebrow-style text ("Edge DET"), not the
filled/half/hollow dot glyph. The dot language remains specced only inside Trade
Outcomes (doc 17) and will be re-reviewed when that page enters the mockup loop.

## Acceptance
Grep confirms no `--line-red` horizontal rules outside data/live/destructive uses;
Panel token present in both themes and AA-checked; existing pages render with the
neutral Sheet rule; tsc and build green.
