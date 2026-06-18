"""
Skater skills radar (Part B1/B3) -> nhl_models.player_radar.

One row per (player_id, season) carrying an ORDERED, VARIABLE-LENGTH list of spokes. Each spoke has
a raw value, a percentile-WITHIN-POSITION (0-100, F and D separately, within the same season), an
optional uncertainty sd (noisy impact spokes), an honesty tag (skill / usage / style / proxy), and
a `present` flag. A spoke whose source is missing for a player-season is ABSENT from the list
(never zero, never greyed) — e.g. Edge burst before the tracking era.

Percentile baseline = within-position, within-season, over the clustering pool (>= ARCHETYPE_
MIN_5V5_MIN 5v5 minutes), so the radar and the archetypes agree. Burst is percentiled only within
the tracking-era cohort (same position-season; those are the only seasons with Edge).

Also writes the derived labels (B3): Overall family (coarse, by position), the offensive
sub-label (the specific v2 archetype — offense is high-resolution), a coarse defensive sub-label
from the deployment/impact spokes, and the archetype descriptor string.

Run:  python -m models_ml.compute_player_radar [--dry-run]
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from models_ml import bq, config

SEASONS = ["2015-16", "2016-17", "2017-18", "2018-19", "2019-20", "2020-21",
           "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

# spoke key -> (label, honesty tag). Ring order: offense arc -> boundary -> defense/style arc.
SPOKES = [
    ("finishing",        "Finishing",              "skill"),
    ("shot_volume",      "Shot Volume",            "skill"),
    ("shot_danger",      "Shot Danger",            "skill"),
    ("rush_offense",     "Rush Offense",           "skill"),
    ("cycle_forecheck",  "Cycle/Forecheck Offense","skill"),
    ("playmaking",       "Playmaking",             "skill"),
    ("ev_off_impact",    "EV Offensive Impact",    "skill"),
    ("pp_value",         "Power-Play Value",       "usage"),
    ("burst",            "Skating/Burst",          "skill"),     # tracking-era only
    ("ev_def_impact",    "EV Defensive Impact",    "skill"),     # noisy -> sd band
    ("pk_role",          "Penalty Kill Role",      "usage"),
    ("def_deployment",   "Defensive Deployment",   "usage"),
    ("penalty_diff",     "Penalty Differential",   "skill"),
    ("physicality",      "Physicality (rink-adj)", "style"),
]
SD_SPOKES = {"ev_off_impact": "off_sd", "ev_def_impact": "def_sd"}  # value_col -> sd_col

# name -> family / descriptor, derived from the v2 config (merged labels share both)
_NAME_FAMILY = {config.ARCHETYPE_NAMES_V2[k]: config.ARCHETYPE_FAMILY_V2[k]
                for k in config.ARCHETYPE_NAMES_V2}
_NAME_DESC = {config.ARCHETYPE_NAMES_V2[k]: config.ARCHETYPE_DESCRIPTORS_V2[k]
              for k in config.ARCHETYPE_NAMES_V2}

BASE_SQL = """
with pg as (
  select player_id, season, any_value(position_code) as position,
    count(*) as games, sum(toi_5v5) as toi_5v5,
    sum(individual_shot_attempts) as attempts, sum(ixg) as ixg,
    sum(first_assists) as first_assists,
    sum(seq_rush_attempts) as rush, sum(seq_forecheck_attempts) as forecheck,
    sum(seq_cycle_attempts) as cycle, sum(hits_adj) as hits_adj
  from `{p}.nhl_mart.mart_player_game_stats`
  where substr(cast(game_id as string), 5, 2) in ('02', '03')
  group by 1, 2
),
toi as (   -- total on-ice TOI (all strengths) for per-60 denominators
  select player_id, season, sum(segment_duration) / 60.0 as total_toi
  from `{p}.nhl_staging.int_shift_segments`
  where is_goalie = 0 and substr(cast(game_id as string), 5, 2) in ('02', '03')
  group by 1, 2
),
pen as (
  select player_id, season, sum(drawn) as drawn, sum(taken) as taken from (
    select drawn_by_player_id as player_id, season, count(*) as drawn, 0 as taken
    from `{p}.nhl_staging.stg_play_by_play`
    where type_desc_key = 'penalty' and drawn_by_player_id is not null
      and substr(cast(game_id as string), 5, 2) in ('02', '03') group by 1, 2
    union all
    select committed_by_player_id as player_id, season, 0 as drawn, count(*) as taken
    from `{p}.nhl_staging.stg_play_by_play`
    where type_desc_key = 'penalty' and committed_by_player_id is not null
      and substr(cast(game_id as string), 5, 2) in ('02', '03') group by 1, 2
  ) group by 1, 2
)
select pg.*, toi.total_toi, coalesce(pen.drawn, 0) as drawn, coalesce(pen.taken, 0) as taken,
  imp.off_impact, imp.off_sd, imp.def_impact, imp.def_sd, imp.pp_impact,
  comp.finishing,
  ct.trust_score, ct.pk_share,
  edge.bursts_22_plus_per60, edge.max_skating_speed_mph,
  arch.primary_archetype
