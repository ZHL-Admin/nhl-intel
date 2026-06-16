# Player archetypes (Phase 4.2)

Per-position Gaussian-mixture clustering of player-season feature vectors
(`models_ml/fit_archetypes.py` + `archetype_features.py` -> `nhl_models.player_archetypes`),
producing soft archetype memberships. Forwards and defensemen are clustered separately, k=12
each.

## Features (per player-season, >= 300 5v5 minutes, 2021-22..2025-26)

Sequence-type shares (rush/rebound/forecheck/cycle/point), shot-location profile (mean
distance, slot share), RAPM offence/defence, PP/PK TOI share, o-zone faceoff-start share,
penalties drawn per 60, NHL Edge bursts and o-zone time, and a **PP-dependency** feature:
`z(PP point share) − z(5v5 RAPM offence)` within position. PP dependency separates genuine
dual-threat stars (high PP usage *and* strong 5v5) from players whose offence is concentrated
on the man-advantage — without it the GMM blended Kucherov-type stars with PP-merchant
profiles. Features are standardised within position; Edge values are mean-imputed when absent.

## Clustering and reproducibility

A Gaussian mixture (`covariance_type='diag'`, `reg_covar=1e-2`) is fit per position. k is
fixed at 12 (BIC over 6–12 prefers 12 but the choice is boundary-sensitive). **sklearn's GMM
is not bitwise-reproducible here** (threaded BLAS is not governed by `random_state`) and has
many local optima — raw likelihood can collapse a giant catch-all scorer cluster. We therefore
select the **best-separated seed by silhouette** among fits with no degenerate (<15-member)
cluster, run single-threaded for determinism, and **persist the fitted scaler+GMM** to
`models_ml/artifacts/archetypes_v1.joblib` (committed). The labeling report, `player_archetypes`,
and the API all load this one canonical model, so the clustering is locked.

## Naming (the one human-in-the-loop step)

`fit_archetypes.py` (no `--write`) prints per-cluster standardised feature means and exemplars
to `artifacts/archetype_labeling_report.md` and stops. A human fills
`config.ARCHETYPE_NAMES`; `--write` then emits `player_archetypes`. The 24 names span elite
drivers (Elite Speed Driver, Elite Offensive D) through depth roles (Fourth-Line Grinder,
Bottom-Pair Defensive D). A player-season's mix lists archetypes with membership ≥ 0.10,
sorted desc; the top one is `primary_archetype`.

## Validation

Memberships are crisp for distinctive players (McDavid 1.00 Elite Speed Driver, MacKinnon 1.00
Perimeter Sniper, Makar 1.00 Elite Offensive D). PP-QB (Hedman/Josi/Hamilton) vs Elite
Offensive D (Makar/Karlsson) is separated by Edge burst speed (+2.9 SD vs ~0). Silhouette is
low (~0.02–0.03), reflecting that player style is a continuum — archetypes are descriptive
regions, not crisp partitions, which is why memberships are soft.

## Surfaces

`GET /players/{id}` returns the archetype mix; `GET /players/archetypes/{archetype}` lists
players whose primary archetype is that one, ranked by composite total. PlayerProfile shows the
mix line ("100% Elite Speed Driver"); the Players index ranks within a selected archetype.
