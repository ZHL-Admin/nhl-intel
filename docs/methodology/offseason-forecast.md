# Offseason Roster Forecast

Predict how good a team will be next season from the moves it has made this offseason, and explain
why in plain language with honest uncertainty. This is the blueprint's "every sustainability call is
a testable prediction" principle applied to a whole roster, and the section 6.4 trade/free-agency
fit engine pointed at an entire offseason rather than one player.

> STATUS: STEP 0 (roster data source) resolved and recorded below. The method, constants,
> backtest, and limitations sections are filled in as the build proceeds.

---

## STEP 0 — Resolved roster data source (recorded before any model code)

The forecast needs two roster snapshots per team and a clean player→team join for each. The
offseason has no games, so a purely game-derived roster cannot reflect signings and trades; the
repo already ingests a LIVE roster feed (built earlier — see SESSION-STATE.md "LIVE ROSTER
MEMBERSHIP" and scripts/ROSTER_FINDINGS.md), which is the current-membership source we use.

### Robust roster at a season BOUNDARY (offseason-only by construction)
This is an OFFSEASON tool, so it compares the prior season's END roster to the next season's
OPENING-night roster — only between-season moves count, never mid-season trades.
`robust_roster_membership(season, boundary)`:

```
a player is on the roster of his {boundary} team that season
  boundary='end'  -> team in his LATEST game of the season   (season-end roster, the BASE)
  boundary='open' -> team in his EARLIEST game of the season  (opening-night roster, the UPDATED)
  IF he played >= MIN_GAMES_ROSTER (10) games that season  (filters cup-of-coffee call-ups)
over stg_rosters, season = S, substr(game_id,5,2) in ('01','02','03')   -- exclude intl games
```

A mid-season trade therefore does NOT show up as a move: a player traded at the deadline was on his
old club at that season's END and on his new club at the next season's OPENING, so he is "returning"
for the club he actually changed teams *within* the season (e.g. Berggren, traded DET→STL at the
2025-26 deadline, returns for DET — he opened 2025-26 there). Only a true between-season signing,
trade, or departure changes a player's boundary team.

Why neither naive source works (measured on Detroit, 2025-26): the NHL's official 21-man published
roster (`stg_roster_current`) is too NARROW — it drops regulars later sent to the AHL (Sandin-Pellikka
70 GP, Söderblom 41 GP). The raw game-derived "anyone who dressed" list is too BROAD — it adds 1-2
game call-ups (Cossa 1 GP, Postava 2 GP). A games floor on the game-derived list, with team assigned
at the season boundary (end vs opening, above), is the honest middle ground. The one remaining blind
spot is a player injured almost an entire season; `MIN_GAMES_ROSTER` is the single tunable, and an
official full-season roster source (per-season `/roster/{TEAM}/{season8}`) is the documented future
upgrade to cover it.

### Forward-looking transition (the UPCOMING offseason)
The live view always targets the upcoming offseason: BASE = latest completed season's END roster
(robust, game-derived), UPDATED = the CURRENT roster from the live published feed
(`offseason_updated_membership`). Today that is `2025-26 -> 2026-27`.

The live feed is refreshed daily and reflects offseason signings and trades AS THEY HAPPEN, even
while it is still labelled the prior season (NHL rolls the season label later) — so we read team
membership from it directly rather than gating on its label. Each player's UPDATED team is his live
team if he is on a published roster, else his base-season END team (a fallback so AHL/unsigned
holdovers do not falsely depart); the universe is (live ∪ base), which excludes stale fallback-only
players. A player only counts as moved when actively on a different club's live roster. The ledger
therefore grows through the summer as moves land; before the first move a team reads "no moves logged
yet", and no-move teams skip the line-fit/style overlays so they are cheap to compute.

The `--backtest` path is the only one that targets a COMPLETED offseason — `2024-25 END -> 2025-26
OPENING` — purely to measure calibration against what actually happened.

Value/rating/aging inputs are keyed to the BASE season. Join key: `player_id` (int64) → `team_id`
(int64); abbrev↔id via `stg_games` (staging).

### Membership ≠ performance (carried into every forecast number)
Affiliation is the team LABEL only. A just-arrived player has ZERO games with his new club, so all
his value inputs (GAR/RAPM/archetype/aging) come from his OLD team's usage. The forecast projects his
prior value forward; it does not invent new-team production. Stated in the verdict's limitations footer.

### Move classification is ROSTER-based, not lineup-based
`move_type` keys on whether the player is on the base/updated ROSTER, not whether he holds a top-N
LINEUP slot — so a holdover merely promoted or demoted in the lineup reads as `returning`, and only a
genuine join/leave reads as `arrival`/`departure`. (The per-player `delta_contribution` stays
lineup-based and still partitions the net rating delta.)

---

## The method

A "transition" is generic: `latest_completed_season -> next_season`. The same path serves the live
view (base = latest completed season) and the 2024-25 -> 2025-26 backtest (base = 2024-25). All
constants live in `config.ROSTER_FORECAST`; `GOALS_PER_WIN` is asserted equal to `GAR_CONFIG` at
import so a WAR delta and the team rating share one goals scale.

1. **Base.** The team's last `team_ratings` row of the base season (`total_rating` + the four
   weighted components `play_5v5` / `finishing` / `goaltending` / `special_teams`) and its
   season-end roster (the BASE join above).

