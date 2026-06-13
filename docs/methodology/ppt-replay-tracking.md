# ppt-replay goal tracking (Phase 1.4)

Real per-frame player and puck coordinates for goals, ingested from the NHL
ppt-replay sprite files. This is measured tracking data (labeled "NHL tracking" in the
product), not an event-inferred proxy.

## Two-hop fetch

1. **Metadata** — `GET https://api-web.nhle.com/v1/ppt-replay/goal/{gameId}/{eventId}`.
   The `/goal/` path 307-redirects to `/v1/ppt-replay/{gameId}/{eventId}`; follow the
   redirect. The response carries a `goal` object whose `pptReplayUrl` field is the
   sprite URL. Use `eventId` from `stg_play_by_play` where `type_desc_key='goal'`
   (confirmed correct; `sortOrder` is not the parameter). Read `pptReplayUrl` from the
   payload rather than constructing it, so a future scheme change can't silently break.
2. **Sprite** — `GET` the `pptReplayUrl`, which lives on a **Cloudflare-fronted host**
   `https://wsr.nhle.com/sprites/{season8}/{gameId}/ev{eventId}.json`. A bare request
   **403s**; it requires `Referer: https://www.nhl.com/` **and** a browser `User-Agent`.
   Verified: plain `httpx` with those two headers returns 200 in this environment —
   **`curl-impersonate` was not needed.** 429s are handled by tenacity exponential backoff.

Sprites are immutable once a game is final, so `get_ppt_replay` caches them on disk
(`PPT_REPLAY_CACHE_DIR`, default `scripts/ppt_cache/`, gitignored).

## Sprite schema

The sprite is a JSON array of frames. Each frame is `{ timeStamp, onIce }`.

- `timeStamp` is **deciseconds** since the Unix epoch (~10 Hz; ~120–140 frames per
  ~12–14 s clip). `frame_seconds` = (timeStamp − clip's first timeStamp) / 10.
- `onIce` is served as a **map** keyed by `<teamId><zero-padded sweater>`, each value
  `{id, playerId, x, y, sweaterNumber, teamId, teamAbbrev}`. The **puck** is the entity
  keyed `"1"` (empty player/team fields). Because BigQuery can't `UNNEST` a JSON object
  with dynamic keys, `get_ppt_replay` **normalizes `onIce` to a list** of those entities
  with the original key preserved as `entityKey` (nothing is dropped) before storage.

## Coordinate transform (empirically corrected)

The plan guessed "tenths of a foot, rink ~2000 × 850". The **observed raw bounds are
~0–2400 (x) and ~0–1020 (y)** — exactly 12 × (200 ft) by 12 × (85 ft). The units are
therefore **inches (12 per foot), corner-origin.** We convert to the same center-origin
**feet** system the shot/xG models use:

```
x_std = raw_x / 12 - 100      -- range ~ -100..100; end boards ±100, goal line ±89
y_std = raw_y / 12 - 42.5     -- range ~ -42.5..42.5
```

**Orientation check (how we caught the unit error):** with the plan's ÷10 the release
puck appeared near ±89 *by construction* (the release-frame picker minimizes distance to
±89), but skaters landed ~20 ft past the boards (x_std up to ~120) — physically
impossible. With ÷12 every tracked entity falls within the rink (observed x ∈ [−100.5,
100.3], y ∈ [−43.5, 43.0]; ~0.3 % marginal boundary noise) **and** the release-frame puck
sits at **x_std ≈ ±89 (the goal line) with y near 0 (the goal mouth)** across sampled
goals — confirming both the scale and the orientation.

## Release frame

The sprite payload carries **no field aligning a frame's epoch `timeStamp` to the game
clock**, so `int_goal_release_frame` pins the scoring moment **geometrically**: the frame
where the puck is nearest a net (`min(|x_std−89|, |x_std+89|)`). At a goal the puck
arrives at the attacked net, making this an orientation-independent anchor (no need to
decode the metadata's home/away defending side). The model emits one row per on-ice
entity (puck + skaters), team-labeled, in standard coords — the moment Phase 6.4 renders.

## Models & scope

- `nhl_raw.raw_ppt_replay` — one row per (game_id, event_id) goal: goal_metadata,
  frames (normalized), frame_count.
- `stg_ppt_tracking_frames` — one row per (game, event, frame, entity) with raw + std
  coords, `frame_seconds`, `is_puck`.
- `int_goal_release_frame` — the release/arrival frame per goal (see above).
- `scripts/backfill_ppt_replay.py` — resumable, throttled (≤1 req/s vs wsr), batch-flushed.

**Scope:** all goals of the current and prior season (matching the landing/right-rail
window in Phase 1.3). Non-goal events expose the same `ev{eventId}.json` scheme, so scope
could widen later; goals are the chosen floor (highest value, bounded volume). Some goals
have no puck coordinates in their sprite (untracked); Phase 6.4 must gate on the presence
of tracking rows and fall back to event-inferred positions (never claiming "tracking").

## Season coverage (empirically probed)

ppt-replay goal sprites exist from **2023-24 onward** — confirmed by probing real
regular-season AND playoff goals: 2021-22 and 2022-23 goals 404 (both game types),
while 2023-24, 2024-25, 2025-26 return tracking. Note this is a NARROWER window than the
Edge aggregates (which go back to 2021-22) — the per-goal replay sprites are a newer
feature than the season tracking aggregates. Preseason games (gameType 01) have no
sprites in any season and are skipped automatically ("not a tracked goal"). The backfill
covers regular + playoff goals for 2023-24, 2024-25, 2025-26 and records per-season
goal-sprite counts as it runs.
