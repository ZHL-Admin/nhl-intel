# Player Assessment — Preregistration

> Committed BEFORE any scoring of the 2025-26 evaluation season (spec 5.2). This file fixes
> the tasks, universes, metrics, cut dates, ship gate, and candidate-selection rule so the
> assessment's point estimator is chosen by a rule written down in advance, not picked after
> seeing the results. Mirrors the goalie-clutch prereg practice already in the repo.

Model: `assessment_v1`. Harness: `models_ml/validate_assessment.py`
(`make assessment-validate`). Baselines: `models_ml/baselines.py`. Estimator candidates:
`models_ml/value_lens.py`.

## Data & cut dates

- Value inputs: single-season rows of `nhl_models.player_gar` (skaters) and
  `nhl_models.goalie_gar` (goalies), `season_window` like `YYYY-YY`. Available seasons at
  prereg time: 2021-22, 2022-23, 2023-24, 2024-25, 2025-26.
- **Eval seasons (S+1): 2024-25 and 2025-26.** Predictors are computed AS OF season S (=
  S+1 minus one) using only data through S. Any constant tuning uses only data through
  S+1 = 2023-24 (i.e. nothing at or after the first eval season tunes anything). The three
  candidates use only fixed, pre-registered constants (the measured `GAR_STABILITY_YOY`
  r-values for C1; `project_roster_player` defaults for C2; `blended_war_rate` defaults for
  C3), so there is no post-hoc tuning on eval data.

## Predictors compared (skaters, T1)

Each reduces to a WAR **rate** (WAR per 5v5 hour) as of S; the harness multiplies by the
player's REALIZED S+1 5v5 TOI, so TOI forecasting is not confounded.

- `naive` — last-season (S) WAR rate carried.
- `marcel` — TOI-weighted blend of the last 3 seasons' WAR rate, weights [5,4,3], regressed
  to the position-group mean rate with shrink = K/(K+Σ wᵢ·toiᵢ), K = 1800 5v5 minutes.
- `c1_r_shrink` — per-component shrink of season S's `player_gar` component rates toward the
  position-group mean by the measured `GAR_STABILITY_YOY` r-values (production 0.66, RAPM
  0.38); the finishing residual (goals − ixg) is shrunk toward 0 by 0.35. NET-NEW.
- `c2_roster_player` — `project_roster_player._project_skater_components` (per-component,
  sample-size shrink toward a position prior), aging zeroed.
- `c3_blended` — `compute_contract_value.blended_war_rate` (total-WAR shrink toward
  replacement by sample size), aging not applied.

Goalies (report only): `naive`, `marcel` (K = 1500 shots, rate = WAR per shot), and the
`goalie_gar` carry-through (already reliability-shrunk).

## Universe (T1)

- Skaters: qualified in S (5v5 TOI ≥ `MIN_TOI_5V5_FOR_RANKING` = 200 min) AND ≥ 400 5v5
  minutes in S+1. Headline RMSE is computed on the common set of players for which every
  method yields a prediction (per-method n also reported).
- Goalies: ≥ 15 games in both S and S+1.

## Metrics

- **T1 (primary, gated):** RMSE and MAE on WAR (rate × realized S+1 TOI), and Spearman rank
  correlation, per eval season, per method.
- **T2 (reported, not gated):** Spearman correlation of each method's as-of-S assessed WAR
  rate with next-season on-ice 5v5 xGF% (`mart_player_onice.on_ice_xgf_pct`, TOI-weighted).
- **T3 (cited, not recomputed):** team-level roster-forecast calibration lives in
  `validate_roster_forecast` / `docs/methodology/roster-projection.md`; not duplicated.
- **T4 (reported, not gated):** distribution of tier + confidence labels per position group
  and season for the shipped estimator, and persistence — among players labeled
  `confidence_label = high` in tier T at S, the share still assigned T at S+1 and the share
  within one tier. Tier ladder + cuts use the spec 6.2 constants. These diagnostics are the
  empirical basis for any later change to `CONFIDENCE_CUTS`; the cuts are NOT retuned here.

## Ship gate G1 + candidate selection (hard, verbatim)

> Ship the candidate with the lowest mean skater T1 RMSE across both eval seasons (2024-25,
> 2025-26), provided it beats Marcel in both. If candidates land within 0.005 RMSE of each
> other, prefer C2 (`c2_roster_player`), then C3 (`c3_blended`), then C1 (`c1_r_shrink`). If
> no candidate beats Marcel in both seasons, gate G1 fires and Marcel ships as the point
> estimate. Record the winner in `point_estimator` (allowed values: `c1_r_shrink`,
> `c2_roster_player`, `c3_blended`, `marcel`).

