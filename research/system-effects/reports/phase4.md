# Phase 4 — Product surfaces (computed, not yet published)

**Project:** System Effects · **Date:** 2026-07-11 · **Seed:** 20260711
**Status:** Phase 4 complete. Two surfaces computed and exposed via `src/syseff/api.py`; nothing
published (promotion is Phase 7 only). Stopping for review per protocol.

Built on the Phase 3 gate ruling: INTERNAL/deployment track proceeds (recommendation 3 adopted —
**`zone_start_polarization` is the primary portability axis; `top6_fwd_toi_share` carries its
stability caveat everywhere**); OPPONENT style-matchup track KILLED, its strength-based schedule
normalization surviving as descriptive accounting only. Reproduce: `make phase4`.

---

## 1. Portability surface (4.1)

**Definition.** Decompose a player-season's modeled on-ice 5v5 xG share (Design B, Phase 3.3):

| component | meaning | travels? |
|---|---|---|
| **offset** (frozen RAPM quality) | SKILL value | yes — by construction it moves with the player |
| **deployment-system + type×deployment** | SYSTEM-DEPENDENT value (property of the current team's deployment fingerprint) | no |
| style / schedule / season | context, not part of the split | — |

```
system_dependence = |sys| / (|sys| + |skill_dev|)   ∈ [0,1]
portability        = 1 − system_dependence           (high = value travels)
```
where `skill_dev = offset − mean(offset)` and `sys` is evaluated at the player's team deployment
fingerprint under the player's type (zone-start polarization primary; top-6 concentration carried
with its caveat). **Uncertainty:** the frozen offset is fixed by declaration, so all uncertainty
is in the shrunk deployment coefficients — grouped-bootstrapped over team-seasons (B=300,
seed 20260711) to 90% CIs on both `sys` and `system_dependence`.

> **Amendment 4.1a (adopted).** The surface's primary ordering and public framing is the
> **absolute system contribution `sys`** (xG-share pts, with CI), not the `system_dependence`
> ratio. A **materiality rule** governs the label: a player is called *system-dependent* only
> where `sys` CI excludes zero **and** `|sys| ≥ 0.004` (= p79 of `|sys|` in the exhibit pool,
> ~the p80 cited; p68 in the full table). `portability_leaderboard` sorts by `|sys|` and defaults
> to `material_only`; the API docstring notes the ratio is undefined-in-spirit near league-average
> skill. The **re-cut exhibit is Appendix A**; the ratio-ranked table below is retained only to
> show the artifact the amendment corrects.

**What the numbers say (honest framing).** Absolute system contributions are **small everywhere**
— `|sys|` median 0.0015, p95 0.008 xG-share points — the direct consequence of F14 / the thin
one-season headroom. The *share* `system_dependence` spans 0→0.99 (2024-25, 700+ min: median
0.06, p95 0.48) because it is a ratio: it is high when a player's own skill contribution is itself
small, so "most system-dependent" surfaces **average-skill, usage-driven players on teams with
distinctive deployment fingerprints**, and the CIs are widest exactly there.

### Face-validity exhibit — 2024-25, 700+ 5v5 min (pool = 490)

**Most system-dependent** (value leans on the current deployment system):

| player | team | type | system_dep | 90% CI | sys (xG-sh pts) |
|---|---|---|---:|---|---:|
| Alexis Lafrenière | NYR | F checker | 0.99 | .97–.99 | +.0046 |
| Jake Bean | CGY | D shutdown | 0.97 | .95–.98 | +.0037 |
| Mason Appleton | WPG | F mid-PP | 0.93 | .75–.96 | −.0064 |
| Darren Raddysh | TBL | D shutdown | 0.91 | .87–.93 | +.0090 |
| Anze Kopitar | LAK | F checker | 0.89 | .53–.94 | +.0027 |
| Martin Fehérváry | WSH | D PP-QB | 0.88 | .49–.95 | −.0025 |
| Jamie Oleksiak | SEA | D PP-QB | 0.88 | .65–.92 | +.0022 |
| Jason Zucker | BUF | F checker | 0.87 | .73–.92 | −.0010 |
| Gage Goncalves | TBL | F mid-PK | 0.83 | .43–.90 | +.0041 |
| Ivan Barbashev | VGK | F checker | 0.79 | .65–.86 | −.0032 |
| John Beecher | BOS | F mid-PP | 0.78 | .67–.83 | −.0099 |
| Matty Beniers | SEA | F top-PP | 0.78 | .26–.88 | +.0012 |
| Gabriel Vilardi | WPG | F checker | 0.76 | .51–.85 | +.0065 |
| Marcus Johansson | MIN | F mid-PK | 0.68 | .18–.85 | +.0007 |
| Elias Lindholm | BOS | F top-PP | 0.68 | .34–.77 | −.0042 |

