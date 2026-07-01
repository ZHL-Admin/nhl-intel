# archive/

Retired one-shot, calibration, and verification scripts. Nothing here is part of any
live pipeline (no DAG task, no Makefile target, no import from live code). These files are
kept for **provenance and reproducibility**, not deletion, so that baked-in constants and
feed-validation findings remain traceable to the code that produced them. Moved with
`git mv`, so history follows each file.

Do not wire anything here into the daily pipeline. If a calibration needs to be re-run,
move the script back out first.

## archive/models_ml/ — calibration one-shots (outputs are hard-coded upstream)

These were run once to derive constants that now live as literals in config/vars. Deleting
them would turn those literals into unreproducible magic numbers, so they are retained here.

| script | derives | consumed as (live location) |
|---|---|---|
| `measure_goalie_reliability.py` | per-danger-tier reliability `k` (method of moments, single-season rows 2021-22..2025-26) | `models_ml/config.py` `GOALIE_GAR_CONFIG["RELIABILITY_K"]`; used by `models_ml/compute_goalie_gar.py` |
| `tune_sequence_thresholds.py` | sequence-mining time/geometry thresholds (rebound / rush / forecheck / cycle windows) | `dbt/dbt_project.yml` vars consumed by `int_shot_sequence` |

To recalibrate: `git mv` the script back to `models_ml/`, run it, and paste the new numbers
into the location above.

## archive/dbt/ — ad-hoc BigQuery inspection scripts

Standalone probes that each open their own `bigquery.Client` for a one-off check. Never
imported; superseded by proper tooling. Kept as a starting point for future manual
inspection.

`check_report_feed.py` (probes `mart_daily_report_feed`), `check_xgf.py` (probes
`mart_team_game_stats.xgf_pct`), `query_metrics.py` (ad-hoc team metric SELECT),
`verify_calculations.py` (single-game CF%/HDCF check), `verify_hot_cold.py`
(`hot_cold_flag` trend check).

## archive/scripts/ — developer smoke harnesses + feed findings

Manual verification scripts (each a `__main__`-only harness run by hand against the real
NHL API / BigQuery) paired with the observational notes they produced. Not collected by
pytest (`pytest.ini testpaths = tests`) and wired to no DAG or Makefile target.

Smokes (11): `smoke_ingest_draft_results.py`, `smoke_ingest_game_context.py`,
`smoke_ingest_glossary.py`, `smoke_ingest_partner_odds.py`, `smoke_ingest_roster.py`,
`smoke_ingest_shiftcharts.py`, `smoke_ingest_standings.py`,
`smoke_ingest_statsrest_faceoffs.py`, `smoke_load_gm_tenures.py`, `smoke_load_trades.py`,
`smoke_roster_source.py`.

Findings notes: `DRAFT_RESULTS_FINDINGS.md`, `EDGE_FINDINGS.md`, `ROSTER_FINDINGS.md`,
`STATSREST_FINDINGS.md`.

Excluded from this archive and left in `scripts/`: `smoke_ingest_ppt_replay.py`
(puck-tracking, retained by owner decision).