2. **Diff.** Updated roster minus base roster, each player classified `arrival` / `departure` /
   `returning`. Prior value comes from `player_gar` (skaters) or `goalie_gar` (goalies) at the
   value window resolved by `value_season_window()` (the stable 3-yr window when it ends at the base
   season, else the single-season row — leak-free for the backtest). A player with no GAR row is
   `no_track_record`: replacement level + a deliberately wide band (`NO_TRACK_RECORD_WAR_SD = 1.2`).
   Never a fabricated value.

3. **Project each player forward one season (value).** Skater: regress toward the repeatable lens,
   then age. **Reliability shrink** — each `player_gar` component is shrunk toward its position mean
   by its MEASURED year-over-year reliability (`config.GAR_STABILITY_YOY`, referenced not re-derived:
   production `r=0.66`, RAPM isolated rate `r=0.38`, finishing residual `r=0.35`). Finishing luck is
   isolated as `(goals - ixg)` — both columns are in `player_gar` — and shrunk hardest toward 0; the
   sustainable production, PP, EV-defense and PK terms shrink by their r toward the pos mean; the
   tiny penalty/faceoff terms pass through. **Aging-as-value-multiplier (approximation, stated
   loudly):** `aging_curves.curve_value` is points/82 (production-shaped); we scale a VALUE (WAR)
   number by the curve's age-t -> age-(t+1) LEVEL ratio, clamped to
   `[AGE_MULT_FLOOR=0.80, AGE_MULT_CEIL=1.08]`, with the All Forwards / All Defensemen fallback. We
   are scaling a value by a production slope — a documented approximation, not an identity.
   **Goalies:** the reliability shrinkage already inside `goalie_gar` (its `RELIABILITY_K`) IS the
   honest point estimate, so we carry its point + band straight through. The goalie band is ~3x a
   skater's by design (the measured goalie-rate reliability is ~0.19), which is why goalie value
   never reads as confident.

4. **Project the lineup at the slot level.** Not "all arrivals minus all departures" — a team ices a
   fixed lineup (`N_FWD=12`, `N_DEF=6`, `N_GOALIE=1`). Take the best players by projected WAR per
   position; any unfilled or vacated slot is filled at `REPLACEMENT_WAR` (0.0 — WAR is above
   replacement by definition; the slot still EXISTS, a departure is never a free hole and never a
   dropped slot). **Both** the base and updated lineups are built and summed by projected WAR, so a
   returning player cancels (his aging shows in the per-player ledger, not twice in the team delta)
   and a no-move roster nets to exactly zero. `net_delta_war = Σ updated slots − Σ base slots`, and
   the per-player `delta_contribution` partitions it exactly (the consistency discipline, unit-tested).

5. **Chemistry + style overlay.** For the projected top two forward trios and top defense pair,
   `score_line` gives each unit's projected xGF share; the updated-minus-base mean share delta becomes
   a BOUNDED goals/game nudge (`CHEMISTRY_XGF_TO_GOALS=0.30`, capped at `CHEMISTRY_ADJ_CAP=0.06`). If
   line-fit is unavailable for any unit the nudge is 0, never fabricated. `score_team_fit`'s style
   dimension adds a one-line read of whether the biggest arrival matches the team's identity.

6. **Projected rating + band + rank.** `projected_rating = base_rating + net_delta_war ×
   GOALS_PER_WIN / GAMES_PER_SEASON + chemistry_adj`; ranked 1..N by projected rating. The **band**
   propagates the per-slot `war_sd` in quadrature, then ADDS terms for the value share from
   no-track-record players (`BAND_NO_TRACK_W`), from goalies (`BAND_GOALIE_W`), and from turnover
   (`BAND_TURNOVER_W`), over a floor (`BAND_FLOOR`). **Negligible-moves guard:** when
   `|net_delta_war| <= NEGLIGIBLE_NET_WAR (0.5)` and moves `<= NEGLIGIBLE_MOVES (2)`, the verdict
   says "no material moves yet" rather than asserting a confident near-zero forecast.

## Limitations (verbatim in every verdict)

The projection moves only the team LABEL of value from the roster's moves; the band excludes salary
cap, injuries, training-camp job battles, a coaching change, and prospect development — the model
cannot see them. A just-arrived player's value still reflects his old-team usage until he plays for
his new club.

## Backtest calibration (validation that matters today)

Project the 2024-25 final rosters forward to 2025-26 (`--backtest`: base = 2024-25 end-of-season
`team_ratings`; updated = actual 2025-26 rosters), then compare each team's projected 2025-26 rank
delta to its actual 2025-26 power-rating rank delta. The verdict language inherits this calibration
as a prior, not a guarantee.

**Measured calibration (`make roster-forecast-validate`, 2024-25 -> 2025-26, 31 teams):**

- Spearman rank-delta correlation: **0.60**
- Mean absolute rank-delta error: **6.7 positions**

Read honestly: the offseason moves explain a MODERATE share of next-season rank movement — they get
the direction right more often than not — but roughly half the variance is the cap/injury/coaching/
camp/prospect reality the model cannot see (which is exactly why the band is wide and the verdict
foregrounds it). It is a directional prior, not a precise rank prediction. (One team is dropped from
the 32 when a franchise id is not present in both seasons' `team_ratings`, e.g. a relocation.)

