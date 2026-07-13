# Rink Theory · Design System v2 ("The Sheet")

This is the master implementation prompt. Run it first, alone, before any page prompt.
It replaces the current visual system (Inter + JetBrains Mono, rounded cards, soft
shadows, warm cream) with a new brand and token layer. Page prompts 01-18 assume this
document has been fully merged.

Scope: `frontend/src/index.css`, font setup, `NavBar.*`, `PageLayout.*`, `PageHeader.*`,
plus new shared primitives listed below. Do not restyle individual pages yet. Keep all
functionality, routes, and data flows exactly as they are. `tsc` and the production
build must pass at the end.

---

## 1. The concept

Rink Theory is a working paper about hockey, printed on ice.

Two ideas carry the whole identity:

**The rink's own graphic language.** A hockey rink is already a designed object: a pale
sheet, a red line at center, two blue lines, circles and dots. We adopt that vocabulary
as interface semantics, not decoration:

- **Blue is threshold.** In hockey you cross the blue line to enter the zone. In the UI,
  blue marks everything you can enter: links, active tabs, selected rows, focus.
- **Red is center and now.** The red line divides the sheet. In the UI, red is reserved
  for the single page-header rule (see the Sheet, section 6.2), live indicators, and
  "negative / below expected" in data.
- **The crease is protection.** The pale crease blue becomes the selection and hover
  wash.
- **Boards yellow** (the kick plate) is the caution color.

**The margin is for theory.** The site's biggest UX debt is that its metrics (WAR, xG,
GSAx, archetypes) need explanation. We turn that into the identity: a Tufte-style
annotation rail where methodology notes, definitions, and caveats live as small serif
sidenotes tied to superscript markers. Explanation becomes the signature, not a modal
buried behind an info icon.

Voice: a serious hockey journal. Serif display type for what we say, a quiet grotesque
for the machinery, numerals that behave like a box score.

## 2. What we are deliberately leaving behind

These are the tells that make the current site read as generated. Remove them
everywhere as pages migrate; the token changes below remove most automatically.

- Inter and JetBrains Mono.
- The floating rounded-card-with-soft-shadow as the default container. Structure now
  comes from whitespace, hairlines, and the grid. Shadows exist only on true overlays
  (menus, dialogs, the command palette).
- 12px radius on everything. See the radius scale: most things are 2px, a few are round,
  one signature radius is reserved.
- Font weight 700-800 as the default emphasis. Maximum UI weight is 600; display weight
  is 500. Emphasis comes from size, family, and color, not boldness.
- Filled pill chips for every label. Replaced by dot-chips (section 6.6).
- Green/red for good/bad in data. Replaced by blue/red (above/below expected), which is
  both on-brand and safer for red-green color blindness. Green survives only as a UI
  success state (toasts, confirmations).
- Purple, gradients, glassmorphism, emoji in UI. None, anywhere.

## 3. Typography

Three families, three jobs. Install via Fontsource (verify exact package names on npm
before installing; fall back to self-hosted woff2 if a package is missing):

```
npm i @fontsource-variable/newsreader @fontsource-variable/archivo @fontsource/spline-sans-mono
```

- **Newsreader (variable, opsz + ital)** is the editorial voice: page titles, section
  titles, deks, pull-quote verdict sentences, chart annotations (italic), sidenotes,
  and large "hero" numerals such as final scores and letter grades. Use the optical
  size axis: large sizes get the display cut automatically.
- **Archivo (variable, wdth + wght)** is the machine: all UI, body text, tables,
  buttons, labels. Two width settings only: `wdth 100` for UI and `wdth 92` for dense
  data tables. Eyebrow labels use `wdth 110`, uppercase, letter-spacing 0.08em.
- **Spline Sans Mono** is demoted to micro-roles only: timestamps, data-as-of notes,
  model version tags, game clocks. If mono appears in body copy or headings anywhere,
  that is a bug.

Numerals: `font-variant-numeric: tabular-nums` on every table, score, and stat readout.

Type scale (add as tokens, keep old `--text-*` names working during migration):

