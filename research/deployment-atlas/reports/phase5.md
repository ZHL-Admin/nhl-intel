# Phase 5 — Pre-registered validation: does context correction travel?

Cohorts, metrics, and the decision rule were fixed **before** results were seen.

## DECISION (per the fixed rule): **INVESTIGATE**

The best leakage-clean adjusted predictor (b2, the Atlas variant RAPM) improves
mover MAE over raw (a) by **+3.70%** with a bootstrap CI of **[+2.01%, +5.38%]
(excludes zero)**. That is a real, significant improvement — context correction
**does travel** — but it is **below the 5% SHIP threshold**. Per the pre-registered
rule (SHIP ≥5% & CI excludes zero; INVESTIGATE if 0–5% or CI spans zero; KILL if
≤0): **the improvement is 0–5% → INVESTIGATE.** The Atlas ships as descriptive
data; adjusted ratings are held.

---

## 5.0 Coverage
Atlas variant RAPM extended to all 16 seasons 2010-11→2025-26 (same spec/seed);
**λ = 46,416 chosen for every added season** (5-fold game-grouped CV). Predictor b2
exists for season S of every evaluation pair.

## 5.1 Cohorts (movers = primary team changed; 400+ 5v5 min in S and S+1, prorated)

| pair | movers | stayers | | pair | movers | stayers |
|---|---|---|---|---|---|---|
| 2010-11→2011-12 | 138 | 343 | | 2018-19→2019-20 | 114 | 402 |
| 2011-12→2012-13 | 94 | 376 | | 2019-20→2020-21 | 112 | 400 |
| 2012-13→2013-14 | 92 | 382 | | 2020-21→2021-22 | 135 | 390 |
| 2013-14→2014-15 | 119 | 379 | | 2021-22→2022-23 | 112 | 407 |
| 2014-15→2015-16 | 99 | 386 | | 2022-23→2023-24 | 124 | 401 |
| 2015-16→2016-17 | 89 | 383 | | 2023-24→2024-25 | 148 | 382 |
| 2016-17→2017-18 | 99 | 392 | | 2024-25→2025-26 | 135 | 395 |
| 2017-18→2018-19 | 95 | 415 | | **total** | **~1,705** | **~5,833** |

Minutes bar prorated by scheduled-games ratio: 2012-13 → 234 min, 2019-20 → 341,
2020-21 → 273. The 2019-20→2020-21 pair is included (noisy — rules/divisions
changed); it does not solely drive the decision.

## 5.2 / 5.3 Predictors (LOSO: fit on stayers of other pairs, evaluate on held-out movers)

