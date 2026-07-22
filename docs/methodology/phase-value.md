# Phase Value (phase_value_v1)

*A transition-based defensive value model. Companion to RAPM `def_impact` (`nhl_models.player_impact`),
which it never modifies and against which it is validated. Filled in progressively by build stage;
sections are stubs until their stage completes. Spec + decisions: `docs/phase-value/` (schema-map,
DECISIONS) and the build specification.*

Status: **Stage 2 complete** (state engine + value function — hard gates green). Stages 3–6 pending.

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

**Models** (dbt, `nhl_staging`): `int_phase_events` (event-level state), `int_phase_spells` (constant-state
intervals split at 5v5 boundaries), `int_zone_episodes` (DZ episodes). The pure-Python reference
`tests/phase_value/reference_state_machine.py` is the authority; the SQL conforms to it.
**State** = (possession, `zone_abs` ∈ {D_home, N, D_away}, liveness), a forward-filled step function reset
each period. `zone_abs` is absolute, derived from the owner-relative `zone_code` + owner home/away side;
possession/zone are "set" by the event or keep the previous value (mapping per spec §5.2). A penalty keeps
the previous zone (does not adopt its own `zone_code`). Blocked-shots send possession to `opponent(owner)`
(the shooter, PV-A1/PV-D005) with the absolute zone from the actual (blocking) owner.

**Stage 1 acceptance (2023-24 → 2025-26), all hard gates PASS:**
- Conservation: 5v5 live spell-seconds vs 5v5 segment-seconds — mean & max |Δ| = **0.000%** (0 games > 1%).
- Golden vectors GV1–GV8: **8/8 pass**.
- Unmapped events: **0.0017%** (gate < 0.5%).
- Goal coverage: **99.95%** of in-scope 5v5 non-EN goals fall inside an episode vs the conceding team
  (gate ≥ 90%; scope = segment-covered games per PV-D010; residual = 8 genuinely outside-zone goals, 0
  DZ artifacts). Goal anchoring is a boundary convention, NOT zone coercion (PV-D008; GV9/GV10).
- dbt↔reference reconciliation (75 games, 25/season × 3): per-event state **0.0000%** (gate ≤ 0.5%),
  episode count **0.0000%** (gate ≤ 2%).
- Schema tests: **18/18 pass**.
- Bands: episodes/team-game **45.0** (20–55); mean episode duration **17.4 s** (6–25); 5v5 possession-time
  shares P_OZ 51.7% / P_NZ 30.1% / P_OWN_D 18.1% (per-team in-zone-against ≈ 25.8%, in 15–30% band).

## 3. Episodes
A DZ episode against team *d* is a maximal set of spells where the opponent possesses in *d*'s D zone,
merging brief interruptions that (a) total ≤ `phase_episode_gap_seconds` (4), (b) keep the puck in *d*'s D
zone, and (c) contain no DEAD boundary. An attacker **goal** anchors/ends an episode even though play goes
DEAD after it (PV-D008) — this is what covers rush/quick-strike goals. **start_type** (precedence
oz_faceoff > rush > forecheck > carry_other): oz_faceoff excludes a defensive-zone draw from `deny` because a
draw is *deployment, not defense* (avoids crediting line-change luck); rush mirrors `int_shot_sequence`'s
`seq_rush`. **end_reason**: goal > stoppage > exit > flip_sustained. Measured mix (3 seasons): start_type
carry 59% / oz_faceoff 19% / rush 11% / forecheck 11%; end_reason exit 56% / stoppage 33% / flip 6% / goal
5%. 5v5-scoped on the start event's strength; clipped-by-strength share **3.4%** (< 10%), kept & flagged (PV-D007).

## 4. The value function
`int_phase_ticks` (one row per 5 s of live-5v5 spell time) + `compute_state_values.py` estimate
**V(state)** = tick-duration-weighted mean net goals (possessing team − opponent) over (t, t+40 s] within
the same period, pooled 2015-16 → 2025-26; cluster bootstrap by game (200). Output `nhl_models.state_values`.

