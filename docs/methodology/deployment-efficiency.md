# Deployment efficiency (the Divergence Board rework)

`nhl_models.deployment_efficiency` — built by `models_ml/compute_deployment_efficiency.py`.
Replaces the old `divergence_board` construction. RAPM / composite / GAR / win-probability are
read-only inputs here.

## What it measures

For each **situation lens**, a player's **actual** usage is compared with the usage his
situation-appropriate **value** justifies, within position:

    divergence (gap) = actual_usage_percentile − justified_usage_percentile      (within position)
    gap > 0  → OVER-used  (deployed beyond what his impact warrants)
    gap < 0  → UNDER-used (value the coach leaves on the bench)

`justified_usage_percentile` = the player's **value percentile mapped onto the usage
distribution**, capped at a realistic ceiling. (A value→usage *regression* was tried first and
rejected: its predictive power is weak — defensemen `r ≈ 0.25` — so "justified" collapsed to the
league mean and the board degenerated into a usage ranking. The direct percentile mapping makes
justified actually track value.)

## Per-situation value pairing (the core fix)

The old board judged *every* situation against composite value plus a defense-weighted trust
score. That broke the under-used side: it mechanically surfaced every offensive star (Quinn
Hughes, MacKinnon) because the trust metric captured defensive-role specialization, not usage
**magnitude**. Each lens now pairs the right value against the right usage:

| Lens | Actual usage | Justified by |
|---|---|---|
| All | total TOI / game | overall value (`player_composite.total`) |
| 5v5 | 5v5 TOI / game | even-strength RAPM (`off_impact + def_impact`) |
| PP | PP TOI / game | PP impact (`pp_impact`) |
| PK | PK TOI / game | **blend toward `pk_impact`** + general `def_impact` (see below) |
| Key moments | high-leverage TOI / game | overall value |

**Key moments** is leverage-defined, not a hand-listed situation set: the most pivotal
`KEY_MOMENT_LEVERAGE_PCTILE` (top 25%) of game time by the win-probability **leverage**
distribution. The threshold is a percentile of the real leverage distribution (≈ `0.396`),
documented as data-derived rather than hand-picked. Leverage is more principled than enumerating
"protect a lead late" situations because it weights every second by how much a goal would actually
swing the win probability.

## The usage ceiling

Justified usage is capped at the realistic maximum — the `USAGE_CEILING_PCTILE` (97th) of observed
per-game usage within position+situation (data-derived, not an arbitrary number, e.g. ~24.6 min/gm
for D in the ALL lens). A maxed-out star whose value would "predict" impossible minutes has his
justified usage clamped to the ceiling, so his actual ≈ capped-justified and his gap closes — he
does **not** read as under-used. (Validated: Quinn Hughes and McDavid are absent from the ALL
under-used side.)

## Reliability: floors, the PK blend, and the confidence sort

Value estimates from a fringe player are small-sample noise, so the board requires
`MIN_TOTAL_TOI` (600 min) + `MIN_GAMES` (60) + `MIN_EV_TOI` (500 5v5 min) over the window.

- **Under-used floor (total lenses only):** for All / 5v5 / Key moments a near-zero-usage player
  is a healthy scratch, not "under-used" — he must clear `MIN_UNDERUSED_ACTUAL_PCTILE` (12th) to
  appear. PP/PK keep zero as the insight (a strong candidate who kills nothing).
- **PK blend (`PK_BLEND_W` = 0.75):** PK justified value is `pk_impact` blended with general
  `def_impact` (each normalised to unit variance), weighted toward `pk_impact`. Pure `def_impact`
  floods the under-used side with offensive forwards whose single-season defensive RAPM is noisily
  high but who have no PK track record; weighting toward `pk_impact` (≈0 for non-killers) damps that
  noise. A genuine two-way defenseman who kills few PKs keeps a real signal.
- **PK reliability gate (`DEF_SD_GATE_PCTILE` = 0.5):** a player may only be flagged under-deployed
  on the PK if his value estimate is reliable (value-sd at or below the within-position median).
- **Confidence sort:** every board ranks by a confidence-adjusted gap (`gap` shrunk toward 0 by
  `CONFIDENCE_K`·`gap_sd`), so a soft/wide-band mismatch ranks below a confident one. Uncertainty
  is surfaced in the UI; wide bands mean the gap is soft.

## The honest note on the change

The old board's `divergence = trust_z − composite_z`. Its **"trusted beyond value"** side worked
(it is the eye-test-vs-analytics signal — Lindgren, Glendening, Goodrow). Its **"value beyond
deployment"** side was **broken**: trust is defense-weighted, so any high-composite offensive star
sat there mechanically — it surfaced maxed-out players the coach was already playing 25 minutes a
night and said nothing a user didn't know. This rework replaces that side with an honest
actual-vs-justified-usage comparison plus the ceiling, and keeps the working side intact (validated
below).

## Validation (window `2023-24_2025-26`, regular + playoff)

- **ALL** — over-used: Trocheck, Matheson, Bedard, Letang (big minutes the model dislikes);
  under-used: **Jordan Spence** (value 10th of 248 D, usage 25th), Schmidt (19th), Brandt Clarke
  (25th) — analytics-darling, under-deployed; maxed-out stars absent.
- **PK** — over-used: Matheson, Gudbranson, Savard, **Lindgren** (heavy PK, low PK+def value — the
  old working cases preserved); under-used: led by two-way defensemen (Spence, Barron, Montour,
  Q. Hughes), with the noisy offensive forwards pushed down by the blend + reliability gate.
- **Key moments** — over-used: Trocheck, Matheson, Chiarot (trusted late, model-disliked);
  under-used: Spence, Andrae, Schmidt (value kept off the ice late).

Known limitation: the PK side leans on RAPM defensive impact, which is genuinely noisy for
forwards; the blend and reliability gate mitigate but cannot fully remove it.

## Endpoints

- `GET /players/deployment-board?situation={all|5v5|pp|pk|key_moments}` — both sides + caption.
- `GET /players/{id}/deployment` — a player's full deployment profile across all situations
  (the board-row expansion). The Players-index "Divergence board" tab renders both with a situation
  filter; the old `GET /players/divergence-board` endpoint is left in place (superseded, not removed).
