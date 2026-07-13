# Rink Theory · Redesign handoff

Nineteen documents: one design system, eighteen pages. Written to be run one at a
time as prompts in Claude Code (or handed to any developer), in this order:

1. `00-DESIGN-SYSTEM.md`, alone, on its own branch. Everything else assumes it.
2. High-traffic spine: 01 Games Explorer, 02 Game Detail, 08 Player Profile,
   06 Team Profile. These four are most of the traffic and establish every pattern.
3. Boards: 03 Rankings, 05 Teams, 07 Players, 10 Offseason.
4. Studio: 09 Hub, 11 Lineup Lab, 12 Player Fit, 13 Trade Builder,
   14 Contract Grader, 15 Roster Builder, 16 Draft Value, 17 Trade Outcomes.
5. Learn: 18 Archetype Explorer.

## The concept in one paragraph

Rink Theory is a working paper about hockey, printed on ice. The rink's own graphic
language becomes the interface semantics: blue is threshold (links, active, selected,
focus), red is center and now (one red rule per page, live, negative), the crease is
the selection wash, boards yellow is caution. The margin is for theory: an annotation
rail carries methodology as serif sidenotes, turning the site's hardest UX problem
(opaque metrics) into its identity. Type: Newsreader for the voice, Archivo for the
machine, Spline Sans Mono demoted to micro-labels. Structure from whitespace and
hairlines, not cards; shadows only on overlays; solid means observed and dashed means
projected, everywhere.

## Working notes

- Each page doc lists a Template (Board, Dossier, or Bench, defined in 00), specific
  directives, one signature moment, an explicit remove list, and acceptance checks.
- The 2px-radius controls, dot-chips, gauges, Gamesheet, Sheet, and Rail are shared
  primitives from 00; page docs reference them by name rather than respecifying.
- `--radius-rink` (24px) is reserved and rationed: shot maps (02, 08), style maps
  (05, 17), the Lineup Lab board (11), the champion slot (04), the archetype key (18).
  If a surface is not listed, it does not get the radius.
- Nav labels in the current build (Today, Studio) postdate the code snapshot these
  docs were written against (Games, Tools). The docs use section eyebrows matching
  the live labels; reconcile link text in the shell during 00.
- Content and microcopy are intentionally out of scope except where a line is needed
  for layout (empty states, deks). Run a separate copy pass after styling lands.
- Verify Fontsource package names on npm before installing; self-host woff2 if any
  are missing.

## Lineage / supersessions
- The Well padding is a global system ruling from 00b (`--space-8`, i.e. 32px, `--space-5`
  below 640), applied once in `PageLayout`. Per-page Well-padding overrides are the exact
  inconsistency the Well was adopted to remove. Doc 19's "padding 28px 32px 32px" is therefore
  **superseded**; the Well stays a uniform 32px on every page, Home included.
