# Trade Outcomes — UI / IA spec (Handoff 8)

The canonical reference for how the Trade Outcomes **page** is organized and rendered. For grading,
verdict math, tenure-capping, the empirical pick curve, the three-tier rule and the maturity band, see
[trade-outcomes.md](../methodology/trade-outcomes.md) (the methodology doc) — this spec does **not**
duplicate any of it. Numbers in examples are illustrative.

## 1. Identity & framing

The page is a **retrospective on how every NHL trade since 2015-16 actually turned out, in realized WAR**
— never a grade of the decision at the time. The organizing principle is **user intent, not chart type**.

The defining truth, stated plainly in the UI copy: **most trades end roughly even** (median absolute net
≈ 0.25 WAR; ~68% under 0.5 WAR; two-team netting of tenure-capped value usually lands near zero). So the
page **leads with lookup** ("my team", "settle an argument about one trade") and the **rare lopsided
exceptions**, and says "close to a coin-flip / mostly efficient" where the data shows it. We **never
manufacture a winner the band can't support**. Sentence case throughout.

## 2. Information architecture & routing

Three top-level tabs (the page-level tab bar is **chrome above the cards**, in the `PageHeader`
controls — not inside any card):

- **Trades** — default landing. `mode=trades` (or the bare base URL).
- **Teams & GMs** — `?mode=teams-gms`.
- **Patterns** — `?mode=patterns`.

Plus two drill states, reachable by route and by search:

- **Dossier** — a team or GM: `/tools/trade-outcomes/{team|gm}/{id}` (`useParams` `kind`/`id`).
- **Single-trade detail** — primarily **inline** (expand-in-place in the feed); a full page exists for
  sharing/deep-link at `/tools/trade-outcomes/trade/{trade_id}`.

URL-driven mode/selection with breadcrumbs is preserved. **Search** (team, GM, player, or trade) is on
every tab — the prominent search card on Trades, a compact search in the header on Teams & GMs and
Patterns. Selecting an entity routes to its dossier; selecting a trade opens its detail.

Base = `/tools/trade-outcomes`. `setMode('trades')` → base; other modes → `?mode=…`.

## 3. Tab 1 — Trades (the landing)  · `TradesLanding`

Two cards:

1. **Search card** — a prominent input ("Find a team, GM, player, or trade") plus a **32-team
   quick-jump** (abbrev + logo chips → dossier). Serves the dominant "my team" and "one trade" intents.
2. **Notable-trades feed card** (`TradesFeed`) — header line states the honest frame ("1,304 trades since
   2015-16. Most ended close to even — these didn't.") and a **sort control in the card header**
   (Most lopsided · Closest · Recent → `/board?sort=lopsided|closest|recent`). Body is a list of
   **inline-expandable rows**. Collapsed row: winning team over losing team, the headline asset, a small
   **tilt sparkline**, the signed net margin (mono), the verdict word when not decisive (e.g. "edge"),
   and a chevron. Expanding reveals the single-trade detail **in place** (§6) — no navigation.
   "Show more" paginates (`limit`/`offset`).

## 4. Tab 2 — Teams & GMs  · `TeamsGms`  (confidence-aware)

**One card.** The header holds the title and the **Teams | GMs** toggle (drives `kind`). **Framing leads
with uncertainty, not skill** — the intro reads "Trade records spread widely, but most of the spread is
measurement noise. Only a couple of front offices separate from even beyond their margin of error." Body =
two regions split by a divider:

- **Value map** (`ValueMap`, `/traders/value-map?kind=`): x = value given up, y = value gained, dashed
  break-even diagonal, bubble size = trades made, above-line = net positive. **Raw coordinates are kept**
  (positions are never shrunk); the σ cue is **visual emphasis only** — `clear` entities solid + labeled,
  `leans` normal, `noise` muted/low-opacity, so the separated few stand out and the cluster reads as a
  cluster. Click a bubble → dossier.
- **Ranked records** — sorted by **`rank_value`** (the confidence-aware, EB-shrunk record; ties broken on
  raw net), not raw net. Each row shows the entity, a σ cue (`clear` → "clearly separated" tag + emphasis;
  `leans` → lighter), the tilt bar, and **raw net beside a faint shrunk "adj" value** so the gap between
  raw and shrunk is visible. After the separated entities, the indistinguishable majority is **collapsed
  into a single "N within noise of even — not distinguishable from luck" cluster** rather than a false
  1..N ordering; `low_n` entities (too few settled trades) are set aside in a small note, not dropped.

A GM is followed across teams (shared `gm_id`) — one bubble/row aggregating all their franchises. A
plain-language note states the nets are settled-only and the ranking is confidence-shrunk. See the
methodology doc's "Ranking entities under uncertainty" for `z` / EB / `separation` definitions (in the
current data `tau2` clamps to 0, so `rank_value` collapses to the mean and the σ cue carries the signal).

## 5. Tab 3 — Patterns  · `ArchetypeExplorer`

**One large card.** The header holds the **archetype sub-tabs** (Player ↔ picks · Player for player ·
Picks for picks · Blockbusters · Three-team). Body, as **divider-separated regions** (not nested cards):

- **Split** — an honest headline ("Trading a star for picks is close to a coin-flip"), a 3-segment bar
  (player % / even % / picks %), and a one-line plain takeaway. Numbers from `/archetypes`.
- **Exemplars** — subtle **insets** (`.t-inset`, `--color-bg-elevated`, no border): "player side's biggest
  win" / "pick side's biggest win" / "closest call", each a **mini balance bar** (click → trade detail).
  No card-on-card.
- **Timing** — share where the acquiring side came out ahead, bucketed by timing (deadline / draft /
  offseason / in-season), as labeled bars.

