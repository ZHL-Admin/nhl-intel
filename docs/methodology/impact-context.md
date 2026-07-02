# Impact context — entanglement, carry, and single-vs-multi-year divergence

The isolated-impact (RAPM) estimate answers "how much does this skater move 5v5 expected
goals, after adjusting for teammates, competition, and usage." It does not, on its own, tell
you **how much to trust that number for this particular player**. Two players with the same
point estimate are not equally knowable: one who plays 60% of his minutes with a single
partner is far harder to separate from that partner than one spread across the lineup.

This layer adds that context, transparently, without inventing a new score. It is the mart
`mart_player_impact_context` plus its two inputs `mart_player_entanglement` and
`mart_player_carry`. It reads `nhl_models.player_impact` and never modifies it. See
[isolated-impact.md](isolated-impact.md) for the RAPM model itself; this doc does not repeat it.

## Why this exists: Seider and Edvinsson

The Detroit pairing of Moritz Seider and Simon Edvinsson is the motivating case. In 2025-26
they played 724 shared 5v5 minutes (up from 463 in 2024-25), and each spent the large
majority of his 5v5 time with the other (partner-TOI share 0.75 for Seider, 0.79 for
Edvinsson). When two players are that welded, RAPM cannot cleanly attribute the pair's on-ice
results between them, and simple on-ice rates are shared almost by construction. The context
layer surfaces that ambiguity instead of hiding it behind a single number:

| 2025-26 | isolated total (single) | 3-yr window | single−multi | partner share | entangled | carry | on-off rel xGF% |
|---|---|---|---|---|---|---|---|
| Seider | 0.738 | 0.472 | **+0.265** | 0.75 | yes | 0.145 | +0.096 (his own) |
| Edvinsson | −0.074 | 0.108 | −0.182 | 0.79 | yes | 0.067 | +0.096 |

Read together: Seider carries a strong, rising isolated impact and a high carry score (his
partners do meaningfully better with him), so his welded minutes read as "genuinely driving
the pair." Edvinsson's on-ice relative is excellent (+0.096) but his isolated RAPM is slightly
negative, and he is heavily entangled with Seider, so the honest reading is "his surface
results are partly Seider's; the isolated estimate is the less flattering, harder-to-separate
signal." That contrast is the product, not a blended verdict.

## The three signals

### Entanglement (`mart_player_entanglement`)

From a symmetric view of `mart_player_toi_matrix` (the pair table stores each unordered pair
once), per (season, player, team):

- `max_partner_toi_share` — the single most-common partner's shared 5v5 TOI divided by the
  player's own 5v5 TOI (`mart_player_onice`). 0.75 means three-quarters of the player's 5v5
  minutes came with one linemate.
- `partner_entropy` — normalized Shannon entropy of the partner-TOI distribution, 0 (all
  minutes with one partner) to 1 (evenly spread). A second, distribution-level view of
  concentration that does not collapse to the single top partner.
- `entangled` — `max_partner_toi_share > 0.55` (decision D18). A flag, not a penalty.

The estimate is least separable exactly when `entangled` is true. Consumers should widen the
shown uncertainty for entangled players rather than read the point estimate at face value;
this matches the RAPM shrinkage behaviour documented in isolated-impact.md (low-separability
minutes pull toward league average with small absolute SD, so "near zero" means *unproven*).

### Carry (`mart_player_carry`)

Per (season, player): the TOI-weighted mean over partners of the WOWY field
`partner_with_focal_minus_partner_without` (the partner's on-ice xGF% *with* the focal minus
*without* the focal), weighted by shared 5v5 TOI so tiny-sample pairings barely move it.
Positive means the player's linemates perform better with him than without — he elevates
partners. Seider's 0.145 (partners average ~14.5 xGF percentage points better with him) is the
mechanism behind his welded minutes reading as real rather than passenger.

### Single vs multi-year divergence (`single_vs_multi_delta`)

`player_impact` carries both a single-season row (`season_window` like `2025-26`) and a
3-season weighted window (`2023-24_2025-26`, weights 1.0/0.6/0.3 newest→oldest). The delta is
`single_total − multi_total` (null when a player has no window row). It is the clearest view
of the carryover question: a young player breaking out reads as a large positive delta
(current season well above his weighted history), which is exactly Seider's +0.265 in 2025-26.
Single-season RAPM is the noisier measurement (isolated-impact.md: YoY r ≈ 0.43 for offence at
≥200 5v5 min), so the delta should be read alongside the window, not instead of it.

## Transparency rules

- **No composite.** `mart_player_impact_context` keeps every field separate: off/def/total
  impact and their SDs, the window totals, the delta, the two entanglement measures, carry,
  and the true on-off `rel_xgf_pct`. It computes no blended score and adds no ranking.
- **Qualification** everywhere is the same 200-5v5-minute floor RAPM uses (12000 s), exposed
  as a `qualified` flag on the input marts rather than by dropping rows.
- **Grain** is (season, player_id, position_group); goalies are excluded (no F/D position).
  Entanglement is taken from the player's primary team that season; the on-off relative is
  aggregated across a traded player's teams.
