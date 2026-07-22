# Targeted blind sample B — rush-guard cold test

On each goal below the model would have fired FAILURE-TO-ACCOUNT, but the RUSH-GUARD suppressed it — it read a fresh rush (zone entry within 4s of the goal) and treated the open scorer as unsettled transition, not a coverage-account failure. Deterministic (md5 order within the suppressed set), excluding every surfaced goal. **No model output.**

Rule each COLD: is this a **genuine rush / transition** (the guard correctly suppressed — the open man is the rush, not an abandoned assignment), or a **settled play** the guard WRONGLY suppressed (a real coverage abandonment the model now misses = an FTA false-negative)?

| # | game_id | event_id | date | matchup (defending vs scored) | scorer | period | clock |
|---|---|---|---|---|---|---|---|
| 1 | 2024020809 | 498 | 2025-01-29 | PHI@NJD (PHI defending, NJD scored) | Luke Hughes #43 | P2 | 13:33 |
| 2 | 2023021286 | 719 | 2024-04-14 | ARI@CGY (CGY defending, ARI scored) | Josh Doan #91 | P2 | 03:43 |
| 3 | 2025020010 | 422 | 2025-10-09 | MTL@DET (DET defending, MTL scored) | Mike Matheson #8 | P1 | 00:07 |
| 4 | 2025020079 | 665 | 2025-10-18 | SEA@TOR (TOR defending, SEA scored) | Jani Nyman #38 | P2 | 05:41 |
| 5 | 2023020882 | 474 | 2024-02-20 | NSH@VGK (VGK defending, NSH scored) | Cody Glass #8 | P1 | 00:52 |
| 6 | 2023020002 | 1117 | 2023-10-10 | CHI@PIT (PIT defending, CHI scored) | Jason Dickinson #16 | P3 | 04:31 |

## STOP — cold review. Return your rush-guard rulings before the model's answers are revealed.
