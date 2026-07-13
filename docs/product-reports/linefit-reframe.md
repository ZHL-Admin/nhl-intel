# Lineup Lab / Player Fit — reframing the linefit_v1 "chemistry" claim

**Work order:** reframe how `linefit_v1`'s output is *presented and labeled* to match the validated
evidence. **This does NOT retrain or delete the model** — the projection stays; only the framing
changes, from *predicting chemistry* to *describing a sensible arrangement of individual pieces*.
Branch `product/linefit-reframe`. **STATUS: proposal — STOP at the gate. No user-facing string has
been changed. Nothing ships until this copy is approved.**

## Why (the evidence)
Five pre-registered research studies (`research/PROGRAM-FINDINGS.md`, F17–F20 + the role-fit Link 2
result) tested whether player fit/chemistry produces value beyond individual talent and role. **None
cleared a usability bar.** Specifically relevant to this surface:
- **F17** — a pair's shared-history over/under-performance beyond the two players' quality does not
  persist (so a "chemistry blend" of observed line history is not predictive).
- **F18 / role-fit Link 2** — forward units over-perform their parts only weakly; two-way role
  composition adds ~1% CV R².
- **F20** — trio *composition/recipe* (complementarity, arrangement) is talent-and-style in disguise
  (adds ~0 beyond talent+style; hard null).
- The models' role/style descriptors ARE real and stable and *do* describe a sensible arrangement —
  that survives as **descriptive** context, labeled co-occurrence, not causation.

**Bottom line for copy:** the projection is honest (it's an individual-profile-based line projection);
the word **"chemistry"** and any framing that implies fit-beyond-talent is *predictive* is not
supported and must be reworded. Role/style/arrangement language is accurate and stays.

---

## 1. What the model actually computes (model, not language)

`models_ml/train_linefit.py` → `artifacts/linefit_v1.joblib`: three LightGBM heads (xGF%, xGF/60,
xGA/60) that predict a **hypothetical line's** 5v5 results **from its members' individual
player-season profiles** — off/def impact, finishing, and style shares (rush/rebound/forecheck/cycle/
point, shot location, PP/PK, skating), aggregated across the line as mean/min/max, **plus four
pairwise "composition" features**: `pair_arch_cos` (archetype similarity), `pair_shotloc_dist`
(shot-location spread), `hand_balance` (handedness), `burst_spread` (skating-pace spread). **No
observed line history enters the model's features** (`linefit_features.py`).

At *scoring* time only, `score_line.py` optionally **blends** the model projection with the exact
line's **observed shared 5v5 history** if it exists (weight = `obs_min/(obs_min+150)`) — this is the
piece currently called the "chemistry-blended projection."

**So there are exactly two things labeled "chemistry," and they are different:**
| labeled "chemistry" | what it really is | verdict |
|---|---|---|
| the four **pairwise features** | role/style **arrangement** descriptors (similarity/complementarity of individual profiles) | **real but tiny** (F20: ~0 predictive lift) → **relabel "arrangement," don't claim predictive** |
| the **observed-history blend** | the exact line's real past xGF% mixed into the projection | **descriptive, not predictive** (F17: doesn't persist) → **show as observed context, not a chemistry prediction** |

**Claims to REWORD** = anything asserting *chemistry* or *fit-beyond-talent as predictive*.
**Claims to KEEP** = the xGF% projection itself, the individual/role/style reasons, and the
arrangement descriptors (phrased as arrangement, not chemistry).

---

## 2. The surface inventory (every user-facing place linefit_v1 output reaches a user)

### A · Lineup Lab (`pages/LineupLab.tsx` + `components/common/LineProjection.tsx`; backend `score_line.py` + `insight_engine/templates/line_fit.py`)
| # | location | exact current string | type |
|---|---|---|---|
| A1 | StudioHub blurb | "Project a line before it takes a shift." · contract "5 skaters → projected xGF%" | blurb |
| A2 | page subtitle | "Place five skaters on the sheet and project the line before it takes a shift." | subtitle |
| A3 | hero grade labels | Elite / Strong / Average / Below average / Struggles | label |
| A4 | hero sentence (`grade_sentence`) | "Projected as a B-grade forward trio at 55% expected-goals share." | copy |
| A5 | hero fallback sentence | "Projected expected-goals share for this line / 5-skater unit." | copy |
| A6 | reasons head | "Why this grade" | label |
| A7 | reasons (`FRAGMENT`, individual/role) | e.g. "strong combined even-strength offensive impact", "shots concentrated in the slot", "power-play pedigree" | copy |
| A8 | reasons (`FRAGMENT`, arrangement) | "complementary, non-overlapping roles" / "overlapping roles among the members"; "varied, hard-to-defend shot locations" / "redundant shot locations"; "left/right handedness balance"; "well-matched / mismatched skating pace" | copy |
| A9 | tag | "Deeper extrapolation · players don't currently play together" | tag |
| A10 | tag | "Widened interval · a member has limited NHL minutes" | tag |
| A11 | **observed-blend note** (`ObservedNote`) | "Blended with {n} real 5v5 minutes (observed {y}% xGF, weighted {z}%)." | copy |
| A12 | limitations footer (`LIMITATIONS_FOOTER`) | "This projects statistical shape only — how these players' measured roles and skills tend to combine. It does not capture personality, practice chemistry, coaching systems, or in-game adjustments. Treat the grade as a prior, not a verdict." | footer |
| A13 | model-inputs table | toggle "Model inputs"; columns Player / Archetype / Off / Def / Fin / 5v5 min | table |
| A14 | "Better fits" panel | h3 "Better fits"; "Finding better fits…"; "Same-caliber alternatives — players in each member's usage tier, ranked by the projected xGF% they'd add. Click one to swap it in and re-project." | panel |
| A15 | swap reasons | positive `FRAGMENT` phrases (same set as A7/A8) | copy |

