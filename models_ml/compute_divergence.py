"""
Divergence board (Phase 4.3, blueprint 4.4).

Contrast how much a coach TRUSTS a player (deployment) with his ISOLATED value (composite).
Standardize both within position; divergence = trust_z - composite_z. The board is the
top/bottom N by |divergence| (min minutes), each with a deterministic explanation
(insight_engine/templates/divergence.py).

Output: nhl_models.divergence_board (player_id, season_window, pos_group, trust_score,
composite_total, trust_z, composite_z, divergence, dominant_trust, top_component,
bottom_component, side, explanation).

Run:  python -m models_ml.compute_divergence [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config
from insight_engine.templates.divergence import explain

WINDOW_LABEL = "2023-24_2025-26"
COMPONENTS = ["ev_offense", "ev_defense", "pp", "pk", "finishing", "penalty_diff", "goalie_gsax"]
TRUST_SIGNALS = list(config.COACH_TRUST_WEIGHTS.keys())


def _z_within(df: pd.DataFrame, col: str) -> pd.Series:
    m = df.groupby("pos_group")[col].transform("mean")
    sd = df.groupby("pos_group")[col].transform("std").replace(0, 1.0)
    return (df[col] - m) / sd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    p = bq.project()

    trust = bq.query_df(f"""select player_id, pos_group, trust_score, total_toi,
        {', '.join(TRUST_SIGNALS)}
        from `{p}.nhl_models.player_coach_trust` where season_window = '{WINDOW_LABEL}'""")
    comp = bq.query_df(f"""select player_id, total as composite_total, toi_5v5,
        {', '.join(COMPONENTS)}
        from `{p}.nhl_models.player_composite` where season_window = '{WINDOW_LABEL}'""")
    df = trust.merge(comp, on="player_id", how="inner")
    df = df[df["toi_5v5"] >= config.DIVERGENCE_MIN_MINUTES].copy()
    df = df[df["pos_group"].isin(["F", "D"])]
    for c in COMPONENTS + TRUST_SIGNALS + ["trust_score", "composite_total"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")

    df["trust_z"] = _z_within(df, "trust_score")
    df["composite_z"] = _z_within(df, "composite_total")
    df["divergence"] = df["trust_z"] - df["composite_z"]

    # dominant trust signal = highest within-position z among the three signals
    sig_z = {s: _z_within(df, s) for s in TRUST_SIGNALS}
    df["dominant_trust"] = pd.DataFrame(sig_z).idxmax(axis=1).values
    # strongest / weakest composite component
    comp_vals = df[COMPONENTS]
    df["top_component"] = comp_vals.idxmax(axis=1).values
    df["bottom_component"] = comp_vals.idxmin(axis=1).values

    # board: top N over (eye-test > numbers) + bottom N under (numbers > eye-test)
    n = config.DIVERGENCE_BOARD_SIZE
    over = df.sort_values("divergence", ascending=False).head(n)
    under = df.sort_values("divergence").head(n)
    board = pd.concat([over.assign(side="trusted_over_value"),
                       under.assign(side="value_over_trust")], ignore_index=True)

    board["explanation"] = board.apply(lambda r: explain(
        divergence=r["divergence"], dominant_trust=r["dominant_trust"],
        top_component=r["top_component"], bottom_component=r["bottom_component"],
        composite_total=r["composite_total"], composite_z=r["composite_z"]), axis=1)
    board["season_window"] = WINDOW_LABEL

    names = _names(board["player_id"].tolist())
    print("=== Trusted beyond value (top divergence) ===")
    for _, r in over.head(8).iterrows():
        print(f"  {names.get(r['player_id'], r['player_id']):22s} div {r['divergence']:+.2f} "
              f"(trust_z {r['trust_z']:+.2f}, comp_z {r['composite_z']:+.2f})")
    print("\n=== Value beyond trust (bottom) ===")
    for _, r in under.head(5).iterrows():
        print(f"  {names.get(r['player_id'], r['player_id']):22s} div {r['divergence']:+.2f}")
    print("\nExample explanation:", board.iloc[0]["explanation"].replace(" — ", " - "))

    if args.dry_run:
        print(f"\n[dry-run] {len(board)} board rows not written")
        return
    cols = ["player_id", "season_window", "pos_group", "trust_score", "composite_total",
            "trust_z", "composite_z", "divergence", "dominant_trust", "top_component",
            "bottom_component", "side", "explanation"]
    out = board[cols].copy()
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = "divergence_v1"
    bq.write_df(out, "divergence_board", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window"])
    print(f"\nWrote {len(out)} rows to nhl_models.divergence_board.")


def _names(ids):
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    df = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) as name
                         from `{bq.project()}.nhl_staging.stg_rosters`
                         where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


if __name__ == "__main__":
    main()
