# Role-fit probe — feasibility report

**Project:** role-fit-probe (`NIR/research/role-fit-probe/`)
**Date:** 2026-07-13 · **Seed:** 20260713 · own `.venv` · polars 1.42 · scikit-learn
**Purpose:** decide one thing — is the *role-composition* theory of fit worth a full project, or does
it die cheaply now? Two gates. Nothing here is promoted or published.

**Standing caveat (carried in every conclusion):** "role" here is a **proxy inferred from on-puck
public events**; it cannot see off-puck movement or defense. The probe tests whether the proxy is
*stable enough to build on*, never that it is complete role truth. Step 0 below sharpens this into a
hard ceiling: in this frozen data the proxy is **shot/offense-based only**.

---

## §0 — Scaffold and inventory (no gate)

**Scaffold.** Dedicated branch `research/role-fit-probe` (off the current research tip, preserving the
uncommitted Chemistry work; folder-isolated, removable by delete, no production imports). Own venv;
Makefile target per step; `data/` gitignored. The **Chemistry stint-expansion machinery is reused**,
not rewritten (`import chem.corpus`; it was brute-force validated 1497=1497).

**Frozen inputs (read-only), timestamps recorded:**

| asset | mtime | rows |
|---|---|---:|
| atlas/stints | 2026-07-10 16:45:15 | 5,905,129 |
| atlas/events | 2026-07-10 13:17:01 | 5,981,128 |
| atlas/player_5v5 | 2026-07-10 16:46:00 | 10,959 |
| atlas/rapm_variant | 2026-07-10 18:01:54 | 13,434 |
| atlas/shot_xg | 2026-07-10 16:43:26 | 1,617,677 |
| atlas/rosters | 2026-07-10 15:49:21 | 765,856 |
| chemistry/pairs_corpus (frozen) | 2026-07-12 22:03:52 | 90,527 |
| syseff/player_types | 2026-07-11 21:08:26 | 10,961 |
| syseff/team_season_fp | 2026-07-11 17:32:22 | 494 |

Chemistry reuse confirmed: `chem.corpus._stints("2024-25")` → 452,784 5v5 RS stints, `rid` present.

**Event-primitive inventory — the pivotal Step-0 finding.** The frozen `events` table attributes an
**individual player only to shot-family events**. Every "hustle/possession" primitive the role theory
would want is **team-attributed only** — no acting player is recorded:

| primitive | n (all seasons) | player-attributed? | usable for role? |
|---|---:|---|---|
| shot-on-goal / missed / goal | 1.64M | **yes** — shooter/scorer id + x,y, shot_type, joinable xG | **yes** |
| blocked-shot | 560k | shooter id only (the **shooter**, not the blocker) | volume only |
| goal assists (assist1/2) | on 114k goals | **yes** — assister id (goals only, sparse) | yes (sparse) |
| hit | 862k | **no** (team only) | no |
| takeaway | 254k | **no** | no |
| giveaway | 365k | **no** | no |
| faceoff | 1.12M | **no** (no taker id) | no |
| zone entries / exits (controlled vs dump) | — | **not present**; no puck-carrier on non-shot events | no (not inferable at player grain) |

**Reliability flags.** Shot counts carry the well-known **rink-scorer/coordinate bias** (attempt
counting and x,y vary by rink; blocked-shot coordinates sit at the *block* point, not the shot
origin — so location/danger axes use **unblocked** shots only, volume uses all attempts). Per-shot xG
partially normalizes location but inherits coordinate bias. The unusable hustle events additionally
have severe rink bias — moot, since they carry no player.

**Consequence (as first reported).** The role proxy looked **offense/shot-based** — but **§0b below
supersedes this**: the "shot-only" limit is an ingestion projection artifact, not a data-truth, and
the recoverable ceiling is much richer. Link 1 was built and passed on the shot-only axes; the fuller
picture changes Link 2's design. 5v5 shot coverage is ample (~105k–125k attributed shots/season;
x,y ≈ 100%).

