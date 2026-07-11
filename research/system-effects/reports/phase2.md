# Phase 2 — System fingerprints v2

**Project:** System Effects · **Date:** 2026-07-11 · **Seed:** 20260711
**Status:** Phase 2 complete. The discontinuity test (the phase centerpiece) returns a
clear, consequential result that shapes Phase 3 — see **§5** and **§7**. Stopping for review.

Frozen-asset provenance: Atlas freeze `24acbab`; rebuild PR #1 merged (`8148462`).
Reproduce: `make phase1 && make phase2` (seq/prim/deploy cached under `data/parquet/`).

---

## 0. Consolidation (Phase 1 §6, Option A — implemented as approved)

`is_transient_stint` with **K=4**: a raw regime of ≤4 games whose predecessor and
successor regimes (same team) are the **same** coach is a fill-in; it is absorbed and the
flanking same-coach regimes merge across it, applied to a fixpoint. The **raw ledger is
preserved unchanged** (235 rows) and gains `is_transient_stint`, `consolidated_start_game_id`,
and `absorbed_into` (parentage). The **consolidated analysis regime is the unit for all
later phases** (`regime_ledger_consolidated.parquet`, 201 regimes).

**K sensitivity (regimes absorbed / consolidated count):**

| K | transient absorbed | consolidated regimes |
|---|---:|---:|
| 3 | 16 | 203 |
| **4 (adopted)** | **17** | **201** |
| 5 | 18 | 199 |

Insensitive to K in [3,5]; K=4 chosen as specced. Raw = 235.

**Recomputed plausibility on the consolidated view** — the implausible tail collapses:

Regimes-per-team-season (494 team-seasons): **1 → 424 · 2 → 65 · 3 → 4 · 4 → 1**
(raw was 1:424, 2:60, 3:3, 4:3, 8:1, 10:2, 11:1). The lone remaining "4" is NJ 2014-15,
the genuine co-coach committee — honestly irreducible.

Mid-season changes per season (raw → consolidated): 2014-15 **14→6**, 2020-21 **12→4**,
**2021-22 23→9**. All seasons now fall in/near the expected band; full table:

| season | chg | season | chg | season | chg |
|---|--:|---|--:|---|--:|
| 2010-11 | 2 | 2015-16 | 3 | 2020-21 | 4 |
| 2011-12 | 9 | 2016-17 | 5 | 2021-22 | 9 |
| 2012-13 | 2 | 2017-18 | 0 | 2022-23 | 1 |
| 2013-14 | 4 | 2018-19 | 7 | 2023-24 | 7 |
| 2014-15 | 6 | 2019-20 | 8 | 2024-25 | 5 |
| | | | | 2025-26 | 4 |

Cohort C is unchanged (defined on raw mid-season changes; 15-game floor already immune).

---

## 1. Reuse audit — `mart_team_identity` (2.0, rule 7b)

**(a) Lineage + reconciliation.** `mart_team_identity` style shares derive from
`int_shot_sequence.seq_type` (rebuild-backbone: uses `int_on_ice_events`/`int_segment_context`
for ice strength; refit 2026-07-11). Reconciled its per-team 2016-17 season shares against
our **frozen-stint recompute**:

| metric | mean abs Δ | max abs Δ | corr |
|---|---:|---:|---:|
| rush_share_for | 0.0011 | 0.0045 | 0.980 |
| cycle_share_for | 0.0025 | 0.0101 | 0.969 |
| forecheck_share_for | 0.0013 | 0.0055 | 0.977 |
| point_shot_share_for | 0.0020 | 0.0086 | 0.987 |

Shares reconcile within ~0.1–0.25pp (r 0.97–0.99). The one material difference is the 5v5
shot **count**: frozen-stint strength yields ~8% fewer 5v5 shots than production's rebuilt-
segment strength (2016-17: 82,562 vs 89,560) — the *composition* is robust to the backbone,
the *denominator* is not. **(a) passes for share components.**

**(b) UL-1 contamination.** `mart_team_identity`'s season comes from `stg_boxscores`, **not**
`stg_games`. Checked `mart_team_identity_inputs`: **0 / 41,894** rows have a season ≠ the
game_id-prefix season. Clean — the UL-1 mislabel (UL-1) does not reach it. **(b) passes.**

**(c) Grain.** `mart_team_identity` is per (team, season, `window_kind`) — 988 rows, 2
windows. It **cannot** express a regime-level discontinuity. Confirmed.

**Decision.** (a) and (b) pass → `mart_team_identity` share components are adoptable for
**season-level display**. Per (c) and the project rule, **all regime-level fingerprints are
derived from frozen assets regardless** (below). Reused verbatim: the `int_shot_sequence`
seq_type rules + window vars (documented in `sequence.py`).

Phase-3 note (per instruction): production `train_style_effect.py` answers a **playoff-series**
style-matchup question (series win prob from same-season fingerprints). The Phase 3.4 opponent
track must audit it and define its delta explicitly — **per-game and per-player** style
adjustment + schedule bias, *not* series win probability — rather than duplicating it.

