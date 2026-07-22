# Gap Control · Phases A + B — coupling + gap, and Phase C tape-reconstruction sheets

Phases A (defender→attacker coupling) + B (gap + zone) built on the LOCKED A0 knobs. Nothing past the Phase C tape gate is computed — no zone-expected gaps, no per-defender profiles, no stability.

## Thresholds actually used (echoed per §6.4)

- Candidate radius **≤ 24 ft** · goal-side slack **6 ft** (D.depth ≤ A.depth+6)
- Backward-posture **vDepthD ≤ -3.2 ft/s** (knob1 CLEAN) · A advancing **vDepthA < 0**
- Coupling ends when separating **d(dist)/dt ≥ +1.7 ft/s** (knob3 CLEAN) · lateral-tracking DROPPED (knob2 smeared)
- Persistence **≥ 3 frames** · two-attacker tie band **20%** → hybrid side prior (winger roster L/R; D tracking-derived if |mean-lat| ≥ 1.1 ft & ≥ 230 frames else handedness; center none); lateral agreement down-weighted (knob4)
- Segment-origin (§4.6): keep only segments whose FIRST frame is in NZ/BL; DZ-origin dropped
- Zone bands by PUCK depth: DZ 0–53 / BL 53–73 / NZ 73–113 ft
- Gap = center-to-center distance; gap−stick = gap − 6 ft

## Coupling rate vs the 40–70% expectation — **BELOW, and the cause is isolated**

- **Raw core coupling** (backward-posture + proximity + goal-side + not-separating): **22.5%** of all defender-frames (1,602,760 / 7,115,500).
- **+ persistence ≥3 frames:** 20.8% (1,482,204).
- **+ §4.6 DZ-origin exclusion → FINAL 6.0%** (423,810). The origin filter alone drops 126,676 of 178,091 persistent segments (~71%).
- **Reading:** the coupling ITSELF sits at ~22% (≈1 of 5 defenders actively in a backward-gap engagement per frame — plausible; the 40–70% figure over-counted, since at any instant most of the 5 defenders are net-front / weak-side / puck-watching, not gapping a man). **The final 6% is a SCOPE artifact of §4.6, not a coupling failure.** The open question for the tape: are the dropped DZ-origin segments genuinely SETTLED play (correctly excluded) or rush drive-ins whose gap only tightened into coupling once the carrier was already past the blue line (wrongly excluded)? **This is the §6.2 judgment — see the reconstructions.**
- Position prior was decisive on **1.2%** of coupled frames (rarely — as expected).

## Gap by zone (raw medians, DESCRIPTIVE only — NOT the zone-expected profile, which is Phase D)

| zone | coupled frames | median gap | 
|---|---|---|
| BL | 163,951 | 13.6 ft |
| DZ | 209,712 | 10.5 ft |
| NZ | 49,956 | 15.2 ft |

(Gap tightens DZ 10.5 < BL 13.6 < NZ 15.2 ft — the expected zone gradient, a sanity signal only.)

---
## PHASE C — tape reconstruction (8 goals + 3 failures) for owner judgment

8 goals md5-selected from clean-entry coupled goals; composition enforced (≥1 deep-carry-to-net, ≥2 forward-gap). For each: coupled segments (right pairing?), and the primary engagement's gap at each zone moment (real gap?).

### Goal 2025021201-516  (carried entry)  [DEEP-CARRY-TO-NET, FORWARD-GAP]

**Coupled segments (defender → attacker, frames):**

| defender | attacker | frames | dur | origin | zones traversed |
|---|---|---|---|---|---|
| Olli Maatta #None (D) | Mitch Marner #93 (R) | 61–65 | 0.5s | BL | BL |
| Victor Olofsson #95 (R) | Mitch Marner #93 (R) | 41–45 | 0.5s | BL | BL |
| Yegor Sharangovich #17 (C) | Mark Stone #61 (R) | 72–74 | 0.3s | BL | BL |
| Brayden Pachal #94 (D) | Ivan Barbashev #49 (L) | 41–49 | 0.9s | BL | BL, DZ |
| Brayden Pachal #94 (D) | Mark Stone #61 (R) | 66–74 | 0.9s | BL | BL |
| Brayden Pachal #94 (D) | Mitch Marner #93 (R) | 75–84 | 1.0s | BL | BL, DZ |

**Primary engagement — Brayden Pachal #94 (D) — gap at each zone moment** (depth = ft from defended net; lateral ± = L/R):

| zone | frame | GAP (c-c) | gap−stick | defender (depth,lat) | attacker (depth,lat) | puck (depth,lat) |
|---|---|---|---|---|---|---|
| BL | 69 | **22.9 ft** | 16.9 | (25, -20) | (47, -17) | (57, -6) |
| DZ | 79 | **6.3 ft** | 0.3 | (14, -8) | (10, -3) | (48, +25) |

### Goal 2025020505-552  (carried entry)  [DEEP-CARRY-TO-NET, FORWARD-GAP]

**Coupled segments (defender → attacker, frames):**

