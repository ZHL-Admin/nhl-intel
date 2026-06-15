# Team identity & style map (Phase 3.2)

Two artifacts describe *how* a team plays (not just how well): a per-team fingerprint
(`mart_team_identity`) and a league style map (`nhl_models.style_map`).

## Fingerprint — `mart_team_identity`

One row per `(season, team_id, window_kind)` where `window_kind` is `season` (all games)
or `last25` (the team's most recent 25 games that season). Regular season + playoffs only
(game-id types `02`/`03`). Every metric carries a league percentile (`*_pctile`,
`percent_rank` within season + window).

Metrics:
- **Offense mix** — 5v5 attempt shares by sequence type (rush / forecheck / cycle /
  point-shot / rebound), for and against, from `mart_team_identity_inputs`.
- **Pace** — 5v5 attempts (for + against) per minute.
- **Shot quality** — 5v5 xGF per attempt; **shot volume** — attempts per 60.
- **Aggression** — rink-adjusted hits per 60, penalties taken / drawn per 60. Per-60 uses
  a 60-minute game approximation (OT negligible).
- **PP structure** — point-shot share of power-play shots.
- **Territory (NHL Edge)** — offensive / defensive zone-time pct, TOI-weighted across the
  team's skaters' even-strength Edge zone time. *The team-level Edge zone-time endpoint
  404s, so this is a documented skater-aggregated proxy.* Edge covers 2021-22 onward; older
  seasons have null zone-time / conversion.
- **Territory-to-danger conversion** — 5v5 xGF per minute of offensive-zone time (our xG,
  Edge OZ minutes; both season aggregates, so the join is legitimate per blueprint 12.1).

## Style map — `compute_style_map.py`

The fingerprint vector (style features only) is standardised across the 32 teams and reduced
to 2D by PCA. Orientation is pinned for run-to-run stability: PC1 is flipped so higher shot
volume reads to the right, PC2 so higher shot quality reads up. Axis-end descriptions are the
top-3 features by loading in each direction (e.g. "high forecheck, high pace"), stored on
every row so one query returns both points and annotations. Recent fit: PC1 ~22% of variance,
PC2 ~17%.

## Conversion diagnosis

The TeamProfile Identity tab renders a plain-English structural diagnosis purely from API
ranks, e.g. a team that is high in offensive-zone time but low in xG per OZ minute is flagged
"controls territory but struggles to turn it into danger — a volume-over-quality structure."
Validated divergence examples (2025-26): NYR and FLA rank high in o-zone time but low in
danger conversion; CBJ and WSH are the inverse (efficient on limited territory).

## Endpoints

`GET /teams/{id}/identity` (per-window metrics + percentiles + league size) and
`GET /teams/style-map` (points + axis annotations).
