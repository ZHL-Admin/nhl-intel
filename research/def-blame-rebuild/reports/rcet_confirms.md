# RCET — three read-only confirms (no norm, no trajectory, no deviation)

## (a) Qualifying entry-captured count

- 5v5 tracked goals: **22,773**
- entry_type breakdown: [{'entry_type': 'off_frame_start', 'count': 13737}, {'entry_type': 'carried', 'count': 6378}, {'entry_type': 'dumped', 'count': 1334}, {'entry_type': 'passed', 'count': 979}, {'entry_type': None, 'count': 345}]
- entry_type ∈ {carried, passed}: **7,357**
- + entry captured (clean_entry): **7,207**
- + rushdef bucket = EVEN → **QUALIFYING = 4,066**

## (b) Non-goal rush tracking?

- tracked-frame events total: 25,946 · ALL goals (GT_FUSED, any strength): 25,945 · 5v5-goal universe: 22,773
- tracked-but-not-5v5-goal: 3,173 — **verified these are all NON-5v5 GOALS** (5v4/4v5 PP 1,626 · 3v3 OT 530 · 4v4 400 · empty-net 5v6/6v5 290 · etc.), NOT non-goal events (3,173/3,173 present in GT_FUSED)
- **truly non-goal tracked events (absent from EVERY goal): 0** → non-goal rush tracking exists: **False**
  (N/A → no all-rush norm to compare; the norm-comparison arm of confirm (b) is N/A. Per the Issue-1 ruling: note the mild selection honestly and proceed — the goals-only norm is still meaningful because most goal-rushes are ordinary rush-defense.)

## (c) Middle-lane entry + drop-pass (carrier-change) frequency (on the qualifying set)

- goals with a measurable entry-lateral: 4,066
- **middle-lane entries (|carrier lateral at entry| < 10 ft): 711 (0.175)** · |entry lateral| IQR: {'p25': 14.0, 'p50': 26.1, 'p75': 34.7}
- **carrier change (≥1 attacking pass, entry→shot): 2,187 of 4,066 (0.538)**

## STOP — three facts reported. No norm, no trajectory, no deviation computed.