| defender | attacker | frames | dur | origin | zones traversed |
|---|---|---|---|---|---|
| Alexander Petrovic #6 (D) | Anton Lundell #15 (C) | 68–84 | 1.7s | BL | BL, DZ |
| Sam Steel #18 (C) | Sam Reinhart #13 (C) | 70–72 | 0.3s | BL | BL |
| Thomas Harley #55 (D) | Sam Reinhart #13 (C) | 72–89 | 1.8s | BL | BL, DZ |
| Wyatt Johnston #53 (C) | Aaron Ekblad #5 (D) | 69–93 | 2.5s | BL | BL, DZ |

**Primary engagement — Wyatt Johnston #53 (C) — gap at each zone moment** (depth = ft from defended net; lateral ± = L/R):

| zone | frame | GAP (c-c) | gap−stick | defender (depth,lat) | attacker (depth,lat) | puck (depth,lat) |
|---|---|---|---|---|---|---|
| BL | 71 | **18.3 ft** | 12.3 | (77, +36) | (94, +30) | (56, -1) |
| DZ | 83 | **19.5 ft** | 13.5 | (61, +31) | (80, +27) | (26, +4) |

### Goal 2023020822-877  (dumped entry)  [FORWARD-GAP]

**Coupled segments (defender → attacker, frames):**

| defender | attacker | frames | dur | origin | zones traversed |
|---|---|---|---|---|---|
| Jonathan Marchessault #81 (C) | Kirill Kaprizov #97 (L) | 40–42 | 0.3s | BL | BL |

**Primary engagement — Jonathan Marchessault #81 (C) — gap at each zone moment** (depth = ft from defended net; lateral ± = L/R):

| zone | frame | GAP (c-c) | gap−stick | defender (depth,lat) | attacker (depth,lat) | puck (depth,lat) |
|---|---|---|---|---|---|---|
| BL | 41 | **4.1 ft** | -1.9 | (78, +36) | (82, +35) | (57, +19) |

### Goal 2025020115-1009  (carried entry)  [FORWARD-GAP]

**Coupled segments (defender → attacker, frames):**

| defender | attacker | frames | dur | origin | zones traversed |
|---|---|---|---|---|---|
| Tony DeAngelo #77 (D) | 8484794 #? (?) | 73–76 | 0.4s | BL | BL, DZ |
| Maxim Tsyplakov #None (R) | 8484794 #? (?) | 75–90 | 1.6s | BL | BL, DZ |

**Primary engagement — Maxim Tsyplakov #None (R) — gap at each zone moment** (depth = ft from defended net; lateral ± = L/R):

| zone | frame | GAP (c-c) | gap−stick | defender (depth,lat) | attacker (depth,lat) | puck (depth,lat) |
|---|---|---|---|---|---|---|
| BL | 75 | **20.9 ft** | 14.9 | (65, -19) | (65, +2) | (53, +25) |
| DZ | 83 | **15.1 ft** | 9.1 | (45, -14) | (45, +1) | (32, +25) |

### Goal 2023020803-1000  (passed entry)  [FORWARD-GAP]

**Coupled segments (defender → attacker, frames):**

| defender | attacker | frames | dur | origin | zones traversed |
|---|---|---|---|---|---|
| 8475164 #? (?) | Mattias Ekholm #14 (D) | 61–63 | 0.3s | BL | BL |
| Frank Vatrano #77 (R) | 8478585 #? (?) | 61–63 | 0.3s | BL | BL |
| Bo Groulx #29 (C) | Mattias Ekholm #14 (D) | 64–67 | 0.4s | BL | BL, DZ |
| Jackson LaCombe #2 (D) | 8475169 #? (?) | 61–63 | 0.3s | BL | BL |

**Primary engagement — Bo Groulx #29 (C) — gap at each zone moment** (depth = ft from defended net; lateral ± = L/R):

| zone | frame | GAP (c-c) | gap−stick | defender (depth,lat) | attacker (depth,lat) | puck (depth,lat) |
|---|---|---|---|---|---|---|
| BL | 65 | **21.8 ft** | 15.8 | (113, +11) | (115, +32) | (54, +34) |
| DZ | 67 | **20.1 ft** | 14.1 | (108, +11) | (115, +30) | (50, +33) |

### Goal 2025020032-82  (carried entry)

**Coupled segments (defender → attacker, frames):**

| defender | attacker | frames | dur | origin | zones traversed |
|---|---|---|---|---|---|
| Roman Josi #59 (D) | Dmitri Simashev #26 (D) | 78–83 | 0.6s | BL | BL, DZ |
| Adam Wilsby #83 (D) | Dylan Guenther #11 (R) | 78–81 | 0.4s | BL | BL |

**Primary engagement — Roman Josi #59 (D) — gap at each zone moment** (depth = ft from defended net; lateral ± = L/R):

| zone | frame | GAP (c-c) | gap−stick | defender (depth,lat) | attacker (depth,lat) | puck (depth,lat) |
|---|---|---|---|---|---|---|
| BL | 80 | **2.1 ft** | -3.9 | (76, -8) | (74, -9) | (56, -16) |
| DZ | 83 | **1.8 ft** | -4.2 | (68, -5) | (66, -6) | (50, -15) |

