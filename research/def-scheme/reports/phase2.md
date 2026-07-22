# Phase 2 — THE KEYSTONE: does defensive identity emerge, and what does it track?

**Defensive Scheme & Role.** Read-only; `make phase2` reproduces. Seed 20260714c. This is the project's go/no-go gate; thresholds and verdict language were fixed before results.

> **LAW 1 · GOALS-ONLY. The tracking corpus contains only goal buildups; there is no tracked non-goal. This project INFERS team scheme and player role from goal geometry and measures deviation from the team's own norm. It never claims 'this positioning caused the goal' nor compares against non-goal plays it does not have. The scheme-norm is a norm ON GOALS.**

> **LAW 2 · NO FAULT LANGUAGE. 'out of position', 'blame', 'fault', 'mistake', 'responsible' never appear. The only permitted claim is DEVIATION FROM THE TEAM'S OWN STRUCTURAL NORM — a descriptive geometric fact, never a verdict of error. Scheme vs individual error cannot be separated per-goal; only aggregate deviation tendency is claimed.**


## 2.1 Scheme vocabulary (clustered team-season deviation signatures)

KMeans on the z-scored deviation-from-league signatures. **Coarse (k=3)** types ARE geometrically interpretable:

| type | n team-seasons | geometry (deviation from league) |
|---|---|---|
| collapse / compact (deeper, tighter) | 40 | highest -1.2 ft, depth -0.8, spread -0.3, marking -0.2 |
| baseline (near league structure) | 42 | highest -0.3 ft, depth -0.3, spread -0.0, marking +0.0 |
| step-up / press (defenders higher & looser) | 13 | highest +5.7 ft, depth +4.2, spread +1.2, marking +0.4 |

A fine (k=6) vocabulary was also fit. **Whether these types are a real, persistent IDENTITY — not just a season-level snapshot — is exactly what 2.3 tests.**

## 2.2 Continuity measures (consecutive tracking-season pairs)

- **ROSTER_CONTINUITY** (returning share of 5v5 defensive-skater TOI): mean 0.76, sd 0.14, range 0.44–1.00 — real variance to estimate a gradient.
- **COACH_CONTINUITY** (same head coach, regime ledger): 66% of pairs (41/62).
- **62 season-pairs** total. Four-cell populations (roster hi/lo × coach same/diff):

| roster | coach | n pairs |
|---|---|---|
| high | same | 20 |
| high | diff | 11 |
| low | same | 21 |
| low | diff | 10 |

(Stable teams keep both, so the same-coach/high-roster and diff-coach/low-roster cells are the fuller ones; the off-diagonal cells are thinner but present.)

## 2.3 THE DECOMPOSITION — what does identity track? (gate part A)

Identity persistence = correlation of a team's z-signature vector between consecutive seasons.

**(a) Continuity gradient** (does persistence rise with roster carryover?):
- coarse: slope **+0.01**, 90% CI [-0.56, +0.53], r=+0.00. fine: slope -0.12, CI [-0.61, +0.32].
- **The gradient is flat and its CI spans zero** — persistence does NOT rise with roster continuity. The same is true using cluster-label stability (gradient r=-0.11).

**Persistence by roster-continuity tercile** (coarse): high 0.16 (n=21) vs low 0.14 (n=21). **Within-season floor** (measurement reliability) = 0.13. Between-season persistence barely exceeds the noise floor.

**(b) Four-cell split — persistence (cluster-label stability) by roster × coach:**

| roster | coach | n | label stability | vs chance (0.33) |
|---|---|---|---|---|
| high | same | 20 | 0.45 | +0.12 |
| high | diff | 11 | 0.36 | +0.03 |
| low | same | 21 | 0.67 | +0.34 |
| low | diff | 10 | 0.20 | -0.13 |

No cell shows a roster-driven OR coach-driven lift: high-roster/same-coach ≈ low-roster/same-coach, and label stability sits near the chance floor everywhere.

**(c) Within-season floor:** 0.13 (coarse). Between-season persistence (0.16 at high continuity) is essentially the same — no durable identity beyond single-season measurement noise.

**Roster-vs-coach determination: NEITHER.** Defensive coverage identity from goal geometry does not track roster carryover (F12's mechanism for OFFENSIVE style) nor the coach; it is noise-dominated at the team-season level. (Contrast F12: offensive style IS roster-carried — but that used full-season on-ice data, not this goals-only defensive geometry.)

## 2.4 External validation — NOT RUN

External validation is judged only at the granularity that SURVIVES 2.3. No granularity survived (neither coarse nor fine cleared the gate), so the one permitted external lookup was **not used** — there is no stable inferred identity to validate against reported systems.

## 2.5 VERDICT (pre-stated)

- Continuity gradient positive & CI-clean? **NO** (slope +0.01, CI includes 0).
- High-continuity coarse persistence ≥ 0.4? **NO** (0.16).

### ➡ **VERDICT: FAIL.**

**Packaged null (a real finding): goal-derived defensive scheme identity is too faint to build on.** The clustering yields interpretable coarse types (collapse / step-up / baseline), but a team does not reliably keep its type season-to-season (label stability ≈ chance), the between-season signature barely exceeds the within-season noise floor, and what little persistence exists tracks **neither** roster continuity nor the coach. Team defensive identity is not recoverable from this goal geometry at a usable level.

**Consequence (pre-stated):** Phases 3–7 are cancelled. Player role-within-scheme, own-system deviation, and pairing/scheme-dependence all presuppose a stable team scheme, which does not exist here. The finding holds an F-number for the owner; nothing is promoted.

## STOP — owner rules survival.
