# RCET §5(a) REFINE — clean-anchor gate + finer splits (anchor-vs-phenomenon test)

Re-run of the Phase 2 variance-band gate (same bar: per-axis IQR ≤ ⅓ of 5-95% spread AND ratio real/placebo < 0.8) on the CLEAN-ANCHOR subset (no carrier change) and finer splits. **STOP at the gate — nothing past it.** Plot: `reports/rcet_refine_cleananchor.png`.

## Clean-anchor subset: **1,802 goals** (of 4,066; the ≥46% where the entry carrier keeps the puck)

The decisive test: here relative-to-carrier is measured against the right object throughout. If bands tighten and beat the placebo → the smear was the anchor. If still ≈placebo → the smear is the phenomenon.

| role | axis | checkpoint | n | IQR | ⅓ spread | placebo | ratio real/placebo | conv? | beats placebo? | TIGHT |
|---|---|---|---|---|---|---|---|---|---|---|
| strong | rel_lateral | entry(-2.0s) | 920 | **15.7** | 15.6 | 16.0 | **0.98** | n | n | no |
| strong | rel_lateral | mid(-1.0s) | 1,397 | **16.9** | 15.2 | 16.0 | **1.06** | n | n | no |
| strong | rel_lateral | shot(0.0s) | 1,477 | **13.9** | 15.0 | 16.0 | **0.87** | Y | n | no |
| strong | rel_depth | entry(-2.0s) | 1,053 | **10.1** | 13.1 | 11.2 | **0.91** | Y | n | no |
| strong | rel_depth | mid(-1.0s) | 1,680 | **11.3** | 13.7 | 11.2 | **1.01** | Y | n | no |
| strong | rel_depth | shot(0.0s) | 1,794 | **10.6** | 14.9 | 11.2 | **0.95** | Y | n | no |
| strong | separation | entry(-2.0s) | 1,053 | **15.2** | 13.1 | 14.2 | **1.07** | n | n | no |
| strong | separation | mid(-1.0s) | 1,680 | **15.4** | 13.0 | 14.2 | **1.09** | n | n | no |
| strong | separation | shot(0.0s) | 1,794 | **12.5** | 13.3 | 14.2 | **0.88** | Y | n | no |
| weak | rel_lateral | entry(-2.0s) | 693 | **28.3** | 21.7 | 27.0 | **1.05** | n | n | no |
| weak | rel_lateral | mid(-1.0s) | 1,058 | **27.1** | 20.3 | 27.0 | **1.0** | n | n | no |
| weak | rel_lateral | shot(0.0s) | 1,094 | **24.9** | 17.9 | 27.0 | **0.92** | n | n | no |
| weak | rel_depth | entry(-2.0s) | 799 | **21.7** | 22.4 | 22.1 | **0.98** | Y | n | no |
| weak | rel_depth | mid(-1.0s) | 1,275 | **21.6** | 24.1 | 22.1 | **0.98** | Y | n | no |
| weak | rel_depth | shot(0.0s) | 1,328 | **19.2** | 25.7 | 22.1 | **0.87** | Y | n | no |
| weak | separation | entry(-2.0s) | 799 | **21.0** | 17.9 | 22.0 | **0.95** | n | n | no |
| weak | separation | mid(-1.0s) | 1,275 | **21.5** | 18.5 | 22.0 | **0.98** | n | n | no |
| weak | separation | shot(0.0s) | 1,328 | **21.5** | 18.0 | 22.0 | **0.97** | n | n | no |

## Finer splits within clean-anchor (placebo ratio real/placebo at each checkpoint; ratio < 0.8 = beats placebo)

| split (N goals) | role | axis | n@shot | ratio entry | ratio mid | ratio shot | any TIGHT? |
|---|---|---|---|---|---|---|---|
| clean+WING (1,483) | strong | rel_lateral | 1,477 | 0.98 | 1.05 | 0.87 | no |
| clean+WING (1,483) | strong | rel_depth | 1,477 | 0.92 | 1.02 | 0.97 | no |
| clean+WING (1,483) | strong | separation | 1,477 | 1.0 | 1.07 | 0.88 | no |
| clean+WING (1,483) | weak | rel_lateral | 1,094 | 1.05 | 1.0 | 0.92 | no |
| clean+WING (1,483) | weak | rel_depth | 1,094 | 0.99 | 0.96 | 0.87 | no |
| clean+WING (1,483) | weak | separation | 1,094 | 0.97 | 0.98 | 1.0 | no |
| clean+MIDDLE (319) | strong | rel_depth | 317 | 0.99 | 1.06 | 0.92 | no |
| clean+MIDDLE (319) | strong | separation | 317 | 1.06 | 1.11 | 0.86 | no |
| clean+MIDDLE (319) | weak | rel_depth | 234 | 0.97 | 0.96 | 0.95 | no |
| clean+MIDDLE (319) | weak | separation | 234 | 1.06 | 1.06 | 0.97 | no |
| clean+FAST (875) | strong | rel_lateral | 671 | 1.04 | 1.05 | 0.68 | **YES** |
| clean+FAST (875) | strong | rel_depth | 872 | 0.88 | 1.01 | 0.83 | no |
| clean+FAST (875) | strong | separation | 872 | 0.91 | 0.99 | 0.72 | **YES** |
| clean+FAST (875) | weak | rel_lateral | 483 | 1.22 | 1.08 | 0.85 | no |
| clean+FAST (875) | weak | rel_depth | 625 | 1.05 | 0.98 | 0.9 | no |
| clean+FAST (875) | weak | separation | 625 | 1.08 | 1.01 | 0.94 | no |
| clean+CONTROLLED (927) | strong | rel_lateral | 806 | 1.0 | 0.94 | 1.01 | no |
| clean+CONTROLLED (927) | strong | rel_depth | 922 | 0.86 | 0.95 | 1.16 | no |
| clean+CONTROLLED (927) | strong | separation | 922 | 0.98 | 1.03 | 0.98 | no |
| clean+CONTROLLED (927) | weak | rel_lateral | 611 | 1.01 | 0.95 | 0.91 | no |
| clean+CONTROLLED (927) | weak | rel_depth | 703 | 0.96 | 0.99 | 0.96 | no |
| clean+CONTROLLED (927) | weak | separation | 703 | 0.94 | 0.97 | 1.03 | no |

## Verdict

- **Clean-anchor gate: 0/18 cells TIGHT.** All ratios real/placebo cluster at ~0.86–1.08 (≈1.0) — identical to the pooled gate. Removing the carrier-change smear did NOT tighten the bands.
- Split cells TIGHT at ≥1 checkpoint: 2; COHERENT (TIGHT at ≥2 of 3 checkpoints): **0** .
- The 2 stray TIGHT cell(s) are single-checkpoint (all at the SHOT instant, in clean+FAST/strong only) with entry/mid ratios ~1.0 — mechanical (at the shot everyone converges on the puck), NOT a coherent time-locked trajectory. Treated as noise, not a pattern.
- **Clean-anchor is STILL ≈ placebo — the smear is the PHENOMENON, not the anchor.** The carrier-change lever was pulled (pre-identified, mechanically motivated) and did not rescue the pattern. This is the earned **§5(b) conclusion**: the continuous role-conditioned trajectory does not recover a tight, time-locked pattern even on the cleanest rushes — consistent with F29/F32/F34.

(Speed split threshold: entry→shot median = 2.2s; fast < that, controlled ≥. Middle-lane split N is small — 319 goals — and lateral axis is N/A there by construction.)

## STOP — owner review of the refined gate. Nothing past it.
