# Gap Control · Phase C DIAGNOSTIC EXTENSION — COMPLETE coupling dump (3 fresh goals)

Every detected coupling, unfiltered: kept AND dropped segments (short <3fr, and §4.6 DZ-origin), gap at EVERY zone moment each segment traverses, plus per-goal coverage (who the detector missed). **Reporting change only — thresholds and coupling logic unchanged from the approved build.** No primary-filtering, no profile, no zone-expected gap, no stability.

3 goals md5-selected from all coupled goals, excluding the 8 already shown: 2025020052-1001, 2023021216-268, 2024020732-717


---
## Goal 2025020052-1001

**Context:** entry_type = `off_frame_start` (clean_entry=False) · turnover-caused: **no** · rush-defense fired: **no**

**Coverage:** 3/4 defenders got a real (≥3fr) coupling · 3/5 attackers were coupled-to.
- Defenders with NO coupling (detector missed entirely): Jake Guentzel #59 (C)
- Attackers never coupled-to: Alex Ovechkin #8 (L), Dylan Strome #17 (C)

**ALL detected segments (kept + dropped):**

| defender | attacker | frames | dur | origin | zones | STATUS |
|---|---|---|---|---|---|---|
| Victor Hedman #77 (D) | 8477947 #? (?) | 10–20 | 1.1s | DZ | DZ | dropped_DZ-origin |
| Yanni Gourde #37 (C) | John Carlson #None (D) | 1–3 | 0.3s | DZ | DZ | dropped_DZ-origin |
| Yanni Gourde #37 (C) | Tom Wilson #43 (R) | 17–18 | 0.2s | DZ | DZ | dropped_short(<3fr) |
| Yanni Gourde #37 (C) | Tom Wilson #43 (R) | 25–25 | 0.1s | DZ | DZ | dropped_short(<3fr) |
| Yanni Gourde #37 (C) | Tom Wilson #43 (R) | 49–57 | 0.9s | BL | BL, DZ | KEPT |
| Yanni Gourde #37 (C) | Tom Wilson #43 (R) | 60–61 | 0.2s | DZ | DZ | dropped_short(<3fr) |
| Jake Guentzel #59 (C) | John Carlson #None (D) | 72–72 | 0.1s | DZ | DZ | dropped_short(<3fr) |
| J.J. Moser #90 (D) | Dylan Strome #17 (C) | 1–2 | 0.2s | DZ | DZ | dropped_short(<3fr) |
| J.J. Moser #90 (D) | 8477947 #? (?) | 4–4 | 0.1s | DZ | DZ | dropped_short(<3fr) |
| J.J. Moser #90 (D) | Tom Wilson #43 (R) | 70–72 | 0.3s | DZ | DZ | dropped_DZ-origin |

**Per-segment gap at every zone moment it traverses** (≥3fr segments; short <3fr omitted as noise):

- **Victor Hedman #77 (D) → 8477947 #? (?)**  frames 10–20  [dropped_DZ-origin]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | DZ | 15 | 11.5 | 5.5 | (20, +1) | (20, +12) | (6, +35) |

- **Yanni Gourde #37 (C) → John Carlson #None (D)**  frames 1–3  [dropped_DZ-origin]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | DZ | 2 | 15.9 | 9.9 | (32, +5) | (44, -5) | (47, -3) |

- **Yanni Gourde #37 (C) → Tom Wilson #43 (R)**  frames 49–57  [KEPT]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | BL | 52 | 4.9 | -1.1 | (37, +19) | (36, +24) | (62, +5) |
    | DZ | 56 | 1.5 | -4.5 | (34, +19) | (33, +20) | (46, +25) |

- **J.J. Moser #90 (D) → Tom Wilson #43 (R)**  frames 70–72  [dropped_DZ-origin]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | DZ | 71 | 22.0 | 16.0 | (19, -12) | (23, +10) | (39, +29) |


---
## Goal 2023021216-268

**Context:** entry_type = `dumped` (clean_entry=False) · turnover-caused: **no** · rush-defense fired: **YES**