**Most system-independent** (value is skill; travels — portability ≈ 1.00):
Connor Bedard (CHI), Auston Matthews (TOR), Justin Faulk (STL), Artem Zub (OTT),
Tyler Bertuzzi (CHI), Ryan Donato (CHI), Vasily Podkolzin (EDM), Nick Jensen (OTT),
Philip Broberg (STL)… — high-skill players, and whole rosters whose team deployment fingerprint
sits near the league mean (CHI, OTT cluster) so no part of their number is system-attributable.

### Predicted-delta-by-destination

`api.predicted_delta(player, season, dest_team, dest_season)` → expected on-ice xG-share shift
from the destination's deployment fingerprint under the player's type, 90% bootstrap CI, role
held at type. **Worked example:** an F mid-PP forward (BOS 2024-25) into CAR 2023-24's fingerprint
→ **+0.012 xG share, CI [0.006, 0.017]**, driven by a −2.85 SD shift on the primary axis
(zone-start polarization). The accessor returns the F14 caveat verbatim.

---

## 2. Schedule-bias context surface (4.2)

The **surviving** opponent-track product: a **strength-only** opponent-schedule adjustment per
player-season — xG-share points the number is shifted by facing an easier/harder opponent set than
league-average, fit `xg_share ~ own strength + opponent strength` (no style; style-matchup was
killed) on 2010-24 and applied to every season. **Published as DESCRIPTIVE ACCOUNTING: no
predictive claim, no validation bar** (per the ruling).

**Magnitude, framed honestly:** small. 2024-25 (756 player-seasons, 200+ min): mean |adjustment|
**0.00296**, p90 **0.00644** xG-share points — essentially identical to the strength+style figure
the gate quoted (0.003 / 0.0065), confirming style added nothing.

### Exhibit — 2024-25 refreshed

| most flattered (easy schedule) | adj | | most punished (hard schedule) | adj |
|---|---:|---|---|---:|
| Spencer Stastney (NSH) | +.0169 | | Nikolai Kovalenko (SJS) | −.0172 |
| Ryan Lindgren (COL) | +.0168 | | Nikita Nesterenko (ANA) | −.0160 |
| Erik Johnson (COL) | +.0145 | | Hampus Lindholm (BOS) | −.0157 |
| Kyle Burroughs (LAK) | +.0145 | | Elmer Söderblom (DET) | −.0153 |
| Michael Callahan (BOS) | +.0134 | | Jacob Bernard-Docker (BUF) | −.0146 |
| Tyler Seguin (DAL) | +.0129 | | Jeremy Lauzon (NSH) | −.0137 |

The flattered list is dominated by 2025-deadline acquisitions to Colorado (Lindgren, Johnson,
Coyle, Nelson) — partial-season players whose game set skewed to a favorable opponent set — which
reads correctly. Magnitudes are ≤ ~0.017 even at the extremes.

---

## 3. API surface (4.3)

`src/syseff/api.py`, mirroring the Atlas `atlas.api` pattern (typed accessors, docstring examples,
frozen-parquet reads, no production touch):

| accessor | returns | notes |
|---|---|---|
| `portability(player_id, season)` | system_dependence (+CI), portability, sys_contrib (+CI), type | **docstring carries F14 verbatim** |
| `predicted_delta(player_id, season, dest_team_id, dest_season)` | predicted xG-share delta + 90% CI + primary-axis shift | returns F14 caveat in payload |
| `schedule_adjustment(player_id, season)` | strength-only schedule adjustment | descriptive-only framing in docstring |
| `portability_leaderboard(season, system_dependent=, min_toi_min=)` | ranked notable players | face-validity |
| `schedule_extremes(season)` | flattered/punished lists + magnitude | descriptive exhibit |

Guarded by `tests/test_phase4.py` (F14 verbatim present in the portability accessor and the delta
payload; `PRIMARY_AXIS == zone_start_polarization`; schedule surface framed non-predictive;
portability = 1 − system_dependence identity). 12 tests pass total.

---

## 4. Where uncertainty is widest (honest notes)