```css
--font-display: 'Newsreader Variable', Georgia, serif;
--font-sans: 'Archivo Variable', system-ui, sans-serif;   /* re-point existing token */
--font-mono: 'Spline Sans Mono', monospace;               /* re-point existing token */

--text-display-1: 44px;  /* line-height 1.05, letter-spacing -0.01em, weight 500 */
--text-display-2: 30px;  /* 1.1, -0.005em, 500 */
--text-title:     21px;  /* 1.2, 500, Newsreader */
--text-base:      15px;  /* 1.55, Archivo */
--text-sm:        13px;
--text-xs:        11.5px;
--text-eyebrow:   11px;  /* uppercase, 0.08em tracking, wdth 110, weight 550 */
```

## 4. Color tokens

Strategy: keep every existing custom-property NAME and change its VALUE, then add the
new brand tokens. The whole site re-skins coherently in one commit; structural work
happens per page afterward. All colors below are exact; do not substitute.

### Light theme, "day sheet" (`:root`)

```css
/* Surfaces: ice, not cream. Cool, faintly blue. */
--color-bg-base:      #F6F9FA;
--color-bg-surface:   #FFFFFF;
--color-bg-elevated:  #EDF3F5;
--color-bg-overlay:   #FFFFFF;

/* Ink */
--color-text-primary:   #101820;
--color-text-secondary: #46545E;
--color-text-muted:     #8A99A3;
--color-text-inverse:   #F6F9FA;

/* Hairlines */
--color-border:        #D8E2E6;
--color-border-subtle: #E7EEF1;
--color-border-strong: #B9C7CD;

/* Rink lines (new) */
--line-blue:       #0033A0;   /* threshold: links, active, selected, focus */
--line-blue-hover: #00287D;
--line-red:        #C8102E;   /* center/now: page rule, live, negative */
--line-red-hover:  #A00D24;
--crease:          #E3F1F9;   /* selection + hover wash */
--boards-yellow:   #B77E00;   /* caution text */
--boards-yellow-bg:#FFF4D6;

/* Re-pointed semantics */
--color-accent:        #101820;      /* primary buttons stay ink */
--color-accent-hover:  #22303A;
--color-accent-subtle: var(--crease);
--color-success:    #177245;  --color-success-bg: #E6F3EC;
--color-danger:     #C8102E;  --color-danger-bg:  #FBE9EC;
--color-warning:    #B77E00;  --color-warning-bg: #FFF4D6;
--color-live:       #C8102E;

/* Data viz */
--color-data-positive: #0033A0;   /* above expected = blue (was green) */
--color-data-negative: #C8102E;   /* below expected = red */
--color-data-neutral:  #9AA7AE;
--color-data-1: #0033A0;  --color-data-2: #C8102E;  --color-data-3: #0E7C86;
--color-data-4: #6B4FA3;  --color-data-5: #B77E00;
```

### Dark theme, "night game" (`html[data-theme="dark"]`)

```css
--color-bg-base:      #0C1218;
--color-bg-surface:   #121A22;
--color-bg-elevated:  #1A242E;
--color-bg-overlay:   #1A242E;
--color-text-primary:   #EAF2F6;
--color-text-secondary: #9FB0BA;
--color-text-muted:     #66788A;
--color-border:        #223039;
--color-border-subtle: #182129;
--color-border-strong: #33454F;
--line-blue: #5B8CFF;  --line-blue-hover: #7DA4FF;
--line-red:  #E5455A;  --line-red-hover:  #F06B7C;
--crease:    #13273A;
--boards-yellow: #E0A61E;  --boards-yellow-bg: #2A2310;
--color-accent: #EAF2F6;  --color-accent-hover: #FFFFFF;
--color-data-positive: #5B8CFF;  --color-data-negative: #E5455A;
```

Contrast floor: WCAG AA for all text roles in both themes. Team colors remain the only
permitted hardcoded hex, and only via `getTeamColor`.

## 5. Space, radius, line, shadow, motion, grid

