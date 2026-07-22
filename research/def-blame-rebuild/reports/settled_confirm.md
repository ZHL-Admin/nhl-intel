# Settled-Play §8 — read-only EXPOSURE confirms (power check; no norm, no gate, no profile)

Provisional settled definition (power-check only): puck in DZ (depth<63) AND ≥1.5s continuously in-zone (not a fresh rush-in) AND ≥1.0s before the shot. Area tiling + role-slots PROVISIONAL — they exist only to size the finest cell. Owner rules the real boundaries.

## (a) Settled-phase exposure

- 5v5 tracked goals: **22,773** · with a real settled DZ phase: **18,570** (81.5%)
- total settled frames: 869,076 · total settled POSSESSIONS: **18,917**
- settled possessions per puck-area: {'point': 10948, 'slot': 10876, 'right_halfwall': 9574, 'left_halfwall': 9532, 'behind_net': 8010, 'right_corner': 7442, 'left_corner': 7267}

**DECISIVE — goals per (defender × area × slot) cell** (split-half unit; need ~≥10/half → ≥20 total to be viable):
- distinct (player × area × slot) cells: 24,303
- goals-per-cell distribution: median **7**, p75 16, p90 28, max 108
- cells with ≥10 goals: **9,942** (40.9%) · with ≥20 goals (split-half viable): **4,835**

## (b) Classifier sanity

- settled puck-frames 869,076 of 1,541,021 buildup puck-frames (**56.4%** of buildup is settled DZ)
- 18570 settled-phase goals vs RCET 4,066 rush goals

- **central (no-split) areas ['behind_net', 'point', 'slot'] hold 158% of settled possessions**

## Proposed (area × slot) cell viability — where the workhorse signal would live (cells ≥20 / ≥33 goals)

| area | slot | cells | ≥20 goals | ≥33 goals | median goals |
|---|---|---|---|---|---|
| point | high-F | 792 | **364** | 239 | 16.0 |
| right_halfwall | high-F | 737 | **269** | 74 | 12.0 |
| slot | low-F | 791 | **256** | 57 | 11.0 |
| left_halfwall | high-F | 749 | **249** | 63 | 11.0 |
| slot | high-F | 721 | **216** | 46 | 11.0 |
| behind_net | net-front | 956 | **192** | 101 | 6.0 |
| point | strong-D | 241 | **182** | 148 | 41.0 |
| behind_net | high-F | 720 | **181** | 21 | 9.5 |
| slot | D | 245 | **181** | 137 | 39.0 |
| left_halfwall | strong-D | 241 | **178** | 125 | 34.0 |
| right_halfwall | strong-D | 239 | **168** | 120 | 33.0 |
| left_halfwall | strong-low-F | 761 | **167** | 38 | 9.0 |
| right_corner | strong-low-F | 769 | **156** | 18 | 9.0 |
| point | strong-low-F | 750 | **153** | 35 | 8.0 |
| point | D | 240 | **151** | 79 | 24.0 |
| right_halfwall | strong-low-F | 757 | **151** | 25 | 9.0 |
| behind_net | strong-low-F | 772 | **150** | 7 | 9.0 |
| left_corner | strong-D | 241 | **142** | 52 | 22.0 |
| behind_net | strong-D | 239 | **138** | 55 | 22.0 |
| left_corner | strong-low-F | 761 | **137** | 10 | 8.0 |
| right_corner | strong-D | 238 | **134** | 69 | 22.5 |
| behind_net | low-F | 750 | **115** | 2 | 9.0 |
| behind_net | D | 233 | **97** | 11 | 16.0 |
| point | net-front | 665 | **85** | 23 | 3.0 |
| slot | net-front | 837 | **84** | 14 | 3.0 |
| point | weak-D | 236 | **80** | 7 | 15.0 |
| right_corner | high-F | 681 | **75** | 0 | 8.0 |
| right_corner | net-front | 700 | **59** | 6 | 3.0 |
| left_corner | net-front | 692 | **57** | 8 | 3.0 |
| left_corner | high-F | 669 | **48** | 0 | 8.0 |
| left_halfwall | net-front | 593 | **42** | 7 | 3.0 |
| right_halfwall | weak-D | 232 | **40** | 5 | 8.0 |
| right_halfwall | net-front | 628 | **37** | 5 | 3.0 |
| point | low-F | 679 | **37** | 1 | 5.0 |
| left_halfwall | weak-D | 227 | **35** | 6 | 7.0 |

## STOP — read-only exposure reported. No norm, no gate, no profile.