from pg
left join toi using (player_id, season)
left join pen using (player_id, season)
left join `{p}.nhl_models.player_impact` imp on imp.player_id = pg.player_id and imp.season_window = pg.season
left join `{p}.nhl_models.player_composite` comp on comp.player_id = pg.player_id and comp.season_window = pg.season
left join `{p}.nhl_models.player_coach_trust` ct on ct.player_id = pg.player_id and ct.season_window = pg.season
left join `{p}.nhl_mart.mart_edge_player_profile` edge on edge.player_id = pg.player_id
  and edge.season_id = cast(substr(pg.season, 1, 4) || '20' || substr(pg.season, 6, 2) as int64)
  and edge.game_type = 2
left join `{p}.nhl_models.player_archetypes` arch on arch.player_id = pg.player_id and arch.season = pg.season
"""


def _raw_values(df: pd.DataFrame) -> pd.DataFrame:
    """Compute each spoke's raw value (np.nan where the source is absent)."""
    num = lambda c: pd.to_numeric(df[c], errors="coerce")
    toi = num("total_toi").replace(0, np.nan)
    att = num("attempts").replace(0, np.nan)
    out = pd.DataFrame(index=df.index)
    toi5 = num("toi_5v5").replace(0, np.nan)
    out["finishing"] = num("finishing")
    out["shot_volume"] = num("attempts") / toi5 * 60.0
    out["shot_danger"] = num("ixg") / att          # per-attempt: this IS a quality (efficiency) metric
    # Rush / cycle "offense" are VOLUME measures of how much rush/cycle generation a player drives,
    # so they must be per-60 RATES (like shot_volume / playmaking) — NOT a share of the player's own
    # attempts. As a share they penalize high-volume shooters (e.g. McDavid's 17 rush of ~540
    # attempts reads low), which is wrong; the per-60 rate ranks elite rush/cycle creators correctly.
    out["rush_offense"] = num("rush") / toi5 * 60.0
    out["cycle_forecheck"] = (num("cycle") + num("forecheck")) / toi5 * 60.0
    out["playmaking"] = num("first_assists") / toi * 60.0
    out["ev_off_impact"] = num("off_impact")
    out["pp_value"] = num("pp_impact")
    out["burst"] = num("bursts_22_plus_per60")
    out["ev_def_impact"] = num("def_impact")
    out["pk_role"] = num("pk_share")
    out["def_deployment"] = num("trust_score")
    out["penalty_diff"] = (num("drawn") - num("taken")) / toi * 60.0
    out["physicality"] = num("hits_adj") / toi * 60.0
    out["off_sd"] = num("off_sd")
    out["def_sd"] = num("def_sd")
    return out


