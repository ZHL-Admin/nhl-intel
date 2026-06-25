# Draft Value (empirical pick-value curve + the "85%" theory test)

What is a draft pick actually *worth*, measured against what picks at that slot have historically
returned? This tool answers that empirically — fitting the value curve on our own outcomes instead of
the hand-calibrated power-law the trade engine shipped with — and uses the same data to test the folk
claim that the vast majority of picks "bust," to surface the biggest steals and busts, and to put a
draft line on every player's page.

Every number traces to a computed table; there are no hand-entered values. The realized-value currency
(pWAR) is an explicit, wide-band **estimate** for seasons before real WAR exists, and is labeled as
such everywhere it appears.

## The pipeline

```
/v1/draft/picks/{year}/all
  -> nhl_raw.raw_draft_results          (Phase A; every pick, the evaluation UNIVERSE incl. busts)
  -> nhl_raw.raw_player_draft_origin    (Phase A; each producing player's landing draftDetails)
  -> stg_draft_results                  (resolves pick -> player_id on (draft_year, overall_pick))
nhl_models.player_gar / goalie_gar (2021-26) + box production (2010+)
  -> pwar_anchor_v1.joblib              (Phase B; anchors box production -> real WAR on the overlap)
  -> nhl_models.player_pwar             (realized WAR per player-season 2010-26, back-cast pre-2021)
  -> int_draft_player_value             (per pick: realized value over a 7yr window; never-NHL = 0)
  -> nhl_models.pick_value_curve        (empirical EV by overall pick; the slot_war replacement)
  -> nhl_models.draft_value_summary     (the theory-test shares, pooled + by range)
     nhl_models.draft_value_player      (per-pick realized vs expected; the steal/bust board)
```

## Data window and the missing data

Historical draft RESULTS (who was taken at each pick) were not ingested before this tool — only
*future* pick ownership was. We ingest `/v1/draft/picks/{year}/all` for 2005–2025 (the endpoint goes
back to 1979; 2005 is the modern 7-round era and our floor). This is the complete evaluation universe.

The draft-results payload carries **no player id and no birth date** in any year, so a pick is resolved
to a `player_id` not by name (name matching cannot distinguish a true bust from a roster-coverage gap,
and produced false zeros in testing) but by the **authoritative `(draft_year, overall_pick)` join** to
each NHL player's own landing `draftDetails`. Name agreement is a validation cross-check: 99.6% overall,
100% within the evaluable classes.

## The currency: realized value (pWAR), in WAR units

Every value in this tool is in the **same WAR units as `player_gar`**, so the empirical curve drops
into the trade engine cleanly. But real WAR only exists 2021-22..2025-26, while careers we evaluate
reach back to 2010. So we **anchor**: on the overlap (single-season GAR windows where real WAR *and*
box production both exist) we fit

```
skater:  war_season ~ f(points/82, ixG/82, 5v5 TOI/GP, on-ice xGF%, games, age, F/D)
goalie:  war_season ~ f(games, save% vs league)
```

choosing per group between a **monotone LightGBM** (WAR non-decreasing in production, chances, ice time,
play-driving and games) and a **linear baseline** by season-held-out (leave-one-season-out) R², and
preferring the simpler linear model when close. Every feature is populated back to 2010-11, so the
fitted model applies to the whole window. `compute_pwar` then scores every player-season 2010-26:
`war_real` where it exists, `pwar_hat` (the anchor estimate) everywhere, `is_backcast = true` for
pre-overlap seasons, and `pwar_sd` (the anchor residual sd, inflated ×1.6 for back-cast seasons).

### Honesty about the anchor
The chosen anchor reaches **LOSO R² ≈ 0.54, Spearman ≈ 0.59 (all players) / ≈ 0.76 (regulars)** — not
the 0.9 we initially targeted. That target is **not achievable from long-history box stats**: WAR's
value also lives in RAPM **defense**, penalties, and deployment, none of which appear in the box score,
and the anchor may only use signals that reach 2010-11 so it can back-cast. We accept it as a **labeled
wide-band estimate** because:
- the pick-value curve's *shape* is dominated by the **never-NHL = 0 rate**, which is measured exactly
  (Phase A), not modeled;
- per-player pWAR noise averages out at the slot level;
- the back-cast smell test is clean — Crosby, Malkin, McDavid, MacKinnon and Draisaitl top the pre-2021
  estimates.

`pwar_hat` is shown with its band and a back-cast label; it is never presented as a precise figure.

## Realized value per pick, and the never-NHL = 0 rule

`int_draft_player_value` sums each pick's player's `pwar_hat` over their first **7 NHL-eligible
post-draft seasons** (a player drafted in year Y, season starts Y..Y+6). The evaluation universe is
**every** pick in the evaluable classes, left-joined to value: **a pick whose player never played an NHL
game has realized value 0, not missing.** The never-NHL picks are the biggest busts and stay in every
denominator — dropping them is the classic survivorship-bias error this tool exists to avoid.

`realized_value` is floored at 0 (replacement): a team plays a freely-available replacement instead of a
net-negative player, so a pick cannot be worth less than nothing. `became_regular` uses the literature's
~200 career-GP threshold. Classes **2010–2018** are fully observable under the 7-year window (≈1,900
picks, 9 complete classes); 2019+ are flagged `is_censored` and excluded from the headline (shown on the
player page and board labeled "still developing").

