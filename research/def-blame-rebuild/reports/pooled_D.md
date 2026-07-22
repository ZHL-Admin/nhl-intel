# Pooled 3-season (2023-26) D-only blame rating — the sample-size attack. Nothing promoted.

Pooled blame / pooled exposure over 3 seasons, D only. **Qualifying D: 249 total · 174 with ≥60 pooled tracked GA · 106 with ≥100** (single-season min-60 gave only ~13).

## Pooled split-half stability (odd/even games, all 3 seasons) vs placebo — 0.30 bar, F25 ref 0.41-0.76

| pool | denominator | n | split-half r | placebo | p(null≥r) | vs 0.30 |
|---|---|---|---|---|---|---|
| min-60 | per_goal | 174 | **0.087** | -0.002±0.075 | 0.122 | FAIL |
| min-60 | per_shift | 174 | **0.278** | 0.001±0.076 | 0.0 | FAIL |
| min-100 | per_goal | 106 | **0.187** | -0.003±0.097 | 0.0275 | FAIL |
| min-100 | per_shift | 106 | **0.264** | -0.004±0.099 | 0.0015 | FAIL |

## Per-LEDGER decomposition — pooled split-half (which component is the durable signal)

| pool | component | n | split-half r | vs 0.30 |
|---|---|---|---|---|
| min-60 | coverage | 174 | **0.154** | FAIL |
| min-60 | turnover | 174 | **-0.045** | FAIL |
| min-60 | rush | 174 | **-0.027** | FAIL |
| min-100 | coverage | 106 | **0.209** | FAIL |
| min-100 | turnover | 106 | **-0.02** | FAIL |
| min-100 | rush | 106 | **0.032** | FAIL |

## Year-over-year (durable-quality test)

- adjacent 2023-24→2024-25: r=0.381 (n=37) · 2024-25→2025-26: r=-0.037 (n=47)
- **seasons 1-2 mean → season 3: r=0.049 (n=27)**
- biggest movers (24→25) — does the move track a deployment change?
  - Ben Chiarot: Δrate +0.166 | Δoz_start +0.023 Δqoc +0.15 Δqot +0.007
  - Darnell Nurse: Δrate +0.079 | Δoz_start -0.002 Δqoc +0.16 Δqot -0.031
  - Mario Ferraro: Δrate -0.074 | Δoz_start +0.013 Δqoc +0.18 Δqot +0.023
  - Zach Werenski: Δrate -0.073 | Δoz_start -0.016 Δqoc +0.15 Δqot +0.028
  - Ivan Provorov: Δrate -0.073 | Δoz_start +0.006 Δqoc +0.16 Δqot +0.037
  - Travis Sanheim: Δrate -0.064 | Δoz_start -0.046 Δqoc +0.19 Δqot -0.013
  - Marcus Pettersson: Δrate +0.063 | Δoz_start -0.041 Δqoc +0.15 Δqot -0.055
  - Noah Hanifin: Δrate +0.061 | Δoz_start +0.058 Δqoc +0.11 Δqot +0.008

## Pooled eye test (D, ≥60 pooled GA) — sort by defensive reputation? does Slavin rise?

- **least blame (best 15, per_shift):** Urho Vaakanainen, MacKenzie Weegar, Hampus Lindholm, Miro Heiskanen, Rasmus Ristolainen, Jake Sanderson, Vladislav Gavrikov, Jonas Siegenthaler, Rasmus Dahlin, Philip Broberg, Jonas Brodin, Noah Hanifin, Owen Power, Adam Larsson, Rasmus Andersson
- **most blame (worst 15, per_shift):** Jayden Struble, Jacob Bryson, Lane Hutson, Kevin Korchinski, Ryan Shea, Arber Xhekaj, Jacob Bernard-Docker, Trevor van Riemsdyk, Jalen Chatfield, Uvis Balinskis, Simon Nemec, Dante Fabbro, Louis Crevier, John Marino, Albert Johansson
  - Jaccob Slavin: rank 112/174 (64%ile), per_shift 1.094, 109 GA
  - Hampus Lindholm: rank 3/174 (1%ile), per_shift 0.703, 73 GA
  - Esa Lindell: rank 25/174 (14%ile), per_shift 0.871, 119 GA
  - Mattias Ekholm: rank 47/174 (27%ile), per_shift 0.935, 118 GA
  - Erik Karlsson: rank 136/174 (78%ile), per_shift 1.188, 152 GA
  - Evan Bouchard: rank 123/174 (70%ile), per_shift 1.137, 125 GA
  - Cale Makar: rank 128/174 (73%ile), per_shift 1.148, 115 GA
  - Luke Hughes: rank 135/174 (77%ile), per_shift 1.181, 119 GA
  - Quinn Hughes: rank 102/174 (58%ile), per_shift 1.066, 157 GA
  - Erik Cernak: rank 33/174 (18%ile), per_shift 0.901, 102 GA
  - Ivan Provorov: rank 71/174 (40%ile), per_shift 1.004, 148 GA

## STOP — owner reads the pooled outcome.
