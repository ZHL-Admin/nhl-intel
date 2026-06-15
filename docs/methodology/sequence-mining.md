# Sequence mining (Phase 2.1)

Every unblocked shot attempt (shot-on-goal, missed-shot, goal) is classified by **how it
was generated**, stored one row per shot in `int_shot_sequence` so every downstream
feature — the in-house xG model, team identity, player shot mixes — can group by it.
Blocked shots are excluded entirely (their coordinates are the block location, not the
shot location).

## The orientation rule (verified empirically)

The NHL API `zone_code` is **relative to the event-owner team**. Verified 2026-06-15
against all shot events: shots are `'O'` ~98% of the time (mean |x| ≈ 62–70 ft), `'N'`
events sit near centre ice (mean |x| ≈ 12 ft), `'D'` shots are the team's own end.

To express a *prior* event's zone relative to the **shooting** team we keep `O/D/N` when
the prior event is owned by the shooter and **flip `O`↔`D`** when it is owned by the
opponent (neutral is symmetric). This single rule drives the rush, forecheck, and cycle
detectors.

`situation_code` is `[awayGoalie][awaySkaters][homeSkaters][homeGoalie]`, left-zero-padded
to 4 chars (e.g. `651` → `0651` = away goalie pulled). Strength (5v5/PP/SH/other) and
`is_empty_net` are derived from it relative to the shooting team (home/away from
`stg_boxscores`).

## Definitions

All windows are dbt vars (`dbt_project.yml`); SQL never hardcodes them. A prior event
*precedes* a shot when its `sort_order` is lower and it falls within the window in
game-elapsed seconds (`(period-1)*1200 + MM*60 + SS`, consistent with `int_on_ice_events`).

| flag | definition |
|---|---|
| `seq_rebound` | a same-team unblocked attempt within `rebound_window_seconds` |
| `seq_rush` | any event in the shooting team's **defensive or neutral** zone within `rush_window_seconds`, occurring **after every faceoff** in the window (no intervening faceoff) |
| `seq_forecheck` | puck recovered by the shooting team in its **offensive** zone (own takeaway or opponent giveaway) within `forecheck_window_seconds` |
| `seq_cross_ice` | a same-team event on the **opposite y-half** (`sign(y)` differs, `|y|≥10` for both) within `cross_ice_window_seconds` — the **royal-road proxy** |
| `seq_point_shot` | the shot itself is taken from `|x| ≤ 40` in the offensive zone |
| `seq_cycle` | (label-only) sustained OZ presence: **no** defensive/neutral-zone event by either team for ≥10 s before the shot, with ≥1 offensive-zone event present |

`seq_type` is a single label with precedence **rebound > rush > forecheck > cycle >
point_shot > other**. `seq_cross_ice` is a standalone flag, not part of the precedence
chain. `time_since_faceoff` and `time_since_turnover` are seconds to the nearest such
prior event, capped at 60, null if none within 60 s.

## Threshold tuning

`models_ml/tune_sequence_thresholds.py` sweeps each window independently over unblocked
shots 2018-19 .. 2024-25 and reports, per candidate window: flagged share, P(goal|flag),
P(goal|¬flag), **lift** (the ratio — separation), and the season-to-season spread of the
flagged share (stability). A good threshold maximises lift while keeping the share stable.

```
flag       win   share  goal%F  goal%U  lift seas_spread
rebound      2    5.5%  16.34%   6.66%  2.45       2.50%
rebound      3    7.1%  15.92%   6.52%  2.44       3.03%
rebound      4    8.8%  14.25%   6.51%  2.19       3.08%
rush         4    5.9%  12.20%   6.88%  1.77       2.75%
rush         5    7.5%  11.60%   6.83%  1.70       3.21%
rush         6    9.3%  11.06%   6.79%  1.63       3.81%
rush         7   11.1%  10.52%   6.78%  1.55       4.54%
forecheck    5    4.4%  10.82%   7.02%  1.54       0.98%
forecheck    6    4.9%  10.53%   7.02%  1.50       1.16%
forecheck    7    5.3%  10.33%   7.02%  1.47       1.31%
```

Tighter windows give both higher lift and better stability (at a coverage cost, which is
not a quality criterion). **Chosen windows:**

- `rush_window_seconds: 4` — highest lift (1.77) and lowest season spread (2.75%).
- `forecheck_window_seconds: 5` — highest lift (1.54) and lowest spread (0.98%).
- `rebound_window_seconds: 3` — **retained over 2** despite the sweep favouring 2: the
  lift is identical (2.44 vs 2.45) so there is no separation cost, and 3 s matches the
  conventional rebound definition while capturing ~1.6 pp more rebounds (7.1% vs 5.5%).
- `cross_ice_window_seconds: 2` and the cycle window (10 s) are definitional (a royal-road
  pass and a sustained cycle, respectively) and not swept.

## Validation (full 16-season build)

League-wide goal rate by `seq_type` confirms the engine separates dangerous from
low-danger generation, and the category shares are stable year over year:

| seq_type | share | goal% |
|---|---|---|
| rebound | 6.5% | **18.2%** |
| rush | 6.5% | 9.6% |
| forecheck | 4.0% | 8.7% |
| cycle | 14.3% | 5.7% |
| point_shot | 11.1% | 2.1% |
| other | 57.6% | 6.5% |

Rebounds and rushes show materially higher goal rates than cycle and point shots, exactly
as expected. `other` (the residual: short possessions, off-faceoff shots that meet no
trigger) sits near the league baseline.

## Downstream

- `mart_team_game_stats` / `mart_team_identity_inputs`: per-game 5v5 shot-attempt shares
  by `seq_type`, for and against.
- `mart_player_game_stats`: per-game individual attempt counts by `seq_type`.
- Backend exposes the seq-type shares as additive fields on the existing game/player stat
  responses (no breaking changes).
