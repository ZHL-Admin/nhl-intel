# Player Assessment — Implementation Spec

> Repo: nhl-intel (master). Audience: a developer/engineer joining the project.
> Status: implementation-ready spec. Every open choice is listed in Section 14 with a
> default; if the owner does not override, build the default. Where this doc conflicts
> with the code, the code wins; flag the conflict rather than improvising.

## Verification notes (audit 2026-07-03)

The inventory below was audited against master on 2026-07-03. Most claims held exactly
(constants, model producers, endpoints, serving/orchestration, frontend components). Three
claims were stale/wrong and the affected sections have been rewritten in place so the body
no longer contradicts these notes:

1. **Assessed-WAR "lens" is net-new, not a factor-out (load-bearing).** Section 6.1
   originally said to factor the reliability-shrinkage lens out of
   `project_roster_forecast.py`. That module does **not** contain it: it delegates to
   `blended_war_rate` (`compute_contract_value.py`), which regresses *total* WAR toward
   *replacement* by sample size, and its docstring records that a per-component
   shrink-toward-zero was *removed*. The per-component-toward-position-prior logic lives in
   a different file (`project_roster_player.py`) and shrinks by sample size, not by the
   `GAR_STABILITY_YOY` r-values. So the r-value per-component shrink the spec wants is
   genuinely new code. **6.1 is now a three-candidate estimator bakeoff (C1/C2/C3)** decided
   by the validation harness; `value_lens.py` becomes a shared interface over all three, not
   an extraction. The cited RMSE evidence (skater 0.720 / Marcel 0.737 / naive 0.764) is
   real but validates `project_roster_player.py` (candidate C2), documented in
   `docs/methodology/roster-projection.md` — not `validate_gar.py`.

2. **WOWY is already materialized and served.** `mart_player_onice`, `mart_player_wowy`,
   `mart_player_toi_matrix` are live in `serving_tables.yml:71-77` (Phase 6 block), with
   `small_sample = toi_together_sec < 3000` and the dependence input
   `together_minus_focal_alone` already precomputed in `mart_player_wowy.sql`. Section 7.1
   is reduced to "confirm nightly selector inclusion"; 7.3 reads the precomputed column.

3. **`GET /players/{id}/wowy` already exists** at `players.py:524` (`PlayerWowy` response
   model, reads `mart_player_wowy`, name-joins `stg_rosters`, orders by `toi_together_sec`
   desc, small_sample passthrough) and the frontend already calls it. Section 9.2 no longer
   builds it; `/context` consumes it.

Minor drifts corrected in the body: `durable_archetype` is computed in
`backend/routers/players.py` (`_durable_archetype`), not `fit_archetypes_v2.py`; archetype
k=12/12 is BIC-selected over `range(6,13)`, not hard-coded; the RMSE trio's provenance is
`project_roster_player.py`'s backtest + `docs/methodology/roster-projection.md`, not
`validate_gar.py` (which reports YoY correlation, not RMSE); and not all served player marts
carry dbt schema tests (several `mart_player_*` marts are served without a `schema.yml` entry).

## Status log

### M0 — validation harness (shipped 2026-07-03)
`baselines.py` (Marcel), `value_lens.py` (candidate interface), `validate_assessment.py`,
prereg. Gate G1: **C2 (`c2_roster_player`) won** (mean skater T1 RMSE 0.795, beats Marcel in
both eval seasons). C1 lost to Marcel; C3 ≈ Marcel.

### M0.5 — backtest expansion + C4 (shipped 2026-07-03)
Prereg v2 committed before scoring. Added: candidate **C4 (`c4_r_speed`)** — per-component
shrinkage with sample-adaptive trust, K derived analytically from the r-values
(K = n0·(1−r)/r); a strict **walk-forward** rule; a **COVID** flag (2019-20/2020-21 excluded
from headline); scoring on **all transitions**; and the **C4 promotion rule** (v2.5). Value
inputs backfilled to 2015-16 via append-only `--seasons` flags on `train_rapm` and
`compute_gar` (idempotent: they delete only the listed season_windows, never existing rows or
the 3yr window). **5,391 rows appended to each of `player_impact` and `player_gar`**; RAPM
off/def centered at 0 for every new season. **The weekly DAG scope is UNCHANGED** — it keeps
its 5-season window; the backfill is a one-off (the new serving rows reach the DuckDB file on
the next nightly export).

**Full expanded T1 (10 transitions 2016-17…2025-26; 2019-20/2020-21/2021-22 COVID-flagged,
excluded from decisions):** C2 (`c2_roster_player`) has the **lowest RMSE on every
non-flagged target**. C1 and C4 (the two net-new r-based candidates) **lose to Marcel** on
most targets — a consistent 10-season finding that the sample-size Marcel-toward-prior lens
(C2) beats the fixed/derived-r-shrink family.

**Verdicts:** v1 gate G1 → C2 (eval mean RMSE 0.793, beats Marcel both seasons). **C4
promotion (v2.5): NOT promoted** — new-target (2018-19/2022-23/2023-24) mean RMSE C4 0.888 vs
C2 0.827; C4 does not beat C2 by >0.005. **C2 ships**; C4 joins C1/C3 as documented also-rans.
T4 persistence over the full history is strong (same-tier 62–83%, within-one 87–95%).
Informational r-refresh (proxies; frozen `GAR_STABILITY_YOY` unchanged): ev_offense YoY ≈
0.52, finishing ≈ 0.30.

### M1 — assessment model on C2 (2026-07-03, code-complete)
`config.ASSESSMENT` (with swappable `POINT_ESTIMATOR`), `compute_assessment.py`
(`nhl_models.player_assessment`, 6,570 rows / 4,921 qualified over 6 windows),
`GET /players/{id}/assessment` + schemas, `serving_tables.yml`, Makefile `assessment`.
Invariants verified (tier_probs sum 1, within_one ≥ confidence, tier monotone in assessed_war,
unqualified ⇒ null tier). Spot check face-valid (McDavid/Draisaitl/MacKinnon = Elite F;
Makar/Hughes = Elite D; goalies capped at grade B). The serving write + live endpoint need the
backend stopped (documented DuckDB export lock; the nightly DAG handles the atomic swap).
Remaining M1 wiring: the Monday-gated `compute_assessment` DAG task.