```css
/* Radius: crisp by default, one reserved signature */
--radius-sm: 2px;      /* buttons, inputs, tags, table cells */
--radius-md: 6px;      /* menus, popovers, tooltips */
--radius-lg: 10px;     /* dialogs, command palette */
--radius-rink: 24px;   /* RESERVED: rink-cornered frames only (shot maps,
                          style maps, the archetype key). Never on buttons/cards. */
--radius-full: 9999px; /* dots, avatars, jersey-number circles only */

/* Shadows: overlays only */
--shadow-overlay: 0 12px 32px rgba(16, 24, 32, 0.14);
/* Re-point --shadow-sm/md/lg/xl to `none` except --shadow-lg: var(--shadow-overlay)
   so unmigrated components go flat immediately. */

/* Layout */
--container-max: 1120px;
--container-gutter: var(--space-6);
--nav-height: 56px;
--rail-width: 280px;   /* annotation rail, Dossier template */

/* Motion */
--ease-out: cubic-bezier(0.2, 0.8, 0.2, 1);
--dur-fast: 120ms;  --dur-med: 200ms;  --dur-draw: 260ms;
```

Spacing scale stays as-is. Grid: 12 columns inside the container. Breakpoints: 640,
900, 1200. Below 1200 the annotation rail collapses (section 6.3).

Motion policy: one orchestrated moment per route change (the Sheet's red rule draws in
left to right over `--dur-draw`, header text fades up 8px with a 60ms stagger), 120ms
ease-out on hovers, nothing else. `prefers-reduced-motion` disables all of it.

## 6. Core primitives (new shared components)

Build these in `components/common/`; page prompts reference them by name.

### 6.1 Shell (NavBar rework)
Full-bleed app chrome, not a floating card. `position: fixed; top: 0`, height
`--nav-height`, background `--color-bg-base`, 1px `--color-border-subtle` bottom
border, no radius, no shadow. Inner container: `max-width: var(--container-max)`,
gutter padding, so the wordmark aligns with page content. Scrolled state
(`.navbar--scrolled`, toggled at `scrollY > 4`): background becomes
`color-mix(in srgb, var(--color-bg-base) 88%, transparent)` with
`backdrop-filter: blur(12px)`, border strengthens to `--color-border`.
Wordmark: logo mark + "Rink Theory" set in Newsreader 500, 18px. Links: Archivo 13.5,
weight 500, `--color-text-secondary`, sentence case; active link gets
`--color-text-primary` plus a 2px `--line-blue` underline anchored to the bar's true
bottom edge (no magic offsets). Dropdown and mega menu keep their logic; restyle to
`--radius-md`, hairline border, `--shadow-overlay`, 150ms opacity + 4px translate.
Replace the inline search input with a command palette trigger: a slim bordered button
with search glyph, placeholder text, and a right-aligned `⌘K` hint (`Ctrl K` off Mac).
The palette itself: centered dialog, 560px, `--radius-lg`, `--shadow-overlay`, reusing
the existing team + player search logic, full keyboard support (open on ⌘K, arrows,
Enter, Escape, focus trap, restore focus). Mobile: search icon opens the palette
full-screen; nav links collapse to the existing drawer, offset below `--nav-height`.

### 6.2 The Sheet (PageHeader replacement)
Every page opens with the same uncarded header block: eyebrow (section name, e.g.
"Studio"), title in `--text-display-1` Newsreader, optional dek in Archivo 15
`--color-text-secondary`, then the page's controls row (tabs, filters, selects), and
finally the site's constant: **a 1px `--line-red` rule spanning the full container
width**, separating header from body. This red rule appears once per page, always in
the same place. It is the brand's handshake; nothing else on the page may be a red
horizontal rule.

### 6.3 Rail + footnotes (annotations)
`<Rail>` renders a `--rail-width` right column (Dossier template) for `<Note>` items:
13.5px Newsreader, sidenote style, optionally italic, each with a superscript marker
matching an in-content `<Ref n={x}/>`. Markers are `--line-blue`. Below 1200px the rail
collapses and each `<Ref>` becomes a tap-to-open popover carrying the same note.
Include a standard "Data as of {timestamp}" note style in Spline Sans Mono 11px.