1. **Portability of average-skill players.** `system_dependence` is a ratio with `|skill_dev|` in
   the denominator, so it is least determined for players near league-average skill — visible in
   the wide CIs (Kopitar .53–.94, Beniers .26–.88, M. Johansson .18–.85). Read those as "system
   share is genuinely uncertain," not as precise scores. High-skill and clearly-checking players
   have tight CIs.
2. **The whole surface lives inside F14.** Absolute system contributions are small (|sys| p95 =
   0.008 xG-share pts). Portability is a decomposition of a **current** number, not a forecast of
   result change on a move; the predicted-delta CIs are correspondingly narrow in points but the
   caveat is that the *result* realization is only ~4%-mediated (F14).
3. **Top-6 concentration.** Carried in `sys` but down-weighted per the ruling; it failed the
   Phase 3.5 YoY-persistence test, so any portability mass it contributes is the less trustworthy
   half. Zone-start polarization is the axis to trust.
4. **Schedule adjustment** is small and descriptive; its extremes are dominated by partial-season
   (traded) players whose opponent sets are least representative — correct behavior, but the tails
   are the least stable rows.

Nothing here is published. **Stopping for review.** Phase 5 follows as pre-registered, **internal
track only** (5B removed with the killed track); Phase 6 prospective registration likewise covers
the internal track only.

---

### Artifacts
`data/parquet/portability.parquet` (11,395; now carries `abs_sys`, `sys_ci_excludes_zero`,
`material`) · `portability_model.json` (coef + bootstrap draws) · `schedule_adjustment.parquet`
(all seasons, 200+ min) · `reports/phase4_analysis.json` · `src/syseff/api.py` · tests
`tests/test_phase4.py` (12 total). Repro: `make phase4`.

---

## Appendix A — Re-cut portability exhibit (amendment 4.1a)

Ranked by **absolute system contribution `|sys|`** among players whose `sys` CI excludes zero
(2024-25, 700+ 5v5 min; pool 490 — **282 signed, 99 material**). `system_dependence` shown
secondary. Note the ranking now groups by **team × type** — the system contribution is a property
of the team's deployment fingerprint under the player's type, so same-type teammates share it
(e.g. Tampa's D PP-QBs all +0.0105). `system_dependence` varies *within* an identical `sys`
(McDonagh 0.14 vs Perbix 0.61 at the same +0.0105) — exactly the denominator artifact the
amendment removes.

**Most system-dependent (by |sys|, all material):**

| player | team | type | **sys** (xG-sh pts) | sys 90% CI | system_dep (2nd) |
|---|---|---|---:|---|---:|
| Emil Lilleberg | TBL | D PP-QB | **+0.0105** | .0072–.0136 | 0.20 |
| Ryan McDonagh | TBL | D PP-QB | +0.0105 | .0072–.0136 | 0.14 |
| Erik Cernak | TBL | D PP-QB | +0.0105 | .0072–.0136 | 0.21 |
| Nick Perbix | TBL | D PP-QB | +0.0105 | .0072–.0136 | 0.61 |
| J.J. Moser | TBL | D PP-QB | +0.0105 | .0072–.0136 | 0.36 |
| Cole Koepke | BOS | F mid-PP | **−0.0099** | −.0139–−.0057 | 0.28 |
| Charlie Coyle | BOS | F mid-PP | −0.0099 | −.0139–−.0057 | 0.31 |
| John Beecher | BOS | F mid-PP | −0.0099 | −.0139–−.0057 | 0.78 |
| Noel Acciari | PIT | F mid-PP | −0.0097 | −.0137–−.0055 | 0.18 |
| Victor Hedman | TBL | D shutdown | +0.0090 | .0057–.0121 | 0.21 |
| Darren Raddysh | TBL | D shutdown | +0.0090 | .0057–.0121 | 0.91 |
| Nic Dowd | WSH | F mid-PP | −0.0087 | −.0134–−.0032 | 0.24 |
| Lars Eller | WSH | F mid-PP | −0.0087 | −.0134–−.0032 | 0.30 |
| Brandon Duhaime | WSH | F mid-PP | −0.0087 | −.0134–−.0032 | 0.58 |
| Cole Smith | NSH | F mid-PP | −0.0083 | −.0116–−.0047 | 0.35 |

**Most system-independent (smallest |sys|, ≈0):** Connor Bedard, Ryan Donato, Patrick Maroon,
Tyler Bertuzzi (CHI); Peyton Krebs (BUF); Cam Fowler (STL) — team deployment fingerprints sit at
the league mean, so no part of the number is system-attributable. Read against F14: even the
largest material `sys` here is ~0.010 xG-share points.
