"""
Shared feature assembly for the Lineup Lab line-fit model (Phase 5.1, blueprint 6.2).

The line-fit model is a COLD-START predictor: a hypothetical line is scored purely from its
members' individual player-season profiles, so every feature here is a player-level aggregate
(no observed line history enters the features — that only enters the chemistry blend at scoring
time). This module is imported by both train_linefit.py and score_line.py so training and serving
build identical feature rows.

Two layers:
  build_member_features(seasons) -> one row per (player_id, season) with scalar role/skill
    features, a 24-d archetype-mix vector, handedness, and the player name.
  aggregate_line(members_df, line_type) -> one feature dict for a line, combining its members'
    rows as mean/min/max plus pairwise chemistry features (archetype cosine, shot-location
    overlap, handedness balance, burst-rate spread, o-zone-tilt mean).
"""

from __future__ import annotations

import json
from itertools import combinations

import numpy as np
import pandas as pd

from models_ml import archetype_features, bq, config

# Scalar member features aggregated as mean/min/max over a line's members. These describe each
# member's role (deployment, shot diet) and isolated skill (RAPM, finishing, Edge pace).
SCALAR_FEATS = [
    "off_impact", "def_impact", "finishing",
    "rush_share", "rebound_share", "forecheck_share", "cycle_share", "point_share",
    "mean_shot_distance", "slot_share",
    "pp_toi_share", "pk_toi_share",
    "edge_burst_per60", "edge_oz_pct",
]

# canonical, stable ordering of the 24 archetype labels for the mix vector
ARCH_LIST = sorted(set(config.ARCHETYPE_NAMES.values()))


def _arch_vector(arch_json: str | None) -> np.ndarray:
    """Parse the player_archetypes JSON ([{archetype, weight}, ...]) into a fixed-order vector."""
    v = np.zeros(len(ARCH_LIST), dtype="float64")
    if arch_json is None or not isinstance(arch_json, str) or not arch_json:
        return v
    idx = {a: i for i, a in enumerate(ARCH_LIST)}
    for item in json.loads(arch_json):
        i = idx.get(item.get("archetype"))
        if i is not None:
            v[i] = float(item.get("weight", 0.0))
    return v


