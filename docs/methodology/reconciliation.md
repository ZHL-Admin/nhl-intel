# Eye-test reconciliation (Phase 4.3)

Four pieces that contrast what the numbers say with how a player is used/perceived
(blueprint 4.4). All windows mirror the composite: recent single seasons + a 3-season window.

## Clutch — leverage-weighted production (`nhl_models.player_clutch`)

`int_event_leverage` joins every unblocked shot to the win-probability **leverage** at its
timestamp (win_probability is ~10s-sampled; both sides are bucketed to a global 10s grid).
`compute_clutch.py` re-weights each of a player's shots by `leverage / his mean leverage`:

- `clutch_ixg = sum(xg·leverage)/mean(leverage)`, `clutch_delta = clutch_ixg − raw_ixg`.
- A **permutation test** (1000 shuffles of leverage across the player's own shots) gives a
  two-sided p-value; the API renders it as a confidence phrase, never a bare p at depth 1.

Leverage exists for 2015-16+ only. Validation: the p-value distribution is ~uniform with a
mild excess of small p's (real signal); top clutch names (Toffoli, Eriksson Ek, Matthews)
pass the smell test.

## Consistency (`nhl_models.player_consistency`)

`mart_player_game_score` is a single-game game score per player (public game-score family;
weights in dbt vars `gs_*`). `compute_consistency.py` summarises the season distribution:
mean, sd, IQR, the share of **good games** (above the league 60th percentile) and **no-shows**
(below the 25th), and a consistency index = the percentile of mean/sd within position. The API
returns the full game-score series for a strip plot. Elite scorers (MacKinnon, Matthews,
Kucherov) are both high-mean and high-consistency.

## Coach trust (`nhl_models.player_coach_trust`)

Deployment signals from the shift/segment layer, z-scored within position and weighted
(config.COACH_TRUST_WEIGHTS): penalty-kill TOI share, **defensive-zone faceoff deployment**,
last-2-minutes-protecting-a-lead TOI rate, and road-vs-home TOI per game (matchup-proof usage).

The DZ-faceoff signal is the share of a player's on-ice faceoffs that are his team's
**defensive-zone** draws. pbp `zone_code` is *owner-relative* (D = the faceoff winner's
defensive zone), so a player is taking a d-zone draw when his team won the draw and
`zone_code='D'`, or lost it and `zone_code='O'`; on-ice skaters come from `int_on_ice_events`.
(An earlier note claimed this was blocked by zone-code symmetry — that was wrong: the symmetry
of the faceoff *outcome* is irrelevant to *which players the coach sends out* for the draw.)
**Post-icing** draws (the iced team stuck defending) remain a future refinement. The
most-trusted forwards are classic defensive specialists with high DZ-draw / PK shares
(Glendening, Stenlund, Jake Evans).

## Divergence board (`nhl_models.divergence_board`)

Standardise coach-trust and composite total within position; `divergence = trust_z −
composite_z`. The board is the top/bottom 15 by |divergence| (min 500 5v5 minutes). Each row
gets a deterministic explanation from `insight_engine/templates/divergence.py` (reused by the
Phase 6 insight engine) that references the player's dominant trust signal and his
strongest/weakest composite component — every number in the sentence is present in the row.
Validation: "trusted beyond value" is led by deployment-heavy, model-disliked players
(Lindgren, Glendening, Goodrow, Brandon Carlo, Ben Chiarot); "value beyond deployment" by
offensive stars not used in defensive roles (MacKinnon, Quinn Hughes, Panarin).

**The board's value is asymmetric.** The "trusted beyond value" side is the eye-test-vs-
analytics signal; the reverse side is largely mechanical (trust is defense-weighted, so any
high-composite offensive star sits there) and says little a user doesn't already know. The
Players-index UI leads with the trusted side and tucks the reverse side into a secondary,
collapsed list.

## Endpoints

`GET /players/{id}/reconciliation` (clutch + consistency + coach trust + the game-score
series) and `GET /players/divergence-board`. PlayerProfile renders a Reconciliation section
(clutch panel with confidence phrase, consistency strip plot, trust); the Players index has a
Divergence Board tab.
