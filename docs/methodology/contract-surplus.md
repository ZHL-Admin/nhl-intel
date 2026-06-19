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
3. **Price it** with a per-position **monotone market curve** (see below), fit in **cap-share** —
   the expected share of the cap that production commands.
4. **Surplus per season** `surplus_y = expected_cap_share_y − actual_cap_share_y`, where
   `actual_cap_share_y = cap_hit / cap_y` and `cap_y` is the cap **projected forward** to season *y*
   (see [Cost in cap share](#cost-in-cap-share-and-the-forward-cap)). Discounted to present value at
   `CONTRACT_VALUE['DISCOUNT'] = 0.90`/yr and summed.

Value is carried in **both currencies** — discounted projected WAR and discounted market dollars —
plus the surplus and a confidence band, so the [unified asset layer](#the-two-axis-asset-layer) can
net it against prospects and picks.

### Cost in cap share, and the forward cap
Raw dollars are the wrong unit for cost: a $10M cap hit means something very different against an
$88M cap than against a $113M one. So cost is measured as a **share of the cap**, which is
**era-neutral**, and the cap is **projected forward across each contract's remaining years**:

- The market curve's target is `cap_hit / current-season cap`, so the benchmark is
  `expected_cap_share(value)` — independent of the dollar era.
- For each remaining season the cap ceiling is taken from the announced NHL/NHLPA figures
  (`config.CAP_UPPER_LIMIT_BY_SEASON`, through 2027-28), and **beyond the announced window** each
  later season is the prior one × `(1 + CAP_GROWTH_BEYOND_KNOWN)`. The growth rate (0.05) is the
  **single most important assumption for long deals** and is deliberately adjustable — a moderate
  default, not the post-pandemic 8–9%/yr catch-up.
- The flat dollar cap hit therefore becomes a **declining share** of a rising cap. For Kaprizov's
  $17M deal the actual cap share falls 16.4% → 11.2% across the term. So a long deal looks **modestly
  better on the cost side** once the cap is projected forward, while short deals barely move (a
  2-year veteran shifts ≈ +$0.6M). The comparison is done entirely in cap share, then **dollarized
  per season by that season's projected cap** for display; both the cap-share surplus and the
  dollar surplus are stored, alongside a **flat-cap baseline** (cap frozen at current) and the
  **per-year cap-share schedule** so the decline is inspectable. The time-preference discount is
  applied **separately** from cap growth — both effects apply.

The talent axis (projected value in WAR) is unchanged by this; only the cost/surplus side moved.

### The market curve (why not isotonic)
The first version fit AAV-as-a-function-of-WAR with **isotonic regression**. Isotonic is monotone but
its terminal block is a flat step: with few elite contracts, it pooled the sparse top into a
**plateau ≈ $9M**, well below what elite production actually commands. Surplus is `expected_aav −
cap_hit`, so every max-deal star fell out as a multi-million *false negative* (Kaprizov read ≈ −$47M).
That is a calibration artifact, not a real read, and a trade engine would net those magnitudes.

The curve is now a smooth, monotone form that **keeps rising at the top** instead of plateauing. It
is fit in **cap-share** (the target is `cap_hit / current cap`, not raw AAV), which is what makes the
benchmark era-neutral; expected AAV for display is recovered as `expected_cap_share × cap_y`.

- **log(cap-share) is linear in WAR** (`log(share) = a + b·WAR`, `b > 0`), fit per position group by
  OLS — so the top end is *multiplicative* and never flattens.
- The intercept is shifted to the **upper-mid conditional quantile** (`MARKET_QUANTILE = 0.65`), not
  the mean. Contracts price peak and reputation that a single noisy season of WAR understates, and the
  high-WAR cohort is diluted by ELC/bridge deals, so the conditional *mean* reads genuine stars as
  overpaid. The 0.65 quantile is "the going rate a well-paid player at this production commands."
- A smooth **soft-cap** asymptotes the very top to the CBA maximum-contract **share** (≈ 20% of the
  cap, taken as `1.05 ×` the max observed cap share). It keeps a positive slope everywhere — a real
  economic bound, not a fitting plateau.

The job asserts and prints the acceptance checks: the curve is monotone and rising at the top for
F/D/G; top-decile production prices within a realistic band of observed elite AAVs (F ×0.94, D ×0.99
— tracking them, not flattening below); and the three sample stars read modest per-year surplus
(Kaprizov −$2.9M, Draisaitl +$2.3M, Eichel +$1.9M) rather than multi-million negative. The **top
decile of production is widened-band and capped at `medium` confidence** — comparables are sparse
there, so the price is inherently lower-confidence (`TOP_DECILE_BAND_MULT = 1.6`).

## Constants (`models_ml/config.CONTRACT_VALUE`)
| constant | value | meaning |
|---|---|---|
| `DISCOUNT` | 0.90 | present-value discount per future season (aging/injury/time-value) |
| `MARKET_MIN_N` | 60 | min sample to fit a position market curve; below it, pool all skaters |
| `MARKET_QUANTILE` | 0.65 | conditional quantile of cap-share the curve targets (the going rate, not the mean) |
| `MARKET_CEIL_MULT` | 1.05 | soft-cap ceiling = this × max observed cap share (the CBA max-contract bound) |
| `MARKET_KNEE_FRAC` | 0.75 | soft-cap bends in from this × ceiling |
| `TOP_DECILE_BAND_MULT` | 1.6 | widen the band (and cap confidence at medium) for top-decile production |
| `REPLACEMENT_WAR` | 0.0 | GAR is above-replacement, so replacement ≈ 0 WAR |
| `PROXY_WAR_BAND` | 1.0 | ± WAR band on a floored (proxy) player — deliberately wide |
| `GROUNDED_MIN_GAMES` | 25 | current-season games to call a WAR estimate grounded/high-confidence |
| `BAND_SDS` | 1.0 | grounded band = ± this many GAR war_sd propagated through the projection |

Cap projection (module-level in `config`): `CAP_UPPER_LIMIT_BY_SEASON` holds the announced NHL/NHLPA
upper limits ($88.0M → $95.5M → $104.0M → $113.5M for 2024-25 … 2027-28); `CAP_GROWTH_BEYOND_KNOWN =
0.05` projects each later season. **The growth rate is the key long-deal lever** — raise it and long
deals look better still; it is intentionally adjustable.

## Uncertainty and grounding
A player with **no current-season WAR** (injured, just called up, too few games) cannot be grounded:
their production is **floored near replacement with a wide band and a `proxy` tag** — never an
invented point estimate. Grounded players get `high` (≥25 games, skater) or `medium` confidence,
with a band propagated from the GAR `war_sd` through the projection (widened in the top decile). On
the latest run: 427 high / 230 medium / 73 proxy.

## Known limitations
- **The top decile is lower-confidence by nature.** Even with the recalibrated curve, elite
  production has few comparables, so its price is the least certain part of the curve — which is why
  the band is widened there and confidence is capped at `medium`. Read the band, not the point.
- **Quantile target is a modeling choice.** Pricing at the 0.65 conditional quantile (not the mean)
  is what lets genuine stars read fairly; it is a deliberate, documented bias toward "what the market
  pays a well-paid player," chosen so the sample stars and the mid/low range both stay sane.
- **Forward cap growth is an assumption.** Past the announced window (2027-28) the cap is projected at
  a flat 5%/yr. For an 8-year deal most seasons fall in that projected region, so the growth rate
  materially moves long-deal surplus (it is the dominant long-deal lever). It is set moderate and left
  adjustable; revisit when the next CBA's cap trajectory is known.
- **Goalie aging.** The aging curves are skater points/82; goalie WAR is held **flat** across
  remaining years and tagged lower-confidence. Revisit when a goalie aging curve exists.
- **Single cap figure.** The snapshot carries one cap hit per contract, not a per-year cash schedule,
  so the cap-share schedule varies only because the cap rises (the dollar cap hit is flat). Front/
  back-loaded cash is not modeled.
- **Extension vs current deal.** When the snapshot row is a future extension, its AAV (not the
  player's current-season cap hit) drives surplus; the value layer uses the extension going forward.

## The two-axis asset layer
Surplus alone is the wrong single currency for a trade: a **fairly paid star** has near-zero surplus
but enormous talent value, while an **overpaid veteran** and a **cheap pick** can show similar surplus
for opposite reasons. So `mart_tradeable_assets` carries value and cost as **two separate axes**, for
players, prospects, and picks alike:

- **Talent** — projected on-ice value over the control window (`value_war` / `value_dollars`, with a
  band). What the asset is *worth*. `value_war` is era-neutral; `value_dollars` is cap-aware (it grows
  with the projected cap over a long deal).
- **Cost** — `cap_hit`, `remaining_years`, and the discounted `cost_dollars`, measured against the
  **cap share** the cap hit occupies each season (declining as the cap rises). What it is *owed*
  (≈ 0 for prospects and picks).
- **Surplus** — value minus cost, with its band. Kept available, but never the only thing exposed.

Worked examples (latest run):

| asset | talent value | cost | surplus | reads as |
|---|---|---|---|---|
| Mitch Marner | $86M (53–110) | $12.0M × 8y | +$18M | elite talent, modest surplus |
| Macklin Celebrini | $35M | $1.0M × 2y | +$33M | underpaid young star |
| Jonathan Huberdeau | $22M | $10.5M × 6y | −$27M | overpaid veteran |
| Jake O'Brien (prospect) | $19M (8–35) | ≈ $0 | +$19M | proxy, wide band |
| 2026 R1 (EDM) pick | $11M (5–22) | $0 | +$11M | proxy, wide band |

(The talent and surplus dollars are now larger than the pre-cap-pass figures: a long deal's
production is worth more in a higher-cap future, and its flat cap hit is a shrinking share of it.)

The unified mart unions all three sources into one interface — `asset_id, asset_type, label, org,
talent value + band, cap_hit/remaining_years/cost, surplus + band, confidence` — all in the same WAR +
dollar currency. A prospect who is also a rostered player appears once, as the player (the grounded
contract value supersedes the proxy). Served via `GET /players/{id}/contract`, `GET /assets/search`,
`GET /rankings/surplus` (efficiency axis), and `GET /rankings/talent` (talent axis).
