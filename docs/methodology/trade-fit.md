# Trade Fit — multi-dimension fit

"Fit" is not one number. The original tool scored fit as a single cosine of the player's
profile against the team's *need* vector (positive gaps only), floored at 0. That collapsed
three different questions into one and produced a now-famous bug: **a defenseman who addresses a
defensive need at a defense-STRONG team scored ~0** — position was never a term, and a surplus
team's need vector was empty exactly where the player was strong, so the cosine went to zero.

The rebuild measures fit on **five separate dimensions**, shows them all, and combines them into a
single letter grade that is *always* decomposable into its parts (the same discipline as the
player-card Overall). `models_ml/score_team_fit.py` → `POST /tools/trade-fit`.

## The five dimensions

Each is a real spectrum in [0, 1]. **None floors at 0 for a relevant player**, and there is no
`max(0, …)` clamp on the cosine anywhere.

1. **Positional fit (the gate).** Does the player's position + handedness + role slot into the
   team? Every NHL team ices forwards and defensemen, so any skater starts from a high base
   (0.82), nudged ±0.12 by the team's handedness balance at his position (a right-shot D is worth
   more to a team light on right-shot D). The result is **bounded in `[GATE_FLOOR=0.55, 1]`** and
   *multiplies* the blend below — so a positionally-relevant player can **never** be zeroed.
2. **Need fit.** The team's `team_needs` gap, **weighted by where the player provides value**
   (his composite-component profile), passed through a sigmoid. A big positive gap reads ~0.9; a
   **surplus reads ~0.15 — low, never negative, never red.** Low need = "not a statistical gap,"
   not "bad fit." A team strong at a position can still validly add a player, so there is **no
   redundancy penalty**.
3. **Style fit.** Does the player generate offense the way the team does? The comparable axis is
   the **rush-vs-(forecheck/cycle) orientation** — each entity's own balance (a within-entity
   ratio), which sidesteps the player-percentile-within-position vs team-percentile-within-league
   scale mismatch. A transition/rush creator into a rush team fits; into a grind-it-out cycle team
   it's a partial mismatch; a balanced team reads neutral. Reuses `mart_team_identity`.
4. **Line fit.** Would he improve the line/pair he'd slot into? We take the team's current top
   unit for his position over its last 10 games, swap him in for the lowest-WAR member, and project
   with the line-fit model (`score_line`). A model estimate — it carries its interval as softness.
5. **Player quality.** His actual level — WAR percentile within position (+ RAPM impact). A good
   fit who is also good matters more than a good fit who is mediocre. Carries the WAR band.

## Combined headline

```
overall = positional_gate × weighted_avg(need, style, line, quality)
```
with weights `need 0.28 / style 0.24 / line 0.20 / quality 0.28` (n/a dimensions drop out and the
weights renormalise). The 0-1 score maps to a letter via `GRADE_BANDS` (A ≥ 0.70, B ≥ 0.58,
C ≥ 0.46, D ≥ 0.34, else F). All constants live in `config.TRADE_FIT`.

Because the gate ≥ 0.55 and quality is weighted, **the headline never reads 0/F for a positionally-
relevant contributor** — a genuinely good player who simply doesn't fill a need lands at C/B, not
F. (A *below-replacement* player can still grade F: that is correct, he is not a contributor.)

The `verdict_sentence` is deterministic, names the tangible drivers, and **explicitly states the
model can't see injury / cap / roster context** so the user integrates it. The grade is always
rendered *with* the five dimensions beneath it — the decomposition is the product; the grade is the
glance.

## Why these design choices

- **Need is one dimension, not the master axis.** Trades happen at strong positions too (injury,
  departure, upgrade). Treating need as the whole score is what produced the zero bug.
- **No redundancy penalty.** Strength at a position does not subtract from fit; it just means the
  case is "fit-and-upgrade," not "need."
- **Colour discipline (UI).** Low need uses a neutral/amber tone, never red — low need is "not a
  gap," not a failure. Strong dimensions use the positive ramp; a genuine stylistic mismatch is
  amber-orange, not red.

## Validation (`models_ml/validate_trade_fit.py`)

Disagreement cases, where need and style/quality diverge (2025-26):

| case | overall | need | the point |
|---|---|---|---|
| Off. D (Hutson) → **strong-def** VGK | **B (62)** | 32 (low) | **was 14.8** — style/line/quality carry it |
| Def. D (Slavin) → **strong-def** VGK | **C (56)** | 19 (low) | **was ~0** — the headline bug is fixed |
| Off. D (Hutson) → **weak-def** CHI | A (75) | 92 (high) | same player, need higher → higher grade |
| Star (McDavid) → CAR vs CBJ | B 60 vs B 59 | — | **style 93 vs 53** — style differs by team |
| Below-replacement D → TOR | F (28) | 50 | quality 0th-pctile → F (correctly; not a contributor) |

No dimension floors at 0 inappropriately, no `max(0,)` clamp remains, and the headline never reads
0/F for a positionally-relevant contributor. RAPM / GAR / composite / archetype-v2 are reused, not
retrained.