## 0. What we are building and why

Today the platform answers "how good is this player" with several parallel lenses
(GAR/WAR, RAPM impact, composite, Overall percentile, radar, archetype, verdict prose).
Each is honest in isolation, but no single surface answers the question the way a general
fan asks it, and no surface communicates uncertainty as the primary fact rather than a
footnote.

The change: a three-layer player assessment that becomes the primary answer on the
player page and in row previews.

- **Layer 1 (the verdict):** a role-based TIER (e.g. "Top-four defenseman"), a CONFIDENCE
  statement (probability mass, not vibes), and a ROLE label. Readable in three seconds.
  Never a bare 0-100 number.
- **Layer 2 (the context):** how that value depends on situation: strength-state splits,
  usage/zone deployment, quality of competition and teammates, linemate dependence
  (WOWY), and a hook into the existing fit/line tools.
- **Layer 3 (the receipts):** the existing component decomposition, intervals, sample
  sizes, measured year-over-year stability, and methodology links. Mostly already built;
  we wire it as the drill-down of Layer 1.

The load-bearing wall underneath is a validation harness: the assessment's point estimate
must demonstrably beat a dumb baseline (Marcel) at predicting future value out of sample,
and the claim is preregistered before evaluation. This is Workstream 0 and ships first.

### Product rules inherited (keep them)

- Components are always shown next to any summary number; never a total-only shape
  (see `models_ml/compute_composite.py` docstring and `compute_overall.py`).
- Summary values are never leaderboard sort keys. No `/rankings/overall`; likewise no
  `/rankings/tier` and no sort-by-tier.
- Consistency rule: any number cited in prose must trace to a stored number
  (see `insight_engine/templates/value_gap.py` and the verdict checker in
  `models_ml/generate_verdicts.py`).
- Every shipped model gets a methodology doc in `docs/methodology/` and, where applicable,
  a `validate_*` module with a Makefile target.
- Uncertainty is surfaced, never hidden; missing data widens bands or gates the surface,
  it never silently reads as average.

## 1. Vocabulary

| term | meaning |
| --- | --- |
| assessment | the new per-player output: tier + confidence + role + provenance |
| tier | a named role band defined by league job-count RANK ceilings on assessed WAR within the position group (Section 6.2) |
| confidence | probability mass of the player's WAR distribution inside the assigned tier |
| within-one mass | `tier_prob_within_one`: mass inside the assigned tier plus its adjacent tier(s); drives the two-tier range copy rule |
| stability grade | A-D data-sufficiency grade (sample + seasons present), separate from confidence |
| assessed WAR | the reliability-shrunk current-ability WAR estimate defined in Section 6 |
| qualified pool | skaters over `config.GAR_CONFIG["MIN_TOI_5V5_FOR_RANKING"]`; goalies over goalie GAR `MIN_GAMES_FOR_RANKING` (15) |
| window | `season_window` as used by player_impact / player_gar (single seasons + 3-season weighted window, e.g. `2023-24_2025-26`) |
| WOWY | with-or-without-you splits, `mart_player_wowy` |

## 2. Current-state inventory

Everything below is claimed to exist on master unless marked otherwise. Do not rebuild.

### 2.1 Value lenses (`nhl_models.*`)

| table | producer | contents | notes |
| --- | --- | --- | --- |
| player_impact | `train_rapm.py` (rapm_v1) | RAPM off/def/pp/pk + bootstrap SDs, per season and 3yr window | 2015-16 floor. Load-bearing. Do NOT modify. |
| player_composite | `compute_composite.py` | goals-scale components (ev_offense, ev_defense, pp, pk, finishing k=350 shrink, penalty_diff, goalie_gsax) + total + total_sd | |
| player_gar / goalie_gar | `compute_gar.py` / `compute_goalie_gar.py` | goals above replacement + components + sd; goalie side applies RELIABILITY_K | replacement level documented in `docs/methodology/value-gar.md` |
| player_overall / goalie_overall | `compute_overall.py` | within-position percentile summary, card-only | weights `config.OVERALL_WEIGHTS` = production 0.55 / play-driving 0.45 |
| player_radar / goalie_radar | `compute_player_radar.py` / `compute_goalie_radar.py` | percentile-within-position spokes + derived labels | `src/api/labels.ts` is the single FE label source |
| player_archetypes | `fit_archetypes_v2.py` (archetypes_v2 joblib) | soft GMM memberships, k BIC-selected over `range(6,13)`, landed at F k=12 / D k=12 | `durable_archetype` (modal over last 3 seasons) is the stable identity, computed in `backend/routers/players.py::_durable_archetype` (not in `fit_archetypes_v2.py`) and exposed in PlayerDetail |
| player_verdict | `generate_verdicts.py` (verdict_v1) | Gemini prose over a deterministic payload, verified by a numeric checker | weekly, scoped to players active in last 7 days |

Supporting: player_consistency, player_twins, player_physical, aging_curves,
player_situation_toi.

### 2.2 Measured constants to reuse (do not re-derive)

- `config.GAR_STABILITY_YOY`: production r = 0.66, RAPM isolated rate r = 0.38, finishing
  residual r = 0.35 (single-season pairs 2021-22..2025-26, `validate_gar.py`).
- `config.GAR_CONFIG["GOALS_PER_WIN"] = 6.0`.
- Goalie reliability: `RELIABILITY_K` per danger tier; goalie overall rate reliability ~0.19.
- A player-projection method (`project_roster_player.py`, per-component sample-size shrink
  toward a position prior) is validated OOS: skater WAR RMSE 0.720 vs Marcel 0.737 vs naive
  0.764; goalie 0.853 / 0.884 / 0.936. Provenance: that module's own backtest, documented in
  `docs/methodology/roster-projection.md` (NOT `validate_gar.py`, which reports YoY
  correlation r, not RMSE). NOTE: the offseason `project_roster_forecast.py` uses a
  *different* estimator — `blended_war_rate` (total-WAR shrink toward replacement by sample
  size) + aging — so there is no single "reuse this exact lens" target; see Section 6.1.

