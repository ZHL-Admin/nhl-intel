# Streak Doctor (Phase 3.3)

Decompose a team's last-N-game run into goal-scale drivers, attach a deterministic verdict
and a 0-100 sustainability meter, and flag notable runs. Implemented in
`models_ml/streak_doctor.py`; output `nhl_models.streak_cards`, one row per
`(season, team_id, window_games)` for windows 5 / 10 / 20.

## Components (all in goals over the window)

| component | definition | persistence |
|---|---|---|
| `shooting_luck` | goals for − xGF (on-ice finishing above expected) | 0.1 |
| `goaltending` | team GSAx (xGA − GA) | 0.2 |
| `special_teams` | actual non-5v5 goal diff − expected (PP + PK) | 0.3 |
| `schedule` | mean opponent power rating faced × games (credit for a hard schedule) | 0.5 |
| `play_change` | (window 5v5 score-adj xGF% − season baseline) → goals | 0.8 |

`total_deviation` is the **sum** of the five components, so the per-component shares sum to
100%. It approximates the window's goal differential minus the team's season-baseline
expectation; the components are an interpretable attribution, not an exact orthogonal
variance partition (e.g. opponent strength also influences xGF, so `schedule` and
`play_change` overlap slightly — acknowledged).

## Sustainability meter (0-100)

A weighted average of component persistence, weighted by each component's absolute share:

```
sustainability = Σ persistence_i · |component_i| / Σ |component_j| × 100
```

Persistence weights (`models_ml/config.STREAK_PERSISTENCE`) reflect regression to the mean:
a genuine 5v5 xG-share change carries forward (0.8); on-ice shooting (0.1) and goaltending
(0.2) swings regress hardest. So a run built on a real play change scores high (sustainable);
one built on shooting luck scores low.

## Verdict

Deterministic templates (no LLM). The driver is the largest component pushing in the run's
direction (sign of `total_deviation`); the sentence states its share, a numeric detail, and
whether underlying 5v5 play improved / worsened / was unchanged. Example:
"74% of this 10-game surge traces to shooting luck (+23.9 goals vs expected). Underlying 5v5
play is worse."

## Notable detection

`is_notable` when the window points-pace z-score (vs the team's season game-level points
distribution) is ≥ 1.5 in magnitude, **or** the current W/L streak is ≥ 4. Computed on the
default window (10).

## Endpoints

`GET /teams/{id}/streak?window=10` (a team's card) and `GET /streaks/active` (notable cards
league-wide, strongest first). The frontend `StreakDoctorCard` (verdict, decomposition bar,
sustainability gauge, depth-3 table) auto-renders on TeamProfile when notable and is always
available via the Form tab; it is embeddable for the Phase 6 Home page.

## Validation (2025-26)

32 teams × 3 windows = 96 cards; component shares sum to 1.0 (max error 0.0). Goaltending-
dominant runs surface for hot/cold goalie teams (OTT +12.9 GSAx surge, DET −11.2 GSAx slump);
shooting-luck runs (WSH, STL, COL) score low sustainability (15-28); the lone play-change run
(NYI) scores highest (50).
