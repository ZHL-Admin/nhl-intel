# Defensive Breakdown — probe.md

**Probe** (`NIR/research/def-breakdown/`). Defensive mirror of Stage 2; avoids the failed def-scheme project (F26): no scheme labels, no team norms. Read-only; `make link0`/`make link1` reproduce from cache. Seed 20260714d.

> **FRAMING RULE.** Outputs are a DESCRIPTIVE per-goal accountability log and a culprit RATE over goals-against, never a claim of certain fault on any single goal and never a full-defensive rating. Permitted: 'was the nearest uncontested defender', 'coverage collapsed to his side', 'culprit rate'. Banned as a single-goal verdict: bad defense, blame, fault, out of position, mistake. No scheme labels, no team norms, no 'where he should have been' (avoids F26).


## Link 0 — the fused defensive event

Reuses the def-scheme phase-0 defensive-frame primitives (5 defenders' normalized trajectories + dist-to-puck/net/nearest-attacker) and adds the puck + the KNOWN scorer's trajectory (pbp scorer fused to his tracked skater) in the defending team's attack-normalized frame.

- **17,781 qualifying goals-against** (TRACKED quality, n_def=5, real NHL teams), 33 teams, 95 team-seasons (median 185/team-season, 150–231).
- **Fused fidelity:** scorer tracked 100%; scorer within stick-reach of the puck in the final 1.0 s (Stage-0-style, release-anchored) **98.3%** — the fused event is high-fidelity.
- Goals with complete release-frame geometry (used for signals): **15,887**.

## Link 1 (rebuilt) — percentile-calibrated signals + combined culprit share

Per your Link-1 ruling, every distance threshold is now a **PERCENTILE of that measure's own distribution across all qualifying goals**, not a guessed foot value; **Signal A(i) (on-puck uncontested release) is DROPPED** as tautological on goals-only data (the release that scores is definitionally uncontested); Signal A is now **only** the off-puck float A(ii); and the combined share is **B-primary: 0.75·B + 0.25·A(ii)**.

**Signal B · open-man vector** (at release): `B_flag` = the nearest defender to a scorer who is **open** (scorer-to-nearest-defender ≥ the p80 of the openness distribution = **12 ft**, vs a goal-median of 7 ft) AND whose **lane is uncontested** (min defender-to-shot-vector ≥ p80 = **8 ft**). Secondary flag: the strong-side/origin defender on a cross-slot feed.

**Signal A(ii) · off-puck float**: `A_flag` = an off-puck defender whose distance to BOTH the nearest attacker (≥ p80 = **18 ft**) AND the net-front (≥ **47 ft**) is unusually large — genuinely floating, exposed to neither a man nor the net.

**Combined culprit share:** `share = 0.75·B_norm + 0.25·A_norm`, each component graded by severity and normalized within the goal to sum to 1; hard-culprit flag at share ≥ 0.40. Every goal distributes exactly one unit of breakdown.

**Percentile → footage mapping** (sanity-check that "open" looks open):

| measure | percentile | footage | goal-median (for scale) |
|---|---|---|---|
| scorer openness (B) | p80 | 12.0 ft | 7.4 ft |
| lane contest (B) | p80 | 8.1 ft | — |
| float vs nearest attacker (A ii) | p80 | 18.2 ft | — |
| float vs net-front (A ii) | p80 | 47.1 ft | — |

**Sub-condition fire rates (frozen):** A(ii) off-puck float 7.2% of defender-rows; B open-man 1.0%; secondary 0.3%. **Per-goal distribution:** median max-share/goal **0.20**; a hard culprit exists on **2,447/15,887** goals (15%); **9,478** (60%) have no clear culprit (good defense beaten — shares distribute ~evenly). The over-firing is fixed: hard culprits fell from 59% of goals to 15%.

**Honest framing note — the metric is COMPARATIVE.** Percentile calibration means a fixed fraction of goals (~19%) will always sit in the top openness percentile. So the culprit-rate ranks defenders **against each other** — "was the collapsed/open man more often than peers" — not against an absolute "coverage was objectively poor". That comparative rate over goals-against is the intended, valuable framing, and it is stated here so it is not read as an absolute judgement.

### Worked examples under the rebuilt, percentile-calibrated assignment (re-eyeball)


**Clean east-west open-man (Signal B)** — `2024020313-649` · scorer_openness=12 ft, lane_contest=11 ft, nearest_puck@release=17 ft, cross_slot=True:

| defender | breakdown share | to scorer | on-puck share | flags |
|---|---|---|---|---|
| Matthew Tkachuk | 0.27 | 12 ft | 0.07 | B |
| Carter Verhaeghe | 0.26 | 98 ft | 0.00 | A_ii |
| Sam Bennett | 0.19 | 18 ft | 0.00 | — |
| Uvis Balinskis | 0.14 | 25 ft | 0.00 | — |
| Nate Schmidt | 0.13 | 52 ft | 0.00 | A_ii,2nd |

**Genuine off-puck float (Signal A(ii))** — `2025020193-249` · scorer_openness=19 ft, lane_contest=4 ft, nearest_puck@release=11 ft, cross_slot=False:

| defender | breakdown share | to scorer | on-puck share | flags |
|---|---|---|---|---|
| Tye Kartye | 0.54 **HARD** | 19 ft | 0.03 | A_ii |
| Vince Dunn | 0.13 | 46 ft | 0.06 | — |
| Ryan Winterton | 0.12 | 52 ft | 0.00 | — |
| Adam Larsson | 0.11 | 54 ft | 0.00 | — |
| Ben Meyers | 0.10 | 57 ft | 0.10 | — |

**No clear culprit (good defense beaten)** — `2023021116-1018` · scorer_openness=4 ft, lane_contest=1 ft, nearest_puck@release=10 ft, cross_slot=False:

| defender | breakdown share | to scorer | on-puck share | flags |
|---|---|---|---|---|
| Christian Fischer | 0.20 | 18 ft | 0.00 | — |
| Andrew Copp | 0.20 | 4 ft | 0.00 | — |
| Ben Chiarot | 0.20 | 21 ft | 0.00 | — |
| Michael Rasmussen | 0.20 | 8 ft | 0.45 | — |
| Jeff Petry | 0.20 | 7 ft | 0.52 | — |

**Previously-spurious well-covered scorer — now does NOT flag** — `2023020339-240` · scorer_openness=4 ft, lane_contest=4 ft, nearest_puck@release=7 ft, cross_slot=False:

| defender | breakdown share | to scorer | on-puck share | flags |
|---|---|---|---|---|
| Aliaksei Protas | 0.20 | 4 ft | 0.03 | — |
| Trevor van Riemsdyk | 0.20 | 11 ft | 0.06 | — |
| Rasmus Sandin | 0.20 | 11 ft | 0.03 | — |
| Anthony Mantha | 0.20 | 24 ft | 0.00 | — |
| Connor McMichael | 0.20 | 27 ft | 0.00 | — |

> **Link 1 CONFIRMED sane by owner; Link 2 tally run on this approved B-primary + A(ii), percentile-calibrated assignment.**

---

## Link 2 — culprit-rate tally + THE STABILITY GATE

Analysis population: **defensemen** (rosters position_code='D'); the per-goal share is distributed among all five defending skaters. `CULPRIT_RATE` = summed breakdown share / on-ice goals-against (qualifying tracked-5v5 universe; min 25 GA to report, min 40 for the gate). Continuous-share and hard-flag versions reported separately.

**280 defensemen** clear ≥25 GA (pooled). League mean culprit rate (continuous) **0.191** (≈ the 1/5 = 0.20 even-split expectation; forwards absorb the rest), hard-flag 0.005.

**Both baselines (culprit rate barely varies):**

| baseline | n | mean continuous | mean hard |
|---|---|---|---|
| league-wide (all D) | 584 | 0.191 | 0.005 |
| TOI tier: top-pair | 195 | 0.191 | 0.005 |
| TOI tier: middle | 197 | 0.192 | 0.005 |
| TOI tier: depth | 192 | 0.190 | 0.004 |

The usage tiers are indistinguishable (~0.19 each) — culprit rate does not separate top-pair from depth defensemen.

## The stability gate (pre-registered: split-half ≥ 0.30 AND beats placebo p<0.05)

| signal | version | split-half r | placebo p | YoY r | pass |
|---|---|---|---|---|---|
| combined | continuous | +0.02 | 0.378 | -0.05 | · |
| combined | hard-flag | -0.09 | 0.943 | +0.06 | · |
| B (open-man) alone | continuous | +0.05 | 0.209 | +0.07 | · |
| A(ii) float alone | continuous | -0.07 | 0.877 | -0.02 | · |
| B east-west subset | continuous | -0.17 | 0.696 | — | · |

**Reference points:** bar = 0.30; the offensive player-signature (Stage 2, F25) reached split-half **0.41–0.76** (net-front 0.76, finisher 0.70). This defensive culprit rate sits at **~0.00–0.05 for every signal, version, and subset** — indistinguishable from noise, and beats no placebo. Even the east-west B-subset (Signal B's designed strength) shows nothing (r=-0.17, n=10).

## Exposure sanity + on-ice xGA face-validity

- Culprit rate vs exposure: on-ice GA volume r=+0.06, 5v5 TOI r=+0.09 — **not exposure-driven** (both far below the 0.7 flag), but that does not rescue an unstable rate.
- **On-ice xGA face-validity: r=+0.04** (n=584 defenseman-seasons). High-culprit defensemen do **not** have worse on-ice defensive results — the culprit rate carries no relationship to actual defensive outcomes.
- (PK share and opponent strength: the culprit universe is 5v5-only, so PK is out of universe; opponent-quality was not separately assembled — moot given the null.)

## VERDICT — WEAK/NULL

**Per-defender defensive breakdown, measured from goals-only geometry, is noise-dominated: it is NOT a stable individual trait.** Every signal (B open-man, A(ii) float, combined; continuous and hard-flag; and the east-west B-subset) sits at split-half ~0, beats no placebo, does not vary by usage tier, and does not relate to on-ice xGA. The percentile-calibrated, B-primary assignment you approved is descriptively sane per-goal, but it does not aggregate into a repeatable per-defender signature.

**This closes the individual-defense question on this data.** It is the second defensive null in the program: neither team defensive identity (F26) nor individual defensive breakdown is recoverable from goals-only tracking geometry — while the OFFENSIVE mirror (Stage 2 buildup signatures, F25) is stable and real. Goals-only + shared coverage + game-to-game variance washes out individual defensive attribution. *(proposed F27.)* Nothing promoted.

## STOP — owner rules.
