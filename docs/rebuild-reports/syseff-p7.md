# System Effects — Phase 7 (production promotion, gated)

**Date:** 2026-07-11 · **Branch:** `promote/system-effects-p7` · **Status:** staged, dbt-reversible,
**STOP for review** before merge/deploy. `research/` untouched (read-only). Shipped claims: **none
predictive** — everything promoted is **descriptive data, clearly marked**.

## What is promoted (per the written authorization)
| table | grain | how | reconciliation |
|---|---|---|---|
| `mart_syseff_regime_ledger` | (team, coach, span) — raw | **derived live** in dbt from coaches | exact (0 mismatches) |
| `mart_syseff_regime_ledger_consolidated` | consolidated regime (K=4) | frozen research values, daily-refreshed | exact (201) |
| `mart_syseff_fingerprints_v2` | (team, regime) | **frozen research values** (re-derivation fails gate) | exact by construction |
| `mart_syseff_fingerprint_metric_status` | (metric) | frozen (reliability + sensitivity + caveats) | exact |
| `mart_syseff_schedule_adjustment` | (player, season, team) | frozen research values | exact by construction |

## What is NOT promoted
The **portability surface** and the **Design B model** remain research-internal under the 4.1a
materiality gate. Anything from the **opponent style-matchup** track (F15, killed) is not promoted.
Reasons in the claims dossier (§7.3).

---

## 7.1 Promotions and reconciliation

### (a) Regime ledger — DERIVED, reconciles exactly

The raw ledger (`mart_syseff_regime_ledger`) is derived live in dbt from
`stg_syseff_game_coaches` (coaches parsed from `raw_game_right_rail.gameInfo`), by gaps-and-islands
on schedule order (`game_id`), season taken from the `game_id` prefix — **UL-1-immune**, exactly as
the frozen research build. The consolidated grain (K=4 transient absorption to a fixpoint) is not
naturally expressible in incremental SQL, so it is materialized from the frozen research output and
refreshed daily (see §7.1d).

**Reconciliation** — the live production coach source vs. the exact source the research used:

| slice | games | home-coach mismatches | away-coach mismatches |
|---|---:|---:|---:|
| 2024-25 + 2025-26 (`stg_game_context`) | 3,340 | **0** | **0** |

The 2010-11…2023-24 coaches are the research backfill itself, loaded verbatim (§7.1c), so the full
ledger equals the frozen research tables **by construction** (raw **235**, consolidated **201**).
The gaps-and-islands algorithm is identical to `syseff.regime_ledger.{annotate_regimes,build_ledger}`.
Row counts are asserted exact; **any divergence at build time stops the phase** (singular tests
`tests/assert_syseff_regime_ledger_unique.sql`).

### (a′/b) fingerprints_v2 and schedule_adjustment — RE-DERIVATION FAILS THE GATE → frozen source of record

Re-deriving fingerprints from production sources was tested and **diverges beyond float tolerance**
— the production shot/stint backbone (rebuilt segments) differs from the frozen Atlas layer, and
production carries **no per-regime, score-close, deployment, or PK grain** at all. Measured
divergence, production `mart_team_identity` (season grain, all-situations) vs the frozen fingerprint
shares (2023-24, 32 teams):

| metric | mean \|Δ\| | max \|Δ\| |
|---|---:|---:|
| rush_share_for | 0.0033 | 0.0107 |
| cycle_share_for | 0.0045 | 0.0125 |
| forecheck_share_for | 0.0023 | 0.0072 |
| point_shot_share_for | 0.0032 | 0.0089 |

These are 3–4 orders of magnitude above any float tolerance, and the deployment/PK/score-close
metrics have **no production source at all**. Per the "any divergence stops the phase" rule,
**re-derivation is stopped**. Because the PO authorized promoting fingerprints_v2 and
schedule_adjustment as *descriptive data*, they are promoted as the **frozen research values**
(dbt seeds → thin mart models), which reconcile exactly by construction. `schedule_adjustment` is
identical in situation (it needs the frozen-Atlas-stint xG the production backbone diverges from).
**Decision surfaced for the gate:** confirm frozen-research-as-source-of-record (recommended), or
defer these two until the production rebuild backbone reconciles to the Atlas layer (UL-2).

### (c) Coach-data ingestion promotion (keeps the ledger current)

- **Daily flow** (`dags/nhl_daily.py`): the right-rail capture now tags provenance
  (`_source="right_rail_daily"`, `_game_final`) and, for **FINAL** games, does an **idempotent
  delete-then-insert** per `game_id` — the settled coach-of-record (plus referees, linesmen,
  scratches, all already in `gameInfo`) — matching the shift-fallback convention.
- **Backfill path taken:** `ingestion/backfill_coach_loader.py` loads the research project's
  **cached** 2010-24 right-rail payloads (16,526 games on disk) into `raw_game_right_rail` via the
  **normal loader** (`load_json_to_bigquery`), idempotent, provenance
  `_source="right_rail_backfill_2010_24"`. **No refetch** — the raw payloads already exist on disk;
  we load them, not re-download. One-time script, not wired into the DAG, imports no research code.

