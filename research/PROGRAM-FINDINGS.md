# NHL Research Program — Findings Ledger

The shared, **growing** cross-project findings ledger. Completed-project reports under each
`research/<project>/reports/` are **frozen** and do not grow; new findings and cross-project
threads are recorded here instead.

Projects:
- **Deployment Atlas** (`research/deployment-atlas/`) — frozen. Findings in its own
  `reports/FINDINGS.md`; summarized threads carried forward here.
- **System Effects** (`research/system-effects/`) — findings below (F-series).

---

# System Effects — Findings (follow-on project, answers "The System Tax")

A follow-on research project (`research/system-effects/`, reads the frozen Atlas parquet
read-only) that measures what coaching **systems** do to the players inside them and the
opponents across from them. It ingested a right-rail coach backfill (2010-11 → 2023-24, 16,526
games + officials + scratches), built a per-(team, regime) system-fingerprint layer, and ran two
tracks with pre-registered validation. Numbered findings (F-series) below; full detail in
`research/system-effects/reports/phase{0..5}.md`.

## What the discontinuity/validation tests established
- **F12 — style is a roster property, deployment is the system.** At within-team coach changes,
  only **deployment** (top-6 forward concentration, zone-start polarization) shifts more than a
  placebo (zone-pol ~1.9×, p=0.0005); on-ice **style** (rush/cycle/forecheck/point-shot shares,
  shot-location, pace) is statistically indistinguishable from placebo. **Extended (Phase 5
  addendum):** the style null holds across **summers** too — controlling for roster continuity, a
  new coach's first full season does not shift style beyond a continuing coach's, and teams do not
  move toward an incoming coach's established style beyond chance (dose +0.05 SD ns; directional
  p=0.08). Deployment installs in **both** windows (summer dose t=3.4, directional p=0.0005) —
  which also proves the test had power, so the style null is real, not underpowering. Penalty-kill
  shot-location installs in neither window. The summer style directional is **positive but
  unconfirmed** — too weak to confirm in sixteen years of transitions, never proven zero.
  *Observational for the summer extension.*
- **F13 — deployment persists with the coach.** Zone-start polarization has YoY correlation 0.70
  within a continuing regime and 0.31 across a coach change — it persists while the coach persists
  and moves when he changes. (Top-6 concentration does **not** show this pattern and carries a
  stability caveat everywhere.)
- **F14 — thin mediation.** A coach change's on-ice **result** effect is small (+0.004 score-close
  on-ice xG-share DiD, t=1.73) and only **~4%** of the within-player result change is mediated by
  the measured deployment change (R²=0.04). Deployment is what coaching demonstrably moves; the
  result payoff of that move is barely detectable at one-season resolution.
- **F15 — style matchups don't matter beyond strength.** In a team-game 5v5 xG-share model,
  style-matchup interactions add **0.00014 R²** over team strength (coefficients ~60× smaller) and
  **do not replicate across eras** (cross-era r = −0.045). The opponent style-matchup track was
  **killed**; only a strength-based schedule normalization survives as descriptive accounting.
- **F16 — the Jolt is reversion (not effort).** The small new-coach on-ice result bump (F14) that
  deployment does not explain is **mean regression**: teams fire coaches at a genuine on-ice trough
  (~1.3 pp below prior-season baseline, CI excludes 0), and the new coach's recovery to baseline is
  **flat, sustained through +40 games (no fade), and statistically indistinguishable** from what a
  matched-trough non-firing team recovers (excess +0.004, CI [−0.011, +0.020]). Effort (a fading
  honeymoon) is rejected; "neither" is rejected (the trough is real). Era-stable, not outlier-driven.
  *Observational.* (Event-time addendum; the registered "deepest-trough" placebo had a
  regression-to-minimum bias, corrected to a matched-depth control — disclosed, no threshold moved.)

## The System Tax — answered
The Atlas open question ("how much of a player's on-ice result is the system vs the player?") now
has a number and a caveat. A joint player-season model (RAPM as frozen offset; team deployment +
type×deployment as the system term; grouped CV) recovers **CV R² ≈ 0.07 of the residual** beyond
player quality — a real, out-of-fold system signal, but small. Absolute per-player system
contributions are **≤ ~0.01 xG-share points** (p95 0.008). So the System Tax is **real but thin**:
the system a player is in explains single-digit percent of what his rating doesn't, concentrated in
**deployment** (not style), and mostly for **defensemen and high-usage players**.