def _defensive_sublabel(pk_p, dep_p, def_p) -> str:
    """Coarse, deployment-leaning defensive sub-label from spoke percentiles (0-100, may be NaN)."""
    dep = dep_p if np.isfinite(dep_p) else 50.0
    pk = pk_p if np.isfinite(pk_p) else 50.0
    dfi = def_p if np.isfinite(def_p) else 50.0
    if dep >= 66 and pk >= 60:
        return "Heavy defensive deployment"
    if dep >= 55 or pk >= 60:
        return "Some defensive responsibility"
    if dfi >= 66:
        return "Strong on-ice defensive results"
    if dep <= 33 and pk <= 33:
        return "Sheltered / offensive usage"
    return "Balanced two-way usage"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    p = bq.project()

    df = bq.query_df(BASE_SQL.format(p=p))
    df = df[df["season"].isin(SEASONS)].copy()
    df["toi_5v5"] = pd.to_numeric(df["toi_5v5"], errors="coerce")
    df = df[(df["position"].isin(["C", "L", "R", "D"]))
            & (df["toi_5v5"] >= config.ARCHETYPE_MIN_5V5_MIN)].copy()
    df["pos_group"] = np.where(df["position"] == "D", "D", "F")
    raw = _raw_values(df)

    # percentile within (pos_group, season) over non-null values
    pctl = pd.DataFrame(index=df.index)
    grp = [df["pos_group"], df["season"]]
    for key, *_ in SPOKES:
        pctl[key] = raw.groupby(grp)[key].rank(pct=True) * 100.0

    rows = []
    for i in df.index:
        spokes = []
        for key, label, tag in SPOKES:
            val = raw.at[i, key]
            if not np.isfinite(val):
                continue                                   # ABSENT spoke — omit entirely
            sd_col = SD_SPOKES.get(key)
            sd = raw.at[i, sd_col] if sd_col else np.nan
            spokes.append({
                "key": key, "label": label, "tag": tag,
                "value": round(float(val), 4),
                "percentile": round(float(pctl.at[i, key]), 1) if np.isfinite(pctl.at[i, key]) else None,
                "sd": round(float(sd), 4) if (sd_col and np.isfinite(sd)) else None,
                "present": True,
            })
        primary = df.at[i, "primary_archetype"]
        family = _NAME_FAMILY.get(primary)
        def_sub = _defensive_sublabel(pctl.at[i, "pk_role"], pctl.at[i, "def_deployment"],
                                      pctl.at[i, "ev_def_impact"])
        rows.append({
            "player_id": int(df.at[i, "player_id"]), "season": df.at[i, "season"],
            "pos_group": df.at[i, "pos_group"], "position": df.at[i, "position"],
            "spokes": json.dumps(spokes),
            "overall_label": family, "offensive_label": primary,
            "defensive_label": def_sub, "descriptor": _NAME_DESC.get(primary),
            "baseline": f"percentile within {'forwards' if df.at[i,'pos_group']=='F' else 'defensemen'}, {df.at[i,'season']}",
            "n_spokes": len(spokes),
        })
    out = pd.DataFrame(rows)
    out["model_version"] = "radar_v1"

    print(f"player_radar: {len(out)} player-seasons "
          f"(F={int((out.pos_group=='F').sum())}, D={int((out.pos_group=='D').sum())})")
    print("spoke coverage (rows with each spoke present):")
    allspokes = [s for js in out["spokes"] for s in json.loads(js)]
    cov = pd.Series([s["key"] for s in allspokes]).value_counts()
    for key, label, _ in SPOKES:
        print(f"  {label:26s} {int(cov.get(key, 0)):5d}")

    if args.dry_run:
        print("[dry-run] not written")
        return
    bq.write_df(out, "player_radar", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season", "player_id"])
    print(f"Wrote {len(out)} rows to nhl_models.player_radar.")


if __name__ == "__main__":
    main()
