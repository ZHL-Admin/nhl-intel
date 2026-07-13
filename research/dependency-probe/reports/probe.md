# Dependency probe — feasibility report

**Project:** dependency-probe (`NIR/research/dependency-probe/`)
**Date:** 2026-07-13 · **Seed:** 20260713b · own `.venv` · polars 1.42 · scikit-learn
**Purpose:** a third angle on fit, after two nulls. Not joint OUTPUT (pair residuals, **F17**; unit
over-performance, **F18** — both failed) but individual **behavior conditioned on teammates**: does a
player change what he DOES by partner (Link A), is that dependence a stable individual trait (Link B),
and does dependence on a departing teammate predict what happens to him (Link C)? The outcome is a
property of ONE player, which sidesteps the identifiability walls the prior arcs hit. Three gates;
nothing promoted or published.

**Standing confound (addressed, not caveated away):** behavioral dependency is tangled with
**deployment** — A does X with B partly because the coach plays them together in certain situations.
Every dependency measure is tested against a deployment control; movement that vanishes once
deployment is controlled is reported AS deployment. **Proxy honesty:** the FEEDING signal is
shot-adjacent sequence inference, **not** true passing (off-puck and non-shot passes are invisible —
Tier iii of the role-fit ceiling).

---

## Inventory (Link A open)

**Scaffold.** Dedicated branch `research/dependency-probe` (off the research tip; folder-isolated,
removable, no production imports). Own venv; Makefile target per link; `data/` gitignored. Reuses the
Chemistry stint-expansion (`import chem.corpus`) and — REQUIRED — the role-fit probe's enriched
event-player attribution (recovered six columns, validated + hashed). **The enriched corpus is
present**; the probe would STOP without it.

**Frozen inputs (read-only), timestamps:**

| asset | mtime |
|---|---|
| atlas/stints, events, rapm_variant, rosters | 2026-07-10 |
| role-fit-probe enriched/event_players.parquet | 2026-07-13 11:47 |
| role-fit-probe enriched/faceoffs.parquet | 2026-07-13 11:47 |
| chemistry/pairs_corpus (deployment context) | 2026-07-12 22:03 |
| system-effects/player_types | 2026-07-11 21:08 |

Scope: primary window 2015-16→2025-26 (`is_primary_scope`; UL-P2 lesson from the role-fit probe).
Events located in their stint by an as-of time join (validated **99.8%** matched).

---

## LINK A (GATE) — does a player's behavior change by partner, measurably?

