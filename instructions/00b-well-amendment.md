# 00b · System amendment: the Well

Amends 00-DESIGN-SYSTEM. Run before 01b and 19. Global change; retrofit all shipped
pages at the end of this prompt.

## Why
The v2 system removed cards and relied on hairlines for structure. On dense boards
that works; on sparse pages (offseason slates, single-game days, the home page) the
content floats on the ice canvas with no figure/ground and reads unfinished. The
owner's mock restores a content container and it is correct. We adopt it as a
first-class primitive with brand meaning: every page's content plays on one white
sheet sitting on the ice.

## The Well
- One per page. A single surface wrapping the entire page body, Sheet header
  included: background `--color-bg-surface`, border 1px `--color-border-subtle`,
  radius `--radius-rink` (24px), padding `--space-8` (`--space-5` below 640),
  margin-top `--space-6` below the nav, max-width `--container-max`, centered.
  No shadow. Implement in `PageLayout` so every page inherits it.
- The Sheet's red rule now spans the full Well width edge to edge (negative margins
  to the Well's inner edges). Still exactly one per page.
- Deepen the canvas one step so the Well reads: light `--color-bg-base` changes from
  `#F6F9FA` to `#EDF2F4`. Dark theme values are unchanged (surface on base already
  separates). Re-check AA for secondary and muted text on the new base.
- `--radius-rink` reservation now reads: the Well, plus the designated frames from
  the page docs (shot maps, style maps, the Lineup Lab board, the champion slot,
  the archetype key). Nothing else.

## Tiles (new primitive)
For tappable navigation objects: game rows, matchup features, short link lists.
- Background `--color-bg-elevated`, 1px `--color-border-subtle`, radius
  `--radius-lg` (10px), no shadow. Hover: `--crease` wash and border shifts to
  `--color-border-strong`; focus: the standard 2px blue outline. The whole tile is
  the link.
- Tiles live directly on the Well, one level deep, maximum. No tile inside a tile,
  no card chrome inside a tile. Lists longer than roughly 10 items and all data
  tables remain hairline Gamesheets, not tile stacks.

## Footer (bless what shipped)
The implemented footer is approved as a system primitive: logo dot + wordmark +
tagline left; "Data through {date} · updated nightly" in mono 11 and quiet links
(Methods, Writing) right; 1px `--color-border-subtle` top rule; sits on the canvas
below the Well, container width.

## Retrofit
Apply the Well to all 18 shipped pages via `PageLayout`, verify per page that: the
red rule touches the Well edges, no double surface appears (remove any per-section
panel backgrounds the Well now makes redundant), rink-radius frames inside the Well
keep their `--color-bg-elevated` fill so they still read against white, and dark
mode separation holds. `tsc` and build green.