### B · Player Fit (`pages/TradeFit.tsx` + backend `score_team_fit.py` + `insight_engine/templates/team_fit.py`)
| # | location | exact current string | type |
|---|---|---|---|
| B1 | StudioHub blurb | "Score how one player suits a given team." · contract "player + team → fit score" | blurb |
| B2 | page subtitle | "Pick a player and a team, and score the fit against that roster's needs." | subtitle |
| B3 | **LINE match dimension** | dimension label "Line", weight **25%**, `title="weight in the fit blend"` | dimension |
| B4 | LINE cap clauses (`team_fit.py`) | "a weak line projection" / "a neutral line projection" | copy |
| B5 | Line row EST tag | `title="Model estimate — read this as a tier, not a precise number"` | tooltip |
| B6 | doc pointer | `score_team_fit.py` docstring: "LINE: complementarity with the unit he'd actually skate with (the line model's PAIRWISE …)" | (methods) |

### C · Team Profile (`pages/TeamProfile.tsx` + `components/common/LineSwapWidget.tsx`)
| # | location | exact current string | type |
|---|---|---|---|
| C1 | **Note n=4** | "**Line chemistry** projects a unit's expected xGF% from how its members have driven play together and apart — swapping a player re-projects the line." | note |
| C2 | LineSwapWidget | inline `LineProjection` cards (inherits A-series strings) | — |

### D · Offseason forecast / Projected Lineup (`components/forecast/ProjectedLineup.tsx`, `TeamDossier.tsx`; backend `project_roster_forecast.py`)
| # | location | exact current string | type |
|---|---|---|---|
| D1 | FitBadge tooltip | `title="Cold-start line-fit grade (xGF%)"` | tooltip |
| D2 | **chemistry_adj** | the bounded goals/game nudge to a team's projected rating (`chemistry_adjustment`, cap 0.06); surfaced in the forecast rating + `chemistry_adj` API field / Move Ledger | value + label |
| D3 | TeamDossier | "The free-agent pool scored by Player Fit for this team lands here — four best fits with a grade and a one-line reason." | copy |
| D4 | offseason methodology doc | `docs/methodology/offseason-forecast.md`: "Chemistry + style overlay … a BOUNDED goals/game nudge" | (methods) |

### E · Team lines board (`components/teams/LineBoard.tsx`)
| # | location | exact current string | type |
|---|---|---|---|
| E1 | LineBoard copy | "… the last 10 games (by shared 5v5 minutes), each projected by the line-fit model. Click a row for the full breakdown." | copy |

### F · Model card + methodology (not user-facing UI, but public-doc surface)
| # | location | exact current string |
|---|---|---|
| F1 | `train_linefit.py` model card | "Pairwise **chemistry** features (blueprint 12.4)"; "## **Chemistry** blend"; "It does not model personality, practice **chemistry**, coaching systems …" |
| F2 | `docs/methodology/lineup-lab.md` | "Pairwise **chemistry** features …" |
| F3 | `models_ml/config.py`, `score_line.py`, `linefit_features.py` | internal `CHEMISTRY_*`, "chemistry blend", "pairwise chemistry features" (code identifiers — internal, rename optional) |

---

## 3. Proposed reword — before / after (only the chemistry / fit-beyond-talent claims)

Guiding rule: keep the projection and every role/style descriptor; delete the word **chemistry** as a
*predictive* claim; make the observed-history blend read as **descriptive context**; add one honest
caveat line. Copy stays plain, non-jargony, claims nothing the research doesn't support.

