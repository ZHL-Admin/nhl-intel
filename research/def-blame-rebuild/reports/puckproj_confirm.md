# Puck-Path Projector §9 — read-only match-set-size by zone (distinct goals, leave-one-goal-out)

Library: 22,728 5v5 goal paths, 1,896,518 moving puck-frames (recent-motion over 0.3s). PROVISIONAL knobs: radius **6 ft**, heading tol **±45°**, speed floor **5 ft/s** (real knobs are held-out-tuned later). Each live state matched against ALL OTHER goals (leave-one-out); a goal counts ONCE (distinct-goal collapse). Question: how many distinct goals match a typical live state per zone.

| decision zone | moving frames (pool) | distinct-goal matches p10/p25/**med**/p75/p90 | % states <5 | % <10 | % ≥30 |
|---|---|---|---|---|---|---|
| blue_line_entry | 51,366 | 920/1257/**1536**/1900/2170 | 0% | 0% | 100% |
| right_point | 63,998 | 1644/2002/**2299**/2576/2849 | 0% | 0% | 100% |
| half_wall_R | 91,243 | 1334/1808/**2746**/3282/3531 | 0% | 0% | 100% |
| below_goal_line | 108,844 | 1237/2047/**2444**/2707/2899 | 0% | 0% | 100% |
| near_net_slot | 87,979 | 1951/2571/**4762**/6706/7773 | 0% | 0% | 100% |

## Read
- A zone whose typical live state matches only a HANDFUL of distinct goals (median <~10, or a large %<5) is too SPARSE to project sharply there, no matter how rich the generic o-zone looks — the projector would be estimating a continuation distribution from a few goals. A zone matching many tens is well-powered. This sizes where (if anywhere) the projection can even be posed.
- Provisional knobs only; tighter radius/heading (the real held-out-tuned values) will REDUCE these counts, so treat these as an UPPER bound on match richness.

## STOP — read-only power confirm. No projector, no sharpness, no modes.