### Goal 2024020293-852  (carried entry)  [FORWARD-GAP]

**Coupled segments (defender → attacker, frames):**

| defender | attacker | frames | dur | origin | zones traversed |
|---|---|---|---|---|---|
| Justin Holl #4 (D) | 8480011 #? (?) | 67–84 | 1.8s | BL | BL, DZ |
| 8476979 #? (?) | Carl Grundstrom #91 (R) | 71–73 | 0.3s | BL | BL |
| J.T. Compher #37 (L) | 8479316 #? (?) | 68–84 | 1.7s | BL | BL, DZ |
| Joe Veleno #None (C) | Timothy Liljegren #27 (D) | 67–70 | 0.4s | BL | BL |
| Joe Veleno #None (C) | Timothy Liljegren #27 (D) | 74–84 | 1.1s | BL | BL, DZ |

**Primary engagement — Justin Holl #4 (D) — gap at each zone moment** (depth = ft from defended net; lateral ± = L/R):

| zone | frame | GAP (c-c) | gap−stick | defender (depth,lat) | attacker (depth,lat) | puck (depth,lat) |
|---|---|---|---|---|---|---|
| BL | 73 | **6.4 ft** | 0.4 | (49, -11) | (55, -9) | (60, +16) |
| DZ | 82 | **3.3 ft** | -2.7 | (30, -5) | (33, -8) | (37, +17) |

### Goal 2023021257-583  (carried entry)  [DEEP-CARRY-TO-NET, FORWARD-GAP]

**Coupled segments (defender → attacker, frames):**

| defender | attacker | frames | dur | origin | zones traversed |
|---|---|---|---|---|---|
| Jonny Brodzinski #76 (C) | Garnet Hathaway #None (R) | 45–50 | 0.6s | BL | BL |
| Jonny Brodzinski #76 (C) | Cam York #8 (D) | 51–57 | 0.7s | BL | BL |
| Alexander Wennberg #21 (C) | Cam York #8 (D) | 43–55 | 1.3s | BL | BL |
| K'Andre Miller #19 (D) | Ryan Poehling #25 (C) | 43–49 | 0.7s | BL | BL |
| K'Andre Miller #19 (D) | Ryan Poehling #25 (C) | 57–68 | 1.2s | BL | BL, DZ |
| Braden Schneider #4 (D) | Bobby Brink #10 (R) | 43–45 | 0.3s | BL | BL |
| Alexis Lafrenière #13 (L) | Bobby Brink #10 (R) | 49–52 | 0.4s | BL | BL |

**Primary engagement — K'Andre Miller #19 (D) — gap at each zone moment** (depth = ft from defended net; lateral ± = L/R):

| zone | frame | GAP (c-c) | gap−stick | defender (depth,lat) | attacker (depth,lat) | puck (depth,lat) |
|---|---|---|---|---|---|---|
| BL | 57 | **11.2 ft** | 5.2 | (32, -25) | (38, -34) | (57, -12) |
| DZ | 66 | **10.8 ft** | 4.8 | (23, -20) | (19, -30) | (49, -0) |

## 3 coupling-FAILURE goals (defender with NO coupled attacker — confirm weak-side/broken, not a miss)

### Goal 2025020473-841 — uncoupled defenders:

| defender | min dist to nearest attacker (whole window) | mean dist to own net |
|---|---|---|
| Oskar Bäck #10 (C) | 2 ft (came near but never satisfied backward-gap coupling) | 75 ft |
| Justin Hryckowian #49 (C) | 2 ft (came near but never satisfied backward-gap coupling) | 62 ft |

### Goal 2023020729-782 — uncoupled defenders:

| defender | min dist to nearest attacker (whole window) | mean dist to own net |
|---|---|---|
| Fabian Zetterlund #20 (L) | 3 ft (came near but never satisfied backward-gap coupling) | 47 ft |
| 8480172 #? (?) | 4 ft (came near but never satisfied backward-gap coupling) | 31 ft |
| 8481537 #? (?) | 1 ft (came near but never satisfied backward-gap coupling) | 9 ft |
| 8474884 #? (?) | 8 ft (came near but never satisfied backward-gap coupling) | 44 ft |

### Goal 2024021065-374 — uncoupled defenders:

| defender | min dist to nearest attacker (whole window) | mean dist to own net |
|---|---|---|
| Joe Veleno #None (C) | 1 ft (came near but never satisfied backward-gap coupling) | 55 ft |
| Tyler Bertuzzi #59 (L) | 7 ft (came near but never satisfied backward-gap coupling) | 48 ft |
| Louis Crevier #None (D) | 1 ft (came near but never satisfied backward-gap coupling) | 29 ft |
| 8482117 #? (?) | 2 ft (came near but never satisfied backward-gap coupling) | 54 ft |

## §6.2 what to judge: (a) right pairing? (b) real gap? (c) prior sensible? PLUS the §4.6 question above.
## STOP — Phase C tape gate. No zone-expected gap, no profile, no stability until owner approves.