| # | before | after (proposed) |
|---|---|---|
| **C1** | "**Line chemistry** projects a unit's expected xGF% from how its members have driven play together and apart — swapping a player re-projects the line." | "**Line projection** estimates a unit's expected xGF% from its members' **individual roles and skill profiles** — swapping a player re-projects the line. It reflects how the pieces fit on paper, not measured chemistry." |
| **A11** | "Blended with {n} real 5v5 minutes (observed {y}% xGF, weighted {z}%)." | "This exact line has **{n} real 5v5 minutes together — {y}% xGF observed**, shown here as **context**. A line's shared-history over/under-performance doesn't reliably carry forward, so the projection still leans on the members' individual profiles." (retain the blend numerically if desired, but label it *observed context*, not a chemistry boost) |
| **A12** (footer) | "This projects statistical shape only — how these players' measured roles and skills tend to combine. It does not capture personality, practice chemistry, coaching systems, or in-game adjustments. Treat the grade as a prior, not a verdict." | "This projection is driven by the members' **individual quality and role/style** — how the pieces fit on paper. We tested whether **fit beyond individual talent** (chemistry, complementarity) adds predictive value and **did not find it** in public data, so treat any line-specific over/under-performance as **descriptive, not predictive**. It doesn't capture personality, practice, coaching systems, or in-game adjustments. Treat the grade as a prior, not a verdict. *[link the Writing piece when it exists]*" |
| **A8** | "complementary, non-overlapping roles" / "varied, hard-to-defend shot locations" (currently sourced from features labeled *chemistry*) | keep the wording verbatim (it is honest **arrangement** language), but re-source under the renamed "**role/style arrangement** features" — no user string change needed; the label change is internal (F1/F3) |
| **B3** (LINE dim) | dimension **"Line"**, weight 25%, tooltip "weight in the fit blend" | dimension **"Line arrangement"** (or keep "Line"), tooltip "**How the player's role/style slots into the unit he'd skate with — an on-paper arrangement estimate, not measured chemistry.**" Consider lowering its blend weight given F20 (owner decision — a model-serving config change, out of scope for copy-only). |
| **B4** | "a weak line projection" / "a neutral line projection" | keep (accurate — it's a projection) |
| **D1** | "Cold-start line-fit grade (xGF%)" | "Cold-start line **projection** grade (xGF%) — from members' individual profiles" |
| **D2** (chemistry_adj) | forecast rating nudge labeled/derived as "**chemistry** adjustment" | rename the *presented* term to "**line-arrangement adjustment**" (a small bounded nudge from how the projected top units are arranged); keep the bound; the `chemistry_adj` API field can stay internally or be aliased (owner call — touches `schemas.py`/`types.ts`, coordinate with API-consumers) |
| **F1/F2** (model card + methodology) | "Pairwise **chemistry** features"; "## **Chemistry** blend" | "Pairwise **role/style arrangement** features"; "## **Observed shared-history** context (descriptive)" + a sentence citing F17–F20 that fit-beyond-talent was tested and not found predictive |
| **A4/A5/A6/A7/A9/A10/A13/A14** | (projection sentence, individual/role reasons, tags, model-inputs, better-fits) | **no change** — already honest, individual/role-based; "Better fits" ranks candidates by *projected xGF% added*, which is projection language, not chemistry |

**Terminology swap, applied everywhere:** "chemistry" (as a predictive claim) → "**role/style
arrangement**" or "**line projection**"; "chemistry-blended projection" → "**projection + observed
shared-history context**." The word "chemistry" may remain only where the copy explicitly says we do
**not** measure it (e.g. the footer: "not measured chemistry").

---

## 4. The honest caveat surface (new, small, one place per tool)
A single methods line (tooltip/footer) on Lineup Lab (A12, revised above) and Player Fit (B3 tooltip):

> *Line results are driven by the members' individual quality and role. Fit beyond individual talent
> was tested across five pre-registered studies and was not found predictive in public data; line
> over/under-performance is shown as descriptive context, not a forecast.* [link the Writing piece]

---

## 5. Scope notes / decisions for the owner
- **Copy-only vs model-serving.** Everything above is copy. Two items touch config/serving and are
  flagged as **owner decisions, out of scope for this copy pass**: (i) the LINE dimension weight
  (.25) in Player Fit given F20; (ii) whether to keep or reduce the `chemistry_adj` forecast nudge
  (`CHEMISTRY_ADJ_CAP`). The model is **not** retrained or deleted either way.
- **API field names** (`chemistry_adj` in `schemas.py`/`types.ts`) are not user-facing strings;
  renaming them is optional and would require coordinating API consumers — recommend leaving the
  field name, changing only display labels, unless the owner wants a clean rename.
- **Writing piece link** (A12/§4) is a placeholder until the public write-up of F17–F20 exists.

---

## GATE — STOP for owner review
No user-facing string has been changed. This report is the inventory + model-vs-language separation +
proposed before/after copy. **On approval**, the string changes land in: `TeamProfile.tsx` (C1),
`insight_engine/templates/line_fit.py` (A11, A12), `score_team_fit.py`/`team_fit.py` + `TradeFit.tsx`
(B3), `ProjectedLineup.tsx` (D1), `project_roster_forecast.py` display + `MoveLedger`/forecast copy
(D2), `train_linefit.py` model card + `docs/methodology/*` (F1/F2), and the internal `CHEMISTRY_*`
identifiers (F3, optional). **Awaiting sign-off on the copy before anything ships.**
