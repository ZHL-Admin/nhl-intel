# Rush-defense — PINNED 10-goal set · BUCKET-based (read-only; nothing charged/aggregated)

The 10 (game, event) pairs are LOCKED to `rushdef_pinned.csv` and do not move between runs. Rush-defense is now assessed as a coarse disadvantage BUCKET (not an exact odd-man count), because the exact integer proved unmeasurable (shot-frame too late, entry-frame too early) and unnecessary. The bar is BUCKET agreement with your tape, not exact-integer agreement.

**The four questions** — Q1 is it a rush? · Q2 turnover-caused? · Q3 which disadvantage bucket? · Q4 flat rush discount. **Buckets:** EVEN/DEF-HAS-NUMBERS (gap<=0) ceiling 1.0 · SLIGHTLY (gap==1) ceiling 0.5 · BADLY/BREAKAWAY (gap>=2 or 0 D back) ceiling 0.1. **Q4 discount = x0.85** on every rush. **Q2 turnover discount = x0.25.** Contest gate + forward x0.65 preserved.

## Q3 bucket vs owner tape (the comparison)

| # | game-event | scorer | model count (nd v na @ threat) | model BUCKET | owner tape bucket | agree? | Q2 turnover? | charge |
|---|---|---|---|---|---|---|---|---|
| 1 | 2025020505-552 | Anton Lundell #15 | 2 v 2 | EVEN | SLIGHTLY | no | no | NULL (contested-beaten) |
| 2 | 2024020410-300 | Dylan Cozens #24 | 2 v 2 | EVEN | EVEN | YES | no | NULL (contested-beaten) |
| 3 | 2023020356-189 | Jamie Benn #14 | 0 v 1 | BADLY | SLIGHTLY | no | no | 0.09 |
| 4 | 2023020735-676 | Yegor Sharangovich #17 | 0 v 0 | EVEN | EVEN | YES | no | 0.85 |
| 5 | 2023020031-1002 | Mason McTavish #23 | 1 v 1 | EVEN | BOUNDARY | boundary (Q1 below) | no | NULL (contested-beaten) |
| 6 | 2025021228-515 | Robert Thomas #18 | 2 v 3 | SLIGHTLY | SLIGHTLY | YES | no | 0.42 |
| 7 | 2024021044-895 | Connor Dewar #24 | 5 v 3 | EVEN | EVEN | YES | no | 0.55 |
| 8 | 2023020317-91 | Jake Neighbours #63 | 0 v 1 | BADLY | pending | pending | no | NULL (contested-beaten) |
| 9 | 2024020433-397 | Bryan Rust #17 | 1 v 1 | EVEN | pending | pending | no | 0.55 |
| 10 | 2024020487-251 | Dylan Guenther #11 | 2 v 1 | EVEN | pending | pending | no | 0.55 |

**Resolved bucket agreement: 4/6** (McTavish is a Q1 boundary, goals 8-10 pending your tape).

## Per-goal detail (Q1 rush/settled · Q2 · responsible defender · contest gate)

| # | scorer | Q1 | pre-set? | Q2 turnover | responsible defender | contest | ceiling | charge |
|---|---|---|---|---|---|---|---|---|
| 1 | Anton Lundell #15 | RUSH | yes | no | Sam Steel #18 (F x0.65) | CONTESTED->null | 1.0 | NULL |
| 2 | Dylan Cozens #24 | RUSH | yes | no | Ville Heinola #None | CONTESTED->null | 1.0 | NULL |
| 3 | Jamie Benn #14 | RUSH | no | no | Nick Perbix #48 | failed to close | 0.1 | 0.09 |
| 4 | Yegor Sharangovich #17 | RUSH | yes | no | Justin Faulk #72 | failed to close | 1.0 | 0.85 |
| 5 | Mason McTavish #23 | RUSH | yes | no | Brayden Pachal #94 | CONTESTED->null | 1.0 | NULL |
| 6 | Robert Thomas #18 | RUSH | yes | no | Devon Toews #7 | failed to close | 0.5 | 0.42 |
| 7 | Connor Dewar #24 | RUSH | yes | no | 8475181 #? (F x0.65) | failed to close | 1.0 | 0.55 |
| 8 | Jake Neighbours #63 | RUSH | no | no | Kevin Korchinski #14 | CONTESTED->null | 0.1 | NULL |
| 9 | Bryan Rust #17 | RUSH | yes | no | Auston Matthews #34 (F x0.65) | failed to close | 1.0 | 0.55 |
| 10 | Dylan Guenther #11 | RUSH | yes | no | Alexander Wennberg #21 (F x0.65) | failed to close | 1.0 | 0.55 |

## Reading the disagreements (honest)

- **Lundell (2025020505):** model 2v2 -> EVEN, tape SLIGHTLY. **Cozens (2024020410) also measures 2v2 and tape is EVEN.** Same count, different tape bucket — a one-body ambiguity no count can resolve; this is precisely why we bucket instead of charging the exact integer. It straddles the softest boundary (1.0 vs 0.5 ceiling).

- **Benn (2023020356):** owner tape SLIGHTLY + turnover-caused. The coupling turnover detector does NOT flag it (Q2=no — the mishandle wasn't a sustained coupled possession), so primary blame is not routed to a giveaway. The model still charges ~0 because it reads the threat as a breakaway (0 defenders goal-side -> BADLY, ceiling 0.1): the right charge for the wrong reason. Flagged as a Q2 detector miss.

- **McTavish (2023020031):** Q1 classifies RUSH (rush-origin entry within 4s). Per the spec a rush the defense merely failed to set up for is still a RUSH; only a genuinely pre-set defense is SETTLED. pre_set diagnostic at entry = yes. Reported as RUSH; your call on the boundary.

## STOP — owner review of the bucket comparison. Nothing integrated, nothing aggregated.
