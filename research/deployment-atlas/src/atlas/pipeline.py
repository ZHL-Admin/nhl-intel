"""End-to-end pipeline orchestrator (Phase 6.3, `make all`).

Reproduces every phase's derived tables from the cached corpus. Each step is
idempotent: if its output Parquet exists it is REUSED (skipped); otherwise it is
rebuilt. Prints reused-vs-built per step and the total wall-clock.
"""

from __future__ import annotations

import time

import polars as pl

from . import config, sources, stints as st

STEPS = [
    ("corpus:shifts", sources.SHIFTS_PARQUET, lambda: sources.materialize_shifts()),
    ("corpus:events", sources.EVENTS_PARQUET, lambda: sources.materialize_events()),
    ("corpus:boxscore_toi", sources.BOXSCORE_TOI_PARQUET, lambda: sources.materialize_boxscore_toi()),
    ("corpus:penalty_ledger", sources.PENALTY_LEDGER_PARQUET, lambda: sources.materialize_penalty_ledger()),
    ("corpus:rosters", sources.ROSTERS_PARQUET, lambda: sources.materialize_rosters()),
    ("corpus:games", sources.GAMES_PARQUET, lambda: sources.materialize_games()),
    ("stints", st.STINTS_PARQUET, lambda: (st.build_stints(), st.attach_outcomes())),
    ("rapm_variant", config.PARQUET_DIR / "rapm_variant.parquet", None),
    ("player_5v5", config.PARQUET_DIR / "player_5v5.parquet", None),
    ("context:fingerprints", config.PARQUET_DIR / "coach_fingerprints_2024_25.parquet", None),
    ("context:player", config.PARQUET_DIR / "player_context_2024-25.parquet", None),
    ("movers_eval", config.PARQUET_DIR / "movers_eval.parquet", None),
    ("shot_xg", config.PARQUET_DIR / "shot_xg.parquet", None),
]


def main() -> int:
    t0 = time.time()
    reused, built, missing = [], [], []
    for name, path, builder in STEPS:
        if path.exists():
            reused.append(name)
            continue
        if builder is None:
            missing.append(name)
            print(f"  MISSING (no builder in `make all` — heavy step, run its phase): {name}")
            continue
        s = time.time()
        builder()
        built.append(name)
        print(f"  built {name} in {time.time()-s:.0f}s")
    print(f"\nreused {len(reused)} / built {len(built)} / missing {len(missing)} steps "
          f"in {time.time()-t0:.1f}s")
    if reused:
        print("  reused:", ", ".join(reused))
    if missing:
        print("  missing (rebuild via: make rapm / make phase4 / make phase5):", ", ".join(missing))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
