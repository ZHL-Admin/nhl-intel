"""
Deserved standings via Monte Carlo (Phase 3.1, blueprint 5.2).

Replay every played regular-season game 10,000 times. In each replay both teams' goals are
Poisson with mean = that team's expected goals in the actual game (5v5 score-adjusted xG
from int_shot_score_adj.weighted_xgf + non-5v5 / special-teams xG from shot_xg;
empty-netters are already excluded from shot_xg). Points are awarded NHL-style:

  - regulation winner: 2 points, loser 0;
  - a simulated regulation tie goes to OT/SO -> the winner (a coin flip weighted by the
    two teams' xG share) gets 2, the loser gets the 1 "loser point".

Aggregating each team's points across the 10,000 replays gives a deserved-points
distribution; we publish the mean and the 10th/90th percentiles. Luck delta = actual points
minus deserved mean (positive = outperformed the chances; negative = unlucky).

Output: ``nhl_models.deserved_standings`` (season, team_id, games, actual_points,
deserved_points mean/p10/p90, luck_delta).

Run:  python -m models_ml.simulate_deserved [--season 2025-26] [--sims 10000] [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq

DEFAULT_SIMS = 10_000
MIN_XG = 0.05   # floor so Poisson(0) games are not degenerate
SEED = 13       # fixed: Math.random()/Date are unavailable; results stay reproducible

# Per-game, per-team deserved xG for regular-season games of one season. weighted_xgf is the
# 5v5 score-adjusted xG; the PP/SH piece is added from shot_xg. Actual points come from the
# final score + whether the game ended in OT/SO (loser point).
PULL_SQL = """
with games as (
  select game_id, season, game_date, home_team_id, away_team_id,
         home_team_score, away_team_score, last_period_type
  from `{p}.nhl_staging.stg_boxscores`
  where game_state in ('OFF', 'FINAL')
    and substr(cast(game_id as string), 5, 2) = '02'   -- regular season only
    and season = '{season}'
),
st as (   -- non-5v5 (special-teams) xG per team-game
  select s.game_id, s.team_id, sum(s.xg) as st_xg
  from `{p}.nhl_models.shot_xg` s
  join `{p}.nhl_staging.int_shot_sequence` q
    on s.game_id = q.game_id and s.event_id = q.event_id
  where s.xg is not null and q.strength in ('PP', 'SH')
  group by 1, 2
)
select g.game_id, g.season, g.home_team_id, g.away_team_id,
       g.home_team_score, g.away_team_score, g.last_period_type,
       coalesce(sa_h.weighted_xgf, 0) + coalesce(st_h.st_xg, 0) as home_xg,
       coalesce(sa_a.weighted_xgf, 0) + coalesce(st_a.st_xg, 0) as away_xg
from games g
left join `{p}.nhl_staging.int_shot_score_adj` sa_h
  on g.game_id = sa_h.game_id and g.home_team_id = sa_h.team_id
left join `{p}.nhl_staging.int_shot_score_adj` sa_a
  on g.game_id = sa_a.game_id and g.away_team_id = sa_a.team_id
