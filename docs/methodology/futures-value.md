# Futures value: prospects and draft picks (Trade tool)

Prospects and draft picks are valued in the **same WAR + dollar currency** as player
[contracts](contract-surplus.md), so a trade engine can net a prospect or a pick against a rostered
player cleanly. Unlike contract surplus, these are explicit **proxies**: every value is carried with
a **wide band** and a `proxy` confidence tag, and is never shown as a bare precise number.

## The pipeline

```
/v1/prospects/{TEAM}  -> nhl_raw.raw_prospects   (P5, org lists + draft pedigree, stamped snapshot)
own-picks assumption  -> nhl_raw.raw_draft_picks (P5, future picks, ownership in a column)
  -> stg_prospects / stg_draft_picks             (P5, typed, season-aware)
  -> nhl_models.futures_value                    (P6, slot-curve proxy value, WAR + dollars)
```

### Inventory (P5, `scripts/ingest_futures.py`)
- **Prospects** are bounded to each org's **published prospect list** (`/v1/prospects/{TEAM}`, the 32
  current franchises) — we never invent prospects. Each is enriched with **draft pedigree** (overall
  pick) pulled from the player landing payload, keyed by player id (no fragile name matching). On the
  2026-06-18 snapshot: 600 prospects, 555 drafted / 45 undrafted free-agent prospects.
- **Draft picks** are future picks (2026–2028 × 7 rounds × 32 teams = 672) as selectable assets.

### The slot curve (P6, `compute_futures_value.py`)
The spine is **expected career WAR-above-replacement as a function of overall draft pick** — a
power-law proxy `V(p) = a / (p + c)^b`, floored near replacement, calibrated to public draft-value
research: round-1 picks dominate, value decays steeply, late picks regress to replacement. The curve
is an **expectation over all picks at that slot**, so busts are already priced in.

- **Prospect value** = `slot(draft_overall)` (undrafted → floored near replacement), times a
  development decay if the prospect is lingering past NHL-ready age without an NHL footprint, times a
  time-value discount over the seasons until they are NHL-ready.
- **Pick value** = `slot(round midpoint)` discounted over `years_out + draft-to-NHL`. The
  within-round slot spread (a strong team picks late, a weak team early) is absorbed into the wide
  band rather than modeled per team.

Value is expressed in **WAR and dollars** (`DOLLARS_PER_WAR`, a proxy market price of a win). Cost is
≈ 0 — the appeal of futures is that they are cheap — so surplus ≈ value.

## Constants (`models_ml/config.FUTURES`)
| constant | value | meaning |
|---|---|---|
| `SLOT_A`, `SLOT_C`, `SLOT_B` | 100, 4, 0.95 | slot curve `V(p)=a/(p+c)^b` (V(1)≈22, V(31)≈3.5, V(100)≈1.2 career WAR) |
| `SLOT_FLOOR_WAR` | 0.3 | never below ~replacement |
| `UNDRAFTED_WAR` | 0.4 | floor for an undrafted org prospect |
| `DISCOUNT` | 0.90 | per-season time-value discount |
| `NHL_READY_AGE` | 23 | time-to-NHL ≈ max(0, this − age) |
| `DRAFT_TO_NHL_YEARS` | 3 | a not-yet-drafted future pick adds ~3 dev years on top of years_out |
| `DEV_DECAY_PER_YEAR` | 0.85 | decay for a prospect past NHL-ready age with no footprint |
| `DOLLARS_PER_WAR` | 3,000,000 | proxy market price of a win (cap era) |
| `BAND_LO`, `BAND_HI` | 0.45, 1.9 | wide multiplicative band on every futures estimate |

## Uncertainty
Every futures value is a proxy with a **wide multiplicative band** (≈ 0.45×–1.9× the point estimate)
and confidence `proxy`. These are deliberately humble: a slot curve cannot know which #10 pick
becomes a star and which busts.

## Known gaps (flagged, not hidden)
- **Pick ownership is assumed.** Pick trades are not in any feed we have, so **every pick is assumed
  to belong to its original team** (`ownership_source='assumed_own'`) unless reassigned by hand in
  `models_ml/data/draft_pick_overrides.csv`. The assumption rides in a column and a per-row
  `ownership_note` ("Assumed own pick — verify before relying"), never baked in silently. This is the
  single biggest caveat of the pick layer.
- **Prospect coverage** is exactly each org's published list — players outside it (deep org
  prospects, recent signings not yet listed) are absent until the list updates.
- **Within-round pick slot** is the round midpoint; the real pick number (driven by where the owning
  team finishes) is absorbed into the band, not projected from standings.
- **Slot curve is parametric**, calibrated to public research rather than re-derived from in-house
  career WAR (the model layer does not hold enough retired-player career WAR to fit it cleanly). It is
  a transparent proxy, which is why bands are wide and the tag is `proxy`.

## The unified asset layer
Prospects and picks join players in `mart_tradeable_assets` (see [contract surplus](contract-surplus.md)).
A prospect who is also a rostered player is deduped to the player row, so the grounded contract value
supersedes the proxy. Searchable across all three asset types via `GET /assets/search`.