---

## 2. Metric set as implemented (5v5 unless stated)

Built as **summable per-(game, team) primitives** (`fingerprints.py`), so any game set — a
consolidated regime, a season, an odd/even split — aggregates by summation.

**Score adjustment (documented per metric).** Attempt-rate/share and location metrics respond
to score state, so they are computed on **score-close** play only: stint `|score_state| ≤ 1`
(within one goal), the ice-derived differential from frozen stints. Deployment metrics
(top-6 share, zone-start polarization) are not score-sensitive → all 5v5.

| metric | definition (frozen) | score-adj |
|---|---|:--:|
| **pace** | (Corsi-for + Corsi-against)/60 on-ice, from stints | close |
| **rush/cycle/forecheck/point_shot _share_for** | seq_type fraction of unblocked 5v5 attempts for (`sequence.py`, reused int_shot_sequence rules; windows rebound 3s/rush 4s/forecheck 5s/cross-ice 2s/cycle 10s; precedence rebound>rush>forecheck>cycle>point_shot>other) | close |
| **rush/cycle _share_against** | same, opponent's attempts | close |
| **shot-location-against** (inner/outer/point) | point = seq_point_shot (\|x\|≤40 & zone O); else inner if \|y\|≤9 else outer; shares of attempts against | close |
| **attack-origin-against** | rush_against vs in-zone (=1−rush) | close |
| **forecheck_pressure_per60** | (OZ takeaways by team + DZ giveaways forced from opp) per 60 5v5; **possession proxy = TOI** (per-60 rate), documented | rate |
| **PP shot-location-for** (inner/outer/point) | same zones, shots on the man-advantage (strength_state + shooter side) | n/a |
| **top6_fwd_toi_share** | top-6 forwards' 5v5 TOI / team forward TOI (reuses Atlas `context` formula) | all 5v5 |
| **zone_start_polarization** | std of players' OZ-start share (players ≥50 5v5 min) | all 5v5 |

**Deployment fingerprints — build-the-delta.** Two of the four Atlas fingerprints
(**top-6 forward TOI share, zone-start polarization**) are fully re-derived from frozen
stints at **both regime and season grain** (own summable primitives, `fingerprints.py`) and
enter the reliability + discontinuity sets below. The other two — `close_game_shortening` and
`home_away_strictness` — are derivable multi-season via the established Atlas path
(`context.coach_fingerprints(season)`), but that per-season function re-reads the full stint
corpus repeatedly and is I/O-heavy; batch regeneration across 16 seasons is **deferred** (the
path is proven, the run is slow) and these two are **not** in the tested set. This is a
deliberate, honest scoping call: `home_away_strictness` carries the Atlas **failed-validation
caveat** (descriptive only), so its absence from any coaching-sensitivity claim is correct;
`close_game_shortening` is a watch-list item for Phase 3 if needed.

---

## 3. Reliability (2.2) — split-half (odd/even games), regimes ≥40 games

184 qualifying consolidated regimes. Pearson r of metric(odd) vs metric(even). **None below
0.5 — nothing flagged.**

| metric | r | metric | r |
|---|--:|---|--:|
| top6_fwd_toi_share | **0.994** | loc_point_against | 0.665 |
| forecheck_pressure_per60 | 0.905 | rush_share_for | 0.653 |
| zone_start_polarization | 0.910 | loc_inner_against | 0.638 |
| pace | 0.848 | point_shot_share_for | 0.631 |
| cycle_share_against | 0.779 | forecheck_share_for | 0.616 |
| cycle_share_for | 0.749 | rush_share_against | 0.614 |
| loc_point_against | 0.665 | loc_outer_against | 0.614 |

Deployment + pace + forecheck-pressure are highly reliable (0.85–0.99). The seq-share and
location metrics are **moderately** reliable (0.61–0.78); carried with a mild caveat (they
sit above 0.5 but their per-regime signal is noisier), which matters for §4.

---

## 4. The discontinuity test (2.3) — does each metric measure *coaching*?

For every Cohort C change (49), the metric's shift old-regime→new-regime within the change
season; compared to the shift distribution across **424 placebo splits** (random midpoint
splits of one-regime, no-change team-seasons, seed 20260711). A metric that moves more at real
coach changes than at placebos is coaching-sensitive; one that does not is a roster property.
Flagged **coaching-sensitive** iff mean-ratio > 1.25 **and** permutation p < 0.05 (2000 perms).

