# Handoff 4: Archetype cluster naming (the Phase 4.2 human step)

**Provide this when Claude Code stops at the archetype labeling step and asks for cluster names.** This document tells it exactly what to give me, and tells me exactly how to answer, so the loop closes in one round trip.

## Why this step is human
Cluster names are the site's player vocabulary: they appear on every player card header, drive the rank-within-archetype view, and feed the Lineup Lab's explanation language. The blueprint (4.5) requires plain-English names a layperson recognizes ("oh, he's a net-front guy"). Statistical fit can't choose words; I will.

## What Claude Code must put in the labeling report
`models_ml/artifacts/archetype_labeling_report.md` must contain, per position group (F, D), per cluster:
1. **Feature fingerprint:** the cluster's mean for every input feature, expressed as a league percentile (not raw z-scores), sorted by distance from the 50th percentile so the defining traits read first.
2. **A one-line statistical caricature** generated from the top 3 traits (e.g. "high rush share, high burst rate, low dz starts"). This is a description, not a proposed name; do not pre-name.
3. **Ten exemplars:** the highest-membership-weight players (current or recent seasons preferred, min 500 minutes), with their membership percentage.
4. **Five edge cases:** the most split players between this cluster and its nearest neighbor, to show me where the boundary lies.
5. **Cluster size** (share of the player population) and the BIC-selected k per position group.

## Naming rules I will follow (and Claude Code should hold me to)
- Plain English, 1-3 words, instantly meaningful to a casual fan. The blueprint's seed vocabulary, to be used where the data matches: **rush creator, cycle forward, net-front finisher, two-way pivot, shutdown defenseman, puck-moving defenseman, volume shooter.** I'll coin the rest in the same register (candidates I'm predisposed to: *forecheck hound, perimeter playmaker, power-play specialist, depth grinder, minute-eating defender, offensive catalyst, stay-at-home defenseman, transition defenseman*).
- No two clusters in a position group share a noun unless the modifier does real work.
- Names describe style, never quality. "Depth grinder" describes usage and shot mix, not badness; the composite stack carries quality.
- If a cluster has no coherent identity (a residual blob), I may name it "balanced forward" / "all-situations defenseman" but if more than one cluster per group is incoherent, that's a signal to revisit k or features, and I'll say "re-fit" instead of naming.

## The response format I will give back
```yaml
# paste-ready for models_ml/config.py ARCHETYPE_NAMES
forwards:
  0: "Rush Creator"
  1: "Net-Front Finisher"
  # ... one entry per cluster id
defense:
  0: "Puck-Moving Defenseman"
  # ...
rejected: []   # or cluster ids I want re-fit, with a reason each
```

## After I respond, Claude Code must
1. Write the mapping into `models_ml/config.py` as `ARCHETYPE_NAMES` with a comment recording the date and that names were human-assigned per this protocol.
2. Regenerate `nhl_models.player_archetypes` with names attached.
3. Add every archetype name + its statistical caricature to the glossary (`frontend/src/config/glossary.ts` in Phase 6; until then, to `docs/methodology/archetypes.md` so the definitions exist the day the feature ships).
4. Mirror the names in the historical reduced-feature GMM (Phase 4.4's pre-tracking fallback) by nearest-centroid mapping, and list in the methodology doc any historical cluster whose centroid mapping is ambiguous (distance ratio to two names within 10 percent), since those drive the career-twins labels.
5. Sanity-print the new rank-within-archetype top-5 for three archetypes so I can veto a name that reads wrong against real players before it reaches the UI.

## Stability note for future refits
On any future archetype refit (new season, new features), cluster ids will shuffle. The refit job must map new clusters to existing names by centroid proximity and only surface to me the clusters that genuinely have no good match (distance above a threshold in config). Names are sticky; ids are not.