| state | V | se | n_ticks |
|---|---|---|---|
| P_OZ_EST | **0.00520** | 0.00027 | 4.65M |
| P_OZ_RUSH | 0.00351 | 0.00084 | 0.12M |
| P_NZ | 0.00143 | 0.00036 | 1.57M |
| P_OWN_D | **−0.00027** | 0.00032 | 1.91M |

**HARD GATE PASS:** V(P_OZ_EST) > V(P_NZ) > V(P_OWN_D) (0.00520 > 0.00143 > −0.00027; pooled gap ~5 se).
V(P_OZ_EST) is stable across seasons (0.0039–0.0068, always the top state).

**The V(P_OWN_D) < 0 finding.** Possession is not uniformly good — *where* you hold the puck is what
matters, and holding it in your own defensive zone is, on net over the next 40 s, **marginally negative**
(−0.00027 goals; slightly worse than neutral-zone possession and than having no particular possession at
all). The hockey reading: a team retrieving the puck deep in its own end is at the highest-turnover-risk
moment of the sequence — it is under forecheck pressure, its breakout can be stripped for a high-danger
chance against, and the reward (a successful exit merely reaches neutral ice) is asymmetric with the risk (a
failed exit yields a chance against). Over a 40 s horizon that asymmetry nets out slightly below zero. The
magnitude is small and near zero (as the spec anticipated), but the **sign is the interesting result**: it
says D-zone puck-possession is not itself a positive state, which is exactly why a defensive model built on
*escaping* that state (the `escape` component) is well-motivated. The value only turns clearly positive once
possession reaches the offensive zone (P_OZ_EST 0.0052).

**Granularity caveat on V(P_OZ_RUSH) (PV-D013).** At the 5 s tick grid V(P_OZ_RUSH)=0.0035 sits *below*
V(P_OZ_EST)=0.0052, but this is a measurement artifact, not a finding: the rush state's ≤5 s lifetime equals
the tick grid and sub-2.5 s partial ticks are dropped, so 71.2% of *scoring* rush episodes (mean duration
2.14 s) contribute zero rush ticks and their goals credit the preceding windows. A tick=2 s diagnostic
restores the spec-expected order (V(rush)=0.0054 > V(est)=0.0051). `c_seq_rush` = 0.0589 is **the costliest
event-visible start category** (highest episode xG cost) — but this is a statement about the *event-space
`start_type='rush'` category*, NOT about tracking rushes: the sprite audit (`sprite-audit.md`) found the label
**anti-selected** at goals (precision below base rate at every k∈{3,4,5,6}; a majority of rush-labeled goals
show no tracking entry at all) with **no positive association** to tracking-fast entries — because it is
success-conditioned (goals only) it cannot speak to non-goal sequences, and the ceiling is absent events, not
window size. So `c_seq_rush` / `V(P_OZ_RUSH)` / `deny_rush_coef` are reported as event-space diagnostics with
that caption, not as tracking-rush danger. V(P_NZ)/V(P_OWN_D) are both near zero, so their fine ordering is
within noise; the accounting relies only on P_OZ_EST ≫ {P_NZ, P_OWN_D ≈ 0}. `phase_rush_state_seconds` stays **5 s** — sprite-tracked
entry-to-goal times (median 3.8 s, **p75 5.3 s**) show a 5 s rush-state lifetime captures ~70% of entries;
this is supporting context, carried with the granularity caveat above. Full detail:
`docs/phase-value/stage2-acceptance.md` and `docs/phase-value/sprite-audit.md`.

**League constants** (`nhl_models.phase_league_constants`, 2015-16+): s_out 12.58 min/60, s_in 17.42 min/60,
`C_seq` (mean `xg_5v5` per non-faceoff episode) 0.0517 (rush highest at 0.0589, oz-faceoff lowest 0.0305),
r_inzone_xg_per_sec 0.00246, xG calibration 0.983 → fixed 1.0 (inside ±0.03). All consume the 5v5-restricted
episode columns (PV-D009), so PP-tail xG is excluded.

