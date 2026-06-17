# Value — Goals/Wins Above Replacement (GAR/WAR)

GAR is the **goals-reality companion** to RAPM impact, not a replacement for it. RAPM
(`nhl_models.player_impact`, see [isolated-impact.md](isolated-impact.md)) measures *repeatable
play-driving* on the in-house xG layer — **what tends to repeat**. GAR measures **actual goals
contributed above a freely-available replacement player**, across all situations, on the goals
scale — **what happened**. It inherits shooting luck *by design*; that is the entire point of a
second lens, and it is labeled as such everywhere. GAR is never presented as predictive.

This is the skater entry in the site's recurring **actual-vs-expected** motif: deserved standings
(team: simulated vs actual points), GSAx-vs-Edge (goalie: our save value vs a second opinion), and
now **Impact (RAPM) vs Value (GAR)** for skaters. `models_ml/compute_gar.py` →
`nhl_models.player_gar`; `models_ml/validate_gar.py` runs the checks below.

## Goals-based vs xG-based

The **offensive** side is fully goals-based — actual goals and assists — because that is where
the finishing question lives. The **defensive** side borrows RAPM. So GAR is *mostly* actual, not
purely actual:

| component | basis | definition |
|---|---|---|
| `ev_offense` | **actual goals** | 5v5 (goals + 0.7·primary + 0.5·secondary assists) per 60 above the replacement rate, × 5v5 TOI/60, normalized to league goals (below) |
| `pp` | **actual goals** | same, on the power play, × PP TOI/60 |
| `ev_defense` | **xG (RAPM)** | RAPM `def_impact` above the replacement defensive level, × 5v5 TOI/60 |
| `pk` | **xG (RAPM)** | RAPM `pk_impact` above the replacement PK level, × PK TOI/60 |
| `penalty` | counts | (penalties drawn − taken) × `PENALTY_VALUE_GOALS` |
| `faceoff` | counts | centers only: net faceoff wins × `FACEOFF_VALUE_GOALS` |

`GAR = Σ components`; `WAR = GAR / GOALS_PER_WIN`.

**Offensive normalization (no triple-count).** A goal credits its scorer (1.0) and assisters
(0.7 / 0.5), ~2.2 credit units per goal. Summed raw, that doubles offensive GAR. The assist values
are therefore treated as *relative* weights and the offensive total is rescaled so league weighted
credit equals actual league goals (per strength). `ev_offense`/`pp` then read as "goals' worth of
real scoring involvement above replacement," fully goals-based with no triple-count.

## Every modeling constant (`config.GAR_CONFIG`)

- `GOALS_PER_WIN = 6.0` — ~6 GF ≈ 1 standings win in the modern NHL (Evolving-Hockey GAR /
  Hockey-Reference point shares). `WAR = GAR / 6`.
- `PRIMARY_ASSIST_VALUE = 0.70`, `SECONDARY_ASSIST_VALUE = 0.50` — of a goal; adopted from the
  public GAR / point-share literature (a goal is worth more than the assists on it). Computing
  these from a league regression is a documented future refinement; the relative weighting + the
  normalization above make the scale honest regardless.
- `PENALTY_VALUE_GOALS = 0.17` — a drawn penalty grants a power play worth ~league PP conversion
  (~17–20%). Conservative vs composite's flat 0.2; per-season conversion is a minor refinement.
- `FACEOFF_VALUE_GOALS = 0.001` — marginal goals per net faceoff win (public faceoff-value
  research); a completeness term, not a driver.
- Replacement level — see below.

## Replacement level

Replacement = a freely-available player (waiver / AHL call-up / 13th–14th forward, 7th–8th
defender). Defined per (position, strength, season-window) as the mean per-60 production of the
**depth pool**: skaters ranked below their team's depth threshold by season 5v5 TOI
(`REPLACEMENT_DEPTH_RANK`: F ranked > 9, D > 6), with at least `REPLACEMENT_MIN_TOI_5V5` = 50 5v5
minutes (rate stability); if a pool is thin (< `REPLACEMENT_MIN_POOL` = 40) it widens to all
seasons. A player's component GAR = (his per-60 − replacement per-60) × his TOI/60 in that state.

**Absolute GAR levels are sensitive to this choice; rankings are not.** Re-running with a tighter
pool (F>10/D>7) and a looser one (F>8/D>5):

| pool | rank Spearman vs base | median GAR shift |
|---|---|---|
| tighter (F10/D7) | 0.999 | +0.4 |
| looser (F8/D5) | 0.997 | −0.8 |

So the UI leads with **ranking and percentile**, not the raw number.

## The stability finding (a genuine result, not a caveat)

The intuition behind a Value vs Impact split is "actual goals are noisy, advanced impact is
stable, trust the advanced number." **In our data that folk ordering is half-backwards.**
Year-over-year correlation (single-season pairs 2021-22…2025-26, qualified skaters,
`validate_gar.py`):

