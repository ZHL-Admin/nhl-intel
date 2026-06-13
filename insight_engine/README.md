# insight_engine

Deterministic insight system (blueprint section 8) built in Phase 6. **No LLM in
the site path** — every insight is a registered detector + a Python format
template, scored by surprise and stakes, and verified by a consistency checker
before it can be shown.

## Structure (built in Phase 6)
- `registry.py` — registry of `Insight` classes (id, scope, detector, surprise,
  stakes, render).
- `detectors/` — one module per insight family; each consumes only existing
  `nhl_models` / mart tables.
- `templates/` — Python format templates with named slots (headlines, bodies,
  divergence/line-fit/matchup/moments fragments). Reused by frontend via the API.
- `smoke.py` — runs every detector against a fixture date + the consistency checker.

## Rules
- Plain language, numbers always in context (percentile or rank), no exclamation points.
- `render()` declares `numbers_used`; the consistency checker drops any insight whose
  numbers do not match what the target page renders.