## The empirical pick-value curve

`fit_pick_value` summarizes, per overall pick over the evaluable classes, the realized value of the
players actually taken there: mean, median, p10/p25/p75/p90, share-never-NHL, share-became-regular, and
sample size. Because each slot has only ~9 samples, the mean and median are **loess-smoothed across pick
number** (Schuckers' approach) and the smoothed mean is forced **monotone non-increasing** (a later pick
is never worth more in expectation). Smoothing is done in **log space** — the curve spans two orders of
magnitude (≈11 WAR at #1 to ≈0 by #200) and linear loess crushes the steep top-pick premium.

### Zero-inflation (why the mean and median diverge so sharply)
Realized value per pick is a **zero-inflated, right-skewed** distribution, not a bell curve. There is a
large point mass at exactly **0** — the 43% of picks who never play an NHL game, plus a few who played
but stayed below replacement (floored to 0) — and then a thin, heavy right tail of the players who hit.
The consequences run through everything here and should be read with it in mind:
- **Mean ≫ median, especially early.** At pick #1 the mean is ~11 WAR but the median is ~9; by the
  second round the *median* is already **0** (the median pick busts) while the mean stays positive on
  the strength of the occasional star. Reporting only the mean would overstate the typical pick; only
  the median would hide the upside. We publish both, plus the never-play rate and the p10–p90 band, so
  the shape is visible rather than collapsed to one number.
- **"Below the mean" is high by construction.** With a right-skewed spike-at-zero distribution, a large
  majority of picks fall below the mean — so the headline "most picks bust" is partly an artifact of the
  distribution's shape, which is exactly why the theory test reports below-mean, below-median, and
  never-play side by side (below).
- **The smoothed mean is the right summary for the trade engine.** Because the engine nets *expected*
  value across many assets, the (zero-inclusive) mean is the unbiased quantity to carry; the median
  would systematically undervalue the option in a later pick. The band stays wide to reflect the skew.
- **The lower band is 0 almost everywhere.** The smoothed p10 sits at 0 for all but the very top picks —
  a faithful read of a distribution whose tenth percentile *is* "never played" outside the lottery.

This curve is the empirical replacement for the hand-set `slot_war` power-law in `config.FUTURES`. It is
published as the **windowed** (7-year) quantity. For the trade engine, which values picks in whole-career
WAR, `compute_futures_value` multiplies by a **career-extrapolation factor** (≈2.4×, derived from the
aging curves' post-window value tail, stored on the curve — not hardcoded). Sanity check: the
career-extrapolated #1 slot (~18 WAR) lands close to the old hand-set proxy's V(1)≈22, from completely
independent data.

This is a **performance-based** curve (what slots have *returned*), which is distinct from a **market**
curve (what GMs *pay* in trades). We measure the former; we do not claim it is the latter.

## The "85% theory" test

`run_draft_theory` compares each evaluable pick's realized value to its slot's empirical expectation and
reports, pooled and by pick range, three framings together so the slogan is not oversold:

| Range | picks | below slot MEAN | below slot MEDIAN | never NHL | became regular |
|---|---|---|---|---|---|
| 1–10 | 90 | 54% | 49% | 0% | 92% |
| 11–31 | 188 | 69% | 31% | 3% | 67% |
| Round 2 | 268 | 75% | 6% | 24% | 41% |
| Round 3–7 | 1,357 | 87% | 0% | 55% | 15% |
| **Pooled** | **1,903** | **82%** | **6%** | **43%** | **27%** |

So the honest version of "~85% of picks bust": **82% of picks return below their slot's mean** (expected
under a right-skewed distribution — a few stars pull the mean above most picks), **43% never play a
single NHL game**, and the median pick outside the first round returns essentially replacement value.
The "below MEAN" and "below MEDIAN" gap (82% vs 6%) is the right-skew itself, and is reported precisely
so the number is read correctly.

A consistency check recomputes the summary shares from the per-pick table and must match before either
table is written.

## Prior research this builds on

- **Schuckers** — games-played draft-value curve and loess smoothing across pick number.
- **Tulsky** — GM-revealed (trade-market) pick-value curve; the market vs performance distinction above.
- **Moreau / Perera / Swartz** — steals-vs-busts framing relative to slot expectation.
- **Tingling** — "no significant difference after round 3," consistent with the flat tail here.
- **Iyer** — value-available vs value-taken at each slot.

## Limitations
- pWAR before 2021-22 is an **estimate** from box production, not measured WAR (wide band, labeled).
- The anchor cannot reconstruct defensive/special-teams WAR from the box score (Spearman ~0.6); per-pick
  values are noisy and shown with bands. Slot-level conclusions are far more robust than any single pick.
- Goalie value is cruder still (GP + save% vs league against `goalie_gar`), flagged lower-confidence.
- This is a **performance retrospective**, not a market curve and not a grade of the pick *at the time*
  it was made (development, injuries and usage are not separated out).
- Pick **trades** are not in any feed, so this measures the value of the *slot*, attributed to the
  player taken — not who ended up owning the pick.