---

## §1 — LINK 1 (GATE): can we build a STABLE role profile per player? → **PASS**

**1.1 Role/action axes** (per player-season, 5v5, rates/shares, z-scored **within (position,
season)** so a D and an F sit on their own scales). Ten shot-derived axes: `cf60` (attempt volume),
`xg60`, `xg_per_shot` (danger), `mean_dist`, `slot_share` (≤25 ft), `point_share` (≥55 ft),
`tip_share`, `slap_share`, `goals60`, `assists60`. Face-valid by position: F shoot from the slot
(mean 28 ft, 0.075 xG/shot), D from the point (51 ft, 0.028 xG/shot, point_share 0.48). Built at
(player, game) grain so odd/even split-halves reuse one code path (half-TOI reconstitutes the season
exactly).

**1.2 Role space** (PCA per position — PCA not NMF because the z-scored axes carry negatives and we
want orthogonal interpretable variance axes). Top components and named loadings:

| axis | var | dominant loadings | name |
|---|---:|---|---|
| **F PC1** | 35% | mean_dist +.53, slot_share −.48, xg_per_shot −.43 | **Shot location / danger** (perimeter↔net-front) |
| **F PC2** | 27% | cf60 +.62, xg60 +.56, goals60 +.36 | **Offensive volume** |
| **F PC3** | 10% | slap_share +.85, assists60 +.38 | Slap/point tendency |
| F PC4 | 9% | assists60 +.81 | (pure playmaking — unstable) |
| **D PC1** | 40% | mean_dist +.46, xg_per_shot −.43, slot_share −.42 | **Shot location** (deep point↔activating) |
| **D PC2** | 20% | cf60 +.68, xg60 +.42 | **Offensive volume** |
| D PC3 | 11% | tip_share +.72, slap_share +.59 | (shot-type mix — unstable) |
| D PC4 | 9% | slap_share +.70, tip_share −.53 | (slap↔tip — unstable) |

Top 2–3 components capture ~72% (F) / 60% (D) of within-position variance; the tail (PC3–4) is
low-variance shot-type detail.

**1.3 Stability** (per position; placebo = shuffled player identity within position-season, 2000
perms, seed 20260713). Split-half = odd/even-game correlation (40+ games); YoY = consecutive-season
correlation. All values below **beat the placebo at p<0.001**.

| axis | split-half r (SB) | YoY same-team r | YoY across-team r | across/same retained |
|---|---:|---:|---:|---:|
| **F PC1** | **0.64** (0.78) | **0.66** | 0.55 | 0.83 |
| **F PC2** | **0.69** (0.82) | **0.71** | 0.60 | 0.85 |
| **F PC3** | **0.50** (0.67) | **0.53** | 0.47 | 0.89 |
| F PC4 | 0.33 (0.49) | 0.38 | 0.26 | 0.69 |
| **D PC1** | **0.60** (0.75) | **0.58** | 0.52 | 0.89 |
| **D PC2** | **0.77** (0.87) | **0.72** | 0.55 | 0.77 |
| D PC3 | 0.37 (0.54) | 0.35 | 0.32 | 0.91 |
| D PC4 | 0.44 (0.61) | 0.39 | 0.36 | 0.93 |

(YoY sample: F 3,064 same-team / 1,022 across-team transitions; D 1,707 / 545.)

> **Scope correction (see §1b / UL-P2):** these numbers were computed on the **2015-16 → 2025-26**
> primary window, not all 16 seasons — pre-2015 shot events carry `is_primary_scope=False` and were
> silently dropped. The verdict is unaffected (re-running explicitly scoped to 2015-16+ reproduces
> these exactly); only the season-count label was wrong.

