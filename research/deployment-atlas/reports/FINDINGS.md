# Deployment Atlas — Findings

## What we built
A from-scratch reconstruction of **who was on the ice for every second of every NHL
game, 2010-11 → 2025-26** (≈19,150 games), and everything that hangs off it: a
clean stint table (personnel + score constant), per-player 5v5 on-ice rates, a
context-corrected player rating (RAPM), quality-of-competition/teammates and other
deployment context, and coach fingerprints. Along the way we found the NHL's shift
feed had silently gone empty for 563 recent games, recovered them from the HTML
reports (validated byte-for-byte), and backfilled them into production.

## What validated
- **Context correction travels.** Predicting a traded player's *next*-season on-ice
  xG share, our context-corrected rating beats the raw prior-season share by
  **+3.70% mean-absolute-error, with a clean confidence interval [+2.0%, +5.4%]**.
- **Clean inputs matter.** Our RAPM beats the production RAPM out-of-sample by
  **+1.94% (CI excludes zero)** — the same model, just fit on deduplicated,
  backfilled, goal-cut data instead of the stale/contaminated segments.
- **Bench shortening is real and universal:** all **32/32** coaches lean harder on
  their top-6 forwards in close third periods.
- The xG model, stint reconstruction, and 5v5 shares all pass their integrity and
  face-validity checks; the recovered games are as clean as native ones.

## What fell short or failed
- **The +3.70% improvement is under our pre-registered 5% ship bar.** The signal is
  real but modest.
- **Destination context did not help.** Adding the new team's fingerprint and the
  player's predicted role made mover predictions slightly *worse* (−1.6%).
- **The "last change" advantage did not appear** in the data — neither a coarse nor
  a refined matchup-targeting metric showed home coaches concentrating their
  checkers on top lines (34–43% of teams positive; the refined metric was
  significantly *reversed*). Reported as an honest null about matching in the modern game.

## The decision (pre-registered, INVESTIGATE)
Because the best clean adjusted predictor beat raw by 0–5% (not ≥5%), the rule
returns **INVESTIGATE**: **the Atlas ships as descriptive data; the adjusted-rating
portability claim is held.** The variant RAPM is our *internal* research rating (no
public "this rating travels" claim). Reviving the portability claim requires a **new
pre-registration** — new cohorts/targets, decided before results are seen.

## Five most surprising player-level findings (2024-25, 5v5)
1. **Sam Reinhart is the league's #1 *defensive* forward by isolated impact** (+0.40)
   with **~zero individual offense** — despite a 59% on-ice xG share. The model
   attributes his line's results to defense and teammates, not his own shooting.
2. **The best players have the best teammates:** Connor McDavid has the **highest
   quality-of-teammates in the league** — even his dominance is partly the
   Draisaitl/Hyman effect, which the context layer surfaces.
3. **Genuine two-way stars are rare:** only Adam Fox and Barrett Hayton land in the
   top-15 offense *and* carry clearly positive defense.
4. **Carolina's Staal–Martinook shutdown pair inflate each other** — mutually among
   the highest QoT, a checking unit that never leaves each other's side.
5. **Context-riders exist and the model catches them:** Reinhart, Schmidt, Podkolzin
   all post 58%+ on-ice xG shares with near-zero individual RAPM — exactly the
   teammate/deployment inflation adjustment is meant to strip out.

## Upstream ledger — final state
1. **Stats shiftcharts feed empty → HTML fallback:** *shipped, pending first nightly*
   (Workstream A: parser + DAG fallback + monitor).
2. **Stale, dup-contaminated segment backbone:** *open* — dbt fix (dedup + rebuild
   post-backfill + goal cut-points); the Atlas works around it in the research layer.
3. **`2013021108` missing pbp:** *open* — one-line ingestion fetch.
4. **Stints for the 2 gap-fetched games:** *open* — negligible (2 of 19,150 games).

## Open questions for a future round
- **The System Tax.** Both the raw and the adjusted models miss the *same* traded
  players — the residual is destination-and-role variance neither rating carries.
  How much of a player's on-ice result is the system he's in versus the player? That
  residual is the real prize, and neither prior-season signal captures it.
- **The noise ceiling.** Is +3.70% close to the intrinsic predictability limit for
  one-season-ahead mover xG share? A power/noise-floor analysis would tell us whether
  the 5% bar is even reachable, or whether we're bumping the ceiling.
- **Ensembles and multi-target.** Combine raw + RAPM + context in one model; predict
  several targets jointly (xG, goals, WAR); widen the mover cohort (lower the minutes
  bar, or use multi-season windows) to shrink the CI — all candidates for the next
  pre-registered attempt.

---
*This report is frozen. Follow-on and cross-project findings (incl. the System Effects project,
which answers "The System Tax" above) live in the growing program ledger:
[`research/PROGRAM-FINDINGS.md`](../../PROGRAM-FINDINGS.md).*
