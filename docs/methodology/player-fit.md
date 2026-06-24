# Player Fit — quality floors fit, need is the core

"Fit" answers one question: **how well does a player's profile serve a team?** It is deliberately
**separate from how good the player is.** The previous versions of this tool made talent the master
term — a single cosine, then a quality-weighted blend — so player quality acted as a *ceiling* on
fit. That is backwards. A low-value specialist who matches a team's exact hole should be able to
score a high fit, and an elite player should never be capped or rated a poor fit.

This rebuild makes **quality a FLOOR, never a cap**, and makes **need the core of the match**. The
model lives in `models_ml/score_team_fit.py` (→ `POST /tools/trade-fit`); team needs are precomputed
by `models_ml/compute_team_needs.py` (→ `nhl_models.team_needs`).

## The composition

Everything is on a 0–1 scale.

```
match = weighted(need, style, line)                  # how well he MATCHES the team
floor = FLOOR_CAP × overall_quality_percentile       # talent floors fit, never caps it
fit   = floor + (1 − floor) × match                  # match drives the upside, UNCAPPED
```

- **`match`** is the weighted blend of the three match dimensions, weights
  `config.TRADE_FIT["MATCH_WEIGHTS"]` = **need 0.55 / style 0.20 / line 0.25** (need is the core).
  Renormalises over whatever dimensions are available.
- **`floor = FLOOR_CAP × quality_pctile`**, `FLOOR_CAP = 0.55`. The quality percentile is the
  player's **projected** within-position talent (see *Projected talent* below) — **not** last
  season's result, so a contract-year or one-off spike does not inflate the floor. An elite player
  (pctile ≈ 1.0) floors at ≈ 0.55 → he is **never** a poor fit anywhere; a depth player (pctile ≈
  0.1) floors ≈ 0.06 → his fit is driven almost entirely by whether he matches.
- **`fit = floor + (1 − floor) × match`**. With `match → 1`, fit → 1 regardless of talent, so a
  need-serving specialist can grade high; with `match` low, fit falls back toward the floor, so a
  star still lands respectably. Quality only ever *raises the floor*.

**Quality is exposed as its own axis** beside fit (`quality`: projected percentile, projected WAR,
band, `last_war`, label), never folded into `match`. The readout shows both independently: *"elite
player, mediocre fit here"* or *"depth player, ideal fit here."* When last season sits well above the
projection, the band widens and the note says *"projects to X, last season Y"* — a spike never reads
as a clean elite.

### Projected talent (the quality input)

The talent that floors fit is a forward **projection**, derived the way the trade talent axis projects
(reuse, not a new model), in `score_team_fit._skater_projection` / `_goalie_projection`:

1. **Recency-weight** the last ~3 seasons of WAR (`player_gar` / `goalie_gar`), weights
   `[1.0, 0.6, 0.3]` newest→oldest, **also weighted by games** (sample). A one-season spike is diluted
   by the player's established seasons — and a young player with little history has little to dilute.
2. **Regress** the weighted level toward replacement (0 WAR, the GAR baseline) by **sample size and
   volatility**: `reliability = n_eff / (n_eff + K·(1 + vol))`, `K = REGRESS_GAMES_K`. Small or
   volatile samples regress hard; a full-sample star barely moves.
3. **Age it forward** one season on the player's archetype aging curve (`aging_curves`; flat for
   goalies). A young breakout ages **up** (tempered little); an older spike ages **down** (more).

`last_war` is carried for the honest spike note. Validated (`make trade-fit-validate`): older spikes
regress more than young (mean proj/last ≈ 0.71 vs 0.80, 2025-26). Constants in
`config.PLAYER_FIT_PROJECTION`.

**The floor lens is the blended Overall standing, not production WAR alone (`_blend_quality`).**
Production (GAR) bakes in shooting luck *by design*, so a finishing-driven one-season spike can floor
a career-ordinary player as "elite" (the documented Raddysh case: 23 goals from a career 6-goal
scorer projected to 95th-percentile WAR among D). The isolated play-driving (RAPM) lens is not fooled
by finishing. So the floor input is the **blended Overall percentile** the system already trusts
(`config.OVERALL_WEIGHTS` = 0.55 production / 0.45 play-driving, read straight off
`nhl_models.player_overall.overall_percentile`), recency- and games-weighted across the recent seasons
and regressed toward the league-average 0.5 by sample. This is a *more stable* predictor than the
isolated rate alone (production YoY r ≈ 0.66 vs RAPM rate r ≈ 0.38, see [value-gar.md](value-gar.md)),
while the play-driving term defuses exactly the unrepeatable finishing residual (r ≈ 0.35) that opens
a luck spike. The production-WAR projection is still computed — it drives the displayed WAR number and
the trajectory series — but it no longer sets the floor. The quality note shows the split honestly
("Nth-percentile all-around value: Xth in production (+W WAR), Yth in isolated play-driving"), which
is exactly where a luck spike is visible. Worked: Raddysh floors at **73rd ("solid top-four")** —
83rd production / 65th play-driving — instead of 95th "elite", while genuine two-lens elites are
untouched (Quinn Hughes 99th/98th → 93rd; McDavid 100th/99th → 94th). Goalies have no play-driving
axis, so they keep the goalie-GAR projection percentile (already reliability-shrunk).

