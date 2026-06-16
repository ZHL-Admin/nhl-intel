"""
Aging curves per archetype (Phase 4.4, blueprint 5.4).

Delta method: for each player, the year-over-year change in production at consecutive ages,
averaged by age within an archetype, integrated into a curve. Decisions:

- Production = **points per 82** (G + A1 + A2), available 2010+, used for both the cohort curve
  and the player's path so they overlay. (Composite is tracking-era only; documented.)
- Each age t->t+1 delta is attributed to the player's archetype in **season t** (start of the
  pair) — the blueprint's per-season hard-max, with a single well-defined owner per delta so
  per-season reassignment can't scramble the paired deltas. Archetypes exist 2015-16+ only;
  pre-2015 seasons have no archetype and don't contribute to per-archetype curves. The
  burst-defined archetypes (Elite Speed Driver, Elite Offensive D) are sparse before 2021 (see
  archetypes.md collapse note), so their curves are tracking-era-dominated.

Output: nhl_models.aging_curves (archetype, age, n_deltas, expected_delta, curve_value) where
curve_value is the integrated, smoothed points-per-82 level anchored at the league mean for the
archetype at the reference age.

Run:  python -m models_ml.fit_aging_curves [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq

MIN_GAMES = 20            # per season, to keep points/82 stable
REF_AGE = 24             # anchor age for the level curve
SMOOTH_WIN = 3           # centered rolling-mean window over age (loess-lite)
MIN_DELTAS = 15          # min paired deltas to publish an (archetype, age) point

PULL_SQL = """
with pg as (
  select player_id, season,
    sum(individual_goals + first_assists + second_assists) as points,
    count(*) as gp
  from `{p}.nhl_mart.mart_player_game_stats`
  where substr(cast(game_id as string), 5, 2) in ('02', '03')
  group by 1, 2
  having count(*) >= {min_games}
),
arch as (
  select player_id, season, primary_archetype, pos_group
  from `{p}.nhl_models.player_archetypes`
),
bio as (select player_id, birth_date from `{p}.nhl_staging.stg_player_bio`)
select pg.player_id, pg.season, pg.points / pg.gp * 82 as points82,
       a.primary_archetype, a.pos_group,
       date_diff(date(cast(substr(pg.season, 1, 4) as int64), 10, 1), b.birth_date, day) / 365.25 as age_exact
from pg
join arch a on pg.player_id = a.player_id and pg.season = a.season
join bio b on pg.player_id = b.player_id
"""


def pull() -> pd.DataFrame:
    df = bq.query_df(PULL_SQL.format(p=bq.project(), min_games=MIN_GAMES))
    df["points82"] = pd.to_numeric(df["points82"]).astype("float64")
    df["age"] = np.floor(pd.to_numeric(df["age_exact"])).astype("int64")
    df["season_start"] = df["season"].str[:4].astype(int)
    return df


def deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Paired consecutive-season deltas, attributed to the start season's archetype/age."""
    df = df.sort_values(["player_id", "season_start"])
    nxt = df[["player_id", "season_start", "points82"]].rename(
        columns={"season_start": "next_start", "points82": "points82_next"})
    nxt["season_start"] = nxt["next_start"] - 1
    m = df.merge(nxt[["player_id", "season_start", "points82_next"]],
                 on=["player_id", "season_start"], how="inner")
    m["delta"] = m["points82_next"] - m["points82"]
    return m  # start-season archetype/age own the delta


def build_curves(d: pd.DataFrame, levels: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for arch, g in d.groupby(group_col):
        by_age = (g.groupby("age")["delta"].agg(["mean", "size"]).reset_index()
                  .rename(columns={"mean": "expected_delta", "size": "n_deltas"}))
        by_age = by_age[by_age["n_deltas"] >= MIN_DELTAS].sort_values("age")
        if len(by_age) < 4:
            continue
        # smooth, then integrate to a relative curve
        by_age["expected_delta"] = (by_age["expected_delta"]
                                    .rolling(SMOOTH_WIN, center=True, min_periods=1).mean())
        ages = by_age["age"].to_numpy()
        cum = np.concatenate([[0.0], np.cumsum(by_age["expected_delta"].to_numpy()[:-1])])
        by_age["rel"] = cum
        # anchor so the curve reads in points/82: align to the archetype mean at REF_AGE
        anchor_age = int(ages[np.argmin(np.abs(ages - REF_AGE))])
        lvl = levels[(levels[group_col] == arch) & (levels["age"] == anchor_age)]
        anchor = float(lvl["points82"].iloc[0]) if len(lvl) else float(by_age["rel"].mean())
        rel_at_anchor = float(by_age.loc[by_age["age"] == anchor_age, "rel"].iloc[0])
        by_age["curve_value"] = by_age["rel"] - rel_at_anchor + anchor
        by_age["archetype"] = arch
        rows.append(by_age[["archetype", "age", "n_deltas", "expected_delta", "curve_value"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    df = pull()
    d = deltas(df)
    # per-archetype curves + position-group fallback curves (for sparse/burst-defined archetypes)
    arch_levels = df.groupby(["primary_archetype", "age"])["points82"].mean().reset_index()
    pos_levels = df.groupby(["pos_group", "age"])["points82"].mean().reset_index()
    arch_curves = build_curves(d, arch_levels, "primary_archetype")
    pos_curves = build_curves(d, pos_levels, "pos_group")
    if not pos_curves.empty:
        pos_curves["archetype"] = pos_curves["archetype"].map(
            {"F": "All Forwards", "D": "All Defensemen"}).fillna(pos_curves["archetype"])
    curves = pd.concat([c for c in [arch_curves, pos_curves] if not c.empty], ignore_index=True)
    if curves.empty:
        print("No curves built.")
        return

    # validation: a forward archetype curve should peak in the mid-20s
    for arch in ["Two-Way Top-Six", "Inside Scorer", "Perimeter Playmaker"]:
        c = curves[curves["archetype"] == arch]
        if len(c):
            peak = int(c.loc[c["curve_value"].idxmax(), "age"])
            print(f"  {arch:22s} peak age {peak} (ages {c.age.min()}-{c.age.max()}, "
                  f"{int(c.n_deltas.sum())} deltas)")

    if args.dry_run:
        print(f"\n[dry-run] {len(curves)} curve points not written")
        return
    curves["model_version"] = "aging_v1"
    bq.write_df(curves, "aging_curves", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["archetype"])
    print(f"\nWrote {len(curves)} rows to nhl_models.aging_curves "
          f"({curves['archetype'].nunique()} archetypes).")


if __name__ == "__main__":
    main()