### (d) Regime-ledger maintenance logic (wired to daily cadence)

- **Extend-current-regime vs. new-regime:** on each day's FINAL games, `stg_syseff_game_coaches`
  gains the settled coaches; `mart_syseff_regime_ledger` recomputes gaps-and-islands — a game whose
  coach **equals** the team's previous game's coach **extends** the current regime (no new row);
  a game whose coach **differs** opens a **new regime** (new `start_game_id`). This is pure
  recomputation, so it is correct without incremental state.
- **Consolidated grain:** a small daily step re-runs `syseff.regime_ledger.consolidate_ledger`
  (K=4) on the live raw ledger and writes `mart_syseff_regime_ledger_consolidated`, scheduled on the
  **same cadence** as the daily marts (after the raw ledger builds). Documented so the consolidated
  grain never drifts from the raw.

---

## 7.2 Integration spec (flag-only — NO user-facing changes in this work order)

Where these tables *would* be consumed, for the product owner's planning; nothing is wired to the
frontend here.

| surface | table(s) | intended use |
|---|---|---|
| **Team pages — a "Bench" section** | `mart_syseff_regime_ledger_consolidated`, `mart_syseff_fingerprints_v2` (+ `_metric_status`) | the current coach, tenure (games/seasons), and the coach's **validated deployment fingerprint** (zone-start polarization, top-6 concentration — with caveats). Style/PK shown only as descriptive context. |
| **Player pages — usage context** | `mart_syseff_fingerprints_v2`, `mart_syseff_regime_ledger_consolidated` | "under the current coach, this team runs \<deployment profile\>" — deployment only; no per-player system claim. |
| **Trade Builder / Contract Grader** | (research-internal portability — **not promoted**) | IF ever surfaced, the internal **portability receipt** would attach here; it stays internal under the 4.1a materiality gate and is out of scope for this work order. |
| **Schedule context (any standings/strength view)** | `mart_syseff_schedule_adjustment` | a descriptive footnote on how easy/hard a player's opponent set was (±~0.003 xG-share pts typical). No predictive use. |

---

## 7.3 Claims dossier — what each promoted table may say

**Coaching/style — the F12-extended nuance (quote verbatim wherever a promoted table touches coaching or style):**

> On-ice **style** is largely a **roster property**, not a system a coach installs — and this holds
> across **summers**, not only mid-season changes. What a coach demonstrably owns is **deployment**
> (who plays, how they start). The summer style-install signal is **positive but too weak to confirm
> in sixteen years of transitions (p=0.08); it is never proven zero.** *(Observational for the
> summer extension.)*

| table | MAY say | MUST NOT say | required caveat |
|---|---|---|---|
| `regime_ledger` (both) | who coached which team over which games; tenure; mid-season vs summer change | — | none (factual) |
| `fingerprints_v2` — **zone_start_polarization** | "the coach's deployment fingerprint" (coaching-sensitive: ratio 1.9, p=0.0005; persists YoY r=0.70) | any *style* claim | — |
| `fingerprints_v2` — **top6_fwd_toi_share** | coaching-sensitive deployment axis | primary portability claims | **STABILITY CAVEAT: no YoY within-regime persistence (Phase 3.5); zone-start polarization is the primary deployment axis.** |
| `fingerprints_v2` — **style + PK metrics** | "descriptive style/PK context for this regime" | "the coach installs/owns this style/PK" | the **F12-extended nuance** above |
| (`home_away_strictness`) — **not carried** | — | anything | **FAILED VALIDATION (Atlas Phase 5.6): descriptive only; excluded from fingerprints_v2.** |
| `schedule_adjustment` | "opponent-strength schedule context, descriptive" | any prediction; any style-matchup claim | **DESCRIPTIVE ONLY, no predictive claim. Typical \|adjustment\| 0.003, p90 0.0065.** |

Per-metric reliability + coaching-sensitivity is carried as columns in
`mart_syseff_fingerprint_metric_status` — the machine-readable gate for these claims.

### Not promoted (with one-line reasons)
- **Portability surface** — research-internal; 5A returned INVESTIGATE (+0.81%, < 3% bar); descriptive-only under the 4.1a materiality gate.
- **Design B model** — the estimator behind portability; not a shippable claim (same reason).
- **Opponent style-matchup (any)** — **killed (F15):** interactions add 0.00014 R², do not replicate across eras (r = −0.045).

---

## STOP

Staged on `promote/system-effects-p7`, dbt-reversible (drop the models/seeds; revert the ingestion
diff). Reconciliation gates encoded as singular tests. **Awaiting product-owner review** before
`dbt seed` / `dbt run` / DAG deploy and the one-time `backfill_coach_loader` run. After this closes,
the **Jolt** addendum (event-time study of the new-coach result bump) follows as the post-close
research thread.

### Artifacts
dbt: `models/staging/stg_syseff_game_coaches.sql`, `models/mart/mart_syseff_*.sql`,
`models/mart/_syseff__models.yml`, `seeds/syseff/*.csv`, `tests/assert_syseff_*`. Ingestion:
`dags/nhl_daily.py` (right-rail idempotent + provenance), `ingestion/backfill_coach_loader.py`.
