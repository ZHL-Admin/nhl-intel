# Phase 0 — Scaffold, inventory, defensive-frame primitives

**Defensive Scheme & Role** (`NIR/research/def-scheme/`). Read-only over goal-tracking + prior research; own venv; `make phase0` reproduces from cache. Seed 20260714c.

> **LAW 1 · GOALS-ONLY. The tracking corpus contains only goal buildups; there is no tracked non-goal. This project INFERS team scheme and player role from goal geometry and measures deviation from the team's own norm. It never claims 'this positioning caused the goal' nor compares against non-goal plays it does not have. The scheme-norm is a norm ON GOALS.**

> **LAW 2 · NO FAULT LANGUAGE. 'out of position', 'blame', 'fault', 'mistake', 'responsible' never appear. The only permitted claim is DEVIATION FROM THE TEAM'S OWN STRUCTURAL NORM — a descriptive geometric fact, never a verdict of error. Scheme vs individual error cannot be separated per-goal; only aggregate deviation tendency is claimed.**


## 0.2 Inventory (read-only inputs)

| input | path | status | timestamp |
|---|---|---|---|
| goal-tracking fused_goals | research/goal-tracking/data/parquet/fused_goals.parquet | OK | 2026-07-14T00:07:41 |
| goal_events | research/goal-tracking/data/parquet/goal_events.parquet | OK | 2026-07-14T00:07:42 |
| frame cache (2023-24) | research/goal-tracking/data/cache/frames_2023_24.parquet | OK | 2026-07-13T23:42:07 |
| Atlas stints | research/deployment-atlas/data/parquet/stints.parquet | OK | 2026-07-10T16:45:15 |
| System Effects regime ledger | research/system-effects/data/parquet/regime_ledger.parquet | OK | 2026-07-11T21:08:05 |
| System Effects team fingerprints | research/system-effects/data/parquet/team_season_fp.parquet | OK | 2026-07-11T17:32:22 |
| Chemistry pairs corpus | research/chemistry/data/parquet/pairs/ | OK | 16 season files |

**`gtrack.api` confirmation:** `team_goals(team, side='against')` returns each team's goals-against (fused rows with goalie_id, home/away/scoring team, attack_sign, q_a/q_b). Frames for those goals are read from the Stage-0 frame cache (`frames_<season>.parquet`) keyed by (game_id, event_id) — the API surfaces the goal identities; the 10 Hz frames come from the Stage-0 cache (read-only). Defensive geometry uses the goal-tracking 10 Hz conventions (positions raw, velocities SavGol-smoothed; Phase 0 is positional only).

## 0.3 Defensive-frame primitive schema

Per goal-against, per frame, per DEFENDING skater, in the defending team's frame (attack-direction normalized so the DEFENDED net is at (+89, 0)). **Geometry only — no scheme or role labels (Law 2).**

| field | meaning |
|---|---|
| `game_id, event_id, season` | goal-against identity (Stage 0 key) |
| `defending_team_id / scoring_team_id` | scored-on team / attacking team |
| `frame_index` | 10 Hz frame within the buildup |
| `player_id` | a DEFENDING skater (goalies excluded) |
| `strength_state / n_def` | ice strength / defending skaters present (pentagon size; 5 at 5v5) |
| `x_norm, y_norm` | position, attack-direction normalized (defended net at +89,0) |
| `dist_net` | distance to the DEFENDED net |
| `dist_puck, dx_puck, dy_puck` | position relative to the puck |
| `off_centroid, team_spread` | distance to defenders' centroid / mean spread (pentagon shape) |
| `dist_nearest_atk` | distance to the nearest attacker |
| `zone` | dzone (x_norm>=25) / neutral / ozone |
| `puck_side` | strong (same y-side as puck) / weak |
| `low_high` | low (x_norm>=54, near net) / high / na |

## Coverage & quality filtering

- **Universe: TRACKED goals** (Stage 0 a∧b) — 23,966/25,946 (92.4%) of all goals; carrier/quality filter reused from Stage 0.
- **15,471,759 defender-frame rows** across **23,918 goals-against** and **44 defending teams**.

| season | defender-frames | goals-against |
|---|---|---|
| 2023-24 | 4,569,873 | 1,394 |
| 2024-25 | 5,404,829 | 1,434 |
| 2025-26 | 5,497,057 | 1,418 |

**Per team-season goals-against** (real NHL team-seasons, ≥20 GA): median 81, p10 77, p90 92, min 73, max 102 (96 team-seasons across 34 NHL teams). (Phase 1 sets the per-situation min-sample gate.)

**Coverage caveat — exhibition rosters flagged:** 10 team-seasons have <20 GA (team-ids [60, 62, 66, 67, 7801, 7802, 7803, 7804, 7805, 7806]) — these are **All-Star Game** (7801–7806) and **4 Nations / international** (60s) exhibition rosters whose goals are in the corpus. They carry non-standard team-ids and a different (exhibition) scheme context; **Phase 1's min-sample gate excludes them** and they are not part of the NHL team-scheme universe.

**Defending skaters present (n_def):** 5=10,451,435, 4=2,502,436, 6=1,742,394, 3=343,467, 7=317,408 (n_def=5 is the clean 5v5 pentagon; other counts are special-teams, flagged for Phase 1).
- **zone:** dzone=11,252,133, neutral=2,364,308, ozone=1,855,318.
- **puck_side:** strong=9,380,665, weak=6,091,094.
- **low_high:** low=8,906,395, na=4,219,626, high=2,345,738.

**Primitive sanity:** median dist_net 33.9 ft, median dist_puck 26.9 ft, median dist_nearest_atk 12.4 ft, median team_spread 18.9 ft.

## STOP — Phase 0 for owner review

Primitives built (geometry only). **Next (Phase 1, on owner go):** aggregate into the coverage signature with the goals-only bias mitigation (league baseline + offensive-goals cross-view). No scheme claim is made in Phase 0.