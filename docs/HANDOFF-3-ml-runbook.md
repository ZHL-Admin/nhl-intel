# Handoff 3: Long-running ML jobs runbook

**Provide this when Claude Code reaches a training job it cannot complete in-session (Phase 2.2 xG, 2.4 win prob, 4.1 RAPM, 4.2 archetypes, 5.1 line fit, plus the bootstrap and tuning sweeps).**

## Division of labor
The session boundary is not allowed to degrade the work. The rule:

1. **You build the job to be runnable, resumable, and self-verifying.** I execute the long runs on my machine and paste back the printed reports. You then make all decisions (hyperparameters, thresholds, ship/no-ship) from the pasted reports, exactly as if you had run it yourself.
2. **Before handing me a long run, prove the pipeline on a slice.** Every training script must accept `--sample` (e.g. `--sample 2022-23` trains on one season, or `--sample-frac 0.02`) and you must run that slice end to end in-session if compute allows, or at minimum run the script's `--dry-run` (build the design matrix shape, print dimensions, fit nothing). A job is not handed off until its slice run completes without error.
3. **No decision gets made from a slice.** Slice runs validate plumbing only; metrics in methodology docs come exclusively from the full runs I execute.

## Engineering requirements for every models_ml training script
- `--dry-run`, `--sample`/`--sample-frac`, `--resume` flags.
- Checkpointing: long loops (bootstrap iterations, hyperparameter grids, threshold sweeps) write progress to `models_ml/artifacts/checkpoints/<job>_<run_id>.json` after each unit and skip completed units on `--resume`.
- Determinism: a single `RANDOM_SEED` in `models_ml/config.py` used everywhere (numpy, lightgbm, sklearn); two runs of the same command must produce the same artifact hash.
- Logging: tqdm progress + a final structured report printed to stdout AND saved to `models_ml/artifacts/reports/<job>_<run_id>.md` (this is the file I paste back; make it self-contained: data window, row counts, params, every metric the plan's validation section demands).
- Memory: stream from BigQuery in chunks or pre-aggregate server-side; assume my machine has 32 GB RAM and no GPU. LightGBM CPU is fine for everything in this plan.
- Artifacts: saved to `models_ml/artifacts/` with the version name from the plan (`xg_v1.txt`, `linefit_v1`, ...) plus a sidecar manifest JSON (feature list, training window, seed, git commit).

## Expected runtimes (so neither of us mistakes slow for stuck)
| Job | Full-run expectation on a modern 8-core laptop |
|---|---|
| Sequence threshold sweep (2.1) | 10-30 min (it's SQL-heavy; most time is BigQuery) |
| xG train + grid (2.2) | 30-90 min for ~1.5M shots x small grid |
| xG full-history scoring (2.2) | 15-45 min, BigQuery-write bound |
| Win prob train (2.4) | 20-60 min (millions of sampled rows, logistic) |
| WP full-history scoring | 30-90 min |
| RAPM single fit (4.1) | 5-20 min on the aggregated design matrix |
| RAPM 200-game-bootstrap (4.1) | 2-8 hours. Checkpoint every iteration; I may run it overnight |
| Archetype GMM + BIC sweep (4.2) | < 10 min |
| Line fit train + season-fold CV (5.1) | 30-90 min |
| Deserved-standings simulation (3.1) | 10-30 min for 10k sims x season |
Anything tracking 3x over these expectations: I'll ctrl-C, paste the checkpoint state, and you diagnose.

## The handoff packet format
When you reach a long run, end your turn with a block exactly like:
```
READY FOR FULL RUN: <job name>
Slice verified: <command you ran> -> <one-line result>
Run this: python -m models_ml.train_xg --full
Then paste back: models_ml/artifacts/reports/train_xg_<run_id>.md
Decisions I will make from it: <e.g. final hyperparams, calibration pass/fail vs the 3% criterion>
```
I run it, paste the report, you proceed. If a report fails its own acceptance criterion (e.g. calibration off by more than the plan's tolerance), you iterate on the model, re-verify the slice, and issue a new packet; the methodology doc records the iteration honestly.
