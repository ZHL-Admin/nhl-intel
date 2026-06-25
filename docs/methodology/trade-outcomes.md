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
