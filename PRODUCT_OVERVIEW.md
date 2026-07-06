# Product Overview: From Feature Collection to Cohesive Product

Companion to `SITE_COHESION_HANDOFF.md` (the engineering document). This file is the
argument; the handoff is the instruction set. Read this first.

---

## 1. The diagnosis

The site is a collection of excellent features that grew one at a time, each designed well
in isolation, none designed against the others. Five specific symptoms:

**1. The front door doesn't say what the product is.** The landing page is a games date
strip. That's the front door of a scores site. This product's soul is player and team
intelligence plus what-if tools; a first-time visitor (a fan, or Dom, or a front office)
currently has to discover that by accident.

**2. "Tools" is a junk drawer.** Eight tools behind one dropdown, three of them with
near-identical names (Trade Fit, Trade Builder, Trade Outcomes) and two that are secretly
the same job (Lineup Lab, Roster Builder). The repo's own inventory flags the trade naming
as a collision hazard. Users can't predict what's behind a label, which reads as hobby-site
sprawl no matter how good each tool is.

**3. Redundant and orphaned destinations.** Rankings is a whole nav item for two team
tables that belong with Teams. Offseason is a top-level nav link for a seasonal tool.
Playoffs is a page that's irrelevant ten months a year. Learn has exactly one page while
the site's single biggest differentiator, the methodology library, lives invisibly in the
repo.

**4. No connective tissue.** Pages don't share a skeleton beyond PageCard. There's no
global sense of "data through last night," no consistent receipts affordance, no editorial
layer that says what's interesting today. Every page is a destination; nothing is a
narrative.

**5. No identity.** The product has no name, no voice statement, no mark. "nhl-intel" is a
repo slug. A million-dollar product knows what it's called and what it believes, and says
so on every page.

None of this is the design system's fault. The tokens, the card grammar, the restraint:
those are good and they stay. This is information architecture, hierarchy, and identity.

---

## 2. Who it's for and the jobs it does

Two readers, established since the assessment work:

- **The fan** wants an answer in three seconds: how good is he, how's my team, was that
  trade good, what happened last night.
- **The analyst** wants the receipts: components, uncertainty, methodology, context.

The product's standing promise to both: **honest answers with visible uncertainty, and
the work shown.** Every structural decision below serves one of six jobs:

1. Tell me about a player (solved; the assessment pages are the reference implementation)
2. Tell me about a team
3. What happened / what's on tonight
4. What if (trades, lineups, contracts, draft, offseason)
5. Teach me how this works
6. What's worth my attention today (currently unserved; becomes the front door)

---

## 3. The new architecture

Six destinations. Every current capability survives; several pages merge.

| Destination | Contents | What changes |
|---|---|---|
| **Today** (`/`, new) | Editorial front page: tonight's slate with win probabilities, last night's results, team movers, luckiest/unluckiest teams, seasonal modules (playoff odds, offseason board), latest writing, studio shortcuts | New page, composed entirely from existing endpoints in v1. The repo's own Phase 6 notes already planned this; this finishes that thought |
| **Games** (`/games`) | The current games explorer, relocated; game detail unchanged | Route move only |
| **Players** (`/players`) | Index + profiles | No changes. This is the reference implementation the rest of the site is being raised to |
| **Teams** (`/teams`) | Index gains view tabs: Standings, Power ratings, Deserved standings. Profiles keep their structure | Absorbs the Rankings page (team-only content, belongs here). `/rankings` redirects |
| **Studio** (`/studio`) | The what-if suite, organized by decision: **Trades** (Build / Fit / History as modes of one workspace), **Lineups** (Lines / Roster as modes), **Contracts**, **Draft**, **Offseason** | Renames Tools; merges 8 tools into 5 decision areas via shell pages and nested routes. No tool logic is rewritten; the three trade tools become three tabs of one room |
| **Learn** (`/learn`) | Concepts hub: archetype explorer, the full methodology library rendered on-site from the repo's markdown, and Writing (the blog; the benchmark piece is post #1 and gets its stable URL here) | Turns the credibility layer from invisible to a pillar |