| lens | YoY r | reading |
|---|---|---|
| actual production (5v5 goal-rate) | **0.66** | sticky — usage and shot volume persist |
| RAPM isolated offensive rate | **0.38** | the *noisier measurement* — regularized isolation adds estimation noise |
| finishing residual (goals − xG) | **0.35** | the only truly luck-flavored slice |

Production repeats *more* than the "advanced" isolated rate. What does **not** repeat is the
**finishing residual** — the exact piece that opens a Value-vs-Impact gap. That asymmetry drives
the two reads, which are deliberately **not symmetric**:

- **Value ≫ Impact** (produces above his play-driving): the production is real and tends to
  persist (r=0.66); only the finishing edge opening the gap is unrepeatable (r=0.35), so expect
  the gap to narrow even if the production holds. The *softer* case.
- **Impact ≫ Value** (drives play, hasn't finished): the **better-grounded regression case** —
  his chances are real and repeatable (r=0.66) and only his poor finishing is the unrepeatable
  part (r=0.35). A buy-low signal with more statistical support than fading a finisher's hot run.

The panel and `insight_engine/templates/value_gap.py` cite these r-values verbatim so "least
repeatable" traces to a number (consistency rule), and the Value uncertainty band says the same
thing visually.

## Validation

- **Intended divergence confirmed** (3-season window): Kucherov **GAR #4 / RAPM-offense #11**,
  Panarin **#11 / #40**, Reinhart **#5 / #837** — elite actual production the isolated impact
  doesn't fully credit. McDavid #1, MacKinnon #2 (aligned). Per the principle, Kucherov ranks
  highly in GAR *despite* a modest RAPM — that gap is the product.
- **Distribution** right-skewed (skew 1.84): most qualified skaters near replacement, stars far
  above; centers near 0 at replacement.
- **Uncertainty band** is dominated by the borrowed RAPM defensive sd plus a shooting-variance
  term on the actual-goals offense — prominent on a finisher whose gap may be partly noise.

## Honest limitations

- GAR is "what happened," not a projection — it includes shooting luck on purpose. Never read it
  as predictive; the band and the gap read both say so.
- EV-defense and PK borrow RAPM (xG-based), so GAR is *mostly* actual; the offensive side (the
  finishing question) is fully goals-based.
- Replacement absolute level is a modeling choice (levels move, rankings don't).
- `other`-strength offense (4v4/3v3/EN/shorthanded goals) is excluded from the actual-offense
  components — a small omission, documented.

## Goalie GAR / WAR — the cross-position currency

Goalies get their own value model (`models_ml/compute_goalie_gar.py` → `nhl_models.goalie_gar`),
the goaltending entry in the same actual-vs-expected family. It is **read-only** over the GSAx
layer (`int_goalie_shots` / `mart_goalie_*`, see [goaltending.md](goaltending.md)); the xG model,
RAPM, and the skater GAR model above are all untouched.

**Goalie GAR = goals saved above a replacement (backup) goalie**, decomposed into the stacked-bar
components (each is `goalie tier GSAx − replacement_GSAx_per_shot × goalie tier shots`):

| component | basis | definition |
|---|---|---|
| `hd_saves` | GSAx | even-strength **high-danger** goals saved above replacement — the difference-maker |
| `md_saves` | GSAx | even-strength mid-danger goals saved above replacement |
| `ld_saves` | GSAx | even-strength low-danger (incl. unknown-coords) goals saved above replacement |
| `pk_goaltending` | GSAx | shorthanded / special-teams save value above replacement |

The four buckets partition **every** faced unblocked shot (EV/other split by danger; special = PK),
so they sum exactly to goalie GAR. `WAR = GAR / GOALS_PER_WIN`.

### Why WAR is the cross-position unit (and GAR is not)

`GOALS_PER_WIN` is the **same 6.0** as skaters (asserted at import in `config.py`). That shared
divisor is the *entire reason* a goalie's WAR is comparable to a skater's: a goal saved and a goal
created are both ~1/6 of a win. **Skater GAR and goalie GAR are different units** (within-position
goals above their own replacement) and are never sorted together — the mixed leaderboard
(`/rankings/value?scope=all`) sorts by **WAR only**, asserted by a test.

### Replacement level (config.GOALIE_GAR_CONFIG)

A replacement goalie is a freely-available **backup**: per season-window, the goalies ranked
**outside the top-32 by games** (32 = one starter per NHL team) who cleared a 150-shot floor. The
replacement save rate is measured **per danger tier and per strength**, so GSAx-above-replacement
decomposes into the components above. As with skaters, absolute levels move with this choice while
**rankings do not** — replacement sensitivity (window): rank Spearman **0.996** (tighter, rank>40)
and **0.999** (looser, rank>24); the UI leads with WAR/ranking.

### Reliability shrinkage — the honest point estimate (not the raw number)

Goaltending is **low-signal season to season**: a single window's GSAx is mostly noise, so the raw
computed value is *not* the honest point estimate. As with low-sample skaters (the RAPM ridge,
player-finishing shrinkage), the honest estimate **regresses the raw value toward the population
mean in proportion to MEASURED reliability**. This is regularization, not a "push goalies down until
they look right" factor — the shrinkage constant is derived from the data.

**Measuring reliability (`models_ml/measure_goalie_reliability.py`).** By method of moments on the
per-shot save rate `x = GSAx/shots` (per danger tier), `reliability(n) = n / (n + k)`, where `k` is
the shots at which the estimate is 50% signal. Measured on single-season rows 2021-22…2025-26:

| tier | k (shots @ 50% reliability) | note |
|---|---|---|
| high-danger | **277** | reliable per shot, but few HD shots/season |
| mid-danger | **1125** | |
| penalty-kill | **599** | |
| low-danger | **→ ∞** | var(true) ≤ 0 — **no detectable talent** on routine shots; regressed fully to average |
| overall | **2028** | for context (shrinkage is applied per tier) |

Reliability-vs-workload (overall rate): 300 sh → 0.13, 800 → 0.28, 1200 → 0.37, 1800 → 0.47,
2500 → 0.55. A year-over-year cross-check agrees (rate YoY r ≈ 0.19 overall) and **rises with
workload**, exactly what the `k`-form encodes. So even a full workhorse season is well under half
signal — the empirical justification for substantial shrinkage.

**Applying it (`compute_goalie_gar.py`).** Per tier `b`:
`shrunk_b = neutral_b + reliability(shots_b)·(raw_b − neutral_b)`, where `neutral_b` = the league
above-replacement rate in tier `b` × this goalie's tier shots (i.e. *what an average goalie produces
on this workload* — so volume credit is kept; only the rate is regressed). Low-workload / low-signal
tiers pull hard to neutral; high-workload elite goalies move little. The **shrunk** value is the
honest point estimate and is what every user-facing surface shows; `raw_gar`/`raw_war` are stored
for transparency (a small "raw, pre-regression" readout on the goalie page) and never the headline.

**The band.** The year-to-year instability is now modelled *explicitly* by the shrinkage, so the
uncertainty band is the pure within-season binomial sampling sd (`sqrt(Σ xg·(1−xg))` in goals) — it
is **not** additionally inflated for instability (that would double-count). It is still ~3× wider
than skaters' (±~2.2 vs ±~0.8 WAR single-season), and the shrunk point now sits honestly inside it.

### Confidence-aware sort (the leaderboard default)

Even after shrinkage, a goalie's ±~2.2 WAR band dwarfs a skater's ±~0.8, so leading with point
estimates still lets a noisy goalie edge a confident skater. The mixed (`all`) leaderboard therefore
**ranks by a lower-confidence bound**, `value − k·band` (`config.CONFIDENCE_SORT_K`), i.e. "value we
are confident the player provided." The DISPLAYED number stays the point estimate; only the SORT KEY
uses the bound. We started at `k = 1.0` (lower edge of the ~68% interval); a full sd buried goalies
entirely (their genuine sampling band is large), so we **tuned to k = 0.5** — a half-sd bound that
demotes noisy goalies below confident skaters yet keeps genuinely-elite high-workload goalies
visible near the top. Skater-only and goalie-only scopes default to the same order with a toggle
back to the raw point estimate. (Implemented in `backend/routers/rankings.py`; the mixed default is
unit-tested in `tests/test_value_overall.py`.)

### Validation (`measure_goalie_reliability.py` + `validate_goalie_gar.py`)

- **Reliability curve** measured and printed (above); reliability rises with workload.
- **Shrinkage effect** — 2024-25 top goalie raw WAR **+8.0 → shrunk +4.0**; small-sample backups
  pulled toward average. The point order alone now puts the top 5 as skaters (Draisaitl, Reinhart,
  Makar, McDavid, Kucherov) with Hellebuyck #6 — no goalie above McDavid (the original bug).
- **Confidence-adjusted mixed order** (k=0.5, 2024-25): confident skaters lead; the #1 goalie
  (Hellebuyck, +3.97 ± 2.21) lands at **rank 12** — visible near the top, not buried above the
  skaters we are far more certain about. Noisy / small-sample goalies fall further.
- **Cross-position sanity** — #1 goalie WAR ≈ **0.8×** the #1 skater WAR (Hellebuyck +4.0 vs
  Draisaitl +5.0): a genuinely great goalie is top-tier but no longer above the best skaters.
- **Replacement-pool sensitivity** rank Spearman 0.99+ (levels move, ranks stable, as before).

Plainly: **goalie estimates are regressed toward the mean by their measured reliability because
goaltending is low-signal season to season, and the board orders by confidence-adjusted value. This
is honesty about uncertainty, not hand-tuning toward a preferred answer.**

## RAPM is untouched

This model only *reads* `player_impact`; it never retrains, re-weights, or modifies it or its
artifact. GAR sits beside RAPM as the second lens. The goalie model likewise only *reads* the GSAx
marts.
