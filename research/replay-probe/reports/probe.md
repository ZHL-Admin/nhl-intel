# Replay probe — what the NHL ppt-replay tracking data actually is

**Project:** replay-probe (`NIR/research/replay-probe/`) · **Date:** 2026-07-13 · read-only, no builds.
**Discipline:** every claim below is verified against actual files (the warehouse table, cached sprite
JSON, and the dbt model SQL) — nothing inferred about fields not seen.

---

## THE DECISIVE ANSWER (2.2) — yes, full player + puck tracking, but goals-only

**The data contains timestamped x/y positions for the PUCK and for ALL players on ice — both teams'
five skaters and both goalies — at 10 Hz, for the ~12–21-second buildup to every goal.** It is **not**
full-game tracking: **only scoring plays are covered.**

Verified from a real frame (warehouse row, 2025-26 game 2025030413) — 13 entities per frame:
```
{"timeStamp": 17807970313, "onIce": [
   {"id":12031,"playerId":8475883,"x":2230.09,"y":501.16,"sweaterNumber":31,"teamId":12,"teamAbbrev":"CAR"},
   ... 11 more skaters/goalies ...,
   {"id":1,"playerId":"","x":1560.40,"y":887.20}]}     # entity key "1" = the PUCK (x/y only)
```
- **Puck:** yes — entity key `"1"`, x/y only (no playerId/team).
- **All on-ice players:** yes — each with `playerId`, `x`, `y`, `sweaterNumber`, `teamId`, `teamAbbrev`
  (12 players = 5v5 skaters + 2 goalies; entity count 13 with the puck).
- **Resolution:** `timeStamp` is **deciseconds → 10 Hz** (verified from the dbt model:
  `frame_seconds = (timestamp_ds − min)/10.0`); ~120–210 frames per goal ≈ **12–21 s of buildup**.
- **Per-event, not high-frequency-continuous:** one frame stream per GOAL event, not a game-long feed.

This single answer bounds everything: it is a **goal-anatomy** dataset (a fully-tracked ~15-second
clip before each goal), not a full-game tracking feed.

---

## Step 1 — where the data lives (found; the owner was right, it is in BigQuery)

| source | finding |
|---|---|
| **(a) warehouse** | **`nhl_raw.raw_ppt_replay` — 25,946 rows** (one per goal). Cols: `season, game_id, event_id, frame_count, goal_metadata, frames, ingestion_date`. `frames` = the sprite array above. **This is the full copy — no fetch needed.** Also present: **NHL EDGE** season aggregates (`raw_edge_skaters` 33,772, `raw_edge_goalies`, `raw_edge_teams`; `mart_edge_player_profile`/`_team_profile`) — skating speed/bursts/shot-speed/danger-zone SEASON stats, **not** positional tracking. Two derived models exist but are **empty (0 rows)**: `stg_ppt_tracking_frames` (frame-explode + coord standardization) and `int_goal_release_frame` (release-frame detection). |
| **(b) on disk** | `scripts/ppt_probe_cache/` (172 files) + `scripts/ppt_cache/` — cached goal sprites + metadata from the earlier `scripts/probe_ppt_events.py` run (2023-24 → 2025-26). Confirms the warehouse structure. |
| **(c) ingestion endpoint** | Already wired: `ingestion.nhl_api.get_ppt_replay` → metadata `api-web.nhle.com/v1/ppt-replay/goal/{gid}/{eid}` (carries `goal.pptReplayUrl`) → sprite `wsr.nhle.com/sprites/{season}/{gid}/ev{eid}.json` (Cloudflare-gated; needs the WSR referer/UA). Backfilled into `raw_ppt_replay` via `ingestion/loaders.py` + on the daily DAG `dags/nhl_daily.py`. Methodology: `docs/methodology/ppt-replay-tracking.md`. |

**No broad fetch was run.** A permitted small era-boundary sample (8 requests, rate-limited) was taken
— see 2.4.

---

## Step 2 — payload characterization (verified)

