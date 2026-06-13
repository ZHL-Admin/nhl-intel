# docs/methodology

One markdown file per shipped model, written **when the model ships**. Each doc
states the data, features, training/validation method, the chosen constants (and
why), uncertainty handling, and known limitations.

These files are the source for the site's `/learn` methodology library (Phase 6),
rendered into the frontend at build time. Sections marked "generated" are produced
by the model jobs and must regenerate idempotently.

Expected files as phases land: `sequence-mining.md`, `xg-model.md`,
`scorer-bias.md`, `win-probability.md`, `goaltending.md`, `power-ratings.md`,
`isolated-impact.md`, `composite.md`, `archetypes.md`, `reconciliation.md`,
`trajectories.md`, `lineup-lab.md`, `streak-doctor.md`, `edge-cross-validation.md`.
