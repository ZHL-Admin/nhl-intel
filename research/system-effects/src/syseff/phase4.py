"""Phase 4 orchestrator — build the two product surfaces (computed, not yet published) and the
face-validity exhibits. Reproducible from the Phase 3 primitives + player_types. Seeded."""
from __future__ import annotations

import json

from . import config, portability as PORT, opponent as OPP


def run() -> dict:
    PORT.build()
    OPP.strength_schedule_table()
    out = {
        "seed": config.SEED,
        "portability_exhibit": PORT.exhibit(),
        "schedule_exhibit": OPP.schedule_exhibit(),
        "predicted_delta_examples": [
            PORT.predicted_delta(8481556, "2024-25", 12, "2023-24"),   # F2 -> high-pace CAR
        ],
        "f14_caveat": PORT.F14_CAVEAT,
    }
    (config.REPORTS / "phase4_analysis.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    r = run()
    print("portability pool:", r["portability_exhibit"]["n_pool"])
    print("schedule pool:", r["schedule_exhibit"]["n_pool"])
    print("done -> reports/phase4_analysis.json")
