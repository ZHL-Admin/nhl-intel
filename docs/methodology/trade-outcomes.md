# Trade Outcomes (who won a past trade, in realized WAR)

Who actually came out ahead in a trade, measured on what the assets went on to produce — not on what
anyone could have known at the time. This is a **retrospective on realized outcomes, not a grade of the
decision when it was made**: the information available then (health, development, cap context, the draft
that hadn't happened yet) was different, and the caveat appears on every surface.

Every value is in the same WAR units as the rest of the value stack (`mart_tradeable_assets`,
`player_pwar`), so the retrospective and the live trade engine reconcile. Numbers are wide-band
estimates; pWAR before 2021-22 is itself a back-cast (see [draft-value.md](draft-value.md)).

## The pipeline

```
Trades 2015-2026.csv  (one row per asset moved; acquiring_team received it)
  -> nhl_raw.raw_trades        (load_trades.py; source-faithful dated snapshot, idempotent)
  -> stg_trades                (typed; parsed picks; resolved_player_id for players; giving_team)
nhl_models.player_pwar + pick_value_curve (career-extrapolated) + stg_draft_results
  -> models_ml/compute_trade_outcomes.py -> nhl_models.trade_outcomes   (one row per trade+team)
```

## Data provenance

A cleaned historical-trades export, **2015-16 through 2025-26, 1,304 trades** (3,816 asset rows):
`Player` (2,178), `Draft Pick` (1,529), `Other` — all "Future Considerations" (108). 1,282 two-team
trades, 22 three-team. Draft picks are **round-only** ("YYYY Nth Round") — no overall pick and **no
original owner**. 221 picks are flagged conditional. The CSV is committed at the repo root like
`contracts.csv`; `raw_trades` is a source-faithful dated snapshot.

## The horizon (the one knob)

`REALIZED_HORIZON_YEARS = 5` (`config.TRADE_OUTCOMES`). A player's realized value is their `pwar_hat`
summed over the **5 seasons following the trade**; a drafted player's value (actual lens) is their first
**5 post-draft seasons**. Five balances "enough career to judge the trade" against censoring recent
deals. It is the single tuning constant; raising it lengthens the window and censors more recent trades.

The post-trade season is derived from the trade date: Oct–Dec → that season; Jan–Apr → the in-progress
season; May–Sep (including draft-day June) → offseason, so the player starts the next season.

## The two lenses (per asset)

**Player asset (both lenses):** realized `pwar_hat` over the 5-season window. An unmatched player, or one
who never played in our data, is **0 — not missing** (the same outcome either way: no realized WAR).

**Pick asset — SLOT lens (headline):** the empirical `pick_value_curve` value at the pick's round
midpoint (overall = (round−1)·32 + 16), **career-extrapolated** (×~2.4) to whole-career WAR, with the
curve's own p10–p90 band. This **isolates the trade decision** — it asks "what was the slot you traded
worth?", independent of who was later drafted, and it does not censor.

**Pick asset — ACTUAL lens (secondary):** the realized value of the player the pick **actually became**.
Because picks are round-only with no owner, we resolve via the **acquiring team's own selection in that
round** (`stg_draft_results`): the team that received the pick is the one most likely to have used it.
When unique, that player's first-5-season `pwar_hat` is the pick's value. This lens **conflates the trade
with the drafting** (a great pick wasted on a bust scores 0) and is explicitly secondary.

**Other ("Future Considerations"):** value **0, labeled** — a real asset we cannot value, not a missing
player. **Conditional picks** (notes flag): valued at expectation under both lenses, flagged conditional.

## Netting

Per team per trade: **net = value received − value sent**, under each lens, with bands combined in
**quadrature** (variances add — the trade engine's exact band propagation). `received` = assets the team
acquired; `sent` = assets it gave up. The giving team is the other team in a two-team trade
(deterministic); for **three-team trades** the giving team for a player is their **pre-trade NHL team**
(last game before the trade), and picks/other in three-team deals are flagged rather than mis-attributed.
N-team netting is reused as-is — three-team trades are not special-cased.

A side's **confidence** is `low` whenever it contains a pick, a Future-Considerations asset, or an
unmatched player (all wide-band proxies), else `medium`. Recent trades whose 5-season window is not yet
complete are flagged `horizon_incomplete` and excluded from the headline board by default.

## Match rates (reported, not hidden)

- **Player name → id:** 86.0% matched on normalized name + position group, 0.8% on a unique name,
  **13.2% unmatched** (players with no footprint in our roster/bio data — depth/AHL players who value to
  0 anyway). Unmatched players are kept with a null id and flagged, never dropped. Spot-checks (Taylor
  Hall, P.K. Subban, Mark Stone, Jack Eichel, Brayden Point) all resolve correctly.
- **Pick → player (actual lens):** ~40% of traded picks resolve to a unique drafted player; the rest are
  unresolved because the pick was flipped again, the acquirer made zero or multiple picks in that round,
  the team relocated (abbrev mismatch), or the draft is too recent. This is expected for a round-only
  feed and is why the actual lens is **secondary**; the slot lens (headline) does not depend on it.

Smell test (slot lens, biggest one-sided wins): CBJ on Panarin-for-Saad (+10.7), VGK on the Mark Stone
deal (+9.9), NYR on Brassard-for-Zibanejad (+8.3), NJD on Taylor-Hall-for-Larsson (+7.5), FLA on the Sam
Reinhart trade (+8.4) — all correctly attributed to the side that got the better realized player.

## Censoring

The **actual-player lens censors picks from 2019+ drafts** — those players' careers are incomplete, so
their first-5-season pWAR understates them; the row is flagged `actual_censored`. The **slot lens does
not censor** (it uses the fixed empirical curve). Separately, any trade whose own 5-season realized
window has not finished (recent deals) is flagged `horizon_incomplete` and kept out of the default
headline board so it is not topped by trades with no observed outcomes yet.

## Limitations
- Pick **ownership** and **three-team sub-deals** are not in the feed; both are assumed and flagged.
- The actual lens attributes a pick to the acquiring team's selection in that round — wrong when the pick
  was flipped; treat it as a rough, secondary read.
- Relocated franchises (ARI→UTA, ATL→WPG) can break the actual-lens draft-team match for older picks.
- Everything is realized **WAR with wide bands**; pre-2021 pWAR is an estimate. This is not advice and
  not a decision grade — only a record of how the assets turned out.

---

# The entity-first surfaces (Handoff 6)

The raw retrospective above is one row per trade-team. The product reads it as **entities and
hypotheses**, not a sorted ledger: a team or GM you want a verdict on, or a kind of trade you want to
test. Everything below composes the shipped `trade_outcomes` table (plus the GM layer); nothing is
recomputed.

## The GM attribution layer

GM history is in no feed, so it is **curated** — `gm_tenures.csv` at the repo root (the same way
contracts are sourced), one row per GM stint, loaded to `nhl_raw.raw_gm_tenures` →
`stg_gm_tenures` (typed; a singular test asserts no two tenures for one team overlap). Coverage is
2015-16 to present (~82 stints, 66 GMs); `gm_id` is stable across stints so a GM who changes teams or
returns is one entity.

**Attribution rule:** a trade side (team, date) is attributed to the tenure whose `team_abbrev` matches
and whose `[start_date, end_date]` contains the trade date (a null end = the current GM, through today).
A date within `GM_LAYER.TRANSITION_WINDOW_DAYS` (14) of a tenure boundary sets a `gm_transition` flag
("attribution uncertain near a handover"). A gap in the curated table attributes to `unknown`, flagged,
never dropped. The team abbrevs align 33/33 with the trade data, so attribution is complete.

**Honesty (also in the UI):** the GM is the decision-maker **of record**, not the sole one (AGMs,
ownership, cap, POHO all shape a deal); tenure dates are curated and approximate near handovers. This is
the same family of caveat as "a retrospective on outcomes, not a grade of the decision at the time."

## Reading the board (the balance bar)

Each trade is a balance bar over a fixed ±`TRADE_BOARD.WAR_DOMAIN` (12 WAR) domain. The tick sits at the
signed margin (the winning side's net received minus the losing side's); the shaded rectangle is the
margin's uncertainty band. The verdict is computed from the margin against the band:
- **too close** when the band straddles zero (`margin − band_hw ≤ 0 ≤ margin + band_hw`) — rendered
  neutral, never a team fill, because the trade is even *within the margin we can measure*;
- **decisive** when `|margin| − band_hw ≥ TRADE_BOARD.DECISIVE_WAR` (2.0);
- **lean** in between.
An **incomplete** trade (realized window not finished) is dashed, dimmed, sorted last, and excluded by
default — its bar reads "still maturing — through year k of 5" instead of a verdict. Unmatched players
widen the band (they do not count as zero), so a missing match can only soften a verdict, never flip it.

## Entity surfaces

- **Value map** (`/traders/value-map?kind=team|gm`): one bubble per entity, value given up (x) vs gained
  (y), a 45° break-even diagonal, bubble colored by team and sized by trade volume. Above the diagonal is
  a net winner.
- **Dossier** (`/traders/{kind}/{id}/dossier`): a team or GM's verdict header (net WAR ± band, record),
  a **cumulative-net timeline banded by regime** — by attributed GM for a team, by franchise for a GM, so
  a regime change and any slope reversal are visible — then best/worst deals and the full deal list. A GM
  who changed teams shows one continuous record across stints.

## Archetype taggability (the Patterns explorer)

`/trades/archetypes` aggregates by **only the archetypes the data can tag cleanly**: `player_for_picks`
(one side ≥ `ARCHETYPE_SHARE` = 70% of received value from players, the other from picks),
`player_for_player`, `picks_for_picks`, `blockbuster` (≥ `BLOCKBUSTER_WAR` = 8 WAR moved), and
`three_team`. **Rental and salary-dump archetypes are deliberately NOT exposed** — they require
contract-expiry-at-trade-time and cap context the trades CSV does not carry. Inventing them would be
faking a tag, so they are omitted, not guessed.