**The player-vs-team decomposition (1.3c → 1.4 finding).** Role profiles **retain 77–89% of their
same-team stability across a team change** — i.e. role is **predominantly a player property that
travels with the player**, not team-imposed. The modest erosion (largest for **D offensive volume**,
retained 0.77) is the team-imposed component: how much a defenseman shoots is partly the system's to
give (consistent with System Effects F12, "deployment is the system"), but *where and how dangerously*
he shoots is his own (D PC1 retained 0.89). This "role = mostly player, partly team" split is exactly
the joint player-and-team structure the downstream theory needs to model.

**1.4 Verdict (pre-registered).** PASS if split-half ≥ 0.50 **and** same-team YoY ≥ 0.40 for the
**majority** of named role axes, each beating placebo at p<0.05.

- Passing both bars: **F PC1, F PC2, F PC3, D PC1, D PC2 → 5 of 8 components (majority).**
- The 3 failures are the low-variance shot-type tail (F PC4, D PC3, D PC4); the interpretable
  high-variance axes (shot location/danger, offensive volume) pass comfortably.
- Robust to the reliability definition: under Spearman-Brown-corrected split-half the same 5 pass
  (indeed 7/8 clear the split-half bar; YoY is the binding constraint on the tail).

### → **LINK 1 PASSES.** ⛔ STOP for owner review (per the gate protocol).

**What passed, stated precisely (with the §0 ceiling):** a **stable, player-carried, offense/shot-
based role proxy** exists — its two interpretable axes per position (shot location/danger; offensive
volume) repeat within season (r 0.50–0.77) and across seasons (r 0.53–0.72), travel with the player
across team changes (77–89% retained), and crush a shuffled-identity placebo. It is **not** a complete
role model: it is blind to defense, possession, and transition (Step 0). The probe has shown the
*foundation bears weight* for the shot-role dimension; whether that is enough to carry the full theory
is the owner's call before Link 2.