### 2.3 Context data

- `mart_player_situational` + `player_situation_toi`: served by
  `bq.get_player_situational` (`backend/services/bigquery.py:753`).
- `mart_player_zone_deployment`, `mart_player_relative`, `mart_player_shooting_luck`: live.
- WOWY branch (ALREADY materialized + served, per 2026-07-03 audit): `int_segment_5v5_results`,
  `int_player_onice_game` upstream, plus leaf marts `mart_player_onice`,
  `mart_player_toi_matrix`, `mart_player_wowy` — all present in `serving_tables.yml:71-77`
  (Phase 6 block) with dbt schema + tests. `mart_player_wowy` also already precomputes
  `together_minus_focal_alone` (the linemate-dependence input). Consumed by an existing
  endpoint (`GET /players/{id}/wowy`, `players.py:524`). No materialization work remains.
- WOWY small-sample rule: `small_sample = toi_together_sec < 3000` (D17), already applied in
  `mart_player_wowy.sql`. Keep it.
- QoC/QoT: does not exist anywhere. New build, Section 7.2.

### 2.4 Serving/orchestration patterns

- Nightly order: ingest -> dbt -> model jobs -> precompute_serving -> export_to_duckdb
  (atomic swap). Backend reads only `data/serving/nhl_intel.duckdb`
  (`SERVING_BACKEND=duckdb` default set in `backend/main.py:19`).
- New tables must be added to `serving_tables.yml`. Single-table refresh:
  `python -m scripts.export_to_duckdb --only <table>` (backend stopped).
- Weekly model jobs Monday-gated in `dags/nhl_daily.py` via the `_mon.format(...)` guard;
  each also gets a Makefile target. Parity: `make verify-serving`
  (`scripts/verify_serving_parity.py`).
- Backend: 13 routers registered in `backend/main.py`; response models in
  `backend/models/schemas.py`; caching via `@cache(ttl=...)`.
- Frontend: `pages/PlayerProfile.tsx`, `components/players/PlayerRowExpansion.tsx`,
  `components/visualizations/SkillRadar.tsx`, `components/common/OverallSummary.tsx`.

### 2.5 Hard "do not touch" list

- `train_rapm.py`, `train_xg.py` outputs and schemas.
- Do not build a duplicate `mart_player_rapm`; read `player_impact`.
- `archetypes_v2.joblib`.
- ppt-replay tracking objects.

## 3. Gap analysis

| Layer | Missing piece | Everything else |
| --- | --- | --- |
| 0 Validation | player-level assessment harness with Marcel baseline, preregistration, pass/fail ship gate | reuse `validate_*` culture, roster-projection eval design |
| 1 Verdict | tier ladder, tier-probability confidence, stability grade, `player_assessment` table + endpoint | assessed-WAR ingredients exist |
| 2 Context | (a) materialize WOWY marts + serve; (b) build QoC/QoT; (c) composed `/context` endpoint; (d) linemate-dependence index | strength splits, zone deployment, fit/line tools exist |
| 3 Receipts | provenance block on the assessment + FE wiring | components, SDs, radar, methodology docs exist |
| Prose | verdict payload extension so `generate_verdicts` cites the tier and checker verifies it | verdict pipeline exists |

## 4. Architecture overview (target state)

```
player_gar / goalie_gar / player_impact / player_archetypes
        |
        v
models_ml/compute_assessment.py  --->  nhl_models.player_assessment
        ^                                     |
config.ASSESSMENT (new block)                 v
                                     serving_tables.yml -> DuckDB
int_segment_5v5_results / int_shift_segments  |
        |                                     v
dbt: mart_player_onice / _toi_matrix /   GET /players/{id}/assessment
     _wowy (materialize) +               GET /players/{id}/context
     mart_player_quality_context (new)   GET /players/{id}/wowy
                                              |
models_ml/baselines.py (Marcel)               v
models_ml/validate_assessment.py     PlayerProfile: AssessmentBand (L1),
        |                            Context tab (L2), Impact tab + provenance (L3);
        v                            PlayerRowExpansion tier chip
docs/methodology/player-assessment.md (+ prereg file, written BEFORE eval)
```

Cadence: `compute_assessment` weekly (Monday-gated), downstream of `compute_gar`,
`compute_goalie_gar`, `write_archetypes`; upstream of `generate_verdicts` and the
precompute/export gate.

## 5. Workstream 0: validation harness (build FIRST, ship gate)

### 5.1 `models_ml/baselines.py` — Marcel

Skaters and goalies separately (defaults, D6):

- Inputs: single-season rows of `player_gar` / `goalie_gar`, rate = `gar / toi_5v5_hours`
  for skaters (use stored TOI denominators); goalies per-shot or per-game rate consistent
  with goalie_gar denominators.
- Season weights newest->oldest `[5, 4, 3]`, TOI-multiplied (`w_i = weight_i * toi_i`).
- Regression to position-group mean rate with `shrink = K / (K + sum w_i_toi)`, K = 1800
  5v5 min (skaters) / 1500 shots (goalies).
- No age adjustment in v1.
- Output: `marcel_war_rate`, `marcel_war` per (player, target_season).

### 5.2 `models_ml/validate_assessment.py` (Makefile: `assessment-validate`)

Reads only; writes report to stdout, appends measured table into
`docs/methodology/player-assessment.md`.

- **T1 (primary, gated):** predict next-season realized WAR. Skaters qualified in S with
  >= 400 5v5 min in S+1; goalies >= 15 games both seasons. Compare (a) naive, (b) Marcel,
  and the three assessed-WAR candidates (c) C1 `c1_r_shrink`, (d) C2 `c2_roster_player`,
  (e) C3 `c3_blended`. Metrics: RMSE, MAE (rate x realized S+1 TOI), Spearman. Eval S+1 =
  2024-25 and 2025-26. Any constant tuning uses only data through S+1 = 2023-24.