Target = season S+1 5v5 on-ice xG share (secondary: GF share).
(a) raw season-S xG share · (b) production RAPM off/def · (b2) Atlas variant off/def
· (c) best-adjusted + destination context (new team's fingerprint + predicted role).

## 5.4 Metrics (pooled over movers; 1000-resample paired bootstrap CIs)

| predictor | pooled MAE | Spearman | vs (a): MAE improvement | 95% CI | CI excl 0 |
|---|---|---|---|---|---|
| (a) raw | 0.03705 | 0.257 | — | — | — |
| (b) production RAPM | 0.03664 | 0.287 | **+2.24%** | [−0.07%, +4.48%] | **no** |
| (b2) Atlas variant | **0.03568** | **0.311** | **+3.70%** | **[+2.01%, +5.38%]** | **yes** |
| (c) b2 + destination | 0.03681 | 0.278 | +2.16% | [−0.17%, +4.44%] | no |

- **(b2) vs (b) head-to-head:** b2 better by **+1.94%**, CI [+0.27%, +3.53%]
  (excludes zero) — the clean-input variant significantly beats production RAPM.
- **(c) vs best adjusted (b2):** **−1.57%**, CI [−3.17%, +0.05%] — **(c) does NOT
  add**; destination context + predicted role slightly *hurts* mover prediction.
- **Secondary target (GF share):** (b2) vs (a) = **+2.37%**, CI [+0.83%, +3.90%]
  (excludes zero) — same direction, smaller (goals are noisier than xG).

### Per-season-pair MAE (a / b / b2)
Variant (b2) ≤ raw (a) on **13 of 15** pairs. Representative:

| pair | a | b | b2 | | pair | a | b | b2 |
|---|---|---|---|---|---|---|---|---|
| 2015-16→2016-17 | .0398 | .0408 | **.0378** | | 2021-22→2022-23 | .0410 | .0405 | **.0397** |
| 2016-17→2017-18 | .0318 | .0295 | **.0294** | | 2022-23→2023-24 | .0395 | .0373 | **.0370** |
| 2020-21→2021-22 | .0406 | .0394 | **.0381** | | 2023-24→2024-25 | .0378 | **.0340** | .0345 |
(b unavailable pre-2015-16: production `player_impact` singles start 2015-16.)

## Leakage accounting + xG sensitivity
- **RAPM predictors are target-clean:** b/b2 for pair (S, S+1) use season-S RAPM,
  fit on season S (+prior) only — never on the S+1 target. The LOSO regression is
  fit on other pairs' stayers. So the *adjustment* is not fit on the evaluation pair.
- **Shared shot_xg overlap:** shot_xg's training window (2010-11→2023-24) overlaps
  the seasons it scores for both features and targets — **uniformly across all
  predictors including raw (a)**, so it cannot inflate the *relative* (b2−a) gap.
- **Pre-registered sensitivity (re-score one pair with the Phase 3 leakage-clean
  refit):** re-scored 2023-24 with the clean model (train ≤2020-21). Production vs
  clean xG correlate **0.963**; recomputing the 2022-23→2023-24 pair's target with
  clean xG leaves **b2 MAE (0.0695) < a (0.0717)** — the conclusion does not flip.

## 5.5 Decision (restated, no editorializing)
- Best leakage-clean adjusted (b2) vs (a): **+3.70%, CI [+2.01%, +5.38%]**.
- 0 < 3.70% < 5% → **INVESTIGATE.** Atlas ships as descriptive data; adjusted
  ratings held pending a larger, clearer effect.
- (c) adds nothing over the best of (b)/(b2) (−1.57%). (b2) beats (b) (+1.94%, CI
  excludes zero).

## 5.6 Fingerprint validation — both metrics fail the last-change test

| metric (2024-25, home−away, 32 teams) | league share positive | paired test |
|---|---|---|
| coarse HHI over all opponent forwards (Phase 4) | 43.3% (14/32) | — |
| **refined top-line targeting** (share of opponent's top forward line's 5v5 TOI absorbed by the team's top-3 defensive forwards) | **34.4% (11/32); mean −0.007** | Wilcoxon p = 0.008 (significant, but *away > home* — opposite of expected) |

Both metrics **fail to show the expected last-change advantage** (home > away). The
refined metric is even slightly reversed and significantly so. **Reported honestly
as a finding about matching in the modern league**, not refined further: shift-chart
on-ice overlap does not reveal a measurable home matchup-targeting edge on top lines
here — plausibly because shifts even out over a game and last change governs starts,
not total overlap.

## Case studies — 10 movers each model missed worst (with context)
The results you'll read first. Nearly all are depth players whose on-ice results
swung hard on the new team (destination effects the ratings can't anticipate — and
which (c)'s destination features failed to capture).

**(a) raw — worst misses:** Cody Hodgson (2014-15→2015-16, actual .606 / pred .429),
Mike Brown (2011-12→2012-13, .316/.488), Frank Vatrano (2021-22→2022-23, .363/.524),
Zack Kassian (2021-22→2022-23, .336/.497), David Clarkson (2012-13→2013-14, .402/.561),
Taylor Pyatt (.368/.520), Alex Galchenyuk (2020-21→2021-22, .383/.533), Henrik
Tallinder (.425/.573), Josh Gorges (2013-14→2014-15, .347/.491), Dmitry Kulikov (.381/.518).

**(b2) variant — worst misses:** Mike Brown (.316/.486), Zack Kassian (.336/.485),
Josh Gorges (.347/.489), Frank Vatrano (.363/.503), Dmitry Kulikov (.381/.520), Jay
McClement (2011-12→2012-13, .351/.488), Anthony Duclair (2019-20→2020-21, .604/.471),
Taylor Pyatt (.368/.501), David Clarkson (.402/.534), Cody Hodgson (.606/.478).

Both models share most of the same misses (Hodgson, Kassian, Vatrano, Kulikov,
Clarkson, Pyatt, Gorges) — players whose new-team role/context, not their prior
on-ice signal, drove the next-season result. The overlap is itself evidence that
the residual after context correction is destination-and-role variance neither the
raw nor the adjusted rating carries.

---

## Summary
- **INVESTIGATE.** Context correction travels (b2 beats a, +3.70%, CI excludes
  zero; b2 beats b, +1.94%, CI excludes zero) but under the 5% ship bar.
- (c) destination context adds nothing; the last-change fingerprint fails on both
  the coarse and refined metrics (honest null).
- Robust to xG leakage (0.963 correlation; conclusion holds on the re-scored pair).
- Atlas ships as **descriptive data**; the adjusted-rating portability claim is held.

**Phase 5 complete. Stopping per the preamble.**