## The decision (pre-registered, INVESTIGATE — matches the Atlas mover verdict)
Do deployment-system terms predict movers beyond the Atlas rating? On the Atlas mover cohort, a
leakage-clean nested test (RAPM vs RAPM+deployment, LOSO-pair-out, sys refit clean per fold)
improves MAE by **+0.81%** (95% CI [0.15%, 1.50%], excludes zero) — **below the 3% ship bar →
INVESTIGATE.** The signal is directionally correct (movers > stayers 0.81 vs 0.49%), stable under
influence, and concentrated in **defensemen (+1.62%) and high-TOI players (+2.48%)**, but sits at
~1.3% of the target's reliability ceiling (split-half 0.70). **Nothing ships publicly.** The
portability surface stays **internal and descriptive** under a materiality gate (label a player
system-dependent only where the absolute system contribution's CI excludes zero **and** |sys| ≥
0.004); the defensemen / high-TOI slices are **pre-specified secondary subgroups** for a future
prospective registration, not claims now.

## Upstream ledger additions (System Effects)
- **UL-1 — `stg_games`/`stg_game_context` season mislabel:** a 2015-16 block tagged `2024-25`
  (game dates correct, only the derived season label corrupt). System Effects immunizes by
  anchoring on the frozen Atlas game universe + game_id joins. Flagged for a future gated
  production fix.
- **UL-3 — right-rail missing one coach for 2 of 16,526 backfilled games** (source omission);
  negligible, HTML-roster fallback available if ever needed.

## Open questions (System Effects → next)
- **The Jolt — RESOLVED → F16 (reversion).** The event-time addendum ruled it mean regression, not
  effort (see F16). Closed.
- **The D / high-TOI concentration thread.** The system signal — retrospectively (5A slices) and by
  construction (deployment) — concentrates in **defensemen and high-usage players**. The 2026-27
  prospective registration carries these as **pre-specified secondary subgroups** to test whether
  the concentration replicates out of sample.

---

# Chemistry — Finding (follow-on project, answers "is pair chemistry a persistent trait?")

A follow-on research project (`research/chemistry/`, reads the frozen Atlas stints read-only) that
built the league's pair-performance corpus (90,527 pair-team-seasons ≥50 shared 5v5 min, 2010-26,
conservation identity exact, reconciled to `player_5v5`) and ran the keystone persistence test.

- **F17 — pair chemistry is not an identifiable, materially persistent trait.** Modeling pair 5v5 xG
  share from individual quality + context (additive-plus-curvature null on rapm_variant, both
  same-season and prior-season anchors), the pair RESIDUAL — over/under-performance beyond the
  players' quality — does **not** persist in a way that could be built on. Within-season split-half
  reliability of the residual is ~0 under the conservative same-season anchor (contamination
  straddling) and only ~0.30 under the clean prior anchor; year-over-year same-pair correlation is
  **tiny (r≈0.04–0.09)** and, decisively, **concentrated in LOCKED pairs** (low partner-diversity,
  D-D) where "the pair" and "the players/deployment" are collinear — under the clean anchor the
  high-diversity (identifiable) stratum shows **zero** YoY persistence (p=0.85), while the locked
  stratum carries all of it (p=0.001). The pre-registered rescue clause (proceed if *diverse* pairs
  persist) **failed**. Single-season pair residuals can be large (±0.13–0.16 xG-share, CIs exclude 0)
  but do **not** repeat: the longest-tenure pairs (up to 16 seasons together) pool to ≈0 residual.
  *Conclusion:* fit is not pair-magic. The predictive "chemistry" arm was not justified; the corpus
  and this null are the deliverables. Nothing shipped. *(Full detail: `research/chemistry/reports/
  phase2.md`; keystone verdict landed in a configuration 2.4 did not enumerate — owner ruled null.)*

## Chemistry → next (the role-composition pivot)
- **F17 reframes fit as role supply-and-demand**, not dyadic magic: a follow-on **role-fit probe**
  (`research/role-fit-probe/`) tests whether (L1) a stable per-player role/action proxy exists and
  (L2) units over-perform their parts within a season. See that project's `reports/probe.md`.

---

# Role-fit probe — Finding (follow-on to F17; `research/role-fit-probe/`, seed 20260713)

Two-link feasibility probe of the role-COMPOSITION theory of fit, scoped to the primary window
2015-16→2025-26. Surfaced a production data finding along the way (**UL-P1**): the frozen Atlas
`events.parquet` dropped six player-attribution columns that `stg_play_by_play` already parses
(hits/takeaways/giveaways/blocks/penalties); an owner-authorized, read-only re-projection recovered
them, turning the role model from offense-only into genuinely two-way.

