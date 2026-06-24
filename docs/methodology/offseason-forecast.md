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

### BASE roster — prior season-end membership (game-derived, accurate for a completed season)
Source: `nhl_staging.stg_rosters` (one row per game per player, from `raw_play_by_play.rosterSpots`).
For a *completed* season the last game a player dressed defines his season-end team, so:

```
season-end team for season S =
  argmax_by(game_id) over stg_rosters
  where season = S
    and substr(cast(game_id as string), 5, 2) in ('01','02','03')   -- exclude intl pollution
  partition by player_id  ->  take the row with the latest game_id  ->  team_id
```

Join keys: `player_id` (int64), `team_id` (int64), `season` (STRING "YYYY-YY"). The `01/02/03`
filter is mandatory (the international-team pollution that bit Phase 5).

### UPDATED roster — current membership (live feed; reflects offseason moves)
Source of truth: `nhl_staging.int_player_current_team` (`player_id` → `current_team_id`,
`is_live_roster`, `team_source`), which resolves **live roster first, latest game as fallback** so
nobody is dropped (UFAs / between-contract players keep their last-game team). It is fed by
`stg_roster_current` (newest-ingestion snapshot per player) over `nhl_raw.raw_rosters`, ingested by
`ingestion.nhl_api.get_roster()` → `max(/roster-season/{TEAM})` → `/v1/roster/{TEAM}/{season8}`
(the planned `/current` endpoint is a 307 redirect; deviation documented in ROSTER_FINDINGS.md).

Live payload shape (verified against real output, TOR, this session — `{forwards, defensemen,
goalies, team_abbrev, season8}`; each player object carries `id`, `firstName.default`,
`lastName.default`, `positionCode`, `sweaterNumber`, `shootsCatches`, `headshot`, height/weight,
birth fields). The join key into the value tables is the NHL `id` (= `player_id`).

Join keys: `player_id` (int64) → `current_team_id` (int64). Abbrev↔id via `stg_games` (staging).

### Membership ≠ performance (carried into every forecast number)
The live roster fixes the team LABEL only. A just-arrived player has ZERO games with his new club,
so all his value inputs (GAR/RAPM/archetype/aging) come from his OLD team's usage. The forecast
projects his prior value forward; it does not invent new-team production. This is stated in the
verdict's limitations footer.

### Transition definition
A "transition" is `prior_completed_season -> next_season`, e.g. `2024-25 -> 2025-26`. BASE =
end-of-`2024-25` `team_ratings` + `2024-25` season-end roster; UPDATED = current
`int_player_current_team` membership (which, in deep offseason, resolves to the latest published
roster — see ROSTER_FINDINGS.md). Backtest uses `2024-25 -> 2025-26` with the ACTUAL 2025-26
rosters as UPDATED.

Smoke: `scripts/smoke_roster_source.py` (exercises the UPDATED live source; BASE is a BigQuery read).

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

