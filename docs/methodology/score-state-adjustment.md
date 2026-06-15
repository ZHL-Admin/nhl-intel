# Score-state & opponent adjustment (Phase 2.3)

Two adjustments to 5v5 possession/xG shares, both **opt-in via a toggle** (never silent).

## Score-state adjustment

Trailing teams shoot more, inflating their raw shot shares. `int_score_state_weights`
computes the league-average 5v5 shot-attempt **rate** (attempts per minute) by score state
per season — time-in-state from 5v5 segment durations (`int_segment_context`), attempts
from unblocked 5v5 shots with the score read just before the event — then sets
`weight = tied_rate / state_rate`. Each Corsi/xG event is weighted by its state's weight
before aggregating into `cf_pct_score_adj` / `xgf_pct_score_adj` on `mart_team_game_stats`.

States are from the shooting team's perspective: `down2plus, down1, tied, up1, up2plus`.

Example weights (2024-25): trailing teams shoot more so are down-weighted, leading teams up:

| state | attempts/min | weight |
|---|---|---|
| down2plus | 0.767 | 0.956 |
| down1 | 0.765 | 0.959 |
| tied | 0.734 | 1.000 |
| up1 | 0.691 | 1.061 |
| up2plus | 0.647 | 1.134 |

Effect: weak/trailing teams' season CF% moves down (e.g. SJS 0.454 → 0.445), strong/leading
teams up (FLA 0.546 → 0.550).

## Opponent adjustment (interim)

`cf_pct_opp_adj` / `xgf_pct_opp_adj` adjust a team's per-game share by the opponent's
**season-to-date** strength (the average possession/xG share the opponent generated in its
prior games that season), half-weighted:

```
xgf_pct_opp_adj = xgf_pct + 0.5 * (opp_season_xgf_to_date - 0.5)
```

A strong possession opponent suppresses your raw share, so the adjustment lifts it. This is
the **interim** method: Phase 3's power ratings replace the opponent-strength source in one
place (the `to_date` CTE), per blueprint 3.5. Documented in the model description so the
swap is localised.
