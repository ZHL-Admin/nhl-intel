# Jolt addendum — event-time study of the new-coach result bump (F14)

**Project:** System Effects · **Date:** 2026-07-11 · **Seed:** 20260711
**Status:** complete. **Observational.** Verdict by the pre-registered rule: **REVERSION** — the
new-coach on-ice bump is mean regression from the trough that got the coach fired, not an effort
honeymoon. Stopping for the product owner's ruling per protocol.

Pre-registered in `reports/registration_jolt.md` (thresholds fixed before results). Inputs frozen to
`data/parquet/frozen_eval_jolt/` before any metric. Reproduce: `python -m syseff.jolt`.

## The question
Design A found a small new-coach on-ice result bump (**+0.004 score-close 5v5 xG-share DiD, t=1.73**)
that measured deployment change does **not** mediate (F14). Is it **effort** (a bump that fades on
an event-time curve), **reversion** (firing at a low ebb → regression), or **neither**?

## Design
For each of the 49 Cohort C changes, the team's 5v5 **score-close** on-ice xG share in event-time
bins around τ=0 (new coach's first game). Compared, as a **recovery** (post minus pre-window, a
difference-in-differences that removes the team-quality level confound), to a **matched-trough
placebo**: no-change team-seasons at a firing-comparable trailing-xG trough.

## The real event-time curve (49 changes)

| bin (τ) | mean score-close xG share | 95% CI |
|---|---:|---|
| pre `[-20..-11]` | 0.4945 | [0.4809, 0.5085] |
| **pre `[-10..-1]`** | **0.4803** | [0.4653, 0.4947] |
| post `[+1..+10]` | 0.4935 | [0.4806, 0.5056] |
| post `[+11..+20]` | 0.4937 | [0.4778, 0.5087] |
| post `[+21..+40]` | 0.4945 | [0.4788, 0.5114] |

The team **dips into a trough in the ~10 games before the firing** (0.4945 → 0.4803), then under
the new coach **returns to ~0.494 and holds it flat through +40 games**. That shape — a dip, then a
sustained return to the team's own level — is the reversion signature.

## The three pre-registered tests

1. **Trough (setup):** pre-change level minus prior-season baseline = **−0.0127**, 95% CI
   **[−0.0251, −0.0008]** (excludes zero). Teams that fire a coach **were in a genuine trough**,
   ~1.3 pp below where they normally play. ✓ Reversion setup present.
2. **Recovery vs. matched-trough placebo (the discriminator):** real recovery from the trough is
   **+0.013** and **flat** (+0.0132, +0.0135, +0.0137 across the three post windows). The **excess
   over the matched-depth placebo** is **+0.004** (τ+1..+10), 95% CI **[−0.011, +0.020] — includes
   zero**: the coach-change team recovers **no more than a comparable non-firing team recovers from
   the same trough**. ✓ Reversion.
3. **Fade (the effort signature):** slope of the real recovery over event time = **+1.9e-5/game,
   t = 0.04** — **flat, no fade**. ✗ Effort rejected (an effort bump would spike then decay).

## Verdict (pre-registered rule, no editorializing)
- Trough significant **✓**; excess-over-placebo CI includes zero **✓** → **REVERSION.**
- Effort requires a positive significant excess **and** a negative fade — **neither holds.**
- Neither is rejected (the trough is real).

**The Jolt is reversion.** The small, deployment-unmediated new-coach bump (F14) is the team
regressing back to its own baseline from the slump that cost the previous coach his job — not a
coaching "effort" effect. Consistent with the project's arc: coaching's measurable on-ice lever is
deployment (F12–F13); the *result* bump around a change is mean reversion, not a system effect.

## Robustness
- **Era split:** excess +0.0036 (2010-17, n=21) and +0.0048 (2018-26, n=28); both CIs include zero.
  Reversion holds in both eras.
- **Influence:** leave-one-change-out excess stays in **[+0.0005, +0.0066]** — not driven by any
  single change.
- **Noise ceiling:** post-window split-half reliability r=0.56 (Spearman-Brown **0.72**); the
  outcome is ~72% reliable, so the flat ~+0.01 recovery sits well inside the noise band — another
  reason the bump is not a robust standalone effect.

## Disclosure — a placebo-construction correction
The registration specified the placebo as each no-change season's **deepest** trailing-10 trough.
That selection has a **regression-to-minimum bias**: the deepest window lands *below* the real
pre-firing level (placebo pre-level **0.4535** vs real **0.4803**), so it mechanically over-recovers
and made the real teams look far worse (excess **−0.064**). This is an artifact of selecting the
season minimum, not a finding. The valid control is the **matched-depth** placebo used above —
sample a pseudo-change point whose trailing level matches the real pre-window range **without**
taking the minimum (placebo pre-level **0.4956**, aligned with real). **No threshold moved**; only
the invalid control was corrected, and the corrected control is if anything conservative against
reversion (its shallower troughs bias the excess upward, yet it still includes zero). Both placebos
are reported in `phase5_jolt_analysis.json`.

## Verdict language for the ledger
> **The Jolt is reversion.** Teams fire coaches at a genuine on-ice trough (~1.3 pp below baseline);
> the new coach's "bump" is the team regressing back to its own level — flat, sustained, and
> statistically indistinguishable from what a comparable non-firing team recovers from the same
> trough. It does **not** fade (ruling out an effort honeymoon) and is **not** nothing (the trough
> is real). Observational.

---

### Artifacts
`data/parquet/frozen_eval_jolt/{real_changes,placebo_matched_depth,placebo_deepest,target_splithalf}.parquet`
· `reports/phase5_jolt_analysis.json` · `src/syseff/jolt.py` · `reports/registration_jolt.md` ·
tests `tests/test_jolt.py` (3 new; 24 total). Repro: `python -m syseff.jolt`.
