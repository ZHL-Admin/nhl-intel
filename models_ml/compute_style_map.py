"""
League style map (Phase 3.2, blueprint 5.1).

Standardise each team's identity fingerprint across the 32 teams, PCA to 2D, and write the
coordinates plus human-readable axis annotations so the Teams index can scatter the 32 logos
with quadrant labels generated from the data. Refit weekly in the DAG.

Orientation is pinned for run-to-run stability (PCA sign is otherwise arbitrary): PC1 is
flipped so more shot volume reads to the RIGHT, PC2 so higher shot quality reads UP.

Output: ``nhl_models.style_map`` (season, team_id, x, y, + the four axis description strings,
repeated on every row so one query returns both the points and the annotations).

Run:  python -m models_ml.compute_style_map [--season 2025-26] [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from models_ml import bq

# Style features (col -> short human label). Quality/territory + play-style mix; these are
# the dimensions a fan would describe a team's identity by.
FEATURES: list[tuple[str, str]] = [
    ("rush_share_for", "rush offense"),
    ("forecheck_share_for", "forecheck offense"),
    ("cycle_share_for", "cycle offense"),
    ("point_shot_share_for", "point-shot offense"),
    ("rush_share_against", "rush defense allowed"),
    ("pace", "pace"),
    ("shot_quality", "shot quality"),
    ("shot_volume_per60", "shot volume"),
    ("hits_per60", "hitting"),
    ("penalties_taken_per60", "penalties taken"),
    ("pp_point_shot_share", "PP point-shot structure"),
    ("oz_time_pct", "o-zone time"),
    ("oz_conversion", "territory-to-danger conversion"),
]
ORIENT_X = "shot_volume_per60"   # higher -> +x
ORIENT_Y = "shot_quality"        # higher -> +y
MODEL_VERSION = "style_map_v1"


def latest_season() -> str:
    return bq.query_df(
        f"select max(season) s from `{bq.project()}.nhl_mart.mart_team_identity`")["s"].iloc[0]


def pull(season: str) -> pd.DataFrame:
    cols = ", ".join(c for c, _ in FEATURES)
    df = bq.query_df(f"""
        select team_id, {cols}
        from `{bq.project()}.nhl_mart.mart_team_identity`
        where season = '{season}' and window_kind = 'season'
    """)
    for c, _ in FEATURES:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    return df


def axis_description(loadings: np.ndarray, sign: int, top_n: int = 3) -> str:
    """Top-N features pushing in the given direction (sign +1 = positive axis end)."""
    signed = loadings * sign
    order = np.argsort(signed)[::-1][:top_n]
    parts = []
    for i in order:
        lab = FEATURES[i][1]
        parts.append(f"{'high' if signed[i] >= 0 else 'low'} {lab}")
    return ", ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    season = args.season or latest_season()
    df = pull(season)
    if len(df) < 5:
        print(f"Only {len(df)} teams for {season}; skipping style map.")
        return
    # mean-impute any stray nulls so a single missing Edge value does not drop a team
    feat = df[[c for c, _ in FEATURES]].copy()
    feat = feat.fillna(feat.mean())

    X = StandardScaler().fit_transform(feat.to_numpy())
    pca = PCA(n_components=2, random_state=0)
    coords = pca.fit_transform(X)
    comp = pca.components_.copy()          # (2, n_features)
    feat_names = [c for c, _ in FEATURES]

    # pin orientation: flip each PC so the orienting feature loads positive on its axis
    if comp[0, feat_names.index(ORIENT_X)] < 0:
        comp[0] *= -1; coords[:, 0] *= -1
    if comp[1, feat_names.index(ORIENT_Y)] < 0:
        comp[1] *= -1; coords[:, 1] *= -1

    out = pd.DataFrame({
        "season": season,
        "team_id": df["team_id"].astype("int64").to_numpy(),
        "x": coords[:, 0],
        "y": coords[:, 1],
        "x_pos_desc": axis_description(comp[0], +1),
        "x_neg_desc": axis_description(comp[0], -1),
        "y_pos_desc": axis_description(comp[1], +1),
        "y_neg_desc": axis_description(comp[1], -1),
        "model_version": MODEL_VERSION,
    })
    var = pca.explained_variance_ratio_
    print(f"{season}: {len(out)} teams. PC variance explained: "
          f"PC1 {var[0]:.1%}, PC2 {var[1]:.1%}")
    print(f"  +x (right): {out['x_pos_desc'].iloc[0]}")
    print(f"  -x (left):  {out['x_neg_desc'].iloc[0]}")
    print(f"  +y (up):    {out['y_pos_desc'].iloc[0]}")
    print(f"  -y (down):  {out['y_neg_desc'].iloc[0]}")

    if args.dry_run:
        print("\n[dry-run] not writing nhl_models.style_map")
        return
    # season-scoped replace so multiple seasons can coexist
    cli = bq.client()
    table_id = f"{bq.project()}.{bq.config.MODELS_DATASET}.style_map"
    try:
        cli.get_table(table_id)
        cli.query(f"delete from `{table_id}` where season = '{season}'").result()
        disp = "WRITE_APPEND"
    except Exception:
        disp = "WRITE_TRUNCATE"
    bq.write_df(out, "style_map", write_disposition=disp, clustering_fields=["season"])
    print(f"\nWrote {len(out)} rows to nhl_models.style_map for {season}.")


if __name__ == "__main__":
    main()