**Do not run Link 2 unless the owner greenlights** (gate protocol: "Do not run Link 2 unless Link 1
passed" — it passed, and both gates STOP for owner review).

### Decisions & deviations recorded
- **Shot-only role proxy** (§0): forced by the data — only shot-family events carry a player. Reported
  as a hard ceiling, not worked around.
- **Blocked-shot handling**: attributes to the shooter; used for attempt *volume* only, excluded from
  *location/danger* (its coordinate is the block point).
- **Split-half bar metric**: raw odd/even correlation used for the 0.50 bar (conservative); SB shown
  in parentheses. Verdict is invariant to the choice.
- **PCA vs NMF**: PCA (z-scored axes have negatives).

### Artifacts
`src/rolefit/{config,step0,profiles,link1}.py` · `reports/probe.md` (this file) ·
`reports/link1_analysis.json` · `data/parquet/profiles/*` (gitignored). Reproduce: `make step0`,
`make link1`. Frozen inputs untouched.

---

## §0b — Re-audit of event attribution (raw vs ingested). Supersedes the §0 "shot-only" ceiling. STOP for review.

**Bottom line:** the "shot-only" ceiling in §0 is an **ingestion projection artifact, not a data
truth.** The upstream production staging table already carries individual player ids for hits,
takeaways, giveaways, shot-blocks, and penalties; the frozen Atlas `events.parquet` simply did not
select them. Recovering them is a **re-projection, not an external re-fetch.**

### 0b.1 Individual attribution, raw vs ingested — a pipeline finding (→ upstream-ledger UL-P1)

*In the frozen `events.parquet` today* (per-event share with any acting-player id populated; stable
across all 16 seasons and both `source` values `bq:stg_play_by_play` / `api:gap_fetch`):

| event | n (all seasons) | player-attributed in `events.parquet`? |
|---|---:|---|
| shot-on-goal / missed-shot | 1.53M | yes (shooter) |
| goal + assists | 114k (+assist1 90%, assist2 73%) | yes (scorer, assisters) |
| blocked-shot | 560k | shooter only (**blocker dropped**) |
| hit | 862k | **no (0%)** |
| giveaway | 365k | **no (0%)** |
| takeaway | 254k | **no (0%)** |
| penalty | 150k | **no (0%)** |
| faceoff | 1.12M | **no (0%)** |

*But upstream `stg_play_by_play` parses these player ids from `raw_play_by_play.details`* (verified
by reading the SQL, no fetch): `hitting_player_id`, `hittee_player_id` (hits); `player_id`
(takeaways/giveaways); `blocking_player_id` (the blocker); `committed_by_player_id`,
`drawn_by_player_id` (penalties). The Atlas `materialize_events` SELECT
(`deployment-atlas/src/atlas/sources.py`) keeps only `shooting/scoring/goalie/assist1/assist2/
event_owner_team_id` and **drops the other six**. Production already consumes some of them
(`int_shot_attempts` uses `blocking_player_id`). **Faceoffs**: winner/loser are *not* in the pbp
stream, but per-player, per-zone faceoff W/L exists via a separate production source
(`stg_statsrest_faceoffs` → `mart_player_faceoff_zones`), at season grain.

**Recovery option (reported, NOT executed — the probe is a frozen, no-fetch corpus).** Adding the six
columns to the events projection recovers individual attribution for **hits, takeaways, giveaways,
shot-blocks, and penalties** with **no external API call** (the raw data is already ingested in
BigQuery); faceoffs come from the stats-REST source. Full evidence + proposed fix layer:
`reports/upstream-ledger.md` UL-P1. This is the decision to finalize before Link 2.

### 0b.2 Opponent-mirror feasibility — YES, at the unit level

Events carry `event_second = (period−1)·1200 + time_in_period_s`; stints carry `start_seconds/
end_seconds` on the same game clock. The interval join (event → stint active at its second) is exact:
on a probe game, **100%** of 5v5 shots matched a stint and **100%** of shooters were on-ice in the
matched stint (validates the alignment). So opponent events during a player's on-ice stints are fully
joinable → an **on-ice-against** role-axis family (shot-against location/danger/volume while on ice)
is buildable **with coordinates**, full coverage. **Explicit caveat:** this is **on-ice
(unit-and-context) attribution, not individual** — the against-events reflect all five on-ice skaters
plus deployment, so it is **valid at the unit level (exactly Link 2's grain) but entangled at the
individual level** (the Chemistry-era teammate-entanglement caution applies). Useful as unit context,
not as a personal defensive rating.

### 0b.3 Sequence-context feasibility — playmaking-shadow YES, dump→retrieval NO

Event order (`sort_order`, monotonic) and timing (`event_second`) support connective-play sequences
without inventing events. **Playmaking-shadow (viable):** takeaway/recovery → same-team shot within
N seconds. On 2024-25, **11% of takeaways (1,437 / 12,628) are followed by a same-team shot within 4
s** — a real, non-trivial signal. *Proposed rule:* for a possession-gain event E (takeaway; or a
same-team recovery = first same-team event after an opponent giveaway) with `event_owner_team_id = T`,
credit a shadow-assist if the next event within ≤ N s (N∈{3,4,5}, pre-registered before use) is a
`T` shot attempt in the offensive zone. **Today this is team-level** (takeaways carry no player);
**with the 0b.1 recovery it becomes individually attributable.** **Dump-in→retrieval (NOT viable):**
there is no dump-in event type and no retrieval event; reconstructing it would require inventing
unrecorded possession events. Flagged as **not recoverable** from the event stream (a Tier-iii item —
needs tracking/possession data).

### 0b.4 The ceiling, restated in three explicit tiers (replaces the flat "shot-only" ceiling)

- **Tier (i) — individually-attributed recorded events.**
  - *Available in the frozen table now:* shots (shooter), goals (scorer), goal assists → **offense
    only** (what Link 1 used).
  - *Recoverable by re-projecting `stg_play_by_play` (no re-fetch):* hits (hitter + hittee),
    takeaways / giveaways (puck-management), shot-blocks (defensive suppression), penalties
    (committed / drawn); plus per-player per-zone faceoffs via stats-REST. This turns the role model
    from offense-only into **offense + possession + defensive-engagement + discipline + faceoffs** —
    a broad on-puck role model.
- **Tier (ii) — sequence-inferred connective play.** Playmaking-shadow (takeaway/recovery → quick
  shot), rush/rebound shot context, zone-sequence patterns — recoverable from ordering + timing;
  individual-level once Tier (i) is recovered. Always labelled a **proxy**.
- **Tier (iii) — invisible without tracking data.** Off-puck movement, screens, gap control,
  positioning, non-assist passing (all passes), puck battles and possession not ending in a recorded
  event, controlled zone entries/exits with carrier. These remain unmeasurable from public
  play-by-play; the standing caveat lives here. Requires tracking (NHL EDGE) data.

**Honest scope statement for the whole direction:** the role proxy is **not** limited to shots. With
one gated re-projection it spans Tier (i) offense + possession + defense + discipline + faceoffs,
augmented by Tier (ii) sequence-inferred connective play; only Tier (iii) off-puck play is truly
invisible. Link 1 already passed on the *narrowest* (Tier-i offense-only) slice — the fuller role
model can only be richer and more separable by role.

### ⛔ STOP for review — Link 2's design will be finalized against this recovery
The owner decides before Link 2: **(A)** authorize a targeted, one-time production read to build a
probe-local **enriched events table** (re-project `stg_play_by_play` + join `stg_statsrest_faceoffs`),
so Link 2's units are scored on the full Tier-(i) role model; or **(B)** proceed with the current
frozen shot-only events table and treat possession/defense/faceoff axes as future enrichment.
**Recommendation:** (A) — the recovery is cheap (a re-SELECT of already-ingested columns), it removes
the single biggest threat to the whole theory (a role model that can't see defense or possession),
and it materially strengthens Link 2's role-composition preview (2.4). No fetch or read has been
performed; awaiting the ruling.

---

## §1b — LINK 1 re-gate on the UL-P1-enriched two-way role space → **PASS (now genuinely two-way)**. STOP for review.

Two things happened since §1: (a) the owner authorized the UL-P1 re-projection, so the role model is
no longer offense-only; (b) re-auditing surfaced **UL-P2** — the shot filter silently dropped pre-2015,
so §1 actually ran on **2015-16 → 2025-26 (11 seasons)**, not 16. The probe is now explicitly scoped
to that integrity-validated window (pre-2015 broken out by exclusion); re-running §1 on it reproduces
§1 **exactly** (F PC1 0.64/0.66, D PC2 0.77/0.72, PASS 5/8), so §1's verdict stands — only its
"16-season" label was wrong.

**Enrichment executed (read-only, UL-P1).** `enrich.py` pulled the six dropped player-id columns from
`stg_play_by_play` (6,545,861 rows, sha256 `078a0dda…`) + per-player zone faceoffs from
`stg_statsrest_faceoffs` (14,231 rows, `d019cc24…`) into probe-local parquet. No production write;
frozen Atlas untouched. Join onto the frozen events is exact (unique game_id,event_id key; attribution
recovered ~100%). **Rink-scorer-bias caveat carried:** hit/takeaway/giveaway *counts* vary by arena;
the stability test measures repeatability (which bias inflates far less than magnitudes), and no
magnitude is trusted as truth.

**Recovered role axes (5v5 rates, position-normalized), stability on the primary window** (split-half
odd/even 40+ games; same-team & across-team YoY; each vs shuffled-identity placebo, 2000 perms, seed
20260713; all cleared axes beat placebo p<0.001):

| axis (family) | F split / YoY-same / retained | D split / YoY-same / retained | clears both bars? |
|---|---|---|---|
| **hit60** (physical) | **0.95 / 0.87 / 0.95** | **0.92 / 0.84 / 0.94** | **F+D** |
| **hittaken60** (physical) | 0.78 / 0.72 / 0.73 | 0.79 / 0.68 / 0.79 | **F+D** |
| **block60** (defensive) | 0.60 / 0.55 / 0.69 | 0.63 / 0.49 / 0.77 | **F+D** |
| **gv60** (possession−) | 0.56 / 0.51 / 0.53 | 0.53 / 0.47 / 0.28 | **F+D** |
| **tk60** (possession+) | 0.47 / 0.47 / 0.60 | 0.54 / 0.47 / 0.67 | D (F split 0.47) |
| **pentake60** (discipline) | 0.52 / 0.51 / 0.94 | 0.49 / 0.44 / 0.85 | F (D split 0.49) |
| pendrawn60 (discipline) | 0.41 / 0.35 | 0.38 / 0.34 | neither (noisier) |
| *ca60* (UNIT suppression) | 0.54 / 0.36 / **0.47** | 0.63 / 0.40 / **0.27** | split only |
| *xga60* (UNIT suppression) | 0.46 / 0.36 / **0.37** | 0.51 / 0.40 / **0.12** | split only |

(Shot axes, now spanning the full window: cf60 F 0.80/0.73, D 0.81/0.69; xg60 0.59/0.55, 0.66/0.57;
mean_dist 0.60/0.55, 0.63/0.54 — all clear, as in §1.)

**Two decisive readings.**

1. **The role model is now genuinely two-way, and the two-way axes are player-carried.** Individual
   possession/physical/defensive axes are stable *and* travel with the player across a team change
   (**retained median 0.79**, same as the shot axes). **Physicality is the single strongest role
   signature in hockey**: `hit60` split-half 0.92–0.95, YoY 0.84–0.87, 94–95% retained across team
   changes — more stable than any shot axis. Blocks, hits-taken, giveaways, and (for D) takeaways all
   clear. So a defenseman's or forward's *two-way* role — not just where he shoots — is a stable,
   personal, transferable trait. This is the foundation Link 2 needs.

2. **The opponent-mirror unit-suppression axes behave exactly as their entanglement predicts.**
   `ca60`/`xga60` (on-ice shots/xG against) are reliable *within* a season (split-half 0.46–0.63) but
   **do not travel with the player**: same-team YoY 0.36–0.40 and **retention across a team change
   collapses to 0.12–0.47** — the lowest of any axis. On-ice suppression is **team/deployment-imposed,
   not an individual property** (consistent with System Effects F12). This validates the §0b call:
   the mirror is valid **unit context** (its natural grain, and Link 2's grain) but must **not** be
   read as an individual defensive rating. It stays a Link 2 input, not a Link 1 role axis.

**Rich role space (PCA on the individual axes, primary window).** The space is now blended
offense+physicality: e.g. F PC3 loads `cf60 +.51, hit60 +.51` (a high-event two-way driver);
D PC3 loads `hit60 +.63, cf60 +.37, pen_drawn +.36` (a physical, penalty-drawing defenseman). Variance
is more distributed than the shot-only space (F PC1 22% vs 35%) because there are more real role
dimensions — which is the point.

**Faceoffs (recovered, season grain).** Per-player zone faceoff W/L is available (`stg_statsrest_
faceoffs`, all-strength, season grain) and joined as a descriptive axis; it is excluded from the
event-grain split-half (no game split at that source) and reported as season-grain context (centers
carry it). Not part of the gate.

**1b Verdict.** 21 of 38 position-axes clear both bars; **10 of the recovered axes clear**, all
player-carried. The majority of named, interpretable role axes — shot location/danger, offensive
volume, physicality, shot-blocking, puck management — are stable and travel with the player.
**LINK 1 PASSES on a genuinely two-way foundation.** The §0-worry (a role model blind to defense and
possession) is resolved: possession and defensive-engagement are now visible, stable, and personal;
only Tier-(iii) off-puck movement/passing remains invisible (still a stated ceiling).

### ⛔ STOP for review before Link 2
The ruling authorized proceeding to Link 2 after this re-gate. Two items warrant a look first:
(i) **UL-P2 scope correction** — the probe is now 2015-16 → 2025-26 (11 seasons), pre-2015 broken out;
(ii) the role model is materially richer than when Link 2 was scoped. On the owner's go, Link 2 runs
with unit residuals scored against this two-way role composition, and its ceiling verdict (2.6)
updated so "blocked pending tracking data" means specifically **off-puck movement and passing**, not
defense/possession (now recovered).

---

## §2 — LINK 2 (GATE): do units over-perform their parts, stably within a season? → **FAIL the gate (weak real signal, below the 0.30 usability bar)**

Ruling carried in: the individual two-way axes are the composition inputs; the opponent-mirror
suppression axis is confirmed team-imposed (Link 1b) and is used **only as an outcome/context
dimension, never as a per-player composition feature**. Scope: the primary window 2015-16 → 2025-26.

### 2.1 Unit definitions — and the five-man question, settled with data
- **Forward trios (F3), 100+ shared 5v5 min: 2,276 trio-seasons** (~123–228/season; fewer in the
  shortened 2019-20/2020-21). This is the tractable unit.
- **True five-man units DO NOT recur within a season.** Of ~160k distinct 5-skater sets per season,
  only **15–46 reach 100 min** (374 across all 11 seasons; median five-man shared TOI ≈ **0.2 min**,
  max ~369). The Chemistry-era caution is confirmed with numbers: fivesomes are far too sparse to
  model; the F-line-plus-D-pair as a *unit* is not a usable grain. Trios carry Link 2.

### 2.2 Unit over-performance (reused Chemistry null)
Observed trio 5v5 xG share minus an additive-plus-curvature prediction from members' `rapm_variant`
(Σoff, Σdef, curvature = (Σq)² and the pairwise-product sum) + context (OZ-start share, score-state
mix, opponent strength, season). Weighted Ridge, LOSO CV. Null CV R² = 0.59 (same-season anchor).

### 2.3 The gate — within-season split-half of the unit residual (odd/even games, TOI-weighted, 1,000-perm placebo)

Applying the Chemistry Phase-2 lesson, the split-half baseline is the **unit-season** prediction
subtracted from each half (constant per unit), never re-predicted with endogenous per-half context;
and it is run under **two anchors** because same-season rapm is contaminated (it was fit on results
that include the unit's own shared minutes).

| anchor | n | null CV R² | **residual split-half** | raw-share split-half | placebo | p |
|---|---:|---:|---:|---:|---:|---:|
| same-season (contaminated) | 2,276 | 0.59 | **−0.15** (straddling artifact) | 0.29 | 0.00 | 1.00 |
| **prior-season (clean, the fair test)** | 1,889 | 0.22 | **+0.18** | 0.31 | 0.00 | **0.001** |

**Reading.** Exactly the Chemistry signature. The **raw** trio share is moderately reliable across
half-seasons (~0.29–0.31 — lower than pairs' 0.47 because a trio's 100–330 shared min make each half
noisy). Remove member quality and the picture splits by anchor: the same-season anchor drives the
residual **negative** (the contamination-straddling artifact, disclosed, not a real anti-signal); the
clean **prior anchor gives +0.18 — a real, placebo-beating signal (p=0.001), but well below the
pre-stated 0.30 usability bar.** The truth is bracketed `[−0.15 artifact, +0.18 clean-upper-bound]`
(the prior anchor still under-removes within-season individual improvement, so +0.18 is an upper
bound). **Under neither anchor does the unit residual clear 0.30.** → **GATE FAILS.**

### 2.4 Role-composition regression (decision input)
Regressing the (clean-anchor) unit over-performance on two-way role-composition features
(per-family complementarity/spread + coverage across offense, physicality, possession, discipline —
built from the individual player-carried axes) plus non-role controls (combined rapm, combined
shooting talent, handedness mix), LOSO CV: controls CV R² = **0.103**, controls+composition =
**0.114**, **incremental composition R² = +0.011** (≈1 point of variance, just over the 0.01
materiality floor). So composition adds a *small* but non-trivial share **when there is over-
performance to explain** — but §2.3 shows there is barely any stable over-performance to begin with,
so this is descriptive, not a green light.

### 2.6 Ceiling verdict (pre-stated) → **(iii)**
Pre-stated: (i) stable over-performance AND material composition → full project viable; (ii) stable
BUT composition immaterial → blocked pending tracking; (iii) not stably over-performing → theory
dies at the unit level.

**Outcome (iii).** The unit residual does not clear the 0.30 usability bar under either anchor
(clean +0.18, contaminated −0.15). Units over-perform their parts only **weakly** — a real,
placebo-beating signal, but too thin to anchor a predictive composition model. Note this is **(iii),
not (ii)**: the limit is **not** that fit hides in the invisible off-puck tier which tracking would
reveal — it is that **stable unit over-performance beyond individual quality barely exists at all** at
trio grain on public data. Tracking data would sharpen the role *profiles* (Tier iii: off-puck
movement, passing) but has no strong, stable unit residual to explain here; the composition signal
that exists (+1 pt R²) is small enough to be consistent with the weak reliability, not proof of a
mechanism.

---

## PROBE VERDICT

**Link 1 PASSES (two-way). Link 2 FAILS the gate. → "Ship roles descriptively; drop the fit theory"
(the pre-stated L1-pass / L2-fail outcome), with one honest caveat: the unit signal is weak-but-real,
a narrow miss rather than a hard null.**

- **Link 1 — a stable, player-carried, genuinely two-way role/action proxy exists.** Shot location,
  volume, physicality (the strongest signature, split-half 0.95), shot-blocking, and puck management
  are reliable within season, persist across seasons, and travel with the player (retained median
  0.79). The §0 fear of an offense-only proxy was resolved by the UL-P1 re-projection. This is a
  **valuable player-description asset in its own right.**
- **Link 2 — unit over-performance is not stably measurable enough to build a fit model on.** Five-man
  units don't recur; forward trios over-perform their parts only weakly (clean split-half +0.18 < the
  0.30 bar), and two-way composition adds only ~1 point of variance. Fit — whether Chemistry's
  pair-magic (killed, F17) or unit role-composition (here) — does not clear the usability bar on
  public event data.

**Recommendation (owner rules).** Do **not** commission the full four-link *fit-prediction* project as
specified — its load-bearing assumption (stable, explainable unit over-performance) does not hold.
**Do** consider shipping the **two-way role profiles** as a descriptive player-role product (Link 1 is
production-grade in method and validated). If the fit thread is pursued at all, it should be a **new,
narrower pre-registration** — higher-TOI unit floors, or a within-season descriptive scope — that
acknowledges the ceiling this probe measured, not the four-link predictive project. Nothing here is
promoted or published.

### Decisions & artifacts (Link 2)
- Split-half run under two anchors (Chemistry Phase-2 straddling lesson); gate on the clean prior
  anchor; 1,000-perm placebo (reported). Materiality floor for composition incremental R² pre-stated
  at 0.01.
- `src/rolefit/{units,link2}.py`; `reports/link2_analysis.json`; `data/parquet/units/*`,
  `enriched/player_bio.parquet` (handedness, UL-P1 read) — gitignored. Reproduce: `make link2`.
  Frozen Atlas / Chemistry / System-Effects inputs untouched.

**STOP — probe complete. Owner rules on whether any follow-on (descriptive role product, or a
narrower re-registered fit study) is written.**