- **F18 — role PROFILES are real, stable, and player-carried, but unit FIT is not usable.**
  *(Link 1 PASS)* A per-player two-way role/action proxy (shot location/volume/danger + physicality +
  shot-blocking + puck-management, 5v5 rates) is reliable within season and across seasons and
  **travels with the player across team changes** (retained median 0.79); **physicality is the single
  strongest signature** (`hit60` split-half 0.95). The opponent-mirror on-ice suppression axis is
  reliable within-season but **team-imposed, not personal** (cross-team retention 0.12–0.47) — a clean
  player-vs-team separation. *(Link 2 FAIL)* Five-man units do **not** recur (only 15–46/season reach
  100 shared min); forward TRIOS over-perform their parts only **weakly** — within-season split-half of
  the unit residual is −0.15 (same-season, straddling artifact) / **+0.18 clean prior anchor, below the
  0.30 usability bar**; two-way role composition adds only ~1 pt CV R². *Conclusion:* fit tested two
  ways now clears no usability bar — pair-magic (F17) and unit role-composition (F18) both fail. The
  **roles themselves** are the real, transferable thing (shippable as a descriptive player-role
  product); **fit-beyond-parts** is not. Nothing shipped. *(Detail: `research/role-fit-probe/reports/
  probe.md` §1b, §2; owner ruled.)*

## Role-fit → next (the behavioral-dependency pivot)
- **F17/F18 killed fit as joint OUTPUT** (pair residual; unit over-performance). A follow-on
  **dependency probe** (`research/dependency-probe/`) tests a different angle — individual BEHAVIOR
  conditioned on teammates (does a player change what he DOES by partner; is that dependence a stable
  trait; does dependence on a departing teammate predict his change). Outcome is a property of ONE
  player, sidestepping the identifiability walls. See that project's `reports/probe.md`.

---

# Dependency probe — Finding (follow-on to F17/F18; `research/dependency-probe/`, seed 20260713b/c)

Third angle on fit after two output-based nulls: individual BEHAVIOR conditioned on teammates (the
outcome is a property of ONE player). Two rounds, deployment-controlled throughout (Round 2 adds the
opponent-strength control). Reuses the role-fit enriched event attribution and the Chemistry
stint-expansion. **Owner-ruled; the probe ends at Link B.**

- **F19 — behavior IS partner-conditioned in exactly one place (shooting deference), but dependence is
  not a buildable trait; chance quality/location/finishing are player constants.**
  - *The one real partner tendency (Link A):* a player's **share of his pair's shot attempts** (shoot
    vs defer) moves by partner — partner-deviation split-half reliability **0.35** (beats placebo
    p=0.002, across-partner SD ≈ 0.10 share pts), **fully survives** the OZ+score+opponent deployment
    control, and strengthens with more shared minutes. His shot *rate* does not move — volume is his
    own; what changes is who shoots.
  - *Tested nulls (Round 2, Link Q):* **chance quality** (xG/attempt), **on-goal / blocked / missed
    share**, **shot location** (slot share, distance), **finishing** (shooting %), and **penalty**
    tendencies are all **player-constant** — they do not move by partner (reliability ~0, never beat
    placebo; none "deployment in disguise"). *We tested whether chance quality is partner-driven, and
    it is not.* Icing (Q5) and zone-exit (Q6) were **dropped on attribution/availability checks** (no
    stoppage `reason` in the frozen events; no exit event type — no timing-inference, per the Round-1
    feeding lesson).
  - *Dependence is not a stable trait (Link B) → no Link C:* collapsing shot-share swing-across-
    partners into a per-player dependence score (noise-corrected across-partner spread; median 0.047
    share pts) yields **split-half 0.15 (bar 0.40), same-team YoY 0.20 (bar 0.30), across-team
    retention 0.28** — real but far too weak and situational to be a predictive feature (3–6
    partners/season measure it too noisily). Link C (post-departure prediction) not justified.
  - *Interpretation, survives as a descriptive result:* **offensive / sheltered / high-usage players
    are the context-dependent ones** (F:top-PP-sheltered-offense +0.19z; +0.17 corr with 5v5 TOI);
    **role/checking players are partner-invariant** (F:bottom-EV-tough-defense −0.20z) — they play
    their game regardless of who's beside them.
  - *Conclusion:* fit tested four ways clears no usability bar as a PREDICTIVE quantity (F17 pair
    residual, F18 unit over-performance, F19 behavioral dependence). The durable results are
    **descriptive** (above). Nothing promoted or published. *(Detail:
    `research/dependency-probe/reports/probe.md` + `FINDINGS.md`; owner ruled.)*
  - *If ever revived:* a new, narrower pre-registration with **multi-season partner pooling** to lift
    the dependence reliability past the ceiling measured here — not a near-term project.

---