**2.1 Structure.** `raw_ppt_replay` = one row per goal: `goal_metadata` (scorer `playerId`, `strength`
e.g. "ev", `situationCode` e.g. "1551"=5v5, `periodDescriptor`) + `frames` = a list of
`{timeStamp, onIce:[entity,…]}`. Frames are **positional snapshots**, not events.

**2.2 Coordinates.** (lead answer above) — puck + all 12 on-ice players, 10 Hz, ~12–21 s per goal.

**2.3 Event richness — no first-class connective events.** The sprites carry **positions, not labeled
plays**. There are **no** pass / puck-touch / zone-entry / retrieval events with a player id. That
connective tissue is **implicit in the trajectories** (a pass = the puck moving from near player A to
near player B; an entry = the puck crossing the blue line with a nearby carrier) and is
**reconstructable** — but it is not pre-labeled. This is still richer than play-by-play (which has
**zero** passes), **for the goal buildup only.**

**2.4 Coverage — hard boundary at 2023-24.** `raw_ppt_replay` by season: **2023-24: 8,618 goals
(1,397 games); 2024-25: 8,635 (1,434); 2025-26: 8,693 (1,419).** Nothing earlier. A permitted
rate-limited API test of pre-2023 goals (one game each) confirmed the boundary is real, not just a
backfill gap:

| season | goal sprite via API |
|---|---|
| 2015-16, 2019-20, 2021-22, **2022-23** | **none** (metadata carries no `pptReplayUrl`) |
| **2023-24** (positive control) | **present, 120 frames** |

So the pptReplay tracking product exists **2023-24 onward only** (even 2021-22, when EDGE tracking
launched, has no replay sprites). The capability boundary is unambiguous.

**2.5 Scope — GOALS ONLY.** Only goal events return a sprite; every non-goal event (shot-on-goal,
missed, blocked, hit, faceoff, takeaway, giveaway, penalty) returns **403 AccessDenied** from wsr's S3
(object-not-found, with identical headers/host/game as the working goals — verified across the cache:
per game, 200 only on goals, 403 on all ~19–24 non-goals). **This is a goal-anatomy dataset, not a
full-game tracking feed** — and a **success-conditioned** one (only sequences that ended in goals).

**2.6 Reliability / quirks.**
- **Coordinate frame (solved):** raw x/y are **inches, corner-origin** (bounds ~0–2400 × 0–1020 =
  12×200 ft by 12×85 ft). Standard center-origin feet: **`x_std = raw_x/12 − 100`** (±100 boards,
  ±89 goal line), **`y_std = raw_y/12 − 42.5`** — verified in `stg_ppt_tracking_frames.sql`.
- **Rink orientation / home-away flip:** raw coords are absolute (not flipped to attacking direction);
  aligning to attacking-net needs period + home-defending-side, as the shot/xG models already do.
- **Frame-count outlier:** 2024-25 `max frame_count = 500` vs ~139 avg — likely a long-OT / concatenated
  clip; spot-check before trusting the tail.
- **Selection bias (fundamental):** goals-only means no counterfactual non-scoring sequences — any
  "value"/"credit" model built here is conditioned on success.

---

## Step 3 — opportunity map (assessment only; nothing built)

**3.1 Idea 10 (Goal Anatomy): BUILDABLE at FULL-tracking fidelity, 2023-24 → 2025-26 (~26k goals).**
The connective goal-buildup dataset (puck + all players at 10 Hz, coords → feet, ~12–21 s pre-goal) is
in the warehouse; it needs only the frame-explode + standardization the two **already-written but
unbuilt** dbt models do. Version = **full** (not thin), span = **3 seasons**.