The tier machinery (spec 6.2) is estimator-agnostic; the winner changes only the point
estimate, not the ladder. Goalies ship on `goalie_gar` regardless of the skater winner.


---

# Preregistration v2 — backtest expansion + C4 (2026-07-03)

> Addendum to the v1 prereg above. Committed BEFORE any new-transition scoring (Track A / M0.5).
> The v1 tasks/universe/metrics stand; this adds a fourth candidate, a strict walk-forward rule,
> a COVID rule, an expanded transition set, and a C4 promotion rule. No new-transition scoring
> runs until this file is committed.

## v2.2 New candidate C4 (`c4_r_speed`)

Per-component shrinkage where each GAR component's trust scales with the player's OWN sample
size, and the per-component speed-of-trust constant K_c is derived ANALYTICALLY from the
measured `GAR_STABILITY_YOY` r-values — not tuned against any scored season.

Derivation (from the definition of a YoY rate reliability): under a signal+noise model, the
year-over-year correlation r of a component measured at a typical per-season sample n0 equals
the reliability at n0, i.e. `reliability(n0) = n0 / (n0 + K_c) = r`. Solving:

    K_c = n0 * (1 - r) / r

n0 is a STRUCTURAL sample-size constant (median 5v5 TOI of the qualified pool in seasons
strictly before the target); it is not fit to any outcome. Then a player with 5v5 sample n gets
reliability `n / (n + K_c)`, shrinking each component's season rate toward the position-group
mean (finishing residual toward 0). Component -> r mapping (finishing distrusted hardest,
production least): finishing r=0.35 (largest K), RAPM-borrowed ev_defense/pk r=0.38, sustainable
production ev_offense/pp r=0.66 (smallest K); penalty/faceoff pass through. Contrast with C1
(fixed r as the shrink weight, sample-blind) and C2 (grid-tuned K_c): C4's K is r-derived and
its trust is sample-adaptive. Implemented behind the existing value_lens interface.

## v2.3 Walk-forward rule (all candidates, all targets)

For target season S+1, every candidate and baseline may use ONLY data from seasons strictly
before S+1 (the `project_roster_player` fit-on-years-before-target pattern). Constants measured
on 2021-22 onward (e.g. `GAR_STABILITY_YOY`) stay FROZEN as shipped; they are NOT re-measured
and swapped mid-evaluation. Refreshed r-values on the longer history are reported as information
only.

## v2.4 COVID rule

Flag any transition where S or S+1 is 2019-20 or 2020-21 (shortened/irregular seasons). The
primary decision metric uses only NON-flagged transitions; flagged transitions are reported as a
sensitivity set, never mixed into the headline.

## v2.5 C4 promotion rule

C4 displaces C2 as `point_estimator` only if (a) C4 beats C2 on mean skater T1 RMSE across the
NEW non-flagged transitions (targets 2018-19, 2022-23, 2023-24), AND (b) C4 is not worse than C2
by more than 0.005 RMSE in either 2024-25 or 2025-26. Ties within 0.005 on (a) keep C2 (incumbent
wins). Otherwise C2 ships and C4 joins C1/C3 as a documented also-ran.

## v2.6 Scope of the expanded table

Re-score naive, marcel, C1, C2, C3, and C4 on every transition the 2015-16 backfill enables. All
are honest out-of-sample on the new pre-2024 targets since none were ever scored there. `point_
estimator` allowed values extend to include `c4_r_speed`.


---

# Preregistration v3 — T5 tier-bucket bias diagnostic (2026-07-03)

> Addendum committed BEFORE T5 is run. T5 is a read-only, report-only diagnostic added to
> `models_ml/validate_assessment.py`; no schema changes, no new tables.

## T5 rule (verbatim)

T5 buckets skaters by the tier assigned from the as-of-season S assessment, computed
walk-forward with data through S only (leak-free by construction); metric is mean signed error
(predicted minus realized S+1 WAR) per bucket, per position group F and D, for at minimum C2 and
Marcel, across all 10 transitions; headline uses non-COVID-flagged transitions with the flagged
set reported as sensitivity. T5 is diagnostic only: no new candidate may be built from it without
a fresh prereg, and any future candidate's promotion rests primarily on the 2026-27 season.

## Notes

- Bucket = the shipped-estimator (C2) tier at S; the same predicted-WAR construction as T1
  (rate × realized S+1 TOI) is used for both C2 and Marcel signed errors, so TOI is not
  confounded. A positive mean signed error in a bucket means the estimator OVER-predicts that
  tier's next-season WAR; negative means it UNDER-predicts.