## 5. Estimation
The unit is the 5v5 stint (`int_segment_context` × `int_shift_segments`, `segment_duration ≥ 5`,
PV-D002), expanded to two attacking-direction rows per stint exactly as RAPM's `expand_rows` does — the
attacking team is the `off` side, the defending team is the `deff` side. Each of the three components
(plus the `deny_rush` diagnostic) is the **same two-sided sparse ridge as RAPM, reused by import**
(`train_rapm.build_design / cv_alpha / bootstrap_sd`): identical controls (attacker score-state, faceoff
zone, home, back-to-back, game-time bucket, season FE), identical replacement pooling (< 100 exposure-min
→ F/D sentinel pools), identical game-grouped 5-fold α-CV over the imported `ALPHAS` grid (PV-D003). The
ONLY per-fit differences are the target and the weight (§7.1):

| fit | target (per 60 of exposure) | weight | exposure floor |
|---|---|---|---|
| `deny` | `episode_starts_nonfo / outside_sec × 3600` | `outside_sec` | `outside_sec ≥ 5` |
| `suppress` | `xg_inzone / inzone_sec × 3600` | `inzone_sec` | `inzone_sec ≥ 5` |
| `escape` | `favorable_ends / inzone_sec × 3600` | `inzone_sec` | `inzone_sec ≥ 5` |
| `deny_rush` (diag.) | `episode_starts_rush / outside_sec × 3600` | `outside_sec` | `outside_sec ≥ 5` |

The floor is applied on the **stint-direction total**, never per-episode (PV-D011), so zero-duration
goal episodes keep their start (deny) and their goal xG (suppress). Each component is read off the
**centered DEFENCE coefficient** with a per-fit sign (PV-D017): `deny`/`suppress` = `−def_c` (good
defence lowers the target), `escape` = `+def_c` (a favourable end is the defender's success and raises
it). Windows mirror RAPM: a 3-season weighted headline (0.3/0.6/1.0) plus single seasons 2021-22→2025-26.

Uncertainty is a single **shared-draw game-resample bootstrap across all four fits** (same seed and draw
sequence; B=100 on the headline window, 40 on singles, PV-D019). The composite `pv_def_g60` sd is priced
**within each draw** from that draw's deny+suppress coefficients (§8.1), never by quadrature — deny and
suppress are positively correlated through the shared resampling, and quadrature would understate it.

