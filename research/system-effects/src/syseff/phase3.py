"""Phase 3 orchestrator — runs the pooling layer, both INTERNAL designs, the OPPONENT track,
and the stability tests, writing each sub-analysis JSON plus a combined phase3_analysis.json.
Reproducible from cache (primitives built by `make primitives`). Seeded (config.SEED)."""
from __future__ import annotations

import json

from . import config, design_a as DA, design_b as DB, opponent as OPP, player_types as PT, stability as STB


def run() -> dict:
    _, types_meta = PT.build()
    types_meta = {k: v for k, v in types_meta.items() if k not in ("scaler_mean", "scaler_scale")}
    out = {
        "seed": config.SEED,
        "pooling_layer": types_meta,
        "designA_coach_change": DA.run(),
        "designB_joint_model": DB.run(),
        "opponent_track": OPP.run(),
        "stability": STB.run(),
    }
    (config.REPORTS / "phase3_analysis.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    r = run()
    print("pooling types:", r["pooling_layer"]["n_types_total"])
    print("designA DiD xg_share_close t:", r["designA_coach_change"]["did"]["d_xg_share_close"]["t_stat"])
    print("designB cv_r2_residual:", r["designB_joint_model"]["cv_r2_residual"])
    print("opponent interaction_r2_gain:", r["opponent_track"]["interaction_r2_gain"])
    print("done -> reports/phase3_analysis.json")
