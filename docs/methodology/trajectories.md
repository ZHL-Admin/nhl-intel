# Career trajectories & twins (Phase 4.4)

Age curves per archetype, nearest-neighbour career twins, and a physical-aging overlay.
Prerequisite: player bio (birth date / height / weight) is ingested from
`/v1/player/{id}/landing` (`scripts/ingest_player_bio.py` -> `raw_player_bio` ->
`stg_player_bio`) — boxscore rosterSpots carry no bio. Age = whole years from birth date to the
season's Oct 1.

## Production metric

The curve and the player's path both use **points per 82** (G + A1 + A2), available 2010+.
Composite (Phase 4.2) is tracking-era only, so it can't carry a long age curve; points/82 is the
classic aging-curve metric and lets the cohort band and the player path share one axis.

## Aging curves (`nhl_models.aging_curves`)

Delta method: for each player, the year-over-year change in points/82 at consecutive ages,
averaged by age within an archetype, integrated and loess-smoothed, then anchored to the
archetype's mean level at age 24. **Each age t->t+1 delta is attributed to the player's archetype
in season t** (the blueprint's per-season hard-max) — one well-defined owner per delta, so
per-season archetype reassignment can't scramble the paired deltas. Validation: forward
archetypes peak in the **mid-20s** (Inside Scorer 23, Perimeter Playmaker 24, Two-Way Top-Six 25).

**Position-fallback bands.** The burst-defined archetypes (Elite Speed Driver, Elite Offensive D)
are sparse before the tracking era (see below), so their per-age delta counts are thin and no
stable archetype curve is produced. The model also emits `All Forwards` / `All Defensemen`
curves; the trajectory endpoint falls back to the position band (and labels it) when a player's
archetype curve is missing — e.g. McDavid (Elite Speed Driver) shows the All-Forwards band.

## Historical archetypes & the burst collapse

Pre-tracking (2015-16…2020-21) player-seasons are archetyped by **projecting onto the locked
GMM with the Edge (and pre-2021 RAPM) features neutralised to the scaler means** — a
reduced-feature assignment (`fit_archetypes.py --write`, flagged `edge_imputed=true`; segments
start 2015-16, so there are no archetypes before that). Because burst speed defines them, the
**Elite Speed Driver and Elite Offensive D clusters collapse** pre-tracking (63->8 and 40->2
primary assignments tracking vs historical); those players fall into their nearest non-burst
cluster. This is expected and visible, not silent.

## Career twins (`nhl_models.player_twins`)

Per current player at age A, the cosine-nearest k=5 players THROUGH age A (>= 2 seasons through
A), on a league-standardised age-aligned vector: cumulative points/82, goals/82, assists/82,
sequence-type shares, height, weight, F/D. Twins whose careers through A predate the 2021
tracking boundary carry `reduced_features=true` ("pre-tracking comparable" in the UI), since the
older side's sequence-share coverage differs. Each twin's subsequent-3-season points/82 is
attached. Validation: McDavid's twins through age 28 are MacKinnon, Crosby, Eichel, Backstrom,
Draisaitl — elite centres, all tagged reduced (their careers span the boundary).

## Physical overlay + burst-decline validation (`nhl_models.player_physical`)

Tracking-era burst rate (22+ mph bursts/60) and top speed by season. The blueprint's
early-warning flag is held to a validation bar: **does a player's year-over-year burst-rate
change predict his next-season points/82 change?** Result: correlation **r = 0.064** (p = 0.010,
n = 1,588) — statistically detectable but a negligible effect, below the 0.10 bar. **The flag is
therefore WITHHELD**: the overlay ships as a burst/speed trend with no early-warning flag, and
this negative result is published here (same discipline as the clutch permutation test). If a
future, larger tracking sample lifts the relationship above the bar, the flag turns on
automatically.

## Endpoints / surfaces

`GET /players/{id}/trajectory` returns the (archetype or fallback) curve band, the player's
points/82 path by age, twins + outcomes, and the physical overlay. PlayerProfile renders a
Career Trajectory section: the path over the curve band, the twins list with the pre-tracking
tag, and the skating-burst trend.