A letter grade is derived from the composed fit (`GRADE_BANDS`) for carding only — the API and UI
**always** render the full decomposition plus the quality axis, never a lone grade.

## The three match dimensions

### 1. Need — the core (it absorbs position)

Position is **not** a separate dimension; it is the **role axis of need**. `compute_team_needs.py`
measures, for every team, its current depth strength at each **(role × component)** and benchmarks it
against the **team's own league standing**, not the league's top teams (the old top-8 benchmark is
gone):

- **Roles**: `C` / `W` (wings) / `D` for skaters, `G` for goalies.
- **Components**: even-strength offense, even-strength defense, power play, penalty kill, finishing
  (skaters, from `nhl_models.player_composite`); goaltending (goalies, from composite GSAx).
- `team_strength[role][component]` = the **sum** of that composite component over the team's current
  players at that role (the sum captures both quality *and* depth — several good centers sum high,
  one good center and scrubs sums low).
- `need = 1 − league_percentile` of that strength across the 32 teams at the same (role, component):
  **weak own depth → high need.**

A candidate scores need only at **his own role**, so a center is measured against the team's center
depth — position is absorbed. Per component, `opportunity_c = team_need_c × player_strength_c`
(the team is weak there **and** the player is strong there; `player_strength_c` is his percentile in
that component *within his role*). The dimension blends the single best opportunity with breadth:

```
need_score = NEED_PRIMARY_W · max_c(opportunity_c) + (1 − NEED_PRIMARY_W) · mean_c(opportunity_c)
```

`NEED_PRIMARY_W = 0.7` — the `max` term rewards a **specialist** who nails the team's biggest hole;
the `mean` term rewards an **all-rounder** who addresses several. **Handedness** is a small modifier
*inside* need (bump if the team is short the player's shot at his position, trim if over-supplied;
bounded by `HAND_MOD`), not a separate dimension. The API returns the full **component-by-role
breakdown** (`need_breakdown`): each component's team-need beside the player's strength.

This is what makes the four behaviors hold: a strong player at a team **already deep** at his role
scores **low** need (their depth strength is high → need low), so a star's fit genuinely varies by
destination; a specialist strong in the one component a team lacks scores **high** need regardless of
his overall value.

### 2. Style

The player's **rush-vs-(forecheck/cycle) orientation** (a within-entity ratio, from the radar) vs
the team's identity orientation (`mart_team_identity`). `level = 1 − |player_lean − team_lean|`. A
**match** of generation style, not a magnitude — it does not scale with the player's value.

### 3. Line — complementarity, not magnitude

The player is slotted into the team's current top unit for his role (replacing the lowest-WAR
member) and projected with the line-fit model (`score_line`). The dimension is the **complementarity**
signal only: the sum of the model's **pairwise** feature contributions (archetype overlap, shot-
location variety, handedness balance, pace spread, territorial tilt), mapped through a sigmoid
(`LINE_COMP_SCALE`; 0.5 = neutral). The member-level contributions — which carry each player's
*individual* quality — are deliberately **excluded**, so line measures how the pieces fit together,
not how good the incoming player is (that already lives in the floor). A higher pairwise contribution
can mean *complementary* (varied roles / shot locations) rather than *similar*; the model learned the
direction from real line outcomes, so complementary pairs are credited where the data supports it.

## Goalies

Goalies take a simplified path: **need only** (the team's goaltending weakness × the goalie's quality
percentile), the **same quality floor**, and the **separate quality axis** — no skater style or line
dimension. The skater framework is not forced onto them.

## Validation (`models_ml/validate_trade_fit.py`)

`make trade-fit-validate` asserts the four behaviors hold **at once** for 2025-26:

1. **A low-value specialist scores a high fit for the need he serves** — uncapped by his low quality.
2. **A star's fit varies meaningfully across teams** (not pinned high everywhere).
3. **A star is never a poor fit anywhere** — the floor holds (worst destination ≥ the B band).
4. **A low-value player nobody needs scores low.**

Representative 2025-26 reads: McDavid → MTL (thin at center even-strength offense, his exact strength)
grades **A (≈ 90)**; McDavid → CAR (deep down the middle) falls to **B (≈ 75)** on low need — a ~19
point spread across the league with the floor never breached. Quality is reported beside fit in every
case, so "elite player, weak fit here" reads honestly.

The fit term also feeds the trade engine's fit overlay (`backend/services/trade_engine.py`,
`_fit`), which is re-validated by `make trade-engine-validate` after any change here.

All constants live in `config.TRADE_FIT`.

## The verdict — deterministic, context-aware clause assembly

The one-line verdict is **not** a fixed template with blind slots. It is assembled from conditional
clauses whose presence, order, and wording are all chosen by computed signals, so it reads as
context-aware while every claim still references a number that agrees with the rest of the page (the
consistency rule). It is built by pure functions in `insight_engine/templates/team_fit.py` — no LLM,
no frontend computation — so the claims are guaranteed against the numbers and the string is
deterministic. `score_team_fit.py` computes the signals and calls them; the **same** trajectory
descriptor and the **same** projected WAR/percentile drive both the verdict and the quality-card
sentence, so the two can never disagree.