Cut/demoted: the Rankings nav item (merged into Teams), Offseason as top-level nav
(now a Studio area and a seasonal Today module), Playoffs as a permanent nav item (seasonal
surfacing on Today and Teams). Nothing is deleted; three nav items disappear and the
product gets simpler while doing more.

Navigation: **Today · Games · Players · Teams · Studio · Learn**, plus a global omnibox
(players and teams, `/` keyboard shortcut). Mobile gets a bottom tab bar; desktop and
mobile are equal-priority renditions of the same architecture.

---

## 4. The connective tissue

Four mechanics make it feel like one product instead of eighteen pages:

**One entity language.** A player renders the same way everywhere at three sizes (row,
card, header): name, position, team, tier badge, confidence. A team renders the same way
everywhere: identity, record, power rating with its band. The Players pages already do
this; the handoff extends the pattern to every surface that shows an entity.

**Receipts everywhere.** Every model-derived number keeps the affordances the assessment
established: visible uncertainty, a "how we measure this" link that now resolves to an
on-site Learn page instead of a tooltip dead-end.

**A freshness contract.** Every page footer states what the data runs through ("Data
through Jul 2 games · updated nightly"). Trust is a feature; a professional product tells
you how fresh it is without being asked.

**An editorial voice.** Today is the narrative layer: the site finally has an opinion
about what's interesting, generated deterministically from the models it already runs
(team trajectory movers, luck extremes, seasonal stakes), with the insight-engine feed as
the planned v2.

---

## 5. Identity proposal

**Name: Open Ice** (primary proposal). Hockey-native (open ice is time and space to make a
play) and a double meaning that IS the brand: the methods are open. The repo, the
preregistrations, the benchmark, the methodology library: this is the rare analytics site
with nothing hidden, and the name should claim that.

Alternates if Open Ice doesn't sit right: **Second Assist** (the unglamorous pass before
the goal; credit for process over results, which is the site's whole thesis) and **Full
Strength**. Owner decision D16; everything in the handoff uses a swappable BRAND_NAME
token, so the choice blocks nothing.

**Tagline:** "Hockey that shows its work."

**Mark:** the faceoff dot. A small ring-and-dot glyph, geometrically identical to the
interval-dot the site already uses to plot every value estimate. The brand mark and the
data language become the same shape, which is the kind of coherence you can't buy. Used
as favicon, wordmark accent, and loading state; never as decoration.

**Voice:** the writeup's voice, product-wide. Plain sentences. First person where a human
is talking. Uncertainty stated, never hidden. No hype words (revolutionary, powerful,
advanced). Sentence case everywhere.

**Visual system:** unchanged tokens, with the discipline the assessment work introduced
now enforced globally: color means one thing (confidence trio reserved, accent is data
ink, team colors only as identity accents), typography in one family with tabular
numerals, motion minimal.

---

## 6. What explicitly does not change

The design tokens and theme. The Players index and PlayerProfile (reference
implementations; other pages rise to them). GameDetail's content. Every model, endpoint,
and pipeline (one optional exception: the insight feed, phase-gated as Today v2). The
PageCard one-page-one-card grammar. The no-tier-sort and honesty rules.

---

## 7. Sequencing at a glance

Six phases, each independently shippable: P0 foundation (nav, routes, redirects, scaffold,
identity token), P1 Today, P2 Teams merge, P3 Studio consolidation, P4 Learn, P5 polish
and QA sweep. Full details, wireframes, and acceptance criteria live in the handoff.

## 8. Decisions requested (defaults ship if unanswered)

| # | Decision | Default |
|---|---|---|
| D16 | Product name | Open Ice |
| D17b | Mobile bottom tabs | Today, Games, Players, Teams, More |
| D18 | Insight feed (Today v2) timing | Deferred until after P5 |
| D19 | Blog hosting | On-site under /learn/writing (gives the benchmark piece its stable URL) |
| D20 | Playoffs seasonal window | Nav item visible March 1 through elimination |
