# Defensive-Scheme Matcher §10 — read-only confirms (port-verify + qualifying count + discriminating exposure)

## (c) Port verification (the easy-to-break things)

- **L/R mirror:** man @ right-corner puck (37,9) → RD expected (37.0,9.0); distance to PUCK = **0.0 ft** (should be small — RD covers the puck, the mirror of LD-on-PUCK at the left corner). PASS
- **Pressure sign:** swarm @ slot (0,19), role C — resting (0.0,19.0) dist-to-puck 0.0 → pressured (0.0,19.0) dist-to-puck 0.0. Pull is TOWARD the puck: PASS
- **Anchor dominance** (resting center at each ANCHOR_PUCK ≈ that anchor's assigned landmark):
    - man @ cornerL(-37, 9): max role error **0.1 ft**, mean 0.0 (PASS)
    - man @ halfWallL(-38, 22): max role error **0.1 ft**, mean 0.0 (PASS)
    - man @ pointL(-20, 60): max role error **0.0 ft**, mean 0.0 (PASS)
    - man @ behindNet(0, -5): max role error **0.2 ft**, mean 0.1 (PASS)
    - man @ slot(0, 19): max role error **0.1 ft**, mean 0.1 (PASS)

## Divergence by puck location (grounds discriminating vs overlap)

- L half-wall: **122** ft cross-scheme spread
- R half-wall: **122** ft cross-scheme spread
- L corner: **122** ft cross-scheme spread
- R corner: **122** ft cross-scheme spread
- R point: **67** ft cross-scheme spread
- L point: **67** ft cross-scheme spread
- Slot: **52** ft cross-scheme spread
- Behind net: **22** ft cross-scheme spread

Discriminating threshold (data-derived) = midpoint of overlap (37) and divergent (122) = **79 ft**.

## (a) Qualifying-goal count

- 5v5 tracked goals: **22,773** · puck in D-zone (depth ∈ [-13,64]) for the ENTIRE buildup: **11,408** (50.1%)

## (b) Discriminating-exposure distribution (over qualifying goals)

- fraction of a goal's frames that are DISCRIMINATING (divergence > 79 ft): median **50%**, p25 35%, p75 64%, p90 77%
- goals with ≥15% discriminating frames (matchable): **10,737** (94%)
- goals with ≥30% discriminating frames (matchable): **9,321** (82%)
- goals with ≥50% discriminating frames (matchable): **5,743** (50%)
- goals with <15% discriminating frames (net-front/slot overlap → forced-AMBIGUOUS regardless): **671** (6%)

## Read
- (a) sizes the strict-scope corpus; (b) sizes how many of those even HAVE enough corner/half-wall/point puck-time to distinguish schemes (the rest are forced-ambiguous in the behind-net/slot overlap, per §4). Together they bound where the matcher can say anything at all. (c) confirms the port is faithful before building.

## STOP — read-only confirms. No matcher, no role assignment, no confidence.
