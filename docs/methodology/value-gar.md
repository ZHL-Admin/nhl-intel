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

### Wider bands, on purpose (principle 6)

Goaltending is genuinely less stable than skater production. Measured year-over-year correlation of
goalie GAR is **r ≈ 0.24** (2021-22 … 2025-26), well below skater production (r=0.66). So the goalie
uncertainty band is the binomial save-outcome sd (`sqrt(Σ xg·(1−xg))` in goals) **× an instability
inflation (1.6)** — visibly wider than skaters' by construction. Goalie rankings are presented at
**tier-level confidence**; the mixed leaderboard renders the wider band so a reader sees the
cross-position order within a cluster is *soft*, not precise.

### Validation (`models_ml/validate_goalie_gar.py`)

- **Smell test** — top GAR is elite starters (2024-25: Hellebuyck, Thompson, Shesterkin,
  Montembeault, Oettinger; 2025-26: Thompson, Swayman, Sorokin, Vasilevskiy); backups near 0.
- **Distribution** replacement-centred (qualified median +3.5 … +6.9 by season) with a long
  positive tail (elite starters).
- **Cross-position sanity** — #1 goalie WAR ≈ **1.6×** the #1 skater WAR (2024-25 Hellebuyck +8.0 vs
  Draisaitl +5.0); same neighbourhood, not 3× off. A workhorse starter genuinely influences more
  goal outcomes than all but the very best skaters — hence goalies can top the mixed list, and the
  wide band is the honest signal that the edge over the top skaters is within noise.

## RAPM is untouched

This model only *reads* `player_impact`; it never retrains, re-weights, or modifies it or its
artifact. GAR sits beside RAPM as the second lens. The goalie model likewise only *reads* the GSAx
marts.