## 6. Single-trade detail (inline-expand)  · `TradeBalanceCard`

When a feed row expands (and on the shareable full page), render: both hauls in two columns (player and
pick assets, each with its slot value, mono); the **balance bar** (tilt at full scale) with the three-tier
verdict and the band drawn; the asset ledger (incl. the pick→player line where present — currently not
surfaced, reserved for the lineage tool); the **GM of record** per side with the "GM of record, not sole
decision-maker" caveat; and an "open full page" link for sharing only. A pick that cannot be valued
(missing round, draft year earlier than the trade season) shows the existing **unvaluable** state,
distinct from any maturity state.

## 7. Dossier  · `TraderDossier`

A **stack of section cards** (each its own card; reads like the rest of the app):

1. **Identity & verdict** — name/logo, role and franchise(s), net WAR (mono) + band, a **separation cue**
   in the header (`clearly separated from even` / `leans` / `within noise of even`, from `z = net/band`),
   and a **prominent record-breakdown line** that frames the net as an accumulation, not domination —
   e.g. "net +23.4 (±11.6) — built from 1 decisive, 9 edges, 25 even, 6 losses". Plus the "GM of record"
   caveat and the settled/maturing denominator note.
2. **Timeline** — cumulative net trade WAR over time, **banded by regime** (by GM regime for a team, by
   franchise for a GM; band boundaries from `gm_tenures`). The line advances only on settled trades;
   still-maturing trades are plotted as **hollow dots** but don't move it.
3. **Record & deals** — two regions in one card: **record by trade partner** (matchup) and **best & worst
   deals** (subtle insets, mini bars), with a disclosure to the **full deal list** (which includes
   maturing trades, flagged). The full list renders as a flat stack of leaf cards (siblings, never nested).

## 8. Card system (the consistency rule)

- One card = one cohesive unit. The card body primitive is `.t-panel`.
- A card's own controls (sub-toggles, sub-tabs, sort) live in **its header** (`.t-cardhead`).
- The page-level tab bar is **chrome above the cards**.
- **No card-on-card.** Inside a card, sub-sections use **dividers** (`.t-divider`) or **subtle insets**
  (`.t-inset`, `--color-bg-elevated`), never another bordered card.
- Applied uniformly: Tab 1 (search card + feed card), Tab 2 (one card), Tab 3 (one card), dossier (stack
  of section cards). A `TradeBalanceCard` is itself a leaf card — rendered as a sibling, never nested.

## 9. Signature motif & visual system

- **Tilt / balance motif** at four scales (`Tilt`, constant `WAR_DOMAIN`): list-row **sparkline**, the
  **value map**, the **dossier timeline**, and the full **balance bar**. Three render states: decisive =
  solid fill in the winner's color; **edge** = faint fill in the winner's color with the band still drawn
  (directional but uncertain); **even** = centered neutral. A still-maturing trade is dashed.
- Colors via CSS variables only; team colors only via `getTeamColor`. Numbers in monospace. Reuse `Tabs`,
  `ChartPanel`, `SkeletonLoader`, `PageHeader`/`PageLayout`, `Select`, `Tooltip`, `PlayerAvatar`. Sentence
  case. Light/dark via variables (no hardcoded hex except team colors from the util).

## 10. Data contracts (what each surface consumes)

- **Feed rows** (`/board`, no toggle — shows everything, maturing sorted last): per row `trade_id`,
  `season`, `date`, the two teams (`sides`), `winner_team_id`, `margin_slot` (signed net to winner),
  `band_hw_slot`, `verdict` (decisive|edge|even), `incomplete`, `window_progress`, `realized_year`.
  Per asset (for expand): `asset_type`, `label`, `war_slot`, `unvaluable`, `retention`/`retained_pct`,
  `player_id`. The headline asset is derived client-side (top `war_slot`).
- **Value map / ranked records** (`/traders/value-map?kind=`): per entity `id`, `label`, `given_up_war`,
  `gained_war`, `net_war`, `net_band_hw`, `trade_count`, `settled_count`, `maturing_count`, `record`, plus
  the confidence-aware fields **`rank_value`, `z`, `separation` (clear|leans|noise), `low_n`**.
- **Dossier** (`/traders/{kind}/{id}/dossier`): identity, `net_war`+`net_band_hw`, `record`
  (decisive_wins/edge/even/losses), regime-banded `timeline` (each point with `incomplete`), `best`/
  `worst`, full `deal_items`, `partners`, `settled_count`, `maturing_count`.
- **Patterns** (`/archetypes`): per archetype `split`, `exemplars`, `timing`, `settled_count`,
  `maturing_count`.
- **Summary** (`/thesis-summary`): three-tier counts + percentages + `directional_*`, plus `settled_count`
  and `maturing_count`.

## 11. Show everything (lists) + settled-only (aggregates)

The **settled/maturing toggle was removed.** It forced a binary choice that hid recent trades or polluted
aggregates; honesty now lives in two places instead:

- **Lists show everything.** The feed, the dossier deal list, and search include still-maturing trades
  with **no toggle** — each maturing trade carries its inline callout ("still maturing — year _k_ of
  `REALIZED_HORIZON_YEARS`", dashed bar, widened band) and sorts last. Nothing is silently hidden.
- **Aggregates are settled-only.** Value-map nets, ranked records, dossier net/record/timeline rollups,
  archetype splits, timing, and the thesis summary are computed on **settled** trades only — preserving
  the known anti-bias (a player's value is still accruing while a pick's is already counted full). Each
  aggregate returns `settled_count`/`maturing_count`, and a plain-language note states the denominator
  ("based on trades old enough to have played out") instead of a toggle. The dossier timeline still plots
  all trades as points, but its cumulative line is settled-only. No aggregate silently includes maturing
  trades; no list silently excludes them.
