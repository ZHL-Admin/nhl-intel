# TAPE SPOT-CHECK — proactive-defensive detectors (what they fire on; owner judges real vs phantom)

NO stability re-run, NO conclusion — this is the pre-trust tape check. Net is at DEPTH 0 (the defended goal line); depth = distance from that net; a defender is GOAL-SIDE if his depth < the puck's depth.

## Measurement scope (confirmed)

- Detectors measure each defender across **ALL goals-against he was on the ice for** (avg 1.8 D/goal = every on-ice D, NOT only the culprit) — correct, he is usually doing normal defense. No failure-bias.

## Per-player EXPOSURE (the F29 sample lesson)

- Median per qualifying D-season (~47 on-ice goals): **SHOT-BLOCK fires ~1×**, **TAKEAWAY fires ~6×**. The continuous actions (step-up / net-front / man-stability) have a value on every on-ice goal (~47). **A stability split-half on a ~1-fire/season detector (shot-block) is a sample-size artifact, not a trait measurement** — flagged before any stability read is believed.

## SHOT-BLOCK
**Rule:** fires on a frame where a DEFENDER is coupled to the puck, the puck ARRIVED fast (max speed over the prior 3 frames > 30 ft/s), AND the defender is GOAL-SIDE of the puck (closer to the defended net than the puck is).

| game-event | player | moment | player dist-from-net | puck dist-from-net (goal-side?) | puck lateral | puck speed (arriving) | after-speed | dir_cos |
|---|---|---|---|---|---|---|---|---|
| 2024020262-856 | Mason Lohrei #6 | 0.4s before goal | 12 ft | 14 ft (YES) | -5 ft | 59 ft/s | 15 ft/s | +0.99 |
| 2023020668-252 | Nicolas Hague #14 | 4.7s before goal | 23 ft | 24 ft (YES) | -14 ft | 50 ft/s | 8 ft/s | +0.96 |
| 2023020510-525 | Ben Chiarot #8 | 6.3s before goal | 65 ft | 66 ft (YES) | 32 ft | 32 ft/s | 17 ft/s | +0.99 |
| 2025020486-783 | Ivan Provorov #9 | 3.7s before goal | 4 ft | 6 ft (YES) | 4 ft | 93 ft/s | 12 ft/s | +0.79 |
| 2024021197-551 | Mason Lohrei #6 | 2.6s before goal | 6 ft | 7 ft (YES) | -3 ft | 77 ft/s | 10 ft/s | +0.99 |
| 2025020341-1005 | Jakob Chychrun #6 | 1.0s before goal | 3 ft | 4 ft (YES) | -1 ft | 109 ft/s | 6 ft/s | +0.07 |

*Judge: is the player between the puck and the net (goal-side YES), was the puck fast arriving and then slowed/reversed (after-speed << arriving, dir_cos low/negative) — a real block — or is he merely near a fast puck?*

**Patterns I flag for your judgment (NOT a conclusion):** (a) BEFORE the is_def filter this rule fired on 3/6 GOALIES making saves (fast shots) — the geometric condition alone is not action-specific. (b) Even D-only, most fires show **dir_cos ≈ +0.99 = the puck CONTINUED past the defender (did not deflect/reverse off him)** — a defender near a passing puck, not a block; only the dir_cos≈0 case (Chychrun 3 ft, redirect) reads as a real deflection. (c) No near-net gate — a fire at 65 ft (Chiarot, point area) is included. The rule lacks a REVERSAL/DEFLECTION requirement and a near-net restriction; it appears to be a loose proxy.

## TAKEAWAY (puck-win)
**Rule:** fires when a DEFENDER is tightly coupled to the puck (within ~5 ft, rel-speed < 8) and moving WITH it (dir_cos > 0) for >= 3 consecutive frames — i.e. he has genuine control of the puck.

| game-event | player | moment | frames of control | player dist-from-net | puck dist-from-net | puck lateral | puck speed | dir_cos |
|---|---|---|---|---|---|---|---|---|
| 2025020672-561 | Niko Mikkola #77 | 6.3s before goal | 15 fr (1.5s) | 0 ft | 0 ft | -36 ft | 8 ft/s | +0.99 |
| 2023020755-698 | K'Andre Miller #79 | 6.8s before goal | 3 fr (0.3s) | 104 ft | 104 ft | 40 ft | 5 ft/s | +0.86 |
| 2024020873-168 | Seth Jones #4 | 4.7s before goal | 9 fr (0.9s) | 113 ft | 114 ft | -24 ft | 16 ft/s | +0.95 |
| 2025020331-396 | Mattias Samuelsson #23 | 0.8s before goal | 4 fr (0.4s) | 6 ft | 7 ft | -4 ft | 2 ft/s | +0.79 |
| 2024020597-836 | Dylan Coghlan #52 | 9.6s before goal | 7 fr (0.7s) | 6 ft | 4 ft | -1 ft | 9 ft/s | +0.99 |
| 2024020051-935 | Damon Severson #78 | 6.8s before goal | 7 fr (0.7s) | 0 ft | -4 ft | -30 ft | 4 ft/s | +0.81 |

*Judge: did the defender genuinely control the puck (>=3 frames, moving with it, tight) — a real takeaway/possession — or a fleeting touch?*

**Patterns I flag for your judgment (NOT a conclusion):** the fires are mostly (a) net-area RETRIEVALS / breakouts (Mikkola/Severson/Coghlan/Samuelsson at 0-6 ft, controlling the puck out of their own end) and (b) NEUTRAL-ZONE carries (Miller 104 ft, Jones 113 ft). These are the defending team simply HAVING the puck — the rule has **no attacker-loss requirement** (it does not check the puck was the ATTACKER's the instant before), so it reads as a generic 'defensive possession' detector, NOT a takeaway (actively winning the puck from the attacker). To be a takeaway it would need an A→D coupling transition.

## STEP-UP / NET-FRONT / MAN-STABILITY (continuous — no discrete fire)

These are per-goal geometric VALUES, not events. STEP-UP = min dist-to-puck + depth-at-that-moment; NET-FRONT = fraction of possession within 15 ft of net; MAN-STABILITY = largest single-attacker share of nearest-man frames. Because they have a value on EVERY on-ice goal, their exposure is adequate — but they are proxies (a low dist-to-puck may be a chosen step-up OR incidental drift; the owner should judge whether the proxy captures the hockey action). Worked geometric examples deferred to the discrete detectors above, which are the phantom-prone ones; the continuous proxies are flagged as PROXIES not verified action-detectors.

## STOP — owner judges whether the detectors fire on real actions. No stability re-run, no conclusion.
