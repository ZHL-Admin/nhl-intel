# Puck-loss (TURNOVER ledger) — blind sample of 10 charged turnovers (cold tape-review)

The final cold-review gate for the turnover ledger (the newest, now-integrated & deterministic ledger). Deterministically selected: goals the turnover ledger CHARGES (severity >= 0.2), ordered by md5(game_id-event_id), first 10 excluding every previously-surfaced goal (validation, holdout, pinned-rush, and the prior blind sample). NOT model-chosen. **No model attribution appears here.**

Rule each goal COLD: **was there a turnover, and by whom?** (a giveaway that directly/dangerously produced the goal). A goal may legitimately have no turnover. Return your 10 rulings, then the model's charged player + severity are revealed and graded.

| # | game_id | event_id | date | matchup (defending vs scored) | scorer | period | clock |
|---|---|---|---|---|---|---|---|
| 1 | 2023021038 | 987 | 2024-03-12 | ANA@CHI (ANA defending, CHI scored) | Tyler Johnson #90 | P3 | 09:54 |
| 2 | 2024020835 | 415 | 2025-02-02 | NJD@BUF (NJD defending, BUF scored) | JJ Peterka #77 | P1 | 04:10 |
| 3 | 2024020053 | 443 | 2024-10-15 | SEA@NSH (SEA defending, NSH scored) | Tommy Novak #82 | P1 | 03:00 |
| 4 | 2024020989 | 882 | 2025-03-06 | BUF@TBL (BUF defending, TBL scored) | Oliver Bjorkstrand #22 | P3 | 18:20 |
| 5 | 2024020119 | 704 | 2024-10-25 | NYI@NJD (NYI defending, NJD scored) | Jesper Bratt #63 | P3 | 01:29 |
| 6 | 2025021152 | 551 | 2026-03-28 | OTT@TBL (OTT defending, TBL scored) | Brandon Hagel #38 | P2 | 16:23 |
| 7 | 2023020547 | 698 | 2023-12-29 | NSH@DET (DET defending, NSH scored) | Filip Forsberg #9 | P2 | 06:11 |
| 8 | 2025030111 | 851 | 2026-04-19 | BOS@BUF (BUF defending, BOS scored) | Elias Lindholm #28 | P3 | 18:52 |
| 9 | 2023021066 | 673 | 2024-03-16 | MTL@CGY (CGY defending, MTL scored) | David Savard #58 | P2 | 01:35 |
| 10 | 2023020848 | 631 | 2024-02-15 | DET@VAN (VAN defending, DET scored) | J.T. Compher #37 | P2 | 05:35 |

## STOP — cold owner review. Return your 10 turnover rulings before the model's answers are revealed.
