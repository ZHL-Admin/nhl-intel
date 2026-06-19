# Contract surplus (Trade tool)

**Surplus** is the dollar value of a player's *projected on-ice production* minus the *fixed cap
hit* they cost, over the remaining years of their contract, discounted to present value. A large
positive surplus is a bargain (an ELC star); a large negative surplus is an overpay (a max deal in
its aging years). It is the headline number a trade engine nets across the assets in a deal.

Every surplus number traces to a computed column — there are no hand-entered values.

## The pipeline

```
contracts.csv (dated snapshot)
  -> nhl_raw.raw_contracts        (P1, source-faithful strings, stamped as_of_date + season)
  -> contract_player_map          (P2, conservative match to canonical player_id)
  -> stg_contracts                (P3, typed: dollars -> INT64, "8 yrs" -> term_years, ...)
  -> mart_player_contracts        (P3, one row per player per snapshot, cap schedule)
  -> nhl_models.player_contract_value  (P4, projected value vs cap surplus)
```

### 1. Snapshot (raw)
The contract feed is a **dated snapshot** (currently a scraped CSV; the schema is structured so the
source can later swap to an API with no change). Every row is stamped with an `as_of_date` and a
`season`. Raw stays source-faithful — dollars are kept as strings (`"$17,000,000"`), term as
`"8 yrs"` — and all parsing is deferred to staging. Re-loading a snapshot is idempotent on
`as_of_date`.

### 2. Matching to player_id (the highest-risk step)
A wrong match silently corrupts a player's contract, so matching is **deterministic and
conservative**. In tiers: normalized name + team + position group, with **age as a tiebreaker**
(the two "Sebastian Aho"s separate by position F/D). A surname-only fallback resolves
nickname/transliteration gaps (`Nicholas -> Nick Paul`, `Sam -> Samuel Montembeault`,
`Dmitriy -> Dmitri`) but is **guarded by a matching first initial**, so a prospect is never matched
to a retired veteran who merely shares a surname (`Cole != Mike Knuble`, `Riley != Nate Thompson`).
Surname-tier matches are tagged `confidence='medium'` so they stay auditable.

Anything not resolvable to exactly one player is written to an **unmatched + ambiguous report**
(`models_ml/artifacts/contract_match_report.md`) for manual resolution via
`models_ml/data/contract_id_overrides.csv` — never guessed. On the 2026-06-18 snapshot: **786
matched / 6 ambiguous / 303 unmatched**. The unmatched are overwhelmingly signed prospects on
entry-level deals with no NHL footprint (expected — they are valued in the [futures
layer](futures-value.md)); the 6 ambiguous are prospect-vs-veteran surname collisions surfaced for
review.

### 3. Typed staging + contract mart
`stg_contracts` parses the snapshot. `remaining_years` is **season-aware** — counted from the later
of the snapshot season and the contract's own start, so a not-yet-started extension (signed now,
begins next season) reports its full term rather than term+1. `mart_player_contracts` joins the
parsed contract to the player_id, one row per (player_id, as_of_date), keeping the larger cap hit on
the rare duplicate source row. dbt tests assert cap_hit ≥ league minimum and 0 ≤ remaining_years ≤ 8.

### 4. Value projection (`compute_contract_value.py`)
For each matched player:

1. **Current WAR** from `nhl_models.player_gar` (skaters) or `goalie_gar` (goalies), season 2025-26.
2. **Age the WAR forward** each remaining season by the per-archetype aging curve
   (`nhl_models.aging_curves`, a points/82 *level* by age) used as a **ratio** vs the player's
   current age. Production-shape aging applied to value is a documented proxy.
3. **Price it** with a per-position **monotone market curve** — an isotonic regression of AAV as a
   function of WAR, fit on the league's matched contracts. This yields the AAV the open market pays
   for that production level.
4. **Surplus** `surplus_y = expected_aav_y − cap_hit`, summed over remaining years and **discounted**
   to present value at `CONTRACT_VALUE['DISCOUNT'] = 0.90`/yr.

Value is carried in **both currencies** — discounted projected WAR and discounted market dollars —
plus the surplus and a confidence band, so the [unified asset layer](#the-unified-asset-layer) can
net it against prospects and picks.

## Constants (`models_ml/config.CONTRACT_VALUE`)
| constant | value | meaning |
|---|---|---|
| `DISCOUNT` | 0.90 | present-value discount per future season (aging/injury/time-value) |
| `MARKET_MIN_N` | 60 | min sample to fit a position market curve; below it, pool all skaters |
| `REPLACEMENT_WAR` | 0.0 | GAR is above-replacement, so replacement ≈ 0 WAR |
| `PROXY_WAR_BAND` | 1.0 | ± WAR band on a floored (proxy) player — deliberately wide |
| `GROUNDED_MIN_GAMES` | 25 | current-season games to call a WAR estimate grounded/high-confidence |
| `BAND_SDS` | 1.0 | grounded band = ± this many GAR war_sd propagated through the projection |

## Uncertainty and grounding
A player with **no current-season WAR** (injured, just called up, too few games) cannot be grounded:
their production is **floored near replacement with a wide band and a `proxy` tag** — never an
invented point estimate. Grounded players get `high` (≥25 games, skater) or `medium` confidence,
with a band propagated from the GAR `war_sd` through the projection. On the latest run: 488 high /
169 medium / 73 proxy.

## Known limitations
- **Market-curve top-end compression.** Isotonic regression flattens the noisy top of the AAV-vs-WAR
  cloud, so elite production on a max contract reads as a large *negative* surplus (you pay full
  freight and the aging tail compounds over 8 years). The ranking among stars is informative; the
  magnitude at the extreme is a proxy.
- **Goalie aging.** The aging curves are skater points/82; goalie WAR is held **flat** across
  remaining years and tagged lower-confidence. Revisit when a goalie aging curve exists.
- **Single cap figure.** The snapshot carries one cap hit per contract, not a per-year cash schedule,
  so the "schedule" is the flat cap hit over remaining years. Front/back-loaded cash is not modeled.
- **Extension vs current deal.** When the snapshot row is a future extension, its AAV (not the
  player's current-season cap hit) drives surplus; the value layer uses the extension going forward.

## The unified asset layer
`mart_tradeable_assets` unions players (this doc), prospects, and picks ([futures](futures-value.md))
into one row with one interface — `asset_id, asset_type, label, org, value+band, cost, surplus,
confidence` — all in the same WAR + dollar currency. A prospect who is also a rostered player appears
once, as the player (the grounded contract value supersedes the proxy). Served via
`GET /players/{id}/contract`, `GET /assets/search`, and `GET /rankings/surplus`.