def build_member_features(seasons: list[str]) -> pd.DataFrame:
    """One row per (player_id, season) of player-level features. Index = (player_id, season)."""
    # Reuse the archetype feature builder (it already pulls + imputes the role/skill features for
    # every skater); a low minutes floor keeps coverage broad so any line is scorable.
    base = archetype_features.build(seasons, min_5v5=1.0).copy()
    base["finishing"] = (pd.to_numeric(base["goals"], errors="coerce")
                         - pd.to_numeric(base["ixg"], errors="coerce"))
    base["finishing"] = base["finishing"].fillna(0.0)

    p = bq.project()
    qs = ", ".join(f"'{s}'" for s in seasons)
    arch = bq.query_df(f"""select player_id, season, archetypes, primary_archetype
                           from `{p}.nhl_models.player_archetypes`
                           where season in ({qs})""")
    bio = bq.query_df(f"""select player_id, shoots from `{p}.nhl_staging.stg_player_bio`""")
    # base (archetype_features) already provides 'position'; only pull the name here to avoid a collision
    names = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) as name
                            from `{p}.nhl_staging.stg_rosters` group by 1""")
    # per (player, season) team + headshot = the player's most recent NHL game that season.
    # Filter to NHL game-id types ('01' pre, '02' reg, '03' playoff): the data includes 2026
    # Olympic / 4-Nations games played by NATIONAL teams (ids 60-67, ...), whose team_id would
    # otherwise be picked as the player's "current team" and falsely flag cross-team lines.
    roster = bq.query_df(f"""select player_id, season,
        array_agg(team_id order by game_id desc limit 1)[offset(0)] as team,
        array_agg(headshot_url order by game_id desc limit 1)[offset(0)] as headshot
        from `{p}.nhl_staging.stg_rosters`
        where season in ({qs}) and substr(cast(game_id as string), 5, 2) in ('01', '02', '03')
        group by 1, 2""")

    df = base.merge(arch, on=["player_id", "season"], how="left")
    df = df.merge(bio, on="player_id", how="left")
    df = df.merge(names, on="player_id", how="left")
    df = df.merge(roster, on=["player_id", "season"], how="left")

    # 24-d archetype mix vector (zeros when a player-season was never archetyped)
    arch_mat = np.vstack([_arch_vector(a) for a in df["archetypes"].tolist()])
    for i, a in enumerate(ARCH_LIST):
        df[f"arch__{a}"] = arch_mat[:, i]

    df["shoots"] = df["shoots"].fillna("U")
    # career 5v5 minutes proxy for the rookie/extrapolation flag: this season's 5v5 TOI
    df["member_toi_5v5"] = pd.to_numeric(df["toi_5v5"], errors="coerce").fillna(0.0)
    df = df.set_index(["player_id", "season"])
    return df


def _arch_cols() -> list[str]:
    return [f"arch__{a}" for a in ARCH_LIST]


def feature_columns() -> list[str]:
    """The exact ordered model feature columns produced by aggregate_line()."""
    cols: list[str] = []
    for f in SCALAR_FEATS:
        cols += [f"{f}_mean", f"{f}_min", f"{f}_max"]
    cols += ["pair_arch_cos", "pair_shotloc_dist", "hand_balance", "burst_spread",
             "oz_tilt_mean", "n_members", "is_forward_line"]
    return cols


def aggregate_line(members: pd.DataFrame, line_type: str) -> dict:
    """Combine a line's member rows (subset of build_member_features) into one feature dict.

    members: DataFrame of the 2-3 member rows (any index). line_type: 'F3' or 'D2'.
    """
    feat: dict[str, float] = {}
    for f in SCALAR_FEATS:
        vals = pd.to_numeric(members[f], errors="coerce").astype("float64")
        vals = vals.fillna(vals.mean())
        feat[f"{f}_mean"] = float(vals.mean())
        feat[f"{f}_min"] = float(vals.min())
        feat[f"{f}_max"] = float(vals.max())

    arch = members[_arch_cols()].to_numpy(dtype="float64")
    dist = pd.to_numeric(members["mean_shot_distance"], errors="coerce").to_numpy(dtype="float64")
    burst = pd.to_numeric(members["edge_burst_per60"], errors="coerce").to_numpy(dtype="float64")
    oz = pd.to_numeric(members["edge_oz_pct"], errors="coerce").to_numpy(dtype="float64")
    shoots = members["shoots"].tolist()

    # pairwise means over the C(n,2) member pairs
    cos_vals, loc_vals = [], []
    for i, j in combinations(range(len(members)), 2):
        a, b = arch[i], arch[j]
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        cos_vals.append(float(np.dot(a, b) / denom) if denom > 0 else 0.0)
        if np.isfinite(dist[i]) and np.isfinite(dist[j]):
            loc_vals.append(abs(dist[i] - dist[j]))
    feat["pair_arch_cos"] = float(np.mean(cos_vals)) if cos_vals else 0.0
    feat["pair_shotloc_dist"] = float(np.mean(loc_vals)) if loc_vals else 0.0

    # handedness balance: 1.0 when L/R are evenly split, 0.0 when all one hand (knowns only)
    n_l = sum(1 for s in shoots if s == "L")
    n_r = sum(1 for s in shoots if s == "R")
    known = n_l + n_r
    feat["hand_balance"] = float(1.0 - abs(n_l - n_r) / known) if known else 0.5

    bvals = burst[np.isfinite(burst)]
    feat["burst_spread"] = float(bvals.max() - bvals.min()) if len(bvals) >= 2 else 0.0
    ovals = oz[np.isfinite(oz)]
    feat["oz_tilt_mean"] = float(ovals.mean()) if len(ovals) else float("nan")

    feat["n_members"] = float(len(members))
    feat["is_forward_line"] = 1.0 if line_type == "F3" else 0.0
    return feat