### A) Trajectory classifier (`classify_trajectory`)

A deterministic classifier over the player's per-season WAR series (reusing the projection's
`player_gar` history — a slightly deeper, floor-neutral pull: the extra season carries recency
weight 0, so `proj_war` and the floor are unchanged). From the series it derives the slope, the
prior-seasons slope, the trailing run of consecutive drops/rises, the track-record depth at the
projected tier, and the band width relative to value, then buckets:

| bucket | phrase | when |
|---|---|---|
| `established_stable` | a flat **"is a {tier}"** *(only here, and only with a deep record)* | flat slope, deep track record |
| `career_year` | "projects as a {tier}, coming off a career year" | newest season spikes well above the established level; projection regresses down |
| `down_year` | "is a proven {tier} coming off a down year the model regresses back up" | newest drops below a **stable** proven plateau; projection regresses up |
| `declining` | "has slipped {N} straight seasons; … trends down toward {lower tier}" | a **sustained** slide (prior seasons were declining too) |
| `ascending` | "is trending up; … and still climbing" | a sustained rise; projection ≥ the prior level |
| `volatile` | "swings year to year … on a wide band" | a wide band / high season-to-season CV with no clean trend |

Two rules make it honest: the tier word maps to the **projection**, never to last season; and
`declining`/`volatile` **must** carry the trend/band caveat, so a high projection never sits silently
beside a downward trajectory. `down_year` and `declining` arise from the *same* "last < baseline"
condition but are separated by whether the prior seasons were a stable plateau (a cliff → down year)
or already sliding (sustained → declining), and they render different phrases.

### B) The verdict clauses (`build_verdict`)

Five clause types, selected by signal, ordered strongest-first, ending on the binding constraint:

1. **identity** (always) — `{player} {trajectory phrase} who {signature strength}`. The signature is
   his top role/skill by within-role percentile (reused from the profile), with a graceful degrade to
   a plain "depth {pos}" when nothing clears the bar (no invented strength). A flat **"is a {tier}"**
   is used **only** for `established_stable` with track-record depth ≥ `TRAJ.MIN_DEPTH_FOR_IS`;
   everything else hedges with "projects/profiles as".
2. **fit driver** (always) — from the need decomposition: a role he *fills* ("That's {team}'s thinnest
   spot at {component} …, so he fills a real need") or, when nothing is tagged `fills`, the low-need
   form ("But {team} are already deep …, so he doesn't fill a real need").
3. **cap** (conditional) — the largest **material** weighted shortfall among the match dimensions
   (`weight × (1 − level)`), plus an "unproven one-year projection" cap for a career-year/volatile
   bucket. It appears only if it exceeds `MATERIAL_CAP` and names a **different** factor than the fit
   driver already covered (need is never restated). Phrased by grade — "the only thing keeping it from
   higher" near the top, "pulls it further down" lower. With nothing material, a top grade gets a
   confidence closer ("Nothing meaningful argues against the fit."), otherwise the clause is dropped.
4. **floor note** (conditional) — "His quality keeps a floor under the grade." appears only when
   `grade_score − match_score ≥ FLOOR_LIFT_MIN` (quality is doing the lifting).
5. **grade** (always, closing) — "Fit grades {grade}."

The quality-card sentence (`quality_note`) is built from the **same** tier descriptor + the same
WAR/percentile, plus a trajectory tail, so the card and the verdict always agree.

### Worked reads (2025-26, live)

- *Raddysh → DET, B:* "Darren Raddysh is an elite #1 defenseman who drives play at both ends. That's
  DET's thinnest spot at even-strength offense on the blue line, so he fills a real need. A partial
  style mismatch is the only thing keeping it from higher. Fit grades B." (card: "Projects as an elite
  #1 defenseman — 95th-percentile value among defensemen (+1.1 WAR ± 0.9).")
- *Raddysh → EDM, C:* same identity, but the low-need form, a style cap that "pulls it further down,"
  and the floor note appear — the fit-driver and cap factors never overlap.
- *McDavid → MTL, A:* "Connor McDavid profiles as an elite first-line forward who drives play at both
  ends. That's MTL's thinnest spot at even-strength offense up front, so he fills a real need. Nothing
  meaningful argues against the fit. Fit grades A." (the hedged "profiles as" — his projection tier is
  not a deep flat record — proves the unhedged-"is" gate.)

All thresholds and labels live in `config.TRADE_FIT` (`TRAJ`, `TIER_LABELS`, `SIGNATURE_*`,
`MATERIAL_CAP`, `FLOOR_LIFT_MIN`, …). The clause functions are unit-tested hermetically (no BigQuery)
in `tests/test_trade_fit_verdict.py`, covering the classifier buckets, the unhedged-"is" gate, the
fit-driver flip, the cap omission/no-restatement, the floor-note gate, verdict↔card coherence, and
determinism.
