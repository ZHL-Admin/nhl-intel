# Phase Value (phase_value_v1)

*A transition-based defensive value model. Companion to RAPM `def_impact` (`nhl_models.player_impact`),
which it never modifies and against which it is validated. Filled in progressively by build stage;
sections are stubs until their stage completes. Spec + decisions: `docs/phase-value/` (schema-map,
DECISIONS) and the build specification.*

Status: **Stage 0 complete** (recon + scaffolding). Stages 1–6 pending.

## 1. Summary and motivation
`def_impact` is structurally the weakest number on the platform (rare outcome, uniform 5-defender
attribution; see `isolated-impact.md`). Phase Value stops regressing on the rare outcome (xGA) and
regresses on the frequent *process* — possession-state transitions that happen hundreds of times per
game — then converts back to goals via an empirical state value function V(state). It **decomposes**;
`def_impact` remains untouched and is the comparison baseline. Components (defending side, higher =
better): `deny` (episode-frequency suppression), `suppress` (in-episode xG-intensity suppression),
`escape` (favorable episode-end rate; published as a rate in v1).

## 2. The state engine
Assumptions stated plainly (all sensitivity-tested or revisited as noted):
- **PV-A1** blocked shots retain attacker possession. *(Recon PV-D005: the blocked-shot event owner is
  actually the BLOCKING team, so "attacker" = opponent(owner) with zone flipped O↔D.)*
- **PV-A2** raw (un-rink-adjusted) giveaways/takeaways drive possession; scorer bias affects counts, not
  the possession truth at that instant.
- **PV-A3** hits do not change possession.
- **PV-A4** the V outcome window counts goals regardless of mid-window strength changes (5v5-goals-only
  is a Stage 5 sensitivity).
*(Mapping table, spells, DZ-episode start/end taxonomy, and Stage 1 acceptance results — filled in Stage 1.)*

## 3. Episodes
*(DZ-episode definition, start_type precedence oz_faceoff>rush>forecheck>carry_other, end_reason
taxonomy, and the oz_faceoff-exclusion rationale — a defensive-zone draw is deployment, not defense, so
excluding it from `deny` avoids crediting line-change luck. Filled in Stage 1.)*

## 4. The value function
*(V(state) table with se, per-season stability, and the one-paragraph interpretation incl. the empirical
sign of V(P_OWN_D). Hard gate V(P_OZ_EST) > V(P_NZ) > V(P_OWN_D). Filled in Stage 2.)*

## 5. Estimation
*(Two-sided stint design, three fits deny/suppress/escape on the RAPM machinery, CV, bootstrap,
centering, def sign-flip. In the register of `isolated-impact.md`. Filled in Stage 3.)*

## 6. Accounting
*(deny_g60 / suppress_g60 / pv_def_g60 formulas, league constants, the worked example with real numbers,
per-60 and per-1000-minute framings. Filled in Stage 4.)*

## 7. Validation
*(Pre-registered reliability tiers A/B/C with thresholds restated, the def_impact baseline comparison,
split-half, team out-of-sample, sensitivity summary, external A3Z agreement if run. Filled in Stage 5.)*

## 8. Known limitations (pre-committed)
Possession is a proxy from scorer-recorded events; entries generating no event are invisible, so `deny`
measures threatening-sequences-allowed, not true entries; `suppress` still rests on shared on-ice
attribution and is expected to be the weakest component; scorer bias on giveaways/takeaways is inherited
(PV-A2); 5v5 only in v1; the V goals-window includes cross-strength goals (PV-A4).

## 9. Surfaces
*(Tables `state_values` + `player_phase_value`, the `GET /players/{id}/phase-value` endpoint, and
serving-manifest entries. Filled in Stage 6.)*

---
### Appendix: Stage 0 reconnaissance (complete)
Full findings in `docs/phase-value/schema-map.md`. Headlines: intermediate models live in `nhl_staging`
(not mart); faceoff `event_owner_team_id` = winner (ground truth 100%, n=81,523); blocked-shot owner =
blocking team (94.15%, → attacker = opponent(owner), PV-D005); 5v5 = `int_segment_context.strength_state
= '5v5'`; `shot_xg` keyed (game_id,event_id), 98.8% attempt coverage; `game_date` on PBP directly;
stoppage reason in `reason`. Both STOP-gated checks cleared; no blocking ambiguity.