# Composition probe — Finding (the last swing at fit; `research/composition-probe/`, seed 20260713d)

The final pre-registered test of fit: does trio RECIPE (fine style composition / complementarity) beat
recipe holding talent+style fixed, and repeat across an era split? Finer style vocabulary (16 forward
archetypes from the validated role-fit two-way axes), continuous complementarity + redundancy scores,
a talent-and-style-matched contrast, and an era-split repeat. Scoped to 2015-16→2025-26 (validated
style axes only 2015+; the spec's 2010-17/2018-25 split adapted to 2015-19 vs 2020-25 — a forced,
owner-accepted deviation). Reuses the Chemistry trio corpus and the additive-plus-curvature null.

- **F20 — trio composition/recipe is talent-and-style in disguise (HARD NULL); predictive fit is
  closed.** Recipes recur (560 distinct over 2,262 trios, median 3 each), so the sample is real — but
  composition explains **nothing** beyond the members' individual quality and style. Incremental
  composition CV R² = **0.0004 (0.04%)** — *below* Link 2's ~1% and far below the 3% ship bar; finer
  ingredients LOWERED it. The talent×season-matched **balanced-minus-redundant** residual contrast is
  **+0.0002 xG-share, 95% CI [−0.004, +0.004] (includes zero)**; the complementarity coefficient is
  **negative** in both eras; the trio residual doesn't even repeat within a season (split-half −0.15).
  Once the three forwards' quality and style are fixed, *how they are arranged* adds no measurable
  performance. *(Detail: `research/composition-probe/reports/probe.md`; owner ruled, verdict accepted
  as written.)*

## THE FIT LINE — formally closed (five pre-registered swings)
Fit-beyond-parts was tested five ways, each pre-registered, each clearing no usability bar:
- **F17** — pair residual: over/under-performance beyond the two players' quality is not an
  identifiable, persistent trait (locked-pair-confounded; diverse pairs show zero YoY).
- **F18** — unit over-performance: forward trios over-perform their parts only weakly (split-half
  +0.18 clean anchor, below 0.30); two-way role composition adds ~1 pt R². (Role-fit L2.)
- **F19** — behavioral dependence: a player's shoot-vs-defer choice IS partner-conditioned (real
  pairwise), but "how dependent a player is" is not a stable individual trait (split-half 0.15,
  across-team retention 0.28); chance quality/location/finishing are player constants.
- **role-fit L1** — the *roles themselves* are real, stable, and player-carried (two-way, retained
  ~0.79), but that is a descriptive asset, not a fit predictor.
- **F20** — composition/recipe: talent-and-style in disguise (hard null).

**Program-level conclusion.** *Predictive fit-beyond-parts does not exist at a buildable scale in
public event data.* The **player is the portable unit** — his quality (RAPM) and his two-way role/
style travel with him; what a specific partner, unit, arrangement, or recipe adds on top does not
persist, replicate, or clear a usability bar. **Reopening the fit question requires a materially new
data source (player-tracking / off-puck + passing — the Tier-iii ceiling), not another arrangement of
public-event features.** The surviving, shippable assets are all DESCRIPTIVE, labeled co-occurrence
not causation: the two-way role profiles, the 16 style archetypes, and shooting-deference-as-a-
pairwise-behavior. Nothing predictive was promoted or published from the fit line.

---

# Goaltending investigation — Findings (goal-tracking Stage 1 + goalie-probe; seeds 20260714 / 20260714b)

Two linked efforts asked what distinguishes goalies. Stage 1 (goal-tracking) profiled goalies from the
composition of GOALS AGAINST (player-tracking, goals-only, no shot denominator); the goalie-probe redid
the question over SHOTS FACED (the denominator) and then tested behavioral habits from the tracking
fusion. **THE DENOMINATOR IS THE POINT:** a goalie is never characterized from the composition of goals
alone.

- **F21 — a goalie's goal-against MECHANISM MIX is not a stable trait (goals-only, unstable).** Stage 1
  tagged each goal's beat-mechanism (east-west, screened, clean-look, unset, rush, location,
  second-chance) and profiled goalies. Reliability split-half: only **1/10 mechanisms (UNSET, r=0.34)**
  replicated; east-west / screened / rush / location all ~0. The mix reflects the defense and situation
  in front of the goalie, not a persistent goalie signature — and it carries no shot denominator. Only
  pooled three-season tables ship; single seasons are noise. *(Detail:
  `research/goal-tracking/reports/stage1.md`.)*

