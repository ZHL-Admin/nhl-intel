"""
Streak Doctor (Phase 3.3, blueprint 5.3).

Decompose a team's last-N-game run into goal-scale components, attach a deterministic verdict
and a 0-100 sustainability meter, and flag notable runs. The five components (all in GOALS
over the window):

  - shooting_luck   = goals for - xGF                  (on-ice finishing above expected)
  - goaltending     = team GSAx (xGA - GA)             (saves above expected)
  - special_teams   = actual non-5v5 goal diff - expected (PP + PK variance)
  - schedule        = (mean opponent rating faced) x games  (credit for a hard schedule)
  - play_change     = (window 5v5 score-adj xGF% - season baseline) -> goals (real play shift)

total_deviation is the SUM of the five components (so shares sum to 100%); it approximates
the window's goal differential minus the team's season-baseline expectation. The
sustainability meter weights each component by its known persistence (config.STREAK_PERSISTENCE).

Output: nhl_models.streak_cards, one row per (season, team_id, window) for the windows in
config.STREAK_WINDOWS; is_notable is computed on the default window.

Run:  python -m models_ml.streak_doctor [--season 2025-26] [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config

# Per team-game inputs for one season (regular + playoffs), ordered by date.
PULL_SQL = """
with base as (
  select m.game_id, m.game_date, m.season, m.team_id, ii.opponent_team_id,
         m.goals_for, m.goals_against, m.xgf, m.xgf_pct_score_adj
  from `{p}.nhl_mart.mart_team_game_stats` m
  join `{p}.nhl_mart.mart_team_identity_inputs` ii
    on m.game_id = ii.game_id and m.team_id = ii.team_id
  where m.season = '{season}' and substr(cast(m.game_id as string), 5, 2) in ('02', '03')
),
gsx as (
  select game_id, team_id, sum(gsax) as gsax
  from `{p}.nhl_mart.mart_goalie_game_stats` group by 1, 2
),
st as (
  select s.game_id, s.team_id,
         sum(if(q.strength in ('PP','SH'), s.xg, 0)) as xgf_st,
         sum(if(q.strength in ('PP','SH'), cast(q.is_goal as int64), 0)) as g_st_for
  from `{p}.nhl_models.shot_xg` s
  join `{p}.nhl_staging.int_shot_sequence` q
    on s.game_id = q.game_id and s.event_id = q.event_id
  where s.xg is not null
  group by 1, 2
),
result as (
  select game_id,
    home_team_id, away_team_id, home_team_score, away_team_score,
    last_period_type
  from `{p}.nhl_staging.stg_boxscores`
  where game_state in ('OFF', 'FINAL')
),
rating as (
  select game_id, team_id, total_rating from `{p}.nhl_models.team_ratings`
)
select b.game_id, b.game_date, b.season, b.team_id, b.opponent_team_id,
       b.goals_for, b.goals_against, b.xgf, b.xgf_pct_score_adj,
       coalesce(g.gsax, 0) as gsax,
       coalesce(st.xgf_st, 0) as xgf_st, coalesce(st.g_st_for, 0) as g_st_for,
       coalesce(sto.xgf_st, 0) as xgf_st_against, coalesce(sto.g_st_for, 0) as g_st_against,
       coalesce(ro.total_rating, 0) as opp_rating,
       case
         when b.team_id = r.home_team_id and r.home_team_score > r.away_team_score then 2
         when b.team_id = r.away_team_id and r.away_team_score > r.home_team_score then 2
         when r.last_period_type in ('OT', 'SO') then 1
         else 0
       end as points