**3.2 Dependent family** (all inherit the goals-only, success-conditioned scope):
| idea | tag | why |
|---|---|---|
| 12 Goal Credit Model | **REOPENED (goal-scoped)** | full player+puck geometry per goal — the most directly enabled; a positional goal-credit model is buildable now |
| 15 Release Clock | **REOPENED (goals only)** | release frame detectable (`int_goal_release_frame`: puck nearest a net); reception→release time + puck-displacement velocity — goal-shots only |
| 4 Chain Credit | **PARTIAL** | can credit the buildup's on-ice contributions per goal, but not non-scoring possessions (biased) |
| 13 Pass Atlas | **PARTIAL** | passes reconstructable from puck trajectory in buildups (~2–6/goal × 26k) — a goal-adjacent atlas, not the full-game pass network |
| 11 Beaten or Broken | **PARTIAL** | defenders' positions show who was beaten on goals-against; no "broken but no goal" cases → biased |
| 14 Pressure-Adjusted Finishing | **PARTIAL (weak)** | defender/goalie proximity at the goal shot is measurable, but there are **no tracked non-goal shots** to form the finishing baseline |
| 16 Clutch Audit | **STILL BLOCKED** | needs game-state/time-pressure across all play; goal buildups add little |

**3.3 Does this reopen FIT? No — not at the scope its closure required.** The fit line (F17–F20) closed
"pending a materially new data source — **tracking for off-puck play**." This data *does* carry off-puck
player coordinates — **but only during goal buildups (goals-only, ~15 s, 2023-26).** A general fit test
needs **full-game** off-puck tracking (to value spacing/routes across all situations); a goals-only,
success-conditioned sample cannot answer it (it would confound "off-puck fit" with "was on the ice for
a goal"). **Assessment: fit is NOT reopened.** A *narrow, descriptive* goal-anatomy off-puck study is
possible (e.g., does a linemate's route open the shooting lane on goals) but inherits the selection
bias and is not the fit question. Do not reopen fit on this data.

**3.4 New ideas the verified data enables** (all goal-scoped, 2023-26):
| idea | question | data | feasibility |
|---|---|---|---|
| Goal-buildup passing networks | which player combinations *manufacture* goals (puck-trajectory passes) | frames | high |
| Screen / net-front geometry | screener/goalie/shooter positions at release → screen effect on goals | release-frame entities | high |
| Goalie positioning on goals | goalie x/y vs puck at release → depth/lateral beaten-how | goalie entity | high |
| Release clock + shot velocity | reception→release time; puck speed from displacement | frames + release | high (dbt scaffolds it) |
| Defensive-coverage collapse | how the 5 defenders' spacing (a "coverage entropy") breaks down pre-goal | frames | medium |
| Entry → goal sequences | the zone entry that led to each goal (puck crossing blue line + carrier) | frames | medium |

**3.5 Cost / readiness + value-over-effort.**
- **No fetch.** `raw_ppt_replay` (25,946 goals) is in the warehouse, backfilled and on the daily DAG.
- **Ingestion layer: done.** The **derived** layer is the gap: `stg_ppt_tracking_frames` (explode
  frames → one row per entity per frame, standardize coords) and `int_goal_release_frame` are
  **written but 0 rows** — they just need `dbt run` / materialization. Explode size ≈ 26k goals ×
  ~140 frames × 13 entities ≈ **~47M frame-entity rows** (a moderate mart).
- **Ranking (value ÷ effort):**
  1. **Materialize the two existing dbt models** (frame table + release frame) — a `dbt run`, no fetch,
     no new code. Unblocks everything; turns 26k raw sprites into a queryable 10 Hz frame mart.
  2. **Goal Anatomy / Goal Credit (Idea 10/12)** on the frame table — the flagship, directly enabled.
  3. **Release Clock + shot velocity (Idea 15)** — cheap once frames exist.
  4. **Goal-buildup Pass Atlas (13) + screen/coverage geometry (new)** — medium.
  5. **Pressure-adjusted finishing (14)** — limited by goals-only; do last.
  - **Avoid:** reopening fit (3.3) and Clutch (16) — the data does not fit the question.

### ➡ Single recommended next step
**`dbt run` the two already-written models (`stg_ppt_tracking_frames`, `int_goal_release_frame`).** No
fetch, no new ingestion, no research commitment — it converts the 26k warehouse goal sprites into a
standardized 10 Hz frame mart + per-goal release frames, replacing this paper feasibility read with a
real one and unblocking Goal Anatomy (Idea 10/12) and the release/geometry family. **STOP for owner
review** — this probe is the map, not a build.