- **F22 — goalies differ in OVERALL stopping, not in identifiable shot-type specialties (with the
  denominator).** Over shots faced (SOG + goals, 2023-26, 248,989 shots, 155 goalies), GSAx-over-shots-
  faced is real and modestly reliable (**split-half 0.44, YoY 0.27**). But **no shot-type bucket** —
  wrist/snap/slap/backhand/deflection, danger tier, region, rebound-shot — is stable *beyond* overall;
  the only buckets clearing the bar (non-rebound ≈ all shots; inner-slot = the danger core) are the
  overall signal in disguise. Goalies are not shot-type specialists. *(Detail:
  `research/goalie-probe/reports/probe.md` G1.)*

- **F23 — one behavioral habit persists: lateral-recovery / how-set, but goals-only.** Continuous goalie
  lateral speed at release (the continuous form of F21's UNSET) is the lone behavior axis clearing the
  stability gate (**split-half 0.41, p<0.001 decisive; YoY p≈0.05 borderline / underpowered on two
  season-pairs**), confirming F21's UNSET hint. But it is measured on goals-against (no save
  denominator), so it is a describable positioning **STYLE, not a skill** — and it barely relates to
  results (r=−0.13 vs overall GSAx). *(goalie-probe G2.)*

- **F24 — rebound-control, the one denominator-backed behavioral axis, is NOT a stable trait.**
  Second-on-goal-shot-within-3s-after-a-save rate (over saves, from the pbp spine — the only behavior
  axis with a real denominator) fails the gate (**split-half 0.21**) and does not relate to overall GSAx
  (r≈0). The honest-denominator behavioral skill does not materialize. *(goalie-probe G2.)*

## GOALTENDING — one durable skill that does not decompose
Goaltending, tested for internal structure the way the fit line was, gives the parallel result: there is
exactly **one durable, denominator-backed goalie skill — overall save-quality over shots faced** (GSAx,
split-half 0.44) — **and it does not decompose.** It does not split into shot-type specialties (F22); it
is not captured by the goals-only mechanism mix (F21); and the behavioral habits that might underlie it
either do not persist (rebound-control, F24) or persist only as a goals-only positioning style with no
tie to results (lateral-recovery, F23). As **the player is the portable unit** in the fit line, **overall
stopping is the portable unit** in goaltending: a single skill that travels with the goalie but resists
being broken into buildable sub-skills on public data. Reopening "what KIND of goalie" as a predictive
question would require tracked **SAVES** (this data is goals-only), not another decomposition of goals.
The shippable asset is descriptive — an overall save-quality card (GSAx-over-shots-faced + 90% CIs),
optionally tagged with the goals-only lateral-recovery style (labeled style-not-skill) — not a
specialties model. **F2 ships on that basis; the Stage-1 mechanism-mix framing is retired.** Nothing
predictive was promoted from the goaltending line.

---

# Goal-tracking playmaking — Finding (Stage 2; `research/goal-tracking/`, seed 20260714)

Stage 2 built per-goal buildup descriptors and per-player buildup signatures from the tracking corpus
(Stage 0 fused goals + reconstructed events, reads the Stage 0 API only), then tested whether the
signatures are stable player traits.

- **F25 — player BUILDUP SIGNATURES are stable, persistent traits (the tracking program's first positive
  result).** Over 735 players with ≥15 involved goals, the reliability gate (odd/even split-half vs a
  shuffled-identity placebo, 2000 perms) PASSES on **5/7 fields**: **net-front (0.76), finisher (0.70),
  entry-driver (0.56), carrier (0.54), rush (0.37)** replicate and beat placebo — these are
  **identity-grade** signatures, and per-season profiles are publishable (subject to the ≥15-goal gate).
  **royal-road (0.24) and feeder (0.16) do NOT replicate** — creating cross-slot goals and feeding a
  specific scorer are situation / linemate-driven, so they ship **descriptive-only, never as identity
  claims.** The role-axis sanity matrix confirms face validity (finisher↔goals60 0.74, net-front↔
  slot_share 0.72, net-front↔tip_share 0.65; no contradictory sign). *(Detail:
  `research/goal-tracking/reports/stage2.md`.)*

**Contrast with the goaltending line.** Where the goalie mechanism mix does NOT decompose into stable
sub-skills (F21–F24), player buildup DOES: how a player contributes to goals — finishes, drives entries,
carries, goes to the net, plays on the rush — is a persistent individual signature. The tracking fusion
delivers real, publishable PLAYER description even though it delivered only confirmation on goalies.
This unlocks the **F1 (goal-anatomy viewer)** and **F3 (player signatures)** design briefs, both fed by
Stage 0 + Stage 2; the visuals proceed through the design (mockup/critique/handoff) process, not a
Claude Code paste. Nothing was promoted from the backend.