from base b
left join gsx g on b.game_id = g.game_id and b.team_id = g.team_id
left join st on b.game_id = st.game_id and b.team_id = st.team_id
left join st sto on b.game_id = sto.game_id and b.opponent_team_id = sto.team_id
left join rating ro on b.game_id = ro.game_id and b.opponent_team_id = ro.team_id
left join result r on b.game_id = r.game_id
order by b.team_id, b.game_date
"""

COMPONENTS = ["shooting_luck", "goaltending", "special_teams", "schedule", "play_change"]
COMP_LABEL = {
    "shooting_luck": "shooting luck", "goaltending": "goaltending",
    "special_teams": "special teams", "schedule": "schedule strength",
    "play_change": "a genuine play change",
}


def latest_season() -> str:
    return bq.query_df(
        f"select max(season) s from `{bq.project()}.nhl_mart.mart_team_game_stats`")["s"].iloc[0]


def pull(season: str) -> pd.DataFrame:
    df = bq.query_df(PULL_SQL.format(p=bq.project(), season=season))
    df["game_date"] = pd.to_datetime(df["game_date"])
    num = ["goals_for", "goals_against", "xgf", "xgf_pct_score_adj", "gsax", "xgf_st",
           "g_st_for", "xgf_st_against", "g_st_against", "opp_rating", "points"]
    for c in num:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    return df.sort_values(["team_id", "game_date"]).reset_index(drop=True)


def trailing_streak(points: np.ndarray) -> int:
    """Signed current streak: +k for k straight wins, -k for k straight non-wins (from the end)."""
    if len(points) == 0:
        return 0
    last_win = points[-1] == 2
    k = 0
    for p in points[::-1]:
        if (p == 2) == last_win:
            k += 1
        else:
            break
    return k if last_win else -k


def verdict(comp: dict, total: float, run_word: str, n: int, play_change: float,
            league_5v5_total: float) -> str:
    gross = sum(abs(v) for v in comp.values()) or 1.0
    # the driver is the biggest component pushing in the run's direction (sign of total);
    # fall back to the biggest absolute mover if nothing aligns.
    sign = 1 if total >= 0 else -1
    aligned = {k: v for k, v in comp.items() if (v >= 0) == (sign >= 0) and v != 0}
    dom = (max(aligned, key=lambda k: abs(aligned[k])) if aligned
           else max(comp, key=lambda k: abs(comp[k])))
    pct = round(abs(comp[dom]) / gross * 100)
    detail = {
        "shooting_luck": f"{comp['shooting_luck']:+.1f} goals vs expected",
        "goaltending": f"{comp['goaltending']:+.1f} GSAx",
        "special_teams": f"{comp['special_teams']:+.1f} special-teams goals vs expected",
        "schedule": f"{comp['schedule']:+.1f}-goal schedule effect",
        "play_change": f"5v5 xG share {'up' if play_change >= 0 else 'down'}",
    }[dom]
    play_word = ("improved" if play_change > 0.15 * n / 10
                 else "worse" if play_change < -0.15 * n / 10 else "unchanged")
    return (f"{pct}% of this {n}-game {run_word} traces to {COMP_LABEL[dom]} "
            f"({detail}). Underlying 5v5 play is {play_word}.")


def compute_card(sub: pd.DataFrame, window: int, season_mean_pts: float,
                 season_std_pts: float, season_xgf_pct: float,
                 league_5v5_total: float) -> dict | None:
    if len(sub) < window:
        return None
    w = sub.tail(window)
    n = len(w)
    shooting_luck = float(w["goals_for"].sum() - w["xgf"].sum())
    goaltending = float(w["gsax"].sum())
    special_teams = float((w["g_st_for"].sum() - w["g_st_against"].sum())
                          - (w["xgf_st"].sum() - w["xgf_st_against"].sum()))
    schedule = float(w["opp_rating"].mean() * n)  # +ve = faced strong opponents (credit)
    dshare = float(w["xgf_pct_score_adj"].mean() - season_xgf_pct)
    play_change = dshare * 2.0 * league_5v5_total * n
    comp = {"shooting_luck": shooting_luck, "goaltending": goaltending,
            "special_teams": special_teams, "schedule": schedule, "play_change": play_change}
    total = float(sum(comp.values()))

    gross = sum(abs(v) for v in comp.values()) or 1.0
    sustainability = round(sum(config.STREAK_PERSISTENCE[k] * abs(v)
                               for k, v in comp.items()) / gross * 100)

    pts = w["points"].to_numpy()
    window_pts_pace = float(pts.mean())
    z = ((window_pts_pace - season_mean_pts) / (season_std_pts / np.sqrt(n))
         if season_std_pts > 0 else 0.0)
    streak = trailing_streak(sub["points"].to_numpy())
    # run direction follows the goal-diff deviation the components explain (keeps the verdict
    # coherent with its driver); notability still uses the fan-facing points pace below.
    run_word = "surge" if total >= 0 else "slump"
    is_notable = (abs(z) >= config.STREAK_NOTABLE_Z
                  or abs(streak) >= config.STREAK_NOTABLE_STREAK)

    card = {
        "season": sub["season"].iloc[0], "team_id": int(sub["team_id"].iloc[0]),
        "window_games": window, "games": n,
        "total_deviation": total, "sustainability": int(sustainability),
        "points_pace": window_pts_pace, "points_pace_z": float(z),
        "streak": int(streak), "is_notable": bool(is_notable),
        "run_word": run_word,
        "verdict": verdict(comp, total, run_word, n, play_change, league_5v5_total),
    }
    for k in COMPONENTS:
        card[k] = comp[k]
        card[k + "_share"] = float(comp[k] / total) if abs(total) > 1e-9 else 0.0
    return card


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    season = args.season or latest_season()
    df = pull(season)
    if df.empty:
        print(f"No games for {season}.")
        return
    # league 5v5 scale for the play-change conversion: combined per-game 5v5 xG. Approximate
    # using all-situations xGF mean x ~0.82 (5v5 share) is brittle; instead use xgf_pct only
    # to scale to goals via league per-game goals. Use league avg goals for per game.
    league_5v5_total = float(df["xgf"].mean() * 2 * 0.80)  # ~combined 5v5 xG/game proxy
    season_xgf_pct = df.groupby("team_id")["xgf_pct_score_adj"].transform("mean")
    df["season_xgf_pct"] = season_xgf_pct

    cards = []
    for team_id, sub in df.groupby("team_id"):
        sub = sub.sort_values("game_date")
        smean = float(sub["points"].mean())
        sstd = float(sub["points"].std(ddof=0))
        sxgf = float(sub["xgf_pct_score_adj"].mean())
        for window in config.STREAK_WINDOWS:
            card = compute_card(sub, window, smean, sstd, sxgf, league_5v5_total)
            if card:
                cards.append(card)
    out = pd.DataFrame(cards)
    if out.empty:
        print("No cards computed.")
        return

    default = out[out["window_games"] == config.STREAK_DEFAULT_WINDOW]
    notable = default[default["is_notable"]].sort_values("points_pace_z", ascending=False)
    ab = dict(zip(*bq.query_df(
        f"select distinct team_id, team_abbrev from `{bq.project()}.nhl_mart.mart_team_game_stats` "
        f"where season='{season}'").values.T))
    print(f"{season}: {len(out)} cards ({out['team_id'].nunique()} teams x {len(config.STREAK_WINDOWS)} windows).")
    print(f"Notable runs (window {config.STREAK_DEFAULT_WINDOW}): {len(notable)}")
    for _, r in notable.iterrows():
        print(f"  {ab.get(r['team_id'], r['team_id'])}: {r['verdict']} "
              f"[sustainability {r['sustainability']}]")

    if args.dry_run:
        print("\n[dry-run] not writing nhl_models.streak_cards")
        return
    cli = bq.client()
    table_id = f"{bq.project()}.{bq.config.MODELS_DATASET}.streak_cards"
    try:
        cli.get_table(table_id)
        cli.query(f"delete from `{table_id}` where season = '{season}'").result()
        disp = "WRITE_APPEND"
    except Exception:
        disp = "WRITE_TRUNCATE"
    bq.write_df(out, "streak_cards", write_disposition=disp,
                clustering_fields=["season", "team_id"])
    print(f"\nWrote {len(out)} rows to nhl_models.streak_cards for {season}.")


if __name__ == "__main__":
    main()