- **T2 (reported):** predict next-season on-ice 5v5 xGF% from assessed WAR vs Marcel.
- **T3 (cite existing):** team-level roster forecast calibration; do not duplicate.
- **T4 (reported, D3):** tier/confidence label distribution per group+window; persistence
  of high-confidence labels S->S+1 (same tier, and within-one).

Preregistration: before running eval on 2025-26, commit
`docs/methodology/assessment-prereg.md` (tasks, universes, metrics, cut dates, gate, and
the verbatim selection rule below).

**Ship gate G1 + candidate selection (hard, preregistered):**

> Ship the candidate with the lowest mean skater T1 RMSE across both eval seasons
> (2024-25, 2025-26), provided it beats Marcel in both. If candidates land within 0.005
> RMSE of each other, prefer C2 (`c2_roster_player`), then C3 (`c3_blended`), then C1
> (`c1_r_shrink`). If no candidate beats Marcel in both seasons, gate G1 fires and Marcel
> ships as the point estimate. Record the winner in `point_estimator` (allowed values:
> `c1_r_shrink`, `c2_roster_player`, `c3_blended`, `marcel`).

The tier machinery is estimator-agnostic, so the winner only changes the point estimate,
not the ladder. Goalies: report only; goalie_gar (r≈0.19) is expected to sit near Marcel and
ships unchanged regardless of the skater winner.

## 6. Workstream 1: the assessment model (Layer 1 spine)

### 6.1 `models_ml/compute_assessment.py` -> `nhl_models.player_assessment`

`MODEL_VERSION = "assessment_v1"`. Skaters + goalies in one table (F/D/G), one row per
(player_id, season_window) for every window `player_gar` carries.

Assessed WAR (skaters) — the point estimator is chosen by a **three-candidate bakeoff**
(no aging applied, D4). The audit (2026-07-03) found there is no single existing lens to
"factor out": `project_roster_forecast.py` uses total-WAR shrink toward replacement, and the
per-component method lives in a different file. So `models_ml/value_lens.py` is a **shared
interface** exposing all three candidates behind one signature (returns `(assessed_war_rate,
war_sd)` per player-window); the validation harness (5.2) picks the winner. Aging is never
applied here (assessment = ability now; the forecast owns aging).

- **C1 — `c1_r_shrink` (NET-NEW code).** Per-component shrink of `player_gar` components
  toward the position-group mean by the measured `GAR_STABILITY_YOY` r-values: finishing
  residual (goals − ixg) shrinks hardest toward 0 (r=0.35); sustainable production r=0.66;
  RAPM-borrowed EV-defense/PK r=0.38; tiny penalty/faceoff terms pass through.
  `assessed_war = shrunk_gar / GOALS_PER_WIN`.
- **C2 — `c2_roster_player` (WRAP `project_roster_player.py`, do not fork).** Its
  per-component, sample-size shrink toward a position prior. This is the method the existing
  0.720 skater-RMSE evidence (`docs/methodology/roster-projection.md`) actually validates, so
  it is the incumbent to beat. Wrap the module's existing projection function; strip its
  aging step (or call the pre-aging value) so no aging is applied.
- **C3 — `c3_blended` (WRAP `blended_war_rate` from `compute_contract_value.py`).**
  Total-WAR shrink toward replacement by sample size — the estimator the offseason
  `project_roster_forecast.py` uses. Wrap it; do not apply the aging multiplier.

`war_sd` for all candidates: carry `gar_sd / GOALS_PER_WIN` from the row — shrinkage moves
the point, not the band (matches the goalie-GAR convention). `point_estimator` on each row
records which candidate won the bakeoff (`c1_r_shrink` | `c2_roster_player` | `c3_blended` |
`marcel`). If G1 fires (no candidate beats Marcel in both eval seasons), `marcel` ships as
the point estimate and the methodology doc says so plainly; the tier machinery below is
estimator-agnostic.

Goalies: `goalie_gar` is already reliability-shrunk; carry its point + band straight through
**regardless of which skater candidate wins**. The bakeoff decides skaters only.

No-track-record players: no `player_gar` row => `qualified = false`, `tier = null`,
`tier_label = "insufficient sample"`.

### 6.2 Tier assignment

New config block `config.ASSESSMENT`. **RESOLVED D2 (2026-07-03):** tier boundaries are
league job counts (cumulative rank by assessed WAR within position group + window), not
percentiles.

```python
ASSESSMENT = {
    "MODEL_VERSION": "assessment_v1",
    "TIER_RANKS": {
        "F": [("elite", 18), ("first_line", 96), ("second_line", 192),
              ("third_line", 288), ("fourth_line", 384), ("fringe", None)],
        "D": [("elite", 12), ("number_one", 32), ("top_pair", 64),
              ("second_pair", 128), ("third_pair", 192), ("fringe", None)],
        "G": [("elite_starter", 8), ("starter", 32), ("tandem", 48),
              ("backup", 64), ("fringe", None)],
    },
    "TIER_REFERENCE_POOL": {"F": 384, "D": 192, "G": 64},
    "TIER_LABELS": {
        "elite": "Elite", "first_line": "First-line forward",
        "second_line": "Second-line forward", "third_line": "Third-line forward",
        "fourth_line": "Fourth-line forward",
        "number_one": "Number-one defenseman", "top_pair": "Top-pair defenseman",
        "second_pair": "Second-pair defenseman", "third_pair": "Third-pair defenseman",
        "elite_starter": "Elite starter", "starter": "Starter",
        "tandem": "Tandem goalie", "backup": "Backup",
        "fringe": "Fringe / replacement",
    },
    "CONFIDENCE_CUTS": {"high": 0.55, "medium": 0.35},   # RESOLVED D3
    "WITHIN_ONE_RANGE_COPY": 0.85,
    "STABILITY_GRADES": {"A": (3000, 3), "B": (2000, 2), "C": (None, 1)},
    "GOALIE_MAX_GRADE": "B",
}
```

Assignment (deterministic):

1. Within each (position_group in {F,D,G}, season_window), rank the qualified pool by
   `assessed_war` desc. Tier threshold for ceiling R = midpoint between assessed_war of
   rank R and R+1. If pool < deepest ceiling, apply percentile fallback and record
   `tier_mode = 'percentile_fallback'`.