### 6.4 Gamesheet (table system)
The site's workhorse. Header cells in eyebrow style with a 1px `--color-border-strong`
rule beneath; body rows 44px (dense variant 36px with Archivo `wdth 92` at 13px)
separated by `--color-border-subtle`; numerics right-aligned tabular; row hover =
`--crease` wash; selected row = `--crease` plus a 2px `--line-blue` left edge (crossing
the blue line). Sticky header on scroll with base background; first column may pin on
horizontal overflow. Rank movement: ▲ in `--line-blue`, ▼ in `--line-red`, tabular.
No zebra striping, no rounded row cards.

### 6.5 Tabs, buttons, inputs
Tabs: plain text on a shared hairline baseline; active tab in `--color-text-primary`
with a 2px `--line-blue` underline; counts in tabular nums. No pill tabs anywhere.
Buttons: primary = ink fill, `--radius-sm`; secondary = 1px `--color-border-strong`
outline; destructive = `--line-red` outline; quiet = blue text button. Focus for all
interactive elements: 2px `--line-blue` outline, 2px offset. Inputs and selects: 1px
hairline, `--radius-sm`, ice surface; focus swaps border to `--line-blue`.

### 6.6 Dot-chips
Replace filled pill chips with: a 7px filled circle + an eyebrow-style label, no
background. Dot color carries meaning (position group, status, archetype family).
States needing three levels use the faceoff-dot language: filled = confirmed,
half (ring with left half filled) = leaning, hollow ring = projected/unsettled.

### 6.7 Gauges (PercentileBar replacement)
A 3px hairline track with a positioned 8px dot marker and a small tabular value.
Diverging variant: track centered on zero, fill runs from center, blue right, red left.
This replaces every fat rounded percentage bar in the codebase.

### 6.8 Chart grammar (applies to every SVG/recharts surface)
Axis lines and gridlines: 1px `--color-border`; tick labels Archivo 11
`--color-text-muted`. Chart annotations, reference labels, and callouts: Newsreader
italic 13, `--color-text-secondary` (the editorial fingerprint on every graphic).
Site-wide law: **solid strokes = observed, dashed strokes = modeled or projected.**
Diverging meaning is always blue above / red below. Team colors only for team identity
in matchups. No chart background fills or shaded plot areas.

### 6.9 States
Skeletons: flat `--color-bg-elevated` blocks, no shimmer. Empty states: one Newsreader
italic line + a quiet action, never an illustration. Errors: plain statement of what
failed and the retry action. Live: 7px `--line-red` dot with a slow 2s pulse (the goal
light), disabled under reduced motion.

## 7. Page templates

Three layouts; every page prompt names one.

- **Board**: full 12-column data surface. Sheet header, then tables/boards at container
  width. No rail; annotations via footnote popovers.
- **Dossier**: reading layout. Main column 8 cols, Rail 4 cols (collapses below 1200).
  For entity profiles and explainers.
- **Bench**: workbench. Inputs panel 4-5 cols left, result canvas 7-8 cols right,
  stacking below 900. For the Studio tools.

## 8. Implementation order and guardrails

1. Fonts + full token swap in `index.css` (values only, plus new tokens). Commit; the
   site should already look different everywhere.
2. Shell: NavBar rework + command palette. `PageLayout` adopts `--container-max` and
   `--nav-height`; kill the old 1280px and 1024px hardcodes.
3. The Sheet replaces `PageHeader` (keep the component API; restyle and add the red
   rule so all pages inherit it before their own prompt runs).
4. Build Rail/Note/Ref, Gamesheet styles, tabs/buttons/inputs, dot-chips, gauges,
   chart-grammar CSS utilities, state styles.
5. Verify both themes, keyboard nav, reduced motion, mobile drawer, `tsc`, build.

Guardrails: no hardcoded colors outside `getTeamColor`; no new fonts beyond the three;
no component may add a shadow except via `--shadow-overlay`; sentence case everywhere;
do not change routes, data fetching, or component APIs beyond what is listed.

## 9. Acceptance

- Wordmark left edge aligns exactly with page titles at desktop widths, both themes.
- Exactly one red rule per page, drawn by the Sheet.
- No Inter, no JetBrains Mono, no pill chips, no card shadows anywhere in rendered CSS.
- ⌘K opens the palette from any page; palette is fully keyboard operable.
- AA contrast spot-checked for text tokens in both themes; `tsc` and build green.
