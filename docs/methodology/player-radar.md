# Skills radar (Part B)

Per-player (and per-goalie) percentile-within-position skill radars, the primary header visual on
player pages. `models_ml/compute_player_radar.py` -> `nhl_models.player_radar`;
`models_ml/compute_goalie_radar.py` -> `nhl_models.goalie_radar`. Backend:
`GET /players/{id}/radar`, `GET /goalies/{id}/radar`. Frontend:
`components/visualizations/SkillRadar.tsx`.

## Principles

- **Every spoke maps to a real computed column.** No spoke is invented to balance the chart. An
  honestly lopsided result (offense high-resolution, defense thinner) is correct.
- **Percentile-within-position is the only baseline at launch** (F and D separately, within
  season, over the clustering pool of ≥300 5v5 minutes). Stated on the chart.
- **Variable spoke set.** A spoke whose source is missing is ABSENT (not greyed, not zero). Edge
  burst is present only for the tracking era (2021-22+); pre-tracking seasons carry the seven
  mart-based spokes. The component accepts any-length spoke list.
- **Honesty tag per spoke** — skill / usage / style / proxy. *Usage* = how the coach deploys him,
  not how good he is.
- **Uncertainty shown on noisy spokes** — EV offensive/defensive impact carry their bootstrap sd
  (rendered as a faint radial whisker; the value is in the tooltip).

## Skater spokes (ring order: offense → boundary → defense/style)

| # | Spoke | Tag | Source |
|---|---|---|---|
| 1 | Finishing | skill | `player_composite.finishing` |
| 2 | Shot Volume | skill | individual attempts /60 (`mart_player_game_stats`) |
| 3 | Shot Danger | skill | mean ixG/attempt |
| 4 | Rush Offense | skill | rush-attempt share (sequence) |
| 5 | Cycle/Forecheck Offense | skill | forecheck+cycle attempt share |
| 6 | Playmaking | skill | primary assists /60 (`first_assists`) |
| 7 | EV Offensive Impact | skill | `player_impact.off_impact` (± `off_sd`) |
| 8 | Power-Play Value | usage | `player_impact.pp_impact` |
| 9 | Skating/Burst | skill | `mart_edge_player_profile.bursts_22_plus_per60` — tracking-era only |
| 10 | EV Defensive Impact | skill | `player_impact.def_impact` (± `def_sd`, noisy) |
| 11 | Penalty Kill Role | usage | coach-trust PK share |
| 12 | Defensive Deployment | usage | coach-trust composite |
| 13 | Penalty Differential | skill | (drawn − taken) /60 |
| 14 | Physicality (rink-adjusted) | style | `hits_adj` /60 (never raw) |

**Deliberate offense/defense resolution asymmetry.** Offense has high-resolution spokes
(finishing, volume, danger, rush, cycle, playmaking, EV impact); defense is intentionally thinner
(EV defensive impact + two deployment spokes). This is honest: RAPM `def_impact` does not cleanly
separate defenders (see `archetypes.md`), so defensive signal is carried mostly by deployment
(usage), and we do not invent skill spokes to fake symmetry.

**Zone suppression is excluded from the radar** (it is redundant with EV Defensive Impact and
noisier) but is kept in the clustering vector (`archetype_features_v2`) and is available in the
depth-3 table.

## Goalie spokes (percentile within goalies)

Overall GSAx (per game), High-Danger GSAx, Mid/Low-Danger GSAx, Workload (shots faced/game),
Consistency (game-to-game GSAx steadiness), NHL Edge Save% (last 10 — the second opinion;
tracking-era only), Quality of Defense Faced (xGA/shot, proxy). Goalies never share an axis with
skaters and are never ranked across them.

**A0 finding:** there is no Edge *high-danger* goalie save% in the data (Edge has no goalie HD
split), so spoke 6 uses the overall `edge_last10_save_pct`, labelled "NHL Edge Save% (last 10)".

## Labels + descriptor (from v2 archetypes)

Written alongside the radar so one source drives both label and chart (`archetypes.md` v2):
- **Overall** = coarse family by position (Offensive / Two-Way / Defensive / Depth), generic
  because it claims less (`config.ARCHETYPE_FAMILY_V2`).
- **Offensive sub-label** = the specific v2 archetype (offense is high-resolution).
- **Defensive sub-label** = coarse, deployment-leaning bucket from the deployment/PK/def-impact
  percentiles (no asserted shutdown skill unless the audit proved it universal).
- **Descriptor** = the cluster's distinctive-trait string (`config.ARCHETYPE_DESCRIPTORS_V2`).

Because v2 clusters on defensive/style features, the label and radar are coherent — the same
information drives both. (A star can shift clusters season-to-season as his on-ice context changes,
e.g. McDavid 2025-26 lands in the fast/conceding "North-South Forward" region for that season; the
radar shows his elite spokes regardless, and the Overall family stays "Offensive".)