2. `tier` = band containing the player's rank.
3. `tier_probs`: model WAR as Normal(assessed_war, war_sd); integrate density over each
   band's thresholds (open-ended top/bottom). Store JSON vector +
   `tier_confidence = tier_probs[tier]` + `tier_prob_within_one` (assigned + adjacent).
4. `confidence_label`: high/medium/low from CONFIDENCE_CUTS. Force low if window has one
   season.
5. `stability_grade`: A-D from STABILITY_GRADES on (window 5v5 TOI, distinct seasons);
   D = unqualified. Goalies cap at GOALIE_MAX_GRADE.
6. `role_primary` = `durable_archetype`; fall back to current-season primary archetype;
   goalies use goalie radar label.
7. `role_deployment` = deployment-based defensive sub-label from `compute_player_radar`.

Schema (`nhl_models.player_assessment`): player_id, season_window, position,
assessed_war, war_sd, war_p10, war_p90, tier, tier_label, tier_confidence, tier_probs
(JSON), tier_prob_within_one, tier_mode, confidence_label, stability_grade, role_primary,
role_deployment, qualified, pool_size, pool_position_group, toi_basis_min, seasons_present,
point_estimator (`c1_r_shrink`|`c2_roster_player`|`c3_blended`|`marcel`), inputs_hash,
model_version, generated_at.

Invariants (code + tests): tier monotone in assessed_war within a pool; tier_probs sums
to 1 +/- 1e-6; tier_prob_within_one >= tier_confidence; unqualified rows null tier/probs;
every qualified skater 2015-16+ and goalie 2021-22+ gets a row; rank/percentile math
reuses `backend/routers/players.py::_value_block` / `compute_overall.py` qualified-pool
logic.

**Pool definition (D13):** the tier pool is the **active qualified** players — qualified by the TOI
floor AND not inactive (a skater/goalie with zero games in the window's most recent season is
excluded; `qualified=false`, `disqualify_reason='inactive'`). `pool_size` counts only these.

**Boundary tie rule (RATIFIED, Amendment A 2026-07-03):** exactly `min(pool_size, ceiling)`
players sit at or above each rank ceiling in `tier_mode='rank'` — UNLESS a WAR tie spans the
boundary, in which case all tied players take the HIGHER tier (so the cumulative count may
exceed the ceiling by the tie size). Monotonicity is the stronger invariant: two players with
equal `assessed_war` must never land in different tiers. The unit test asserts this rule (equal
WAR ⇒ same, higher tier), not a raw exact-count.

### 6.3 Relationship to existing Overall

`player_overall` stays as is (card-only). Assessment is the page-level verdict; Overall
remains the percentile summary inside the card. No Overall endpoint/job changes.

## 7. Workstream 2: the context layer (Layer 2)

### 7.1 WOWY branch (ALREADY DONE — confirm nightly selector only)

Per the 2026-07-03 audit, `mart_player_onice`, `mart_player_toi_matrix`, `mart_player_wowy`
are already materialized, in `serving_tables.yml:71-77`, and consumed by an existing endpoint.
No dbt run, no serving-manifest change, no endpoint work remains here.

- **Only task:** confirm the three marts are in the nightly dbt selector so they refresh
  with the other marts (verify, add only if missing).
- D17 already enforced in `mart_player_wowy.sql` (`toi_together_sec < 3000` =>
  `small_sample = true`), passed through by the API; FE renders muted, never hidden.

### 7.2 QoC / QoT (net-new)

dbt model `mart_player_quality_context` (mart), grain (season, player_id, team_id):

- Source: `int_shift_segments` x `int_segment_context` (5v5, >= 4s, 5 skaters/side),
  joined to opposing and same-team on-ice skaters per segment.
- Quality metric per on-ice skater: prior-season shrunk WAR rate — the Marcel rate at S-1,
  persisted by the assessment job into `nhl_models.player_prior_quality` (player_id,
  season, prior_war_rate). Rookies = 0.0. Using S-1 makes QoC leak-free (D7).
- `qoc_war_rate` = TOI-weighted mean prior_war_rate of opposing skaters; `qot_war_rate`
  = same over same-team on-ice skaters (excluding self). Store `qoc_pctile`, `qot_pctile`
  and `toi_5v5_sec`. **Percentiles are ranked ONLY within the qualified pool** (5v5 TOI >=
  `MIN_TOI_5V5_FOR_RANKING` = 200 min = 12000 sec), per position group + season, so a low-TOI
  player cannot top the percentile on noise. Below-floor players keep the raw `qoc_war_rate` /
  `qot_war_rate` but carry NULL `qoc_pctile` / `qot_pctile`; `/context` passes the nulls through
  and the UI mutes them. A dbt test asserts percentile is NULL iff below the floor.
- v1 is season-level QoC/QoT LEVELS, not performance-split-by-QoC-tercile (v1.1, D11).

Run weekly (Monday gate).

### 7.3 Linemate dependence index

Computed in `compute_assessment.py` from `mart_player_wowy` + `mart_player_toi_matrix`,
stored on the assessment row: `top_partner_id`, `top_partner_toi_share`,
`dependence_index`, `dependence_n_partners`. The per-partner "with help minus alone" term is
**already precomputed** in `mart_player_wowy.sql` as `together_minus_focal_alone` (=
`xgf_pct_together − xgf_pct_focal_without_partner`); read it directly rather than recomputing.
`dependence_index` = TOI-weighted mean of `together_minus_focal_alone` over partners with
`toi_together_sec >= 3000`. Null when no partner clears 3000s. Copy uses hedged language when
`dependence_n_partners < 3`.

### 7.4 Context endpoint composition

`GET /players/{id}/context` composes existing + new reads. The fit hook is a LINK, not a
computation: payload includes the player id preformatted for Player Fit / Lineup Lab.

## 8. Workstream 3: receipts (Layer 3)

- Provenance block on `GET /players/{id}/assessment`: pool size + floor, window TOI,
  seasons present, three r-values from `GAR_STABILITY_YOY` (verbatim), point_estimator,
  model_version, generated_at, methodology slug.
