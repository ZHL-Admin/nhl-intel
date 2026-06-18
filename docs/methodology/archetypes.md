# Player archetypes — v2 (current)

Per-position Gaussian-mixture clustering of player-season feature vectors
(`models_ml/fit_archetypes_v2.py` + `archetype_features_v2.py` -> `nhl_models.player_archetypes`,
model_version `archetypes_v2`), producing soft memberships. F and D clustered separately, k=12
each (BIC-selected over [6,12] with a degenerate-cluster guard). Persisted, single-threaded fit at
`artifacts/archetypes_v2.joblib`.

**Why v2 (enriched feature vector).** v1 clustered on offense/sequence/shot-location/PP/penalty/
deployment/Edge features; defense entered only as low-variance RAPM `def_impact`, so it barely
separated clusters — defensive roles were a *display* afterthought. v2 ADDS the stronger
defensive/style signals that postdate v1 and were never used to classify: the **coach-trust
composite + its components** (PK role, DZ-faceoff-start share, lead-protection usage, road/home
matchup usage), **rink-adjusted hits /60** (never raw), **penalty differential (drawn−taken) /60**,
and **on-ice xGA /60 at 5v5** (defensive suppression, computed from `int_on_ice_events × shot_xg`).
These now drive separation: coach-trust, PK, DZ-faceoff, hits, and xGA-suppression are *universal*
traits across many clusters. The radar (`player-radar.md`) and the labels are therefore coherent —
the same information drives both.

**Trait-audit governs naming** (`artifacts/archetype_trait_audit_v2.md`). For each cluster:
a **universal** trait = ≥80% of members on one side of the position median; a name may assert ONLY
universal traits. **Distinctive** traits (centroid |z|) drive the per-cluster DESCRIPTOR
(`config.ARCHETYPE_DESCRIPTORS_V2`), not the name. A **near-twin** check flags merge candidates.
Systemic finding (carried from v1): RAPM `def_impact` does not separate defensive players, so
"shutdown/two-way" *skill* claims read weak — surviving defensive labels are **deployment-based**.

**Two-cluster display merge (footnote).** Defensemen clusters **D3 and D4 are distinct GMM
components at the model layer** but were merged at DISPLAY into one label, **"Depth Defenseman"**:
their union (n≈193) is universally low power-play TOI (83%) and low penalty-kill share (90–92%) —
i.e. depth D with no special-teams role — which is principle-1-legal. `config.ARCHETYPE_NAMES_V2`
maps both `D3` and `D4` to "Depth Defenseman"; the row builder sums their membership weights so a
player's mix carries a single "Depth Defenseman" entry. Net: 12 forward + 11 defense labels.
`F4` "North-South Forward" is named for its universal/distinctive speed; its descriptor carries the
honest conceding detail (on-ice xGF ~31st / xGA ~84th pctl). The naming review was human-confirmed.

---

# Player archetypes v1 (superseded — retained for history)

Per-position Gaussian-mixture clustering of player-season feature vectors
(`models_ml/fit_archetypes.py` + `archetype_features.py`), k=12 each.

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
drivers (High-Danger Driver, Elite Offensive D) through depth roles (Fourth-Line Grinder,
Bottom-Pair Defensive D). A player-season's mix lists archetypes with membership ≥ 0.10,
sorted desc; the top one is `primary_archetype`.

## Validation

Memberships are crisp for distinctive players (McDavid 1.00 High-Danger Driver, MacKinnon 1.00
Perimeter Sniper, Makar 1.00 Elite Offensive D). PP-QB (Hedman/Josi/Hamilton) vs Elite
Offensive D (Makar/Karlsson) is separated by Edge burst speed (+2.9 SD vs ~0). Silhouette is
low (~0.02–0.03), reflecting that player style is a continuum — archetypes are descriptive
regions, not crisp partitions, which is why memberships are soft.

## Label membership audit (2026-06)

The hand-applied labels were audited against their membership: for each cluster we checked
whether the trait the *name* asserts actually holds for ≥80% of the cluster's members (not just
the exemplars that inspired it). Seven names leaned on a trait that wasn't universal and were
renamed to fit every member:

| Was | Failing claim | Now |
|---|---|---|
| Elite Speed Driver (F1) | only 17% are fast; it's a slot/in-tight shooting cluster | **High-Danger Driver** |
| Energy Forechecker (F3) | only 39% forecheck above avg; 52% are wingers | **Bottom-Six Forward** |
| Two-Way Shutdown Forward (F4) | defense only 71%; it's a 5v5 *offense* cluster | **Middle-Six Driver** |
| Defensive/Energy Center (F5) | defense only 59%; 41% are wingers | **Energy Forward** |
| Two-Way Top-Six (F7) | defense 48% (coin flip); only PP usage is universal | **Top Six Scorer** |
| Rush-Joining D (D1) | rush only 55%; they shoot from in tight, not the point | **Attacking D** |
| Shutdown PK D (D4) | defensive impact 50%; low-offense/slow PK deployment | **Defensive Defenseman** |
| Physical Mobile D (D6) | "mobile" only 62%; "physical" unmeasured (no hits feature) | **Depth Defenseman** |

Systemic finding: RAPM `def_impact` does not cleanly separate "defensive" players, so any label
asserting *measured* defensive shutdown impact reads weak. The reliable defensive signals are
**low offense + deployment** (no PP, PK minutes, slow, low-event), not `def_impact` — so the
surviving defensive labels are deployment-based. The labels are membership-audited; renaming is a
pure relabel of the locked GMM's clusters (no refit), re-emitted by `fit_archetypes --write`.

## Surfaces

`GET /players/{id}` returns the archetype mix; `GET /players/archetypes/{archetype}` lists
players whose primary archetype is that one, ranked by composite total. PlayerProfile shows the
mix line ("100% High-Danger Driver"); the Players index ranks within a selected archetype.

## Archetype explainer (gallery + player style-map)

`models_ml/compute_archetype_explainer.py` (reads the locked v2 artifacts — NO retrain) writes two
tables that drive the Learn → Archetypes page:

- **`nhl_models.archetype_gallery`** — one row per DISPLAY archetype (12 F + 11 D; D3+D4 merge to
  "Depth Defenseman"): name, family, descriptor, member count, the **universal traits** (the same
  >=80%-one-sided audit that governs naming), the **distinctive traits** (top centroid |z|), the
  **exemplars** (top members by GMM membership weight, current-season preferred), and the
  **characteristic centroid radar** — the mean of the cluster members' shipped `player_radar`
  spokes (percentile-within-position), so each type renders as a recognisable radar shape.

- **`nhl_models.player_style_map`** — one row per tracking-era player-season: a **2D PCA projection
  of the standardized clustering feature vector**, primary archetype, membership strength, and a
  boundary flag (max membership < 0.6). **Forwards and defensemen are projected SEPARATELY** — they
  occupy different feature spaces, so co-plotting them on one axis would be meaningless; the UI
  toggles F/D and never co-plots. PCA orientation is sign-pinned by a reference feature so the axes
  are stable across rebuilds. Per-archetype region metadata is the centroid of its plotted points;
  the endpoint plots one point per player (latest season).

Honest by construction: archetypes are **discovered** clusters, not designable points. The gallery
browses the real discrete types; the map shows where real players actually sit. Gaps between
clusters are real and read as empty — neither surface lets a user invent an archetype, and the map
returns only real players. Endpoints: `GET /archetypes` (gallery) and `GET /archetypes/style-map?pos=`.
Archetype tags across the site (player detail, the expanded leaderboard card) deep-link into the
explainer at the matching type (`/learn/archetypes?type={name}`).
