# Upstream data-defect ledger — Goal-Tracking program

Defects found in read-only upstream inputs. Nothing is fixed mid-program; each item waits for a gate.

| # | stage | input | defect | scale | handling (this program) | proposed upstream fix |
|---|---|---|---|---|---|---|
| L1 | 0.2 | `nhl_staging.stg_ppt_tracking_frames` | some entity-frames carry a null `x_std`/`y_std` (tracking dropout for that entity in that frame) | 28,368 / 44,721,173 rows = **0.06%** | interior nulls linearly interpolated before smoothing; an entity all-null across a clip is dropped from kinematics (speed undefined, not a crash) | none needed unless a downstream stage needs per-frame completeness; note as a known sparsity |
| L1b | 0.2 | `nhl_staging.stg_ppt_tracking_frames` | one goal has puck rows but **zero** valid puck coordinates in the whole clip: `2025021204-157` | **1 / 25,946 goals** | row kept (pbp labels live) with `reconstruction_ok=false` and all geometry null; excluded from geometry stats | investigate the sprite ingest for this event; likely a source sprite with a malformed puck track |
| L2 | 0.2 | Atlas `stints.parquet` (regular season, game type 02 only) | playoff goals (game type 03) in the tracking corpus have no covering stint | playoff goals in corpus (strength via situationCode fallback) | strength_state from the sprite `situationCode` with `strength_source='situationCode'`; regular-season goals use the ice-derived stint (`strength_source='stint'`) | if playoff ice-strength is later needed, extend the Atlas stint build to game type 03 |

Both items are expected consequences of the source data, not corruptions. They are logged for traceability; neither blocks Stage 0.