- Per-component stability tags on `ComponentStackBar` (FE-only): production r=0.66, RAPM
  r=0.38, finishing r=0.35. Data already in PlayerValue (production_r/rapm_r/finishing_r).
- Verdict integration: extend `build_verdict_payload.py` with the assessment row; extend
  the `generate_verdicts` checker to verify cited tier/confidence.

## 9. Workstream 4: API

Response models in `backend/models/schemas.py`; reads via DuckDB serving file.

### 9.1 `GET /players/{player_id}/assessment` (router: players.py)

Query: `season_window` (default 3-season window, single-season fallback). Response
`PlayerAssessment` (see schema classes in spec). 404 never; unqualified => qualified=false
with nulls. Cache TTL 3600.

### 9.2 `GET /players/{player_id}/wowy?season=` — ALREADY EXISTS, do not rebuild

Implemented at `players.py:524` (`response_model=PlayerWowy`, `@cache(ttl=1800)`): reads
`mart_player_wowy`, name-joins `stg_rosters`, orders by `toi_together_sec` desc, passes
`small_sample` through. The frontend already calls it. No work here; `/context` (9.3)
composes this existing endpoint's data rather than a new route.

### 9.3 `GET /players/{player_id}/context?season=` -> `PlayerContext`

Composes strength splits (`get_player_situational`), zone deployment
(`get_player_zone_deployment`), QoC/QoT (`mart_player_quality_context`), top-5 WOWY rows,
fit deep-link slugs.

### 9.4 Explicitly NOT built

No `/rankings/tier`, no tier sort param, no tier filter producing a 1..N ordering.
Rankings rows MAY display the tier chip (read-only).

## 10. Workstream 5: frontend

### 10.1 PlayerProfile Overview — `AssessmentBand.tsx` (first block of Overview)

**Visual system (RATIFIED V1-V6, 2026-07-03).** The band renders a **headline + meta line +
ladder histogram** — NOT the deterministic sentence (V5). Layout: (V1) quiet muted role eyebrow →
**tier label as the headline** (~26px, weight 500); when the range-copy rule fires the RANGE is the
headline (e.g. "Elite or first-line"). (V2) A **ladder histogram** replaces the dash strip: one
equal-width column per tier in ladder order (F/D six, G five), fill height = tier probability,
assigned tier(s) in the accent data color, near-zero columns are empty wells; % labels above
columns ≥5%, short tier labels beneath. (V3) **Single-meaning color** — green/amber/gray are
reserved for CONFIDENCE only (dot + word High/Medium/Low); tier is size/weight, never color; accent
blue is data ink only. (V4) stability_grade DISPLAYS as "Sample A/B/C" (field/API names unchanged),
tooltip states thresholds; confidence display caps at ">99%", never 100% (exact value in tooltip/API).
(V5) The deterministic **sentence is not printed in the band** — the headline + meta carry the
verdict; single-season meta reads "Low confidence, single-season window, sample C". (V6) no
overlapping single-season banner. The sentence rules below govern the **API response and verdict
copy only** (unchanged); the band renders headline+meta per V1-V5.

- **Sentence selection (RATIFIED, Amendment B 2026-07-03) — governs API + verdict copy; evaluate in this order:**
  1. **Single-season fallback window** (`season_window` has no `_`): use the single-season
     template — plain tier + a single-season hedge + grade, NOT a range
     (e.g. "Elite on a single-season sample, stability grade C"). The `confidence_label` still
     displays as forced-low; only the sentence changes.
  2. **Range copy** — trigger on RAW values, not the forced label:
     `tier_confidence < CONFIDENCE_CUTS["high"]` AND
     `tier_prob_within_one >= WITHIN_ONE_RANGE_COPY` → name the two heaviest adjacent tiers as
     a range (e.g. "Likely an elite or first-line forward (98% combined), grade A").
  3. **Otherwise** — name the assigned tier with the confidence word.
  This applies verbatim to verdict prose via payload + checker. Keying on `tier_confidence`
  (not `confidence_label`) prevents a concentrated-mass single-season player (McDavid 2025-26,
  99% elite) from being mislabeled as a straddle.
- Unqualified state: muted band, "Not enough NHL sample to assess (needs X 5v5 minutes)".

### 10.2 New Context tab

Add `context` to TAB_VALUES. Sections: strength splits, deployment, QoC/QoT (two
percentile dials + copy), WOWY table (small_sample muted, dependence index with n), and a
"Try him elsewhere" card deep-linking Player Fit / Lineup Lab.

### 10.3 Row previews and rankings

`PlayerRowExpansion.tsx`: TierBadge + confidence pill next to archetype chips. Rankings /
Players index rows: tier chip only, display-only.

### 10.4 States (exhaustive)

qualified/full; qualified low-confidence; single-season fallback (meta line); unqualified;
inactive (D13); pre-2015-16 (assessment absent, descriptor fallback); goalie (ladder + capped
grade note); Context: muted null-percentile QoC/QoT row.

### 10.5 M3.5: Players index simplification (D14, resolved 2026-07-03)

Runs AFTER the M3 checkpoint clears. Small pass: FE + one ordering change + tests + docs.

1. ORDERING. The Players index ranks by `player_assessment.assessed_war` for all scopes (skaters,
   goalies, mixed; per selected season or window). Rationale, recorded: assessed WAR is
   reliability-shrunk at the root (C2 skaters, shrunk goalie GAR), so the presentation-layer
   half-sd sort key (`CONFIDENCE_SORT_K`) is redundant; it was built to fix noisy goalies
   out-ranking skaters before root shrinkage existed. The displayed number stays the point
   estimate with the error-bar band.
2. RETIRED CONTROLS. Remove the Confidence-adjusted | Point estimate toggle and the
   Rank by [Total value | Play-driving | Production] tabs from the toolbar. The toolbar keeps:
   mode (Rankings | Usage and Value), Show, Season, search. Backend: `/rankings/value` still
   ACCEPTS the sort param for compatibility but the FE no longer sends it; mark it deprecated in
   BACKEND_API.md. `getOverallLeaders` and all lens endpoints are unchanged (no API removals). The
   How we measure value note gains one sentence: ranking uses the reliability-shrunk assessed
   estimate, and lens disagreements live on the Usage and Value board (link).