**Coverage:** 5/6 defenders got a real (≥3fr) coupling · 4/5 attackers were coupled-to.
- Defenders with NO coupling (detector missed entirely): Chandler Stephenson #9 (C)
- Attackers never coupled-to: Lawson Crouse #67 (L)

**ALL detected segments (kept + dropped):**

| defender | attacker | frames | dur | origin | zones | STATUS |
|---|---|---|---|---|---|---|
| 8474166 #? (?) | Logan Cooley #92 (C) | 51–69 | 1.9s | OUT | NZ, OUT | dropped_OUT-origin(>far-BL) |
| Jonathan Marchessault #81 (C) | 8478408 #? (?) | 53–62 | 1.0s | OUT | OUT | dropped_OUT-origin(>far-BL) |
| Shea Theodore #27 (D) | Lawson Crouse #67 (L) | 20–21 | 0.2s | OUT | OUT | dropped_short(<3fr) |
| Shea Theodore #27 (D) | Lawson Crouse #67 (L) | 57–58 | 0.2s | OUT | OUT | dropped_short(<3fr) |
| Shea Theodore #27 (D) | Dylan Guenther #11 (R) | 59–59 | 0.1s | OUT | OUT | dropped_short(<3fr) |
| Shea Theodore #27 (D) | Logan Cooley #92 (C) | 60–69 | 1.0s | OUT | NZ, OUT | dropped_OUT-origin(>far-BL) |
| Ivan Barbashev #49 (L) | 8477384 #? (?) | 1–7 | 0.7s | OUT | OUT | dropped_OUT-origin(>far-BL) |
| Ivan Barbashev #49 (L) | 8478408 #? (?) | 11–11 | 0.1s | OUT | OUT | dropped_short(<3fr) |
| Ivan Barbashev #49 (L) | 8478408 #? (?) | 41–41 | 0.1s | OUT | OUT | dropped_short(<3fr) |
| Ivan Barbashev #49 (L) | Dylan Guenther #11 (R) | 42–53 | 1.2s | OUT | OUT | dropped_OUT-origin(>far-BL) |
| Ivan Barbashev #49 (L) | Logan Cooley #92 (C) | 54–55 | 0.2s | OUT | OUT | dropped_short(<3fr) |
| Ivan Barbashev #49 (L) | Dylan Guenther #11 (R) | 56–56 | 0.1s | OUT | OUT | dropped_short(<3fr) |
| Ivan Barbashev #49 (L) | Logan Cooley #92 (C) | 60–62 | 0.3s | OUT | OUT | dropped_OUT-origin(>far-BL) |
| Ivan Barbashev #49 (L) | Logan Cooley #92 (C) | 66–69 | 0.4s | OUT | NZ, OUT | dropped_OUT-origin(>far-BL) |
| Jack Eichel #9 (C) | 8478408 #? (?) | 2–24 | 2.3s | OUT | OUT | dropped_OUT-origin(>far-BL) |
| Jack Eichel #9 (C) | 8477384 #? (?) | 64–69 | 0.6s | OUT | NZ, OUT | dropped_OUT-origin(>far-BL) |

**Per-segment gap at every zone moment it traverses** (≥3fr segments; short <3fr omitted as noise):

- **8474166 #? (?) → Logan Cooley #92 (C)**  frames 51–69  [dropped_OUT-origin(>far-BL)]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | OUT | 60 | 19.2 | 13.2 | (114, +11) | (132, +16) | (131, +15) |
    | NZ | 69 | 13.4 | 7.4 | (104, +19) | (116, +24) | (110, +19) |

- **Jonathan Marchessault #81 (C) → 8478408 #? (?)**  frames 53–62  [dropped_OUT-origin(>far-BL)]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | OUT | 58 | 14.8 | 8.8 | (160, -21) | (166, -7) | (134, +14) |

- **Shea Theodore #27 (D) → Logan Cooley #92 (C)**  frames 60–69  [dropped_OUT-origin(>far-BL)]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | OUT | 64 | 17.0 | 11.0 | (121, +4) | (126, +20) | (123, +18) |
    | NZ | 69 | 11.7 | 5.7 | (113, +13) | (116, +24) | (110, +19) |

