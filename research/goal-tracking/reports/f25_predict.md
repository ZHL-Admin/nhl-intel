# F25 offensive-signature PREDICTIVE test (gated; nothing promoted)

**LAW 1 · GOALS-ONLY. Every tracked sequence ended in a goal; there is no tracked non-goal in this data. You may DESCRIBE and ATTRIBUTE what happened on goals and build goal-as-the-unit measurements. You may NEVER make a predictive or comparative 'what causes goals / what wins' claim from this data alone.** — tracking supplies only the SIGNATURE (early 2023-24); the OUTCOME is dense conventional stats (Atlas 5v5 on-ice + pbp scoring + on-ice TOI). Bar: incremental 5-fold-CV OOS R² ≥ +0.02 over the box-score autoregressive baseline (box at T → outcome at T+2). Signature = the 5 STABLE F25 fields (finisher/carrier/rush/entry_driver/net_front).

## Link 3 — GLOBAL: does early signature beat the box-score baseline for 2025-26 (T+2)?

| outcome | n | baseline CV R² | +signature incremental CV R² | noise floor | ≥+0.02? |
|---|---|---|---|---|---|
| xgf60 | 436 | 0.189 | **+0.038** | 0.011 | YES |
| pts60 | 434 | 0.389 | **+0.021** | 0.012 | YES |
| cf60 | 436 | 0.178 | **+0.029** | 0.011 | YES |
| toi_min | 436 | 0.238 | **+0.067** | 0.011 | YES |

## Link 4a — YOUNG / thin-track-record subset (bottom-40% 2023-24 TOI — where box score is least informative)

| outcome | n | baseline CV R² | +signature incremental CV R² | ≥+0.02? |
|---|---|---|---|---|
| xgf60 | 66 | 0.064 | **+0.076** | YES |
| pts60 | 66 | 0.056 | **-0.116** | no |

## Link 4b — BREAKOUT/BUST direction (xGF/60): does signature flag who beats the box next?

- CV directional accuracy = 0.534 (0.5 = coin flip); residual CV R² from signature = +0.036

## Link 4c — ROLE prediction (future 5v5 TOI): signature incremental over current TOI = +0.067 (n=436)

## Robustness — HARDER baseline: early signature (2023-24) vs MOST-RECENT box (2024-25) → predict 2025-26

- xgf60: baseline CV R² 0.316, +signature incremental **+0.003** (does NOT beat the recent-box baseline)
- toi_min: baseline CV R² 0.302, +signature incremental **+0.052** (still beats the recent-box baseline)
## Link 5 — verdict (split: ROLE vs PRODUCTION, after the robustness check)

- **ROLE prediction: a GENUINE, ROBUST predictive edge.** The signature forecasts future 5v5 TOI/usage beyond current usage — incremental CV OOS R² +0.05-0.07, and it HOLDS even against the MOST-RECENT box (2024-25). The buildup style (entry-driver/rush/net-front) predicts what ROLE a player grows into, which current usage does not fully capture. This is the mission's target: a real predictive signal from the tracking, on the stable offensive trait (F25).
- **PRODUCTION (xGF/60, points): NOT a durable edge.** The signature beats a STALE early box (+0.038) but does NOT beat the recent box (+0.003) — for how MUCH a player will produce, recent conventional stats are as good; the signature adds no durable info. The young/thin subset hint (xGF +0.076) is vs the stale box and n=66 — suggestive, not robust.
- **Breakout/bust direction:** marginal (accuracy ~0.53) — weak, don't over-claim.
- **Net:** the F25 offensive signature is BOTH a validated descriptive asset AND a robust predictor of future ROLE (not production). First predictive success in the program — aimed at the stable thing, and it forecasts role. Nothing promoted.

## STOP — owner review. Nothing promoted.