**A.1 Behavioral axes** per (focal player A, season, partner B) over their shared 5v5 ice, at a
100-shared-minute floor (directed; A's OWN behavior conditioned on B):

| axis | definition | family |
|---|---|---|
| `A_sh60` | A's shot-attempt rate | shooting assertion |
| `A_shot_share` | A's share of the pair's combined attempts (deference vs assertion) | shooting |
| `A_feed60` | A-event immediately precedes a B shot within 4 s (shot-adjacent **proxy**) | feeding |
| `A_hit60` | A's hit rate | physicality |
| `A_tk60`, `A_gv60` | A's takeaway / giveaway rates | possession risk |
| `A_ozsh60` | A's offensive-zone shot rate (D-pair activation proxy) | activation |

All are A's individual events, attributed via the enriched actor ids and located in stints shared with
B. Sensitivity floors 75/150 min reported alongside 100.

**A.2 within-player across-partner test.** For focal players with **3+ qualifying partners**
(7,010 player-seasons, 84,799 directed (A,B) rows at 100 min), each (A,B) axis is split odd/even by
shared game; A's partner-specific **deviation** d(A,B) = x(A,B) − mean over A's partners is computed
per half; the **reliability** is the TOI-weighted corr(d_odd, d_even) — does A's shift-with-B repeat
across halves, or is it sampling noise? Placebo = shuffle partner labels within player-season
(500 perms, seed 20260713b).

**A.3 deployment control.** Each axis is residualized on the shared-minutes deployment context
(OZ-start share, score-state mix, from the validated Chemistry pair corpus) and A.2 is re-run on the
residual. Movement that survives is dependency; movement that vanishes is deployment.

| axis | raw reliability (p) | deployment-controlled (p) | across-partner SD | survives? |
|---|---:|---:|---:|:--:|
| **`A_shot_share`** (deference) | **+0.352** (0.002) | **+0.352** (0.002), retained **1.00** | **±0.10 share** | **YES** |
| `A_feed60` (feeding proxy) | +0.061 (0.002) | +0.060 (0.002) | ±0.32/60 | no (<0.10 floor) |
| `A_hit60` (physicality) | −0.056 (1.0) | +0.090 (0.002) | ±1.5/60 | no (<0.10 floor) |
| `A_sh60` (shot rate) | −0.004 (0.87) | −0.004 (0.82) | ±2.4/60 | no |
| `A_tk60` / `A_gv60` (possession) | −0.10 / −0.09 (1.0) | −0.10 / −0.08 (1.0) | ±0.8 / ±0.9 | no |
| `A_ozsh60` (D activation) | −0.032 (1.0) | −0.036 (1.0) | ±1.9/60 | no |

**Reading.** Only **shooting deference/assertion** genuinely moves by partner: a player's *share* of
the pair's shot attempts reliably shifts with who he's with (reliability **0.352**, beats placebo
p=0.002), it is **material in absolute terms** (across-partner SD ≈ **0.10** — with one partner a
player takes ~55% of the pair's attempts, with another ~45%), and it **fully survives** the deployment
control (retained 1.00 — OZ/score explain none of it). It **strengthens with more shared minutes**
(reliability 0.32 / 0.35 / 0.41 at the 75 / 100 / 150-min floors), the signature of real signal, not
noise. Notably, a player's shot *rate* (`A_sh60`) does **not** move by partner — his volume is his
own; what changes is whether he **shoots or defers** given the partner. Physicality, possession, and
D-activation do **not** move by partner beyond noise (raw reliabilities ~0 or negative); the
shot-adjacent feeding proxy beats placebo but is too thin (0.06) to carry weight — and it is only a
Tier-iii shadow of passing anyway.

**A.4 Verdict (pre-stated).** PASS requires ≥2 axes surviving the deployment control; **if only
shooting-deference survives, proceed SCOPED to that axis (the owner's shot angle).** Exactly one axis
survives — `A_shot_share`. → **PASS (scoped to shooting deference/assertion).** Dependency is **not**
deployment in disguise here: the one real partner-conditioned behavior is a genuine individual
choice, robust to the deployment control and to the shared-minute floor.

### ⛔ STOP for review before Link B
Link A passes, scoped to shooting deference. On the owner's go, Link B collapses each player's
shot-share swing-across-partners into a per-player **dependence score** and tests whether *that* is a
stable, repeating individual trait (split-half, YoY same-team, and the across-team-change retention
that decides whether a Link C predictor could travel). The other axes are carried as descriptive
nulls (behavior there is player-constant, not partner-conditioned) — itself a clean finding.

### Decisions & artifacts (Link A)
- Reliability-of-deviation design (split-half of the within-player partner deviation) with a
  within-player partner-shuffle placebo (500 perms); deployment control by residualizing on OZ/score.
  Survival rule pre-stated: retained ≥ 0.5× raw AND controlled reliability ≥ 0.10, beating placebo.
- `src/deppro/{config,behavior,linkA}.py`; `reports/linkA_analysis.json`; `data/parquet/behavior/*`
  (gitignored). Reproduce: `make linkA`. Reuses the role-fit enriched attribution + Chemistry
  stint-expansion; frozen inputs untouched.

**STOP — owner review before Link B.**

---

## LINK Q (Round 2) — do QUALITY / LOCATION / DECISION axes move by partner? → **no new axis clears; quality & location are the player's own**

Same conditioned-on-partner test as Round 1 (reliability of A's partner-deviation d(A,B)=x−mean_B x via
odd/even shared games, TOI-weighted, within-player partner-shuffle placebo, 500 perms, seed
20260713c), on 84,799 directed (A,B) rows at the 100-min floor. **The control is sharper this round:**
each axis is residualized on OZ-start share, score-state mix, **and opponent strength (opp_rapm)** of
the shared minutes before re-testing. Pre-stated pass: raw reliability ≥ 0.30, beats placebo p<0.05,
**and** the deployment+opponent-controlled reliability stays ≥ 0.30.

**Attribution / availability checks (done before building):**
- **Q5 icing — DROPPED.** The frozen Atlas `events` carries no stoppage `reason` column (dropped in
  the same Atlas projection as UL-P1), so icing can't even be identified; and icing is team-only
  upstream (no committed-by player). Not individually attributable — not inferred.
- **Q6 zone-exit / breakout — DROPPED.** No exit/entry/carry/dump event type exists in the events;
  recovering a clean-exit signal would require timing-inference of unrecorded passing/carries — exactly
  the Round-1 feeding lesson. Not built.

**Per-axis result** (all ratios shown with their median denominator; denominator traps flagged):

| axis (family) | raw reliability (p) | +opponent-controlled | across-partner SD (abs) | median denom | class |
|---|---:|---:|---:|---:|---|
| `xg_per_unb` — shot **quality** (Q1) | −0.07 (1.0) | −0.07 | ±0.008 xG | 25 unb | player-constant |
| `on_goal_rate` (Q1) | −0.09 (1.0) | −0.09 | ±0.076 | 35 att | player-constant |
| `blocked_share` / `missed_share` (Q1) | −0.08 / −0.09 (1.0) | −0.08 / −0.09 | ±0.067 / ±0.063 | 35 att | player-constant |
| `slot_share` — **location** (Q2) | −0.07 (1.0) | −0.08 | ±0.075 | 25 unb | player-constant |
| `mean_dist` (Q2) | −0.05 (1.0) | −0.06 | ±3.0 ft | 25 unb | player-constant |
| `shooting_pct` — **finishing** (Q4) | −0.08 (1.0) | −0.08 | ±0.026 | **17 SOG (thin)** | player-constant (noise) |
| `pen_taken60` / `pen_drawn60` (Q7) | −0.10 / −0.10 (1.0) | −0.10 / −0.10 | ±0.00 | (rate) | player-constant |
| **Q3** `D shot-share by forward UNIT` | **+0.12 (0.002)** | (below bar) | ±0.051 share | (50-min D-trio) | **real but weak** |

(The uniformly small **negative** raw reliabilities are the expected within-player demeaning artifact
in finite samples — none beat placebo, p=1.0; the reading is "does not move by partner," not a real
anti-signal.)

**Reading.**
- **Shot QUALITY and LOCATION are the player's own constants, not partner tendencies.** How dangerous
  a player's chances are (`xg_per_unb`), whether his shots get through (`on_goal_rate`,
  `blocked/missed_share`), where he shoots from (`slot_share`, `mean_dist`), how he finishes
  (`shooting_pct`), and his penalty rates **do not move by partner** beyond noise, and there is nothing
  for the opponent control to even bite on. A player brings his own shot profile; the teammate does
  not reshape it. (This aligns with role-fit F18: the shot axes were the most *player-carried* role
  dimensions.)
- **The one real partner-conditioned behavior is still the shoot-vs-defer DECISION**, not the shot
  itself. Q3 confirms that decision *weakly* organizes by the forward unit too (D shot-share by trio:
  reliability +0.12, beats placebo p=0.002, ±0.05 share) — but far below the pairwise signal
  (Round-1 shot-share 0.35) and below the 0.30 bar. So deference is **primarily a pairwise choice**,
  only faintly a unit-level one.

**Q.VERDICT (pre-stated).** **No quality/location/decision axis passes** the 0.30 + placebo + control
bar. Q1/Q2/Q4/Q7 are **player-constant** (a tidy null — the player's own game). Q5/Q6 are **not
attributable/recorded** (honest drops, not inferred). Q3 is **real but sub-bar** (weak unit-level echo
of the pairwise decision). **Nothing is deployment-in-disguise** — the player-constant axes never moved
raw, so the sharper opponent control was never the thing that killed them.

**Recommendation to the owner.** The map is now clear across two rounds: of all measurable behaviors,
**only the shoot-vs-defer decision (Round-1 `shot_share`) is a real, material, deployment-robust
partner tendency.** No Round-2 axis earns a place beside it. Recommend the stability/prediction arc
(Link B/C) proceed **on `shot_share` alone**, carrying Q3 (unit-grain deference) descriptively as a
weak corroborating cut, and treating quality/location/finishing as **player constants** (useful as
Link-C *controls*, not dependence features). No new dependence axis is worth a B/C test.

### Decisions & artifacts (Round 2)
- Q5/Q6 dropped on pre-build checks (not inferred). Opponent strength added to the deployment control.
  Denominator disclosed per axis; `shooting_pct` flagged thin-denominator (median 17 SOG).
- `src/deppro/{qaxes,linkQ,q3unit}.py`; `reports/linkQ_analysis.json`, `linkQ3_analysis.json`;
  `data/parquet/{qaxes,q3unit}/*` (gitignored). Reproduce: `make linkQ`. Frozen inputs untouched.

**STOP — owner review.**

---

## LINK B (GATE) — is DEPENDENCE a stable individual trait? → **FAIL (real but weak, and it doesn't travel)**

Scope confirmed by the owner: dependence built from the **shot-share** axis only (the sole Link-A
survivor); Q3 unit-grain deference carried descriptively below; quality/location axes held as Link-C
controls, not dependence features.

**B.1 Dependence score.** Per (player A, season): the **noise-corrected across-partner spread of A's
shot-share** — how much his shoot-vs-defer choice swings across his qualifying partners. Raw spread is
inflated by measurement noise (a player measured over few attempts looks swingier), so the binomial
share-variance is subtracted: `dep = sqrt(max(0, wVar_B(shot_share) − wMean_B(share(1−share)/attempts)))`,
TOI-weighted, 2+ partners. **Absolute magnitude:** median **0.047** shot-share points (p10 0.00,
p90 **0.078**) — the most context-dependent players swing their shot-share ~8 points across partners;
many swing ~0 (they shoot the same regardless).

**B.2 Stability (gate)** — placebo = shuffled identity within position-season, 1,000 perms:

| test | r | placebo p | bar | pass |
|---|---:|---:|---:|:--:|
| split-half (odd/even shared games) | **0.147** | 0.001 | 0.40 | ✗ |
| YoY same-team | **0.201** | 0.001 | 0.30 | ✗ |
| **YoY across a team change** | **0.056** | — | — | (retention **0.28**) |

Split-half rises with the floor (0.11 / 0.15 / 0.19 at 75 / 100 / 150 min) — more shared minutes
sharpen it — but it **never approaches 0.40**. Both stability bars are missed by a wide margin, though
both beat placebo (there IS a small real stable component). The **across-team retention is 0.28**: the
little dependence that repeats is **mostly situational, not a traveling player trait** — the number
that would decide whether a Link-C predictor could travel says it largely cannot.

**B.3 Who is dependent (interpretation).** The pattern is real and sensible even though the trait
isn't stable enough to build on: dependence concentrates in **offensive / sheltered / high-usage**
players and is near-zero for **defensive / checking** players.

| player type (System Effects) | mean dependence (z) |
|---|---:|
| F: top-PP-sheltered-offense | **+0.19** (most dependent) |
| D: top-PP-sheltered-offense | +0.10 |
| F: mid-PP-sheltered-offense | +0.09 |
| D: bottom-PK-tough-defense | −0.07 |
| F: mid-PK-tough-defense | −0.12 |
| F: bottom-EV-tough-defense | **−0.20** (least dependent) |

(Corroborating: dep correlates +0.17 with 5v5 TOI, ~0 with experience and offense/defense balance.)
So offensive players adjust **who shoots** by partner (defer to a better shooter, assert with a
weaker one); defensive/checking players just do their job regardless — a clean descriptive read.

**B.4 Verdict (pre-stated).** PASS required split-half ≥ 0.40 AND same-team YoY ≥ 0.30. Both fail
(0.15, 0.20). **→ FAIL.** Per the pre-registration, *if dependence is not stable it cannot be a
predictive feature* — so **Link C is not justified**: there is no stable per-player dependence trait
to feed a post-departure predictor, and what little there is does not travel across teams (retention
0.28).

### Probe-level read (this arc)
The behavior IS partner-conditioned — a player's **shoot-vs-defer choice genuinely moves by partner**
(Link A, deviation reliability 0.35) — but that does **not** aggregate into a stable individual
**dependence trait**: "how much player X's game changes by teammate" is measured too noisily (3–6
partners/season) and repeats too weakly (split-half 0.15, YoY 0.20) and travels too little (retention
0.28) to be a buildable predictive feature. Like the pair-residual (F17) and unit-over-performance
(F18) arcs, the fit signal is real in the small but does not clear a usability bar. **Nothing to
promote.**

**Recommendation (owner rules).** Do not proceed to Link C — the dependence feature it needs isn't
stable. The **durable, shippable results** across three rounds are descriptive: (1) shooting deference
is a real pairwise behavior; (2) chance quality/location/finishing/penalties are **player constants**,
not partner-driven (a clean, useful null — see `reports/FINDINGS.md`); (3) offensive players are the
context-dependent ones, defensive players are not. If any fit thread continues, it needs a **new,
narrower pre-registration** (e.g., more partners via multi-season pooling to lift the dependence
reliability) that acknowledges the ceiling measured here.

### Decisions & artifacts (Link B)
- Dependence = noise-corrected across-partner shot-share spread (binomial-variance subtracted);
  standardized within position-season; split-half on odd/even, YoY on the full-season score.
- `src/deppro/linkB.py`; `reports/linkB_analysis.json`; two-round map in `reports/FINDINGS.md`.
  Reproduce: `make linkB`. Frozen inputs untouched.

**STOP — owner review.**