- **Ivan Barbashev #49 (L) → 8477384 #? (?)**  frames 1–7  [dropped_OUT-origin(>far-BL)]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | OUT | 4 | 6.1 | 0.1 | (158, +3) | (164, +4) | (120, +25) |

- **Ivan Barbashev #49 (L) → Dylan Guenther #11 (R)**  frames 42–53  [dropped_OUT-origin(>far-BL)]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | OUT | 48 | 4.5 | -1.5 | (158, -7) | (154, -5) | (150, -4) |

- **Ivan Barbashev #49 (L) → Logan Cooley #92 (C)**  frames 60–62  [dropped_OUT-origin(>far-BL)]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | OUT | 61 | 16.8 | 10.8 | (134, +1) | (131, +17) | (129, +15) |

- **Ivan Barbashev #49 (L) → Logan Cooley #92 (C)**  frames 66–69  [dropped_OUT-origin(>far-BL)]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | OUT | 67 | 17.6 | 11.6 | (121, +5) | (120, +23) | (120, +19) |
    | NZ | 69 | 17.0 | 11.0 | (118, +7) | (116, +24) | (110, +19) |

- **Jack Eichel #9 (C) → 8478408 #? (?)**  frames 2–24  [dropped_OUT-origin(>far-BL)]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | OUT | 13 | 6.9 | 0.9 | (172, +18) | (174, +11) | (138, -22) |

- **Jack Eichel #9 (C) → 8477384 #? (?)**  frames 64–69  [dropped_OUT-origin(>far-BL)]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | OUT | 66 | 2.9 | -3.1 | (169, -11) | (168, -8) | (122, +19) |
    | NZ | 69 | 2.6 | -3.4 | (167, -11) | (166, -9) | (110, +19) |


---
## Goal 2024020732-717

**Context:** entry_type = `off_frame_start` (clean_entry=False) · turnover-caused: **no** · rush-defense fired: **no**

**Coverage:** 3/4 defenders got a real (≥3fr) coupling · 3/5 attackers were coupled-to.
- Defenders with NO coupling (detector missed entirely): 8474166 #? (?)
- Attackers never coupled-to: Shea Theodore #27 (D), Jack Eichel #9 (C)

**ALL detected segments (kept + dropped):**

| defender | attacker | frames | dur | origin | zones | STATUS |
|---|---|---|---|---|---|---|
| Nick Foligno #71 (L) | Shea Theodore #27 (D) | 13–13 | 0.1s | DZ | DZ | dropped_short(<3fr) |
| Nick Foligno #71 (L) | Tomas Hertl #48 (C) | 84–97 | 1.4s | BL | BL, DZ | KEPT |
| 8474166 #? (?) | Tomas Hertl #48 (C) | 92–92 | 0.1s | BL | BL | dropped_short(<3fr) |
| Seth Jones #3 (D) | Pavel Dorofeyev #None (L) | 1–11 | 1.1s | DZ | DZ | dropped_DZ-origin |
| Ilya Mikheyev #None (R) | Mark Stone #61 (R) | 1–10 | 1.0s | DZ | DZ | dropped_DZ-origin |

**Per-segment gap at every zone moment it traverses** (≥3fr segments; short <3fr omitted as noise):

- **Nick Foligno #71 (L) → Tomas Hertl #48 (C)**  frames 84–97  [KEPT]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | BL | 88 | 17.2 | 11.2 | (26, -18) | (22, -2) | (59, -16) |
    | DZ | 95 | 13.3 | 7.3 | (23, -17) | (21, -3) | (28, -11) |

- **Seth Jones #3 (D) → Pavel Dorofeyev #None (L)**  frames 1–11  [dropped_DZ-origin]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | DZ | 6 | 9.2 | 3.2 | (2, -24) | (8, -17) | (5, -19) |

- **Ilya Mikheyev #None (R) → Mark Stone #61 (R)**  frames 1–10  [dropped_DZ-origin]
    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |
    |---|---|---|---|---|---|---|
    | DZ | 6 | 14.4 | 8.4 | (15, +1) | (13, +15) | (5, -19) |

## STOP — owner tape review of the COMPLETE coupling set. No profile, no zone-expected gap, no stability.