| metric | median \|Δ\| real | median \|Δ\| placebo | mean ratio | perm p | sensitive |
|---|---:|---:|---:|---:|:--:|
| **zone_start_polarization** | 0.0227 | 0.0144 | **1.92** | **0.0005** | ✅ |
| **top6_fwd_toi_share** | 0.0222 | 0.0156 | **1.27** | **0.023** | ✅ |
| forecheck_share_for | 0.0086 | 0.0074 | 1.21 | 0.038 | – (ratio<1.25) |
| loc_outer_against | 0.0202 | 0.0174 | 1.19 | 0.059 | – |
| pace | 3.385 | 2.844 | 1.18 | 0.064 | – |
| cycle_share_for | 0.0128 | 0.0132 | 1.12 | 0.152 | – |
| loc_inner_against | 0.0179 | 0.0166 | 1.10 | 0.205 | – |
| rush_share_against | 0.0083 | 0.0075 | 1.10 | 0.194 | – |
| loc_point_against | 0.0144 | 0.0140 | 1.06 | 0.301 | – |
| point_shot_share_for | 0.0111 | 0.0113 | 1.02 | 0.426 | – |
| forecheck_pressure_per60 | 0.849 | 0.728 | 1.00 | 0.495 | – |
| rush_share_for | 0.0074 | 0.0076 | 0.97 | 0.620 | – |
| cycle_share_against | 0.0112 | 0.0116 | 0.93 | 0.733 | – |

**Result.** Only the two **deployment** metrics move significantly more at real coach changes
than at placebo splits — decisively so for zone-start polarization (nearly 2×, p=0.0005). The
**style** metrics (rush/cycle/point-shot shares, shot-location profiles, pace, forecheck
pressure) are **statistically indistinguishable from placebo**; three are mildly elevated
(forecheck_share_for, pace, loc_outer_against: p≈0.04–0.06) but none clears both thresholds.

**Interpretation.** At the resolution of within-team, one-season coach changes, coaching most
measurably changes **deployment** — *who* plays (top-6 concentration) and *how they start*
(zone-start polarization). On-ice **shot-style composition is largely a roster property**, not
a system property, over this cohort. This is consistent with the project's thin one-season
headroom (5v5 xG share split-half ≈ 0.70) and is exactly what the placebo design was built to
detect. It is a constraint on the whole project, reported as a product (§7).

---

## 5. Example fingerprints (three regimes)

Score-close shares; full vectors in `phase2_analysis.json`.

| metric | CHI 2012-13 (48g) | CAR 2023-24 (82g) | BOS '24-25 Montgomery (20g) | → Sacco (62g) |
|---|--:|--:|--:|--:|
| pace | 100.1 | 120.0 | 111.1 | 114.6 |
| rush_share_for | .045 | .050 | .106 | .085 |
| cycle_share_for | .154 | .150 | .104 | .087 |
| forecheck_share_for | .040 | .044 | .037 | .049 |
| point_shot_share_for | .111 | .126 | .128 | .131 |
| loc_inner_against | .354 | .330 | .279 | .297 |
| loc_outer_against | .509 | .520 | .528 | .529 |
| loc_point_against | .137 | .150 | .194 | .175 |
| forecheck_pressure/60 | 8.19 | 8.29 | 11.67 | 10.28 |
| pp_loc_inner_for | .303 | .396 | .377 | .348 |
| **top6_fwd_toi_share** | .543 | .520 | .523 | .515 |
| **zone_start_polarization** | .067 | .058 | .119 | **.165** |

The illustrative BOS Montgomery→Sacco change shows the pattern: **zone-start polarization
jumps (.119→.165)** while top-6 share barely moves and the style shares wander within the
roster-noise band the discontinuity test quantifies. CHI 2012-13 (Quenneville) and CAR
2023-24 (Brind'Amour) read as expected — CAR high-pace, forecheck-heavy; CHI cycle-heavy.

---

## 6. Artifacts
`data/parquet/seq/*` (16 seasons, frozen int_shot_sequence recompute) ·
`prim/*`, `deploy/*` (summable primitives, incl. regime-level top-6 share + zone-start
polarization) · `regime_ledger_consolidated.parquet` (201) · raw `regime_ledger.parquet`
(235, now annotated) · `reports/phase2_analysis.json`. (Season-level
`close_game_shortening`/`home_away_strictness` regeneration deferred — §2.)

---

## 7. For review — the finding that shapes Phase 3

The discontinuity test validates **deployment** (top-6 concentration, zone-start
polarization) as coaching-sensitive and finds **on-ice shot-style composition largely a
roster property** at this cohort's resolution. Recommendation for Phase 3:

1. Anchor per-player **portability** on the validated coaching-sensitive axes (deployment),
   and treat the style metrics as **descriptive context**, carried with the §4 caveat — do
   not build portability claims on metrics that behave like placebo.
2. Keep the mildly-elevated trio (forecheck_share_for, pace, loc_outer_against) as
   **watch-list** metrics — possibly coaching-sensitive with more power (49 changes is a
   small cohort); revisit if Phase 3 adds the movers track's leverage.
3. The two clean deployment metrics + pace + forecheck-pressure are the reliable core
   (r ≥ 0.85). Style shares (r 0.61–0.78) go in with their reliability caveat.

No new upstream defects in Phase 2. `home_away_strictness` retains its Atlas failed-validation
caveat and is excluded from any coaching-sensitivity claim. **Stopping for review.**