left join st st_h on g.game_id = st_h.game_id and g.home_team_id = st_h.team_id
left join st st_a on g.game_id = st_a.game_id and g.away_team_id = st_a.team_id
"""


def latest_season() -> str:
    return bq.query_df(
        f"select max(season) s from `{bq.project()}.nhl_mart.mart_team_game_stats`"
    )["s"].iloc[0]


def actual_points(games: pd.DataFrame) -> pd.DataFrame:
    """NHL points from the real results: win 2, OT/SO loss 1, regulation loss 0."""
    rows = []
    ot = games["last_period_type"].isin(["OT", "SO"])
    for side, opp in [("home", "away"), ("away", "home")]:
        gf = games[f"{side}_team_score"]
        ga = games[f"{opp}_team_score"]
        pts = np.where(gf > ga, 2, np.where(ot, 1, 0))
        rows.append(pd.DataFrame({"team_id": games[f"{side}_team_id"], "points": pts}))
    out = pd.concat(rows)
    return out.groupby("team_id")["points"].agg(actual_points="sum", games="size").reset_index()


def simulate(games: pd.DataFrame, sims: int, rng: np.random.Generator) -> pd.DataFrame:
    """Vectorised Monte Carlo: returns long frame (team_id, sim, points)."""
    hx = np.clip(games["home_xg"].to_numpy(dtype="float64"), MIN_XG, None)
    ax = np.clip(games["away_xg"].to_numpy(dtype="float64"), MIN_XG, None)
    home = games["home_team_id"].to_numpy()
    away = games["away_team_id"].to_numpy()
    n = len(games)

    hg = rng.poisson(hx[:, None], size=(n, sims))     # (game, sim) home goals
    ag = rng.poisson(ax[:, None], size=(n, sims))
    # OT decided by an xG-share-weighted coin flip on tied sims
    share_home = (hx / (hx + ax))[:, None]
    ot_home_wins = rng.random((n, sims)) < share_home

    home_win = hg > ag
    away_win = ag > hg
    tie = ~home_win & ~away_win

    home_pts = np.where(home_win, 2,
               np.where(away_win, 0,
               np.where(ot_home_wins, 2, 1))).astype(np.int16)
    # away symmetrically: win 2, loss 0, OT win 2, OT loss 1
    away_pts = np.where(away_win, 2,
               np.where(home_win, 0,
               np.where(ot_home_wins, 1, 2))).astype(np.int16)

    # accumulate per team across games -> (team, sim) points
    teams = np.unique(np.concatenate([home, away]))
    idx = {t: i for i, t in enumerate(teams)}
    acc = np.zeros((len(teams), sims), dtype=np.int32)
    for gi in range(n):
        acc[idx[home[gi]]] += home_pts[gi]
        acc[idx[away[gi]]] += away_pts[gi]

    return teams, acc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None, help="season to simulate (default: latest)")
    ap.add_argument("--sims", type=int, default=DEFAULT_SIMS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    season = args.season or latest_season()
    games = bq.query_df(PULL_SQL.format(p=bq.project(), season=season))
    if games.empty:
        print(f"No regular-season games for {season}.")
        return
    for c in ["home_xg", "away_xg"]:
        games[c] = pd.to_numeric(games[c]).astype("float64")
    print(f"{season}: {len(games):,} regular-season games, simulating {args.sims:,}x ...")

    rng = np.random.default_rng(SEED)
    teams, acc = simulate(games, args.sims, rng)
    act = actual_points(games).set_index("team_id")

    out = pd.DataFrame({
        "team_id": teams,
        "deserved_points": acc.mean(axis=1),
        "deserved_p10": np.percentile(acc, 10, axis=1),
        "deserved_p90": np.percentile(acc, 90, axis=1),
    })
    out = out.merge(act, left_on="team_id", right_index=True, how="left")
    out["luck_delta"] = out["actual_points"] - out["deserved_points"]
    out["season"] = season
    out = out.sort_values("deserved_points", ascending=False).reset_index(drop=True)

    show = out[["team_id", "games", "actual_points", "deserved_points",
                "deserved_p10", "deserved_p90", "luck_delta"]].round(1)
    print("\nDeserved standings (top/bottom by deserved points):")
    print(show.head(8).to_string(index=False))
    print("...")
    print(show.tail(4).to_string(index=False))
    lucky = out.reindex(out["luck_delta"].abs().sort_values(ascending=False).index)
    print("\n3 luckiest:")
    print(lucky[lucky.luck_delta > 0].head(3)[["team_id", "actual_points",
          "deserved_points", "luck_delta"]].round(1).to_string(index=False))
    print("3 unluckiest:")
    print(lucky[lucky.luck_delta < 0].head(3)[["team_id", "actual_points",
          "deserved_points", "luck_delta"]].round(1).to_string(index=False))

    if args.dry_run:
        print("\n[dry-run] not writing nhl_models.deserved_standings")
        return
    write = out[["season", "team_id", "games", "actual_points", "deserved_points",
                 "deserved_p10", "deserved_p90", "luck_delta"]].copy()
    write["team_id"] = write["team_id"].astype("int64")
    write["games"] = write["games"].astype("int64")
    write["actual_points"] = write["actual_points"].astype("int64")
    # season-scoped replace so several seasons can coexist in the table
    cli = bq.client()
    table_id = f"{bq.project()}.{bq.config.MODELS_DATASET}.deserved_standings"
    try:
        cli.get_table(table_id)
        cli.query(f"delete from `{table_id}` where season = '{season}'").result()
        disp = "WRITE_APPEND"
    except Exception:
        disp = "WRITE_TRUNCATE"
    bq.write_df(write, "deserved_standings",
                write_disposition=disp, clustering_fields=["season", "team_id"])
    print(f"\nWrote {len(write)} rows to nhl_models.deserved_standings for {season}.")


if __name__ == "__main__":
    main()
