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
  player's within-position-group **Overall** (`nhl_models.player_overall`, goalies
  `goalie_overall`), the same number the player card shows. An elite player (pctile ≈ 1.0) floors at
  ≈ 0.55 → he is **never** a poor fit anywhere; a depth player (pctile ≈ 0.1) floors ≈ 0.06 → his
  fit is driven almost entirely by whether he matches.
- **`fit = floor + (1 − floor) × match`**. With `match → 1`, fit → 1 regardless of talent, so a
  need-serving specialist can grade high; with `match` low, fit falls back toward the floor, so a
  star still lands respectably. Quality only ever *raises the floor*.

**Quality is exposed as its own axis** beside fit (`quality`: percentile, WAR, label), never folded
into `match`. The readout therefore shows both, independently: *"elite player, mediocre fit here"* or
*"depth player, ideal fit here."* Neither masks the other.

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
