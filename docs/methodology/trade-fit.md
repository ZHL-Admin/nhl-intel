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
2. **Need fit — an asymmetric ADDITIVE bonus, not an averaged term.** The team's `team_needs`
   gap, **weighted by where the player provides value** (his composite-component profile). Need is
   **not** blended into the base score; it is added on top (see *Combined headline*): a real gap
   adds up to `NEED_BONUS_MAX = 0.12`, while a surplus / no gap adds **exactly 0**. So need can
   only **help** — it never drags a score down. (The breakdown still shows a Need *level*
   `max(NEED_FLOOR, sigmoid(gap/SCALE))` for the bar, but that display value no longer enters the
   score.) This fixes the prior structure where need was a 4th averaged, floored term: a top-5
   player going to a team already strong at his position was mathematically *demoted* purely for
   the absence of a gap, which is wrong — a great player is a great add regardless of need.
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

The score is a player-and-fit **base** (gated by positional relevance) plus an asymmetric **need
bonus**:

```
base          = weighted_avg(quality, line, style)          # talent-dominant; n/a dims renormalise
gated_base    = positional_gate × base                      # gate ∈ [0.55, 1]
need_bonus    = NEED_BONUS_MAX × max(0, 2·sigmoid(gap/SCALE) − 1)   # ∈ [0, 0.12]; 0 for a surplus
overall       = clamp(gated_base + need_bonus, 0, 1)
```

with base weights `quality 0.45 / line 0.30 / style 0.25` (quality dominant — talent is good
regardless of need; line is the most concrete value-in-context; style third). `NEED_BONUS_MAX =
0.12` is large enough that filling a real hole visibly lifts the grade (≈ a B→A- bump) yet small
enough it can **never rescue a bad player** (0.30 base + 0.12 = 0.42 is still C/D). The 0-1 score
maps to a letter via `GRADE_BANDS` (**A ≥ 0.70, B ≥ 0.56, C ≥ 0.42, D ≥ 0.30, else F** — re-tuned
to the post-change distribution, which removing the need drag lifted; see *Validation*). All
constants live in `config.TRADE_FIT`.

Need is **asymmetric**: a big gap is a large positive, low need is **neutral** (no bonus, no
penalty). Because the gate ≥ 0.55 and quality dominates the base, **the headline never reads 0/F
for a positionally-relevant contributor**, and a great player to a team with no gap still grades A
(talent carries; the missing need simply adds nothing). A *below-replacement* player still grades
F — correctly, he is not a contributor, and no amount of need rescues him.

The `verdict_sentence` is deterministic, names the tangible drivers, and **explicitly states the
model can't see injury / cap / roster context** so the user integrates it. The grade is always
rendered *with* the five dimensions beneath it — the decomposition is the product; the grade is the
glance.

## Why these design choices

- **Need is an asymmetric bonus, not an averaged term.** Need is *relative to talent*, not a flat
  contributor to a mean. Averaging it in (the old structure) dragged every low-need trade toward the
  floor, so a top-5 player to a team strong at his position scored *lower* than the identical player
  to a needy team — penalising the absence of a gap. As an additive bonus, filling a hole is upside
  and low need is neutral: a great player is a great add regardless of need.
- **Bonus capped so it can't rescue a bad player.** `NEED_BONUS_MAX = 0.12` lifts a real-need fit by
  about one grade step but cannot turn a below-average player into a good fit (validated below).
- **Quality dominates the base.** Talent is the largest base weight (0.45); when a grade is held
  down it's attributed to the player's value, not to a lack of need (the verdict says so).
- **Colour discipline (UI).** Low need uses a neutral tone, never red — low need is "not a gap,"
  not a failure. A genuine stylistic mismatch is amber-orange, not red.

## Validation (`models_ml/validate_trade_fit.py`)

The script prints the decomposition (gate, base, need_bonus, final, grade) per case and asserts the
asymmetry. The must-hold property: **low need never lowers a grade (bonus ≥ 0); need can only help;
a bad player is never rescued by need alone.** Results (2025-26):

| case | gated_base | need_bonus | final | grade | the point |
|---|---|---|---|---|---|
| Top-5 (McDavid) → **strong / low-need** team | 0.746 | **+0.00** | 0.746 | **A** | the key test — talent carries, no gap adds nothing and does **not** penalise |
| Top-5 (McDavid) → **big-need** team | 0.741 | +0.077 | 0.818 | **A** | same player, real hole → a bonus on top (the highest grade) |
| Below-avg D (Kesselring) → ANA (low need) | 0.452 | +0.00 | 0.452 | **C** | elite line/style fit, **dragged only by below-average value** — not D, and need doesn't drag it |
| Mediocre D → big-need team | 0.411 | +0.079 | 0.491 | **C** | the bonus lifts a middling player a step, but can't make him good |
| Bad D → low-need team | 0.233 | +0.00 | 0.233 | **F** | bad player, no help |
| Bad D → **big-need** team | 0.202 | +0.072 | 0.274 | **F** | full need bonus **cannot rescue** a below-replacement player |

The asymmetry is confirmed: removing the need bonus never raises a grade (it's ≥ 0), low/no need
contributes exactly 0, and need-driven lift can never carry a bad player to a good grade.

No dimension floors at 0 inappropriately, no `max(0,)` clamp remains, and the headline never reads
0/F for a positionally-relevant contributor. RAPM / GAR / composite / archetype-v2 are reused, not
retrained.
