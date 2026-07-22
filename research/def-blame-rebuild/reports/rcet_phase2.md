# RCET Phases 0-2 — expected relative D-trajectory + VARIANCE-BAND GATE (controlled even rush)

Phases 0 (normalize) + 1 (per-axis expected curves + bands) + 2 (tightness gate). **STOP at the gate — no per-goal deviation, no diagnosis, no aggregation.** Plot: `reports/rcet_phase2.png`.

## Phase 0 — normalization + role/anchor (facts)

- Goals: **4,066** (5v5 · carried/passed · entry-captured · rushdef EVEN).
- Defensemen present at entry — histogram: {1: 946, 2: 2875, 3: 105, 4: 9} · one-D-only (no weak-side role): 946 · two-role goals: 3,120.
- Strong/weak role by entry geometry (goal-side + nearest carrier lane). **Contested (lane gap < 5 ft): 396** (9.7%).
- **Middle-lane entries (|carrier entry lateral| < 10 ft): 684** (16.8%) — flip left UNSET (sign +1) and FLAGGED; the lateral-axis norm/gate EXCLUDES them (sign ill-defined); depth & separation axes KEEP them (sign-independent).
- Anchor = designated ENTRY CARRIER (fixed man, tracked through passes). Clock: real seconds, t=0 at shot; median entry at **-3.0 s** before the shot (ragged entry end).

## Phase 2 — tightness gate (per axis at entry / mid / shot)

Bar: per-axis IQR ≤ ⅓ of the 5-95% inter-defender spread **AND** IQR materially tighter (< 0.8×) than the TIME-SCRAMBLED placebo (same defenders, shuffled time index). Lateral verdict excludes middle-lane.

| role | axis | checkpoint | n | median | IQR | 5-95% spread | ⅓ spread | placebo IQR | conv? | placebo? | TIGHT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| strong | rel_lateral | entry(~-3.0s) | 1,748 | -7.6 | **16.5** | 48.4 | 16.1 | 16.2 | n | n | no |
| strong | rel_lateral | mid(-1.0s) | 3,150 | -7.3 | **17.4** | 51.3 | 17.1 | 16.2 | n | n | no |
| strong | rel_lateral | shot(0.0s) | 3,228 | -4.8 | **16.1** | 51.8 | 17.3 | 16.2 | Y | n | no |
| strong | rel_depth | entry(~-3.0s) | 2,053 | 6.9 | **11.6** | 41.6 | 13.9 | 11.6 | Y | n | no |
| strong | rel_depth | mid(-1.0s) | 3,796 | 3.8 | **12.5** | 44.5 | 14.8 | 11.6 | Y | n | no |
| strong | rel_depth | shot(0.0s) | 3,908 | 1.5 | **12.9** | 50.8 | 16.9 | 11.6 | Y | n | no |
| strong | separation | entry(~-3.0s) | 2,053 | 14.8 | **15.7** | 42.2 | 14.1 | 14.4 | n | n | no |
| strong | separation | mid(-1.0s) | 3,796 | 15.2 | **16.0** | 41.2 | 13.7 | 14.4 | n | n | no |
| strong | separation | shot(0.0s) | 3,908 | 12.8 | **15.5** | 43.5 | 14.5 | 14.4 | n | n | no |
| weak | rel_lateral | entry(~-3.0s) | 1,337 | -26.0 | **25.5** | 62.9 | 21.0 | 26.5 | n | n | no |
| weak | rel_lateral | mid(-1.0s) | 2,404 | -18.4 | **27.0** | 63.0 | 21.0 | 26.5 | n | n | no |
| weak | rel_lateral | shot(0.0s) | 2,435 | -11.5 | **25.1** | 58.3 | 19.4 | 26.5 | n | n | no |
| weak | rel_depth | entry(~-3.0s) | 1,567 | 6.5 | **19.2** | 59.9 | 20.0 | 19.9 | Y | n | no |
| weak | rel_depth | mid(-1.0s) | 2,895 | 1.2 | **21.0** | 69.9 | 23.3 | 19.9 | Y | n | no |
| weak | rel_depth | shot(0.0s) | 2,942 | -1.0 | **20.7** | 73.5 | 24.5 | 19.9 | Y | n | no |
| weak | separation | entry(~-3.0s) | 1,567 | 29.7 | **21.7** | 53.4 | 17.8 | 22.1 | n | n | no |
| weak | separation | mid(-1.0s) | 2,895 | 26.4 | **22.1** | 52.2 | 17.4 | 22.1 | n | n | no |
| weak | separation | shot(0.0s) | 2,942 | 22.4 | **21.8** | 51.4 | 17.1 | 22.1 | n | n | no |

## Per-axis verdict (does the foundation separate?)

- **strong-side · rel_lateral**: TIGHT at 0/3 checkpoints (FAILS the gate).
- **strong-side · rel_depth**: TIGHT at 0/3 checkpoints (FAILS the gate).
- **strong-side · separation**: TIGHT at 0/3 checkpoints (FAILS the gate).
- **weak-side · rel_lateral**: TIGHT at 0/3 checkpoints (FAILS the gate).
- **weak-side · rel_depth**: TIGHT at 0/3 checkpoints (FAILS the gate).
- **weak-side · separation**: TIGHT at 0/3 checkpoints (FAILS the gate).

## STOP — owner review of the variance band (plot + verdict). No per-goal deviation, no diagnosis.
