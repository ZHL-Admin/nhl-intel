"""
Team need profiles for the trade/free-agency fit tool (Phase 5.3, blueprint 6.4).

A team's need = where it falls short of the league's best teams, on two axes:
  (a) archetype gaps  — the team's TOI-weighted archetype mix vs the average mix of the top-8
                        teams by power rating (which roles is it short on?);
  (b) component gaps  — the team's summed composite by component (EV offense/defense, PP, PK,
                        finishing) vs the top-8 average (which kind of value is it short on?).

Output: nhl_models.team_needs (long format), one row per (team, season, need_type, key):
team_value, reference_value (top-8 avg), gap (reference - team; positive = a need). The trade-fit
service (models_ml/score_team_fit.py) reads this to score how well a player fills the gaps.

Run:  python -m models_ml.compute_team_needs [--season 2025-26] [--dry-run]
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from models_ml import bq, config

ARCH_LIST = sorted(set(config.ARCHETYPE_NAMES_V2.values()))
COMPONENTS = ["ev_offense", "ev_defense", "pp", "pk", "finishing"]
COMPONENT_LABEL = {
    "ev_offense": "Even-strength offense", "ev_defense": "Even-strength defense",
    "pp": "Power play", "pk": "Penalty kill", "finishing": "Finishing",
}


def _arch_vector(arch_json) -> np.ndarray:
    v = np.zeros(len(ARCH_LIST), dtype="float64")
    if not isinstance(arch_json, str):
        return v
    idx = {a: i for i, a in enumerate(ARCH_LIST)}
    for item in json.loads(arch_json):
        i = idx.get(item.get("archetype"))
        if i is not None:
            v[i] = float(item.get("weight", 0.0))
    return v


def _latest_season(p: str) -> str:
    return bq.query_df(f"select max(season) as s from `{p}.nhl_models.team_ratings`").iloc[0]["s"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    p = bq.project()
    season = args.season or _latest_season(p)

    # players: composite components + 5v5 TOI, archetype mix, and current NHL team that season
    players = bq.query_df(f"""
        with comp as (
            select player_id, {', '.join(COMPONENTS)}, toi_5v5
            from `{p}.nhl_models.player_composite` where season_window = '{season}'
        ),
        arch as (
            select player_id, archetypes from `{p}.nhl_models.player_archetypes`
            where season = '{season}'
        ),
        team as (
            select player_id,
                array_agg(team_id order by game_id desc limit 1)[offset(0)] as team_id
            from `{p}.nhl_staging.stg_rosters`
            where season = '{season}' and substr(cast(game_id as string), 5, 2) in ('01', '02', '03')
            group by 1
        )
        select c.player_id, t.team_id, c.toi_5v5, {', '.join('c.' + x for x in COMPONENTS)},
               a.archetypes
        from comp c
        join team t using (player_id)
        left join arch a using (player_id)
    """)
    players = players[players["team_id"].notna()].copy()
    for col in COMPONENTS + ["toi_5v5"]:
        players[col] = pd.to_numeric(players[col], errors="coerce").fillna(0.0)
    arch_mat = np.vstack([_arch_vector(a) for a in players["archetypes"].tolist()])

    # team archetype mix (TOI-weighted, renormalized) + summed components
    team_arch: dict[int, np.ndarray] = {}
    team_comp: dict[int, np.ndarray] = {}
    for team_id, idx in players.groupby("team_id").groups.items():
        rows = players.loc[idx]
        w = rows["toi_5v5"].to_numpy()
        sub = arch_mat[[players.index.get_loc(i) for i in idx]]
        mix = (sub * w[:, None]).sum(axis=0)
        s = mix.sum()
        team_arch[int(team_id)] = mix / s if s > 0 else mix
        team_comp[int(team_id)] = rows[COMPONENTS].to_numpy().sum(axis=0)

    # top-8 teams by current power rating
    ratings = bq.query_df(f"""
        select team_id, total_rating from (
            select team_id, total_rating,
                   row_number() over (partition by team_id order by game_date desc) rn
            from `{p}.nhl_models.team_ratings` where season = '{season}'
        ) where rn = 1 order by total_rating desc limit {config.TEAM_NEEDS_TOP_N}
    """)
    top8 = [int(t) for t in ratings["team_id"].tolist() if int(t) in team_arch]
    ref_arch = np.mean([team_arch[t] for t in top8], axis=0)
    ref_comp = np.mean([team_comp[t] for t in top8], axis=0)
    print(f"Season {season}: top-{len(top8)} reference teams {top8}")

    out_rows = []
    for team_id in team_arch:
        for i, a in enumerate(ARCH_LIST):
            tv, rv = float(team_arch[team_id][i]), float(ref_arch[i])
            out_rows.append(dict(team_id=team_id, season=season, need_type="archetype",
                                 key=a, label=a, team_value=tv, reference_value=rv, gap=rv - tv))
        for i, comp in enumerate(COMPONENTS):
            tv, rv = float(team_comp[team_id][i]), float(ref_comp[i])
            out_rows.append(dict(team_id=team_id, season=season, need_type="component",
                                 key=comp, label=COMPONENT_LABEL[comp],
                                 team_value=tv, reference_value=rv, gap=rv - tv))
    out = pd.DataFrame(out_rows)
    out["model_version"] = "team_needs_v1"

    # report: a couple of teams' biggest needs
    print("\n=== Sample team needs (largest gaps) ===")
    abbrev = _abbrev(p, season)
    for team_id in list(team_arch)[:3]:
        sub = out[(out.team_id == team_id)].sort_values("gap", ascending=False).head(3)
        needs = ", ".join(f"{r.label} ({r.gap:+.2f})" for r in sub.itertuples())
        print(f"  {abbrev.get(team_id, team_id)}: {needs}")

    if args.dry_run:
        print(f"\n[dry-run] {len(out)} rows not written")
        return
    out["team_id"] = out["team_id"].astype("int64")
    bq.write_df(out, "team_needs", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season", "team_id"])
    print(f"\nWrote {len(out)} rows to nhl_models.team_needs.")


def _abbrev(p: str, season: str) -> dict:
    df = bq.query_df(f"""select team_id, any_value(team_abbrev) a
                         from `{p}.nhl_mart.mart_team_game_stats`
                         where season = '{season}' group by 1""")
    return dict(zip(df["team_id"], df["a"]))


if __name__ == "__main__":
    main()
