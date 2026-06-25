# Trade engine: multi-team trade evaluation

The trade engine evaluates a *proposed* trade. It nets assets across N teams, models retention,
flags cap compliance, overlays fit, and returns a **per-team multi-axis decomposition** — never a
single grade. It is backend + model only (`backend/services/trade_engine.py`, exposed at
`POST /tools/trade-evaluate`); the trade-builder UI is a separate pass that consumes this contract.

It reads only the built value foundation — `mart_tradeable_assets` (talent value in WAR, surplus in
cap-share and dollars, with bands) and `mart_player_contracts` (committed cap) — via the DuckDB
serving layer. No fake data: an unknown asset is a 400, never a guess.

## The request
A trade is a set of **asset movements** among teams, plus optional **retention elections**:

```jsonc
{
  "team_ids": [30, 54],                    // all involved teams (N >= 2; two-team is the common case)
  "movements": [
    {"asset_id": "player:8478864", "from_team_id": 30, "to_team_id": 54},
    {"asset_id": "pick:VGK:2026:R1", "from_team_id": 54, "to_team_id": 30}
  ],
  "retentions": [                          // optional
    {"player_id": 8478864, "retaining_team_id": 30, "retained_pct": 0.5}
  ],
  "season": "2025-26"                      // optional; defaults to the latest contract snapshot
}
```

`asset_id` is the key from `mart_tradeable_assets` (`player:<id>` / `prospect:<id>` /
`pick:<team>:<year>:R<round>`). Validation (400 on failure): ≥2 distinct teams, every movement is
between involved teams and references a known asset, no asset moves twice, and the retention rules
below.

## The response — a per-team decomposition
Each involved team gets a `TeamTradeResult` with the three considerations kept **separate**:

- **Talent** — net projected value in WAR over the control window (`talent_delta_war` + band).
- **Cost-efficiency** — net surplus in **dollars** and **cap-share** (`surplus_delta_dollars`,
  `surplus_delta_capshare`, each + band).
- **Fit** — aggregate fit of incoming players to the team's needs (`fit_delta` + per-player detail).

plus a **soft cap** flag (`cap`), a **confidence** read, the incoming/outgoing **ledgers**, and a
one-line **summary**. A cross-team `summary` lists "who gains what" as parts, and `caveats` carries
the standing warnings.

## Netting (talent and cost-efficiency)
For each team, incoming minus outgoing on each axis, pulled from `mart_tradeable_assets`. The two
axes are never collapsed. **Band propagation**: each asset's band is a half-width; the net delta's
band combines **variances** (`hw_net = sqrt(Σ hw_iÂ²)`) — incoming and outgoing both add uncertainty —
so a prospect/pick-heavy side shows a wide net band (a star-for-three-picks side spans ~12 WAR).
Pick/prospect WAR comes from `mart_tradeable_assets` → `nhl_models.futures_value`, whose slot curve is
now the **empirical** pick-value curve fit on our own draft outcomes (Handoff 5; see
[futures-value.md](futures-value.md) and [draft-value.md](draft-value.md)), career-extrapolated to the
whole-career WAR units the engine nets. It stays a wide-band proxy, so pick-heavy sides remain
`low`-confidence regardless.

## Retention math
Retention is a **value lever modeled at evaluation time**, not a static attribute. When the source
team retains a fraction `X` of a traded contract:

- the **receiving** team pays only `(1 − X)` of the cost, so its surplus improves by `X · cost`;
- the **retaining** team keeps `X · cost` as **dead money with no player**, so its surplus drops by
  `X · cost`;
- **talent is unaffected** (it moves fully with the player).

Applied in both surplus units (dollars and the nominal cap-share). Rules: `0 < X ≤ 0.50` per
contract, at most **3** retained contracts per team, and only the **source** team may retain.

## Cap-compliance soft flag (approximate)
Per team: committed cap from `mart_player_contracts` (sum of cap hits), plus the net current-year
cap-hit change (an incoming player adds `(1 − X)` of their cap hit; the source sheds `(1 − X)` and
keeps `X · cap_hit` dead money; prospects and picks are cap-neutral), compared to the season ceiling
(`config.CAP_UPPER_LIMIT_BY_SEASON`). Returns committed before/after, the change, the margin, and an
over/under flag.

**It is a soft flag, never a gate, and labeled approximate everywhere.** It sums cap hits only —
LTIR, performance bonuses, and roster size are not modeled — so a team's committed figure can exceed
the ceiling when more than a 23-man roster of contracts is on file.

## Fit overlay
For each **incoming player**, `models_ml.score_team_fit` is run against the receiving team's
`team_needs`; the team's `fit_delta` is the mean incoming fit centered at the neutral 50, and each
player's score/grade/verdict is carried for explanation. Picks and prospects have no current profile,
so they contribute **no immediate fit** (noted).

## Verdict assembly
Per team, a **confidence** read driven by the asset mix on that side — any proxy asset
(prospect/pick) → `low`, any medium (e.g. a top-decile star) → `medium`, else `high` — and a readable
summary. The cross-team "who gains what" is a list of **parts** (talent, surplus, fit, soft cap),
never a single grade. Multi-team aware: one line per involved team.

## Validation (representative archetypes)
`make trade-engine-validate` runs three archetypes and prints a pasteable report:

- **Star-for-picks** — the acquiring team gains talent and worsens surplus (takes the contract); the
  rebuilding team sheds talent, improves surplus, drops cap, and reads **low confidence** (the pick
  return is a wide-band proxy).
- **Hockey trade (comparable stars)** — small talent delta, surplus follows the better contract, both
  sides medium confidence.
- **Cap dump with 50% retention** — the dumping team sheds cap (the retained-adjusted change) and
  pays a steep surplus price (dead money + sweetener); the acquiring team gets the player at half
  price plus a pick. Retention shifts both sides correctly.

## Limitations
- Cap is approximate (above); never trust it as compliance, only as a directional flag.
- Prospect/pick values (and their cap-share, a nominal `value / current cap`) are wide-band proxies;
  confidence on those sides is `low` by construction.
- Fit uses the latest `team_needs` season, which may differ from the contract snapshot season; it is
  an overlay, not netted into talent or surplus.
- Out of scope (future passes): the two-sided trade *builder* UI, and any auto-balancing or
  trade-suggestion logic. This engine only *evaluates* a fully specified proposal.
