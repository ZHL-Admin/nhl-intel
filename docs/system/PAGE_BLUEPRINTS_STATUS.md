# Page Blueprints — status & decisions

## Decisions (D27+)
D27 Player compare page — Build (pending B2).
D28 Share card — client-side canvas, brand mark bottom-right (shipped in B0).
D29 "Deserved" tab label — "Luck" (shipped, P2/DS).
D30 Depth chart on offseason data — Yes, flagged "projected" (pending B3).
D31 Trades/History GM leaderboard rail — Build (pending B4).
D32 Studio hub inline pickers — Build (pending B4).
**D33 Upset branch in the game verdict — DEFERRED.** The game-detail payload carries no pregame
win probability, so `composeGameVerdict`'s `upset` input is always false and that template branch is
inert. Accepted as a known gap (no backend change); revisit if a pregame win-prob field is added.

## B1 data-fix status (game 2025030215, MTL @ BUF, MTL won 6-3 — the reviewed game)

| Fix | Status | Notes |
|---|---|---|
| F1 GSAx single-source | ✅ | Verdict theft now reads GSAx from the danger-band table (getGameGoalieDanger), the per-game xG-derived number. The two prior sources (goaltending endpoint vs danger table) disagreed; the "stole-one" +8.72 was an inflated/leaked value in a since-removed insight panel. |
| F2 xG lane basis | ✅ (labelled) | Comparison xG row is all-situations total xGF (same basis as team receipts); labelled "All situations". The timeline worm lane (cumulative_xg_diff) is a different basis and must carry its own label — pending in GameTimelineStack. |
| F3 5v5 CF% percent | ✅ | Was rendering the fraction (0.42 → "0%"); now ×100 → "42%". |
| F4 moments | ✅ | Recomputed from the raw win-prob SERIES joined to the goals feed (goal_swings had a bracketing bug — it read the post-goal spike as "before"). Signed from the scoring team's own perspective, floored at 5 points, top 3 (fewer if fewer qualify). |
| F5 shot-map caption | ✅ (honest) | Feed labels every attempt as on-goal → "48/48". Now shows attempts (Corsi) only; SOG must be wired from the team-stats receipt, not this feed. |
| F6 period insight | ⚙️ config shipped | `config/periodInsights.ts` provides the score-aware template set (trailing team winning possession = score effects, not control). Wiring into the period panel is pending with the K-dedupe. |

## Remaining B1 (next increment)
- **K1–K8 dedupe / final order** on "The game" (kill teaser/top-performers/insight-strip/standalone
  team-stats/matchup-context cards; move scoring timeline to Box score; merge control-and-danger and
  the two goaltending panels into one each; final order: verdict · timeline · moments · comparison ·
  shot map · who drove · receipts). This deletes the old panels and removes GameNarrative's duplicate
  fetches (F2 worm label + F6 wiring land here).
- **P1** tab labels already sentence case ("The game", "Box score").
- **P2** P4 bars: neutral fills + team-color end dots — implemented in CompareRows; verify in a
  red-vs-blue matchup and both themes.

## D34 Studio verdicts — augment, not replace (B4)
The blueprint framing was "wire VerdictCard into 8 tools," but the code already had richer bespoke
verdict banners on the strongest tools. Per code-wins-over-doc, the chosen approach (user-confirmed):
- **Share grammar extracted** to one `ShareActions` (Copy link + ⤓ Card PNG); `VerdictCard` now uses it too.
- **Augmented the bespoke banners** with a mono kicker overline + `ShareActions`: ContractGrader
  (`cg-banner`), TradeBuilder (`TradeSummaryBand`), TradeFit (result bar — replaced the URL-only Share
  with the standard Copy-link + Card so it gains the image card), Offseason ("The verdict" §01),
  RosterBuilder (`rb-headline`). LineupLab already had a graded share button (left as-is).
- **Explorers left without a page verdict — deliberately.** TradeOutcomes (historical browse, three
  tabs + drill), DraftValue (pick-value curves / steals & busts research), and the trades
  ArchetypeExplorer have no single input→verdict; their verdict units are per-row (a trade balance
  card, a pick row) and are already verdict-shaped. Bolting a page-level VerdictCard on would be
  artificial, so it was not done.

## B2 status
- **§2.4 Players-index compare affordance — DONE.** "Compare with…" button in the row preview
  (`PlayerRowExpansion`) opens the `EntityPicker` → `/players/compare?a=<row>&b=<pick>`. Verified.
- **§2.5 PlayerProfile Overview recompose — still open.** Tab-rename (→ "Receipts") + serif verdict
  prose shipped earlier; the full case/shape 7-5 grid + season-reality strip + receipts teaser +
  Overall-card move + Log tab is a large recompose of a 1428-line file and needs the exact §2.5 spec
  (not in any doc) or an explicit "use your judgment" go-ahead before attempting — not improvised.

## B2 §2.5 — RESOLVED (use-judgment go-ahead)
Audited the live Overview: prior B2 work had already recomposed it — the case (verdict) / shape
(radar) grid, season-totals + "Is it real?" reality strip, "Full impact breakdown →" receipts teaser,
Overall-in-grid, and the Game Log tab all existed. The one genuine gap vs the "7-col case / 5-col
shape" target was the hero split, which was inverted (45% case / 55% shape). Flipped to 58.333% /
~42% so the case leads at 7/12 and the shape reads at 5/12 (stacks vertically ≤860px). §2.5 complete.
