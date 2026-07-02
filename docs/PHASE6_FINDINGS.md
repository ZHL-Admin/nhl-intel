# Phase 6 findings — impact context + WOWY

Confirmed from real sources (`models_ml/train_rapm.py`, `docs/methodology/isolated-impact.md`,
`serving_tables.yml`, the committed WOWY mart `.sql`, and `frontend/src/pages/PlayerProfile.tsx`).
Nothing here is guessed. Written 2026-07-02 on branch `feature/phase6-impact-context` (branched
from `master`, which carries the cleanup commits and the five WOWY model files; `finalization`
lacks them).

## 1. `nhl_models.player_impact` columns and sign convention

Write list (`train_rapm.py:413-417`), clustered by `(season_window, player_id)`:

| column | meaning |
|---|---|
| `player_id` | INT64 |
| `season_window` | join key (see §2) |
| `off_impact` | centred offence coefficient, xGF/60, **higher = better** (`train_rapm.py:254`) |
| `off_sd` | bootstrap SD of `off_impact` |
| `def_impact` | **−(centred defence coefficient)**, already sign-flipped so **higher = better** (`train_rapm.py:251`; isolated-impact.md:32-34) |
| `def_sd` | bootstrap SD of `def_impact` |
| `pp_impact`, `pp_sd` | power-play offence impact + SD (5v4) |
| `pk_impact`, `pk_sd` | penalty-kill defence impact + SD (4v5), sign-flipped |
| `toi_min` | 5v5 minutes (the TOI field; qualification uses this) |
| `alpha` | selected ridge lambda |
| `model_version` | e.g. `rapm_v1` |

**Total impact = `off_impact + def_impact` directly** (both already higher-is-better after
centring/negation). No further sign handling needed. Confirmed, not assumed.

## 2. `season_window` format (the context-layer join key)

- **Single season:** plain `"YYYY-YY"`. Single-season rows exist for each of
  `SINGLE_SEASONS = ["2021-22","2022-23","2023-24","2024-25","2025-26"]` (`train_rapm.py:46`).
- **Multi-year window:** `f"{win[0]}_{win[-1]}"` where `win = SINGLE_SEASONS[-3:]`
  (`train_rapm.py:358-360`), i.e. currently **`"2023-24_2025-26"`** — a single 3-season
  weighted window. Weights `WINDOW_WEIGHTS = [0.3, 0.6, 1.0]` oldest→newest
  (`train_rapm.py:47`; isolated-impact.md:38: weighted 1.0/0.6/0.3 newest→oldest).
- **Discriminator:** multi-year `season_window` **contains `_`**; single-season does not.
- **Delta join (Phase 6.3):** for season S, `single_total` = row where `season_window = S`;
  `multi_total` = the window row (`season_window LIKE '%\_%'`). Only one window exists, so
  `single_vs_multi_delta = single_total(S) - multi_total(window)`. Left-join the window row and
  null the delta when a player has no window row (documented in 6.3).

## 3. WOWY / on-ice mart columns (committed `.sql`, verified)

**`mart_player_wowy`** grain `(season, team_id, player_id [focal], partner_id)`, directional:
`toi_together_sec, focal_without_partner_toi_sec, partner_without_focal_toi_sec,
xgf_pct_together, xgf_per60_together, xga_per60_together, xgf_pct_focal_without_partner,
xgf_pct_partner_without_focal, together_minus_focal_alone,
**partner_with_focal_minus_partner_without**, small_sample`.

- **Carry field (Phase 6.2):** `partner_with_focal_minus_partner_without`
  ( = `xgf_pct_together − xgf_pct_partner_without_focal` ). Positive = the partner posts a
  better on-ice xGF% *with* the focal than *without* → the focal elevates partners.
- `small_sample = toi_together_sec < 3000` (50 min, decision D17).

**`mart_player_toi_matrix`** grain `(season, team_id, player_id_a < player_id_b)`:
`toi_together_sec, games_together`. Stored **once per unordered pair** — 6.2 must build a
symmetric view (union the mirror) before computing per-player max share / entropy.

**`mart_player_onice`** grain `(season, player_id, team_id)`: raw sums `toi_5v5_sec,
off_toi_5v5_sec, on_xgf, on_xga, on_cf, on_ca, off_xgf, off_xga, off_cf, off_ca` plus
`on_ice_xgf_pct, off_ice_xgf_pct, on_ice_cf_pct, off_ice_cf_pct, rel_xgf_pct, rel_cf_pct`.
`rel_xgf_pct` is the true on-ice-minus-off-ice relative used in 6.3.

## 4. ImpactValuePanel mount + data contract

- **Rendered in exactly one place:** `frontend/src/pages/PlayerProfile.tsx:861`:
  `<ImpactValuePanel value={playerDetail.value} name={playerDetail.player_name} />`.
- Data source is the `value` block of the `/players/{id}` `PlayerDetail` response (Impact/RAPM
  vs Value/GAR, with an uncertainty band rendered as a percentile-point visual proxy;
  `ImpactValuePanel.tsx:2-37`). Its own doc-comment says the "least repeatable" claim traces to
  the measured stability r-values.
- **Attach point (6.5/6.6):** the new impact-context readout attaches on **PlayerProfile**,
  beside `ImpactValuePanel`, fed by a context block. Per 6.5 the block is attached to
  `/players/{id}/summary` or a sibling; PlayerProfile already calls both `/players/{id}` and
  `/players/{id}/summary`, so either is reachable there.

## 5. Stability figure + qualification floor (for tier-level confidence, not invented)

- **YoY stability** (isolated-impact.md:64-66): single-season **offence** impact, players with
  **≥200 5v5 min**, adjacent-season Pearson r = 0.47, 0.42, 0.46, 0.37, **mean r = 0.43**
  (expected 0.3–0.5). Use **0.43** as the headline tier-confidence figure. A secondary framing
  (isolated-impact.md:81) gives the isolated *rate* r ≈ 0.38; cite 0.43 as primary.
- **Qualification floor:** **200 5v5 minutes** (`toi_min >= 200`, used in `train_rapm.report()`;
  isolated-impact.md validation). In seconds for `mart_player_onice.toi_5v5_sec`: **≥ 12000**.
- **Entangled → wider shown band (6.6):** isolated-impact.md:67-72 — low-TOI/entangled players
  carry small absolute SD (shrinkage toward 0), so a near-zero impact means *unproven*, not
  *confidently average*. The UI should widen the shown band for entangled players rather than
  read the point estimate at face value.

## 6. Serving state (confirms 6.4 is needed)

`serving_tables.yml:83` already serves `player_impact` (`kind: source, cap: full, indexes
[player_id, season_window]`). **None** of `mart_player_wowy / _onice / _toi_matrix /
_entanglement / _carry / _impact_context` is in `serving_tables.yml` yet — so nothing reaches
the app until Phase 6.4 adds them + exports to DuckDB. Confirmed.

## Gate

All expected fields exist and match the names above. No missing or differently-named field.
Proceeding to 6.1 (materialize + validate).