**Wiring gate (report-only diagnostic, not a reliability test).** Per target, the exposure-weighted
team-season mean of the fitted prediction is correlated against the directly-observed team-season target
rate; the gate is r ≥ 0.80. **All 24 fit×window combinations pass.** The single-season fits are the sharp
check (r ≈ 0.97–0.99); the 3-season window softens (deny 0.819) as expected shrinkage from
season-weighting + replacement pooling — both sides carry the same 0.3/0.6/1.0 weights, and removing them
*lowers* r (0.795), so the softening is pooling, not a weighting artifact (PV-D019). Reliability itself —
the defence-coef spread is only ~1.1–1.4× the mean bootstrap sd across every fit and window (defence is
the platform's weakest signal) — is quantified but **formally adjudicated by the pre-registered Stage 5
tiers**, not here.

## 6. Accounting
Rate coefficients are priced per 60 of ICE time in goals per **spec §8.1**, with the Stage-2 constants
(a=`deny`, b=`suppress`, cal=`xg_calibration`; PV-D018):

```
deny_g60     = a · (s_out_min_per_60/60) · c_seq_xg_nonfo · cal      # 12.58/60 · 0.0517 · 1.0
suppress_g60 = b · (s_in_min_per_60/60) · cal                        # 17.42/60 · 1.0
escape       = published as a RATE only (favourable ends /60 in-zone)
pv_def_g60   = deny_g60 + suppress_g60
```

Worked example (top-of-league defender, 3-season): `deny` 2.23 → `deny_g60` 0.024; `suppress` 0.609 →
`suppress_g60` 0.177; **`pv_def_g60` 0.201** goals saved /60 (vs RAPM `def_impact` 0.34). PV-D011 capture
(per-episode, k=1): zero-duration goal episodes are 3.5–9.4% of nonfo starts and 5–9% of in-zone xG per
window, and are retained.

**Component-first, per the pre-registered thesis (owner Ruling 1).** Because g60 pricing makes `deny_g60`
≈ 1/7 the magnitude of `suppress_g60`, the composite `pv_def_g60` is **suppress-dominated** and correlates
**~0.87 with `def_impact`**. It is kept exactly as §8.1 defines it — no reweighting (any other weighting
is ad-hoc tuning), and the dominance is reported as an empirical finding, not engineered away. It
**confirms** the project thesis rather than undercutting it: `suppress` at 0.86 with `def_impact` is the
expected result of shared on-ice attribution (it is `def_impact`'s xG channel re-denominated per in-zone
second); `deny` at 0.42 and `escape` at ≈0 are the genuinely **new** channels the transition frame adds,
and `deny`-vs-`suppress` at 0.29 clears the spec's 0.8 double-counting flag with enormous room. Surfaces
are therefore built **component-first**; the composite carries an honesty note that it is suppress-dominated
and overlaps `def_impact` at ~0.87. Final publication emphasis is set by the **Stage 5 reliability tiers**
(if `deny`/`escape` earn tiers `suppress` does not, component-first follows from the pre-registered rules),
not by this overlap matrix.

## 7. Validation
*(Pre-registered reliability tiers A/B/C with thresholds restated, the def_impact baseline comparison,
split-half, team out-of-sample, sensitivity summary, external A3Z agreement if run. Filled in Stage 5.)*
**External-validation module #2 (already run, report-only): the sprite audit** (`docs/phase-value/
sprite-audit.md`) — 10 Hz PPT goal-replay ground-truth of episode `start_type` + entry timing at goals,
sits beside the A3Z module. Success-conditioned (goals only); the goals-only banner caveat is stated
plainly there and inherited here.
**Pre-registered arena-bias diagnostic for `deny` (PV-D015, report-only):** correlate team-level `deny`
aggregates (minutes-weighted, per season) against the home-arena under-recording rate (the
`established_full_window` share from the sprite audit's arena table). A material correlation means `deny`
partially measures scorekeeper behavior, not defense; reported beside the smell tests either way, and it is
the activation test for the v1.1 rink adjustment.

## 8. Known limitations (pre-committed)
Possession is a proxy from scorer-recorded events; entries generating no event are invisible, so `deny`
measures **event-visible threatening sequences allowed**, not true entries; `suppress` still rests on shared
on-ice attribution and is expected to be the weakest component; scorer bias on giveaways/takeaways is
inherited (PV-A2); 5v5 only in v1; the V goals-window includes cross-strength goals (PV-A4).

**Measured against sprite ground-truth (10 Hz PPT goal replays, 16,074 usable goals; report-only, PV-D014):**
- `start_type='rush'` is an **event-visible rush** — a small, non-random subset of true rushes. Against
  tracking-detected entries its recall is pinned at **~0.09 across k∈{3,4,5,6}** (the ceiling is absent
  events, not window size). Contamination is architecturally contained: `deny`/`suppress`/`escape` never
  consume the rush label; only the diagnostics `c_seq_rush`, `V(P_OZ_RUSH)`, `deny_rush_coef` are affected,
  and each carries this caveat where it surfaces.
- Zero-duration goal-only episodes (PV-D008) are **57.9% genuine rapid entries / 42.1% under-recorded settled
  possession**; the 42% share shows arena spread (p10 35% / p90 50%), so `deny` may inherit scorekeeper bias
  (Stage 5 input; v1.1 rink-adjustment candidate). This refines `deny`'s meaning, not its construction — the
  accounting stays consistent because `C_seq` prices exactly the universe the coefficient counts.
The sprite audit is **success-conditioned (goals only)**; the inherited banner caveat is carried verbatim in
`docs/phase-value/sprite-audit.md`.

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