3. TIER PRESENTATION. Index rows show the TierBadge (display-only). When a position filter (F/D/G)
   is active, render tier group separators at boundary crossings, labeled from TIER_LABELS.
   Separators ANNOTATE the existing assessed-WAR order (tiers are monotone in assessed WAR by
   invariant); they are never a control. Mixed All scope: chips only, no separators (ladders are
   per position group and would interleave).
4. CONSISTENCY. The index order must equal the tier pool order: same source table, same qualified
   pool (active per D13), same tie rule. Add a test asserting (a) filtered list order ==
   assessed_war desc from player_assessment, and (b) separator positions match the rank ceilings
   with the tie-takes-higher rule.
5. UNCHANGED RULES. No /rankings/tier, no tier sort or rank param, no detail page changes.
   Unqualified and inactive players remain excluded from ranked pools.
6. RELEASE VALVE (owner-revisitable): if users ask for one-click component leaderboards back, the
   first remedy is an overflow lens menu, not restored co-equal tabs.

Mock-derived refinements folded in: (a) separators include tier counts ("Elite defensemen · 12");
(b) rows use a shared-axis interval (thin track, ±1 sd band, point dot) instead of a filled
magnitude bar, keeping the visibly wider goalie bands in mixed view; (c) tabular numerals on
rank/value; (d) one typeface family page-wide (retire the display mono headline); (e) the expanded
methodology paragraph collapses to a one-line caption ("Ranked by assessed WAR, the
reliability-shrunk estimate. Bands show ±1 sd. N qualified.") with the How-we-measure-value link
retained; (f) filtered views show separators without per-row chips; mixed view shows chips without
separators.

## 11. Orchestration, serving, docs wiring (checklist)

- `dags/nhl_daily.py`: Monday-gated `compute_assessment`;
  `[compute_gar, compute_goalie_gar, write_archetypes] >> compute_assessment >>
  generate_verdicts`; `compute_assessment >> generate_report`. dbt build of
  `mart_player_quality_context` into the marts run (WOWY marts already in the run).
- Makefile: `assessment`, `assessment-validate` (+ `.PHONY`).
- `serving_tables.yml`: add `player_assessment`, `mart_player_quality_context`,
  `player_prior_quality` (the WOWY marts are already present). Then `make export-serving`.
- `scripts/verify_serving_parity.py`: probes for three new service methods.
- dbt `schema.yml` + tests for `mart_player_quality_context`.
- Docs: `player-assessment.md`, `player-context.md`, `assessment-prereg.md` (BEFORE eval),
  update `FEATURE_MAP.md`, `BACKEND_API.md`.
- Tests: `tests/test_assessment.py`, baselines unit test, endpoint tests (unqualified +
  goalie).

## 12. Sequencing and milestones

| M | Contents | Exit criteria | Effort |
| --- | --- | --- | --- |
| M0 | baselines.py, value_lens.py (3-candidate interface), validate_assessment.py, prereg | T1 table (naive/Marcel/C1/C2/C3) for 2024-25 + 2025-26; gate G1 + winner decided | 4-7 d |
| M1 | compute_assessment.py, config, table, DAG/Make/serving, /assessment | spot list correct; invariants green; parity green | 4-6 d |
| M2 | quality_context + prior_quality; /context (WOWY already served — consume it) | dbt tests green; D17 respected; QoC sane | 3-5 d |
| M3 | AssessmentBand, Context tab, row chip, all 10.4 states | all states demoed; no tier sort; screenshots | 4-6 d |
| M4 ✅ | Verdict payload + checker, receipts provenance, docs, FEATURE_MAP/BACKEND_API; **D15** one tier vocabulary | checker verifies tier-citing verdict; docs merged | **COMPLETE 2026-07-03** |

**Initiative complete through M4 + D15 (2026-07-03).** M0 validation harness → M0.5 backtest
expansion (C4 not promoted) → M1 assessment model (C2) → M2 context layer → M3 frontend + M3.5 index
→ M4 verdict/receipts/docs + D15 single tier vocabulary → P1 linemate-dependence columns (spec 7.3)
now populated on `player_assessment` (`top_partner_id`, `top_partner_toi_share`, `dependence_index`,
`dependence_n_partners`); the verdict payload carries real values and the checker's hedged-dependence
rule (n < 3) is live.

M0 blocks M1 (the gate decides the point estimator). M2 runs parallel to M1 (WOWY already
served, so no dbt-run prerequisite). M3 needs M1 + M2. Net total unchanged (~3-4 weeks
solo): the 1-2 days M0 gains from the three-candidate bakeoff are recovered in M2 from the
already-shipped WOWY work.

## 13. Risks and constraints

- BigQuery cost/storage: the QoC segment aggregation is the only meaningful QUERY cost —
  weekly cadence bounds it. STORAGE is NOT within the free tier: the project holds ~25 GB
  (predominantly pre-existing `nhl_raw` ~14 GB + `nhl_staging` ~9.5 GB, from ingest back to
  2010-11), which exceeds the 10 GB BigQuery free-storage line (owner-acknowledged; ~$0.30/mo
  at standard rates). The model tables this initiative adds are negligible: `player_assessment`
  is a few thousand rows, and the 2015-16 value backfill appended ~5.4k rows each to
  `player_impact`/`player_gar` (tens of MB), so this work does not move the storage line.
- Data floors: RAPM/segments 2015-16+; assessment starts 2015-16 (skaters), follows
  goalie_gar for goalies. Pre-floor renders fallback.
- Adjacent-tier honesty: many players straddle two tiers ~45/40 — product working, not a
  bug; probability strip + range copy rule exist for this.
- Boundary drift: rank ceilings fixed, WAR at each ceiling moves weekly; store thresholds
  (inputs_hash). Tier-change copy cites the WAR move, not a rules change.
- Gemini: tier language rides weekly-active scope; full backfill needs paid tier.
- DuckDB export lock: exports require backend stopped; use `--only` for dev.
- Archetype season flips: roles from `durable_archetype`, not single-season primary.

## 14. Decisions (defaults ship if unanswered)

| # | Decision | Default |
| --- | --- | --- |
| D1 | Table/feature name | `player_assessment`, UI word "Assessment" |
| D2 | Tier names + boundaries | RESOLVED: league job-count rank ceilings (6.2) |
| D3 | Confidence labels + straddle | RESOLVED: cuts 0.55/0.35; within-one 0.85 range rule; T4 diagnostics |
| D4 | Apply aging to assessed WAR? | No |
| D5 | Stability grade thresholds + goalie cap | as specced; goalies cap at B |
| D6 | Marcel constants | weights 5/4/3, K=1800 min / 1500 shots |
| D7 | QoC quality source | prior-season Marcel rate, rookies = 0 |
| D8 | Retire/keep player_overall | Keep unchanged |
| D9 | Tier chip on Rankings rows | Yes, display-only |
| D10 | Default window on endpoint | 3-season window, single-season fallback |
| D11 | Performance-by-QoC-tercile | Deferred to v1.1 |
| D12 | Publish T1 benchmark publicly | Owner call |
| D13 | Inactive players in the tier pool | RESOLVED 2026-07-03: EXCLUDED (see below) |
| D14 | Players index ranking + controls | RESOLVED 2026-07-03: rank by assessed_war; retire confidence toggle + rank-by tabs; tier separators (filtered) / chips (mixed); `/rankings/value` sort param deprecated. See §10.5 |
| D15 | One tier vocabulary | RESOLVED 2026-07-03: the assessment tier ladder (`config.ASSESSMENT["TIER_LABELS"]`, sourced from `player_assessment`) is the ONLY player value vocabulary rendered anywhere. The legacy percentile→noun mapping (`_value_tier`: elite/high-end/middle-tier/depth/fringe) retires from the expansion chip and the verdict identity anchor (anchor → `tier_label`). SCOPE: value-tier mapping only — archetype names containing "Elite", team-needs/trade-fit copy, and radar spoke adjectives are OUT of scope. |

**D13 — Inactive players excluded from the tier pool (RESOLVED 2026-07-03).** The ladder's premise
is league job counts; a player who has not skated in the window's most recent season cannot occupy
a job slot (the Shattenkirk case: last played 2023-24, still appeared at second_pair in the current
window). Rule: a skater or goalie with **zero games in the window's MOST RECENT season** is excluded
from tier assignment — his row returns `qualified=false`, `disqualify_reason='inactive'`, and
`last_played_season` populated; historical single-season rows are untouched; `pool_size` reflects the
exclusion. Schema additions to `player_assessment` and the `PlayerAssessment` model:
`disqualify_reason STRING NULL`, `last_played_season STRING NULL`. Unqualified copy for this case:
"Inactive, last played {season}". NOTE: a player injured for the entire most recent season also reads
inactive under this rule — the accepted default, owner-revisitable.

## 15. Out of scope

ppt-replay/tracking; any change to xG, RAPM, archetype fits or schemas; public
multi-model leaderboard; card visual redesign beyond 10.1-10.3; betting-market
comparisons; historical backfill of segments to 2010-14.

## 16. Appendix: file-by-file change list

**New:** `models_ml/baselines.py`, `models_ml/value_lens.py` (shared 3-candidate interface,
not an extraction),
`models_ml/compute_assessment.py`, `models_ml/validate_assessment.py`,
`dbt/models/mart/mart_player_quality_context.sql` (+ schema.yml),
backend schema classes + 3 routes in `routers/players.py`,
`frontend/src/components/players/AssessmentBand.tsx`, `TierBadge.tsx`,
Context tab section components, `docs/methodology/player-assessment.md`,
`docs/methodology/player-context.md`, `docs/methodology/assessment-prereg.md`,
`tests/test_assessment.py`.

**Modified:** `models_ml/config.py` (ASSESSMENT block),
`models_ml/build_verdict_payload.py`, `models_ml/generate_verdicts.py` (checker),
`dags/nhl_daily.py`, `Makefile`, `serving_tables.yml`,
`scripts/verify_serving_parity.py`, `frontend/src/pages/PlayerProfile.tsx`,
`frontend/src/components/players/PlayerRowExpansion.tsx`,
`frontend/src/api/players.ts`, `docs/system/FEATURE_MAP.md`, `docs/system/BACKEND_API.md`.

**Materialized (no code change):** `mart_player_onice`, `mart_player_toi_matrix`,
`mart_player_wowy` via dbt run, then exported.

## 17. Deferred and Open Items (2026-07-03 close-out)

The initiative is closed through M4 + D15 + P1. The following are intentionally out of the shipped
scope and recorded here so nothing lives only in chat:

- **D11 — QoC/QoT performance-by-tercile splits** → v1.1. Shipped v1 is QoC/QoT LEVELS only; the
  tercile performance split (how a player does vs weak/median/strong competition) needs a
  segment rollup keyed by opponent-quality bucket.
- **C4 revisit** → only after 2026-27 adds a fresh transition, and only under a NEW preregistration
  (per prereg v3). C4 was not promoted; it remains a documented also-ran in `value_lens`.
- **2010-14 segment backfill** → deferred and UNCOUPLED from this initiative. RAPM/segments start
  2015-16; extending to 2010-14 is a separate workstream (watch the 10 GB storage line) and must not
  be coupled to assessment work.
- **Full verdict regeneration** → owner-triggered (`generate_verdicts --full`), bounded by the
  free-tier Gemini quota. The **weekly-active scope converges active players' verdicts to the new
  D15 tier vocabulary automatically** — a full backfill only accelerates the tail (inactive /
  not-recently-played players).

Landed this close-out (no longer deferred): **P1** — linemate-dependence columns
(`top_partner_id`, `top_partner_toi_share`, `dependence_index`, `dependence_n_partners`) are
populated on `player_assessment` from `mart_player_wowy` (D17: partners with `toi_together_sec >=
3000`); the verdict payload carries real values and the checker's hedged-dependence rule (n < 3) is
active. Nightly export serves the new columns.
