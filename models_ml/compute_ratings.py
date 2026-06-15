"""
Power ratings with visible components (Phase 3.1, blueprint 5.2).

A team's rating is the sum of four components, each on a **goals-per-game** scale so the
stacked-bar product reads as "where this team's edge comes from":

  1. play_5v5     - score-and-opponent-adjusted 5v5 xGF% converted to a goal differential
                    per game at the season's league-average 5v5 scoring. The "process"
                    term: chance generation minus chance suppression at even strength.
  2. finishing    - 5v5 (goals for - xGF), per game, regressed toward 0 by shot volume
                    (shrinkage k, tuned by season-over-season predictiveness). Shooting
                    talent above expected.
  3. goaltending  - even-strength GSAx (xGA - GA) per game, regressed similarly. Save
                    talent above expected.
  4. special_teams- PP + PK goals above expected per game: (actual non-5v5 goal diff) minus
                    (expected non-5v5 goal diff). Captures both PP conversion and PK kill.

These four partition a team's goal differential cleanly (5v5 GF-GA decomposes into
process + finishing + goaltending; special teams is the non-5v5 remainder), so there is no
double counting. Component WEIGHTS are fit by out-of-sample prediction of game results
(logistic on pregame rating-component differences -> home win), then normalised to mean 1
so the total stays on the goals/game scale. Ranking order is invariant to that scaling.

Opponent adjustment is the project's established half-weighted, season-to-date method
(same as the Phase 2.3 mart interim), computed here in Python from the *score-adjusted*
xGF% input only -- it never reads the mart's own ``*_opp_adj`` column, so there is no
circular dependency between this job and ``mart_team_game_stats``.

Output: ``nhl_models.team_ratings``, one row per (team, game_date) carrying the
season-to-date rating THROUGH that date (inclusive): total, the four weighted component
contributions (they sum to total), each raw component, a bootstrap-style standard error,
games played, and trajectory (rating now minus rating 15 days ago). The latest row per
(team, season) is the current power rating the Rankings page renders. The win-probability
prior reads the most recent row STRICTLY before a game's date as the pregame strength.

Run:  python -m models_ml.compute_ratings [--season 2025-26] [--tune-k] [--dry-run]
Outputs: nhl_models.team_ratings, docs/methodology/power-ratings.md (weights + accuracy).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss

from models_ml import bq, config

MODEL_VERSION = "ratings_v1"
METHODOLOGY = Path(__file__).parent.parent / "docs" / "methodology" / "power-ratings.md"

COMPONENTS = ["play_5v5", "finishing", "goaltending", "special_teams"]
OPP_ADJ_WEIGHT = 0.5          # half-weighted opponent adjustment (matches Phase 2.3 mart)
OPP_ADJ_ITERS = 3             # season-to-date opponent strength is a fixed input; light passes
TRAJECTORY_DAYS = 15
BOOTSTRAP_MIN_GAMES = 3       # below this, SE is not meaningful
WEIGHT_FIT_MIN_SEASON = "2015-16"
WEIGHT_FIT_MAX_SEASON = "2023-24"   # 2024-25 = validation, 2025-26 = holdout (reported)

# Per-team-game component inputs. The strength splits come from shot_xg (non-empty-net,
# so goals and xG share one population) joined to int_shot_sequence for the strength label.
PULL_SQL = """
with base as (
  select game_id, game_date, season, team_id, home_away,
         goals_for, goals_against, xgf_pct_score_adj
  from `{p}.nhl_mart.mart_team_game_stats`
  -- game_id chars 5-6 encode game type: 02 = regular season, 03 = playoffs. Exclude
  -- preseason (01) and exhibition/all-star (04/09/...) which would distort team strength.
  where substr(cast(game_id as string), 5, 2) in ('02', '03') {where}
),
sx as (
  select s.game_id, s.team_id, q.strength,
         sum(s.xg) as xg, sum(cast(q.is_goal as int64)) as g, count(*) as shots
  from `{p}.nhl_models.shot_xg` s
  join `{p}.nhl_staging.int_shot_sequence` q
    on s.game_id = q.game_id and s.event_id = q.event_id
  where s.xg is not null
  group by 1, 2, 3
),
sxp as (
  select game_id, team_id,
    sum(if(strength = '5v5', xg, 0))   as xgf_5v5,
    sum(if(strength = '5v5', g, 0))    as g5v5_for,
    sum(if(strength = '5v5', shots, 0)) as shots_5v5,
    sum(if(strength in ('PP', 'SH'), xg, 0))   as xgf_st,
    sum(if(strength in ('PP', 'SH'), g, 0))    as g_st_for
  from sx group by 1, 2
),
gsx as (
  select game_id, team_id, sum(ev_gsax) as ev_gsax, sum(ev_shots) as ev_shots
  from `{p}.nhl_mart.mart_goalie_game_stats` group by 1, 2
)
select b.game_id, b.game_date, b.season, b.team_id, b.home_away,
       b.goals_for, b.goals_against, b.xgf_pct_score_adj,
       coalesce(p.xgf_5v5, 0)  as xgf_5v5,
       coalesce(p.g5v5_for, 0) as g5v5_for,
       coalesce(p.shots_5v5, 0) as shots_5v5,
       coalesce(p.xgf_st, 0)   as xgf_st,
       coalesce(p.g_st_for, 0) as g_st_for,
       coalesce(g.ev_gsax, 0)  as ev_gsax,
       coalesce(g.ev_shots, 0) as ev_shots
from base b
left join sxp p on b.game_id = p.game_id and b.team_id = p.team_id
left join gsx g on b.game_id = g.game_id and b.team_id = g.team_id
"""


def pull(where: str = "") -> pd.DataFrame:
    df = bq.query_df(PULL_SQL.format(p=bq.project(), where=where))
    df["game_date"] = pd.to_datetime(df["game_date"])
    num = ["goals_for", "goals_against", "xgf_pct_score_adj", "xgf_5v5", "g5v5_for",
           "shots_5v5", "xgf_st", "g_st_for", "ev_gsax", "ev_shots"]
    for c in num:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    df["xgf_pct_score_adj"] = df["xgf_pct_score_adj"].fillna(0.5)
    return df.sort_values(["season", "game_date", "game_id", "team_id"]).reset_index(drop=True)


def add_opponent_columns(df: pd.DataFrame) -> pd.DataFrame:
    """For each (game, team) attach the opponent's same-game aggregates (against side)."""
    opp = df[["game_id", "team_id", "g5v5_for", "xgf_5v5", "g_st_for", "xgf_st",
              "xgf_pct_score_adj"]].rename(columns={
        "team_id": "opp_id", "g5v5_for": "g5v5_against", "xgf_5v5": "xgf_5v5_against",
        "g_st_for": "g_st_against", "xgf_st": "xgf_st_against",
        "xgf_pct_score_adj": "opp_xgf_pct_raw"})
    # the opponent is the other team_id sharing the game_id
    merged = df.merge(opp, on="game_id")
    merged = merged[merged["team_id"] != merged["opp_id"]].copy()
    return merged


def _expanding_mean_pre(s: pd.Series) -> pd.Series:
    """Season-to-date mean of all PRIOR rows (leak-free; first row -> NaN)."""
    return s.shift(1).expanding().mean()


def opponent_adjust(df: pd.DataFrame) -> pd.DataFrame:
    """Per game, adjust score-adjusted xGF% by the opponent's season-to-date strength.
    adj = raw + w*(opp_strength_pre - 0.5): a stronger opponent (depresses your share)
    credits you. opp_strength_pre is the opponent's pregame season-to-date score-adj xGF%.
    Iterating refines the strength input; OPP_ADJ_ITERS passes is plenty for stability."""
    df = df.sort_values(["season", "team_id", "game_date"]).copy()
    df["strength_pre"] = (df.groupby(["season", "team_id"])["xgf_pct_score_adj"]
                          .transform(_expanding_mean_pre))
    for _ in range(OPP_ADJ_ITERS):
        # opponent's pregame strength for THIS game = their strength_pre keyed by game/opp
        opp_pre = df[["game_id", "team_id", "strength_pre"]].rename(
            columns={"team_id": "opp_id", "strength_pre": "opp_strength_pre"})
        df = df.drop(columns=[c for c in ["opp_strength_pre"] if c in df.columns])
        df = df.merge(opp_pre, on=["game_id", "opp_id"], how="left")
        df["opp_strength_pre"] = df["opp_strength_pre"].fillna(0.5)
        df["adj_share"] = (df["xgf_pct_score_adj"]
                           + OPP_ADJ_WEIGHT * (df["opp_strength_pre"] - 0.5))
        # refresh each team's strength estimate from the adjusted share for the next pass
        df = df.sort_values(["season", "team_id", "game_date"])
        df["strength_pre"] = (df.groupby(["season", "team_id"])["adj_share"]
                              .transform(_expanding_mean_pre)).fillna(df["adj_share"])
    return df


def per_game_components(df: pd.DataFrame, league_5v5_total: pd.Series,
                        k_fin: float, k_goal: float) -> pd.DataFrame:
    """Per-game (not yet season-aggregated) component values, goals/game scale."""
    df = df.copy()
    df["league_total"] = df["season"].map(league_5v5_total).astype("float64")
    # play: (2*share - 1) * combined 5v5 xG per game -> 5v5 goal differential from process
    df["play_pg"] = (2.0 * df["adj_share"] - 1.0) * df["league_total"]
    df["finishing_pg"] = df["g5v5_for"] - df["xgf_5v5"]
    df["goaltending_pg"] = df["ev_gsax"]
    df["special_pg"] = ((df["g_st_for"] - df["g_st_against"])
                        - (df["xgf_st"] - df["xgf_st_against"]))
    return df


def season_to_date(df: pd.DataFrame, k_fin: float, k_goal: float) -> pd.DataFrame:
    """Expanding (inclusive) season-to-date component values per (team, game_date).
    Finishing/goaltending are shrunk toward 0 by accumulated shot volume."""
    df = df.sort_values(["season", "team_id", "game_date"]).copy()
    g = df.groupby(["season", "team_id"], sort=False)
    n = g.cumcount() + 1
    df["games_played"] = n
    df["play_5v5"] = g["play_pg"].cumsum() / n
    # finishing: cumulative (goals - xGF) per game, shrunk by cumulative 5v5 shots
    cum_fin = g["finishing_pg"].cumsum()
    cum_sh5 = g["shots_5v5"].cumsum()
    df["finishing"] = (cum_fin / n) * (cum_sh5 / (cum_sh5 + k_fin))
    # goaltending: cumulative EV GSAx per game, shrunk by cumulative EV shots faced
    cum_g = g["goaltending_pg"].cumsum()
    cum_evs = g["ev_shots"].cumsum()
    df["goaltending"] = (cum_g / n) * (cum_evs / (cum_evs + k_goal))
    df["special_teams"] = g["special_pg"].cumsum() / n
    return df


def fit_weights(std: pd.DataFrame) -> tuple[dict, dict]:
    """Fit component weights by predicting home wins from PREGAME rating-component diffs.
    Returns (weights dict normalised to mean 1, metrics dict)."""
    # pregame (exclusive) season-to-date components per (game, team): shift the through
    # values back by one game within team-season
    pre = std.sort_values(["season", "team_id", "game_date"]).copy()
    gcol = pre.groupby(["season", "team_id"], sort=False)
    for c in COMPONENTS:
        pre[c + "_pre"] = gcol[c].shift(1)
    home = pre[pre["home_away"] == "home"]
    away = pre[pre["home_away"] == "away"]
    keys = ["game_id", "season"]
    m = home.merge(away, on=keys, suffixes=("_h", "_a"))
    for c in COMPONENTS:
        m[c + "_diff"] = m[c + "_pre_h"] - m[c + "_pre_a"]
    m["home_won"] = (m["goals_for_h"] > m["goals_against_h"]).astype(int)
    feats = [c + "_diff" for c in COMPONENTS]
    m = m.dropna(subset=feats)
    train = m[(m["season"] >= WEIGHT_FIT_MIN_SEASON) & (m["season"] <= WEIGHT_FIT_MAX_SEASON)]
    val = m[m["season"] == "2024-25"]
    hold = m[m["season"] == "2025-26"]
    X, y = train[feats].to_numpy(), train["home_won"].to_numpy()
    clf = LogisticRegression(max_iter=2000)
    clf.fit(X, y)
    coef = np.maximum(clf.coef_[0], 0.0)  # weights are non-negative by construction
    if coef.sum() == 0:
        coef = np.ones_like(coef)
    weights = dict(zip(COMPONENTS, coef * len(coef) / coef.sum()))  # normalise to mean 1

    def report(d: pd.DataFrame) -> dict:
        if d.empty:
            return {}
        p = clf.predict_proba(d[feats].to_numpy())[:, 1]
        yy = d["home_won"].to_numpy()
        return {"n": int(len(d)), "accuracy": float(accuracy_score(yy, p > 0.5)),
                "log_loss": float(log_loss(yy, p, labels=[0, 1]))}

    metrics = {"raw_coef": dict(zip(COMPONENTS, clf.coef_[0].tolist())),
               "intercept": float(clf.intercept_[0]),
               "train": report(train), "val": report(val), "holdout": report(hold),
               "home_win_base_rate": float(train["home_won"].mean())}
    return weights, metrics


def tune_shrinkage(std_full: pd.DataFrame, comp: str, per_game_col: str,
                   vol_col: str, ks: list[float]) -> tuple[float, list[dict]]:
    """Pick k minimising out-of-sample MSE: season t's SHRUNK component predicting season
    t+1's RAW per-game component. (Correlation would be wrong here -- it is invariant to the
    uniform part of the shrink; only an error metric has an interior optimum: k=0 chases
    noise, k=inf predicts a flat 0.)"""
    agg = (std_full.groupby(["season", "team_id"])
           .agg(num=(per_game_col, "sum"), n=(per_game_col, "size"), vol=(vol_col, "sum"))
           .reset_index())
    agg["raw"] = agg["num"] / agg["n"]
    seasons = sorted(agg["season"].unique())
    pairs = []
    for s0, s1 in zip(seasons, seasons[1:]):
        a = agg[agg["season"] == s0].set_index("team_id")
        b = agg[agg["season"] == s1].set_index("team_id")["raw"].rename("target")
        pairs.append(a.join(b, how="inner").dropna(subset=["target"]))
    joined = pd.concat(pairs) if pairs else agg.iloc[:0]
    rows = []
    for k in ks:
        pred = joined["raw"] * (joined["vol"] / (joined["vol"] + k))
        mse = float(((pred - joined["target"]) ** 2).mean()) if len(joined) else float("nan")
        rows.append({"k": k, "mse": mse})
    best = min(rows, key=lambda r: (r["mse"] if not np.isnan(r["mse"]) else 1e9))
    return best["k"], rows


def add_trajectory_and_se(std: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """Weighted contributions (sum to total), trajectory vs 15 days ago, and a game-resample
    standard error of the total (closed-form: sd of per-game rating value / sqrt(games))."""
    df = std.copy()
    # pregame opponent-adjusted 5v5 share (leak-free, [0,1]); the mart opponent adjustment
    # consumes this when RATING_SOURCE='power_rating' on the same scale as the interim.
    df["pregame_strength_share"] = df["strength_pre"]
    for c in COMPONENTS:
        df["contrib_" + c] = df[c] * weights[c]
    df["total_rating"] = sum(df["contrib_" + c] for c in COMPONENTS)
    # per-game rating value (unshrunk) for the SE estimate
    df["game_value"] = sum(
        weights[c] * df[{"play_5v5": "play_pg", "finishing": "finishing_pg",
                         "goaltending": "goaltending_pg",
                         "special_teams": "special_pg"}[c]] for c in COMPONENTS)
    df = df.sort_values(["season", "team_id", "game_date"])
    g = df.groupby(["season", "team_id"], sort=False)
    n = df["games_played"]
    gv_std = g["game_value"].transform(lambda s: s.expanding().std())
    df["rating_se"] = (gv_std / np.sqrt(n)).where(n >= BOOTSTRAP_MIN_GAMES)
    # trajectory: total now minus the team's total as-of (date - 15d), via as-of merge
    traj = []
    for (_, _), sub in g:
        sub = sub.sort_values("game_date")
        prior = pd.merge_asof(
            sub[["game_date"]],
            sub[["game_date", "total_rating"]].rename(columns={"total_rating": "prev"}),
            left_on="game_date",
            right_on=sub["game_date"] - pd.Timedelta(days=TRAJECTORY_DAYS),
            direction="backward")
        traj.append(pd.Series(
            sub["total_rating"].to_numpy() - prior["prev"].to_numpy(), index=sub.index))
    df["trajectory_15d"] = pd.concat(traj).reindex(df.index)
    return df


def build(df_pre: pd.DataFrame, k_fin: float, k_goal: float,
          weights: dict | None = None, metrics: dict | None = None):
    """Full pipeline from opponent-adjusted per-game inputs to the rating series."""
    league_5v5_total = (df_pre.assign(comb=df_pre["xgf_5v5"] + df_pre["xgf_5v5_against"])
                        .groupby("season")["comb"].mean())
    pg = per_game_components(df_pre, league_5v5_total, k_fin, k_goal)
    std = season_to_date(pg, k_fin, k_goal)
    if weights is None:
        weights, metrics = fit_weights(std)
    out = add_trajectory_and_se(std, weights)
    return out, weights, metrics, league_5v5_total


OUT_COLS = (["game_id", "game_date", "season", "team_id", "games_played",
             "total_rating", "rating_se", "trajectory_15d", "pregame_strength_share"]
            + COMPONENTS + ["contrib_" + c for c in COMPONENTS])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None, help="restrict the pull to one season")
    ap.add_argument("--tune-k", action="store_true",
                    help="re-tune shrinkage k (else use config values)")
    ap.add_argument("--dry-run", action="store_true", help="compute + report, do not write")
    args = ap.parse_args()

    where = f"and season = '{args.season}'" if args.season else ""
    raw = pull(where)
    df = add_opponent_columns(raw)
    df = opponent_adjust(df)
    print(f"Pulled {len(raw):,} team-games across {raw['season'].nunique()} seasons.")

    # shrinkage: per-game finishing/goaltending need to be present for tuning
    league_5v5_total = (df.assign(comb=df["xgf_5v5"] + df["xgf_5v5_against"])
                        .groupby("season")["comb"].mean())
    pg = per_game_components(df, league_5v5_total, 0, 0)
    if args.tune_k:
        k_fin, fin_rows = tune_shrinkage(pg, "finishing", "finishing_pg", "shots_5v5",
                                         [100, 250, 500, 1000, 2000, 4000])
        k_goal, goal_rows = tune_shrinkage(pg, "goaltending", "goaltending_pg", "ev_shots",
                                           [100, 250, 500, 1000, 2000, 4000])
        print("Finishing k sweep:", fin_rows)
        print("Goaltending k sweep:", goal_rows)
        print(f"Chosen k_fin={k_fin}, k_goal={k_goal}")
    else:
        k_fin = config.FINISHING_SHRINKAGE_K or 1000
        k_goal = config.GOALTENDING_SHRINKAGE_K or 1000
        fin_rows = goal_rows = None

    out, weights, metrics, _ = build(df, k_fin, k_goal)

    print("\nComponent weights (normalised to mean 1):")
    for c in COMPONENTS:
        print(f"  {c:14s} {weights[c]:.3f}")
    print("Win-prediction metrics:", metrics["train"], "| holdout:", metrics["holdout"])

    latest = (out.sort_values("game_date").groupby(["season", "team_id"]).tail(1))
    cur = latest[latest["season"] == "2025-26"].sort_values("total_rating", ascending=False)
    show = cur[["team_id", "games_played", "total_rating", "rating_se"] + COMPONENTS].head(10)
    print("\nTop-10 current (2025-26) power ratings:")
    print(show.to_string(index=False))

    if args.dry_run:
        print("\n[dry-run] not writing nhl_models.team_ratings")
        return

    write = out[OUT_COLS].copy()
    write["model_version"] = MODEL_VERSION
    bq.write_df(write, "team_ratings", clustering_fields=["season", "team_id"])
    print(f"\nWrote {len(write):,} rows to nhl_models.team_ratings.")
    write_methodology(weights, metrics, k_fin, k_goal, fin_rows, goal_rows, cur)


def write_methodology(weights, metrics, k_fin, k_goal, fin_rows, goal_rows, cur) -> None:
    lines = [
        "# Power ratings (Phase 3.1)", "",
        "Team strength as the sum of four components, each on a **goals-per-game** scale.",
        "See `models_ml/compute_ratings.py` for the implementation.", "",
        "## Components", "",
        "1. **play_5v5** - score- and opponent-adjusted 5v5 xGF% converted to a goal",
        "   differential per game at the season's league-average 5v5 scoring.",
        "2. **finishing** - 5v5 (goals for - xGF) per game, shrunk toward 0 by 5v5 shot",
        f"   volume with k={k_fin:g} (`FINISHING_SHRINKAGE_K`).",
        "3. **goaltending** - even-strength GSAx (xGA - GA) per game, shrunk by EV shots",
        f"   faced with k={k_goal:g} (`GOALTENDING_SHRINKAGE_K`).",
        "4. **special_teams** - non-5v5 goals above expected per game (PP + PK).", "",
        "The three 5v5 terms additively reconstruct 5v5 goal differential; special teams is",
        "the non-5v5 remainder, so the components do not double count.", "",
        "## Opponent adjustment", "",
        "Half-weighted, season-to-date (same method as the Phase 2.3 mart interim), computed",
        "in Python from the score-adjusted xGF% input only - no dependency on the mart's own",
        "opponent-adjusted column, so there is no circular build dependency.", "",
        "## Component weights", "",
        "Fit by logistic regression predicting the home win from pregame rating-component",
        f"differences ({WEIGHT_FIT_MIN_SEASON}..{WEIGHT_FIT_MAX_SEASON} train), then",
        "normalised to mean 1 so the total stays on the goals/game scale (ranking order is",
        "invariant to positive scaling).", "",
        "| component | weight | raw logit coef |", "|---|---|---|",
    ]
    for c in COMPONENTS:
        lines.append(f"| {c} | {weights[c]:.3f} | {metrics['raw_coef'][c]:+.3f} |")
    lines += ["",
        "Reading the weights: each is the predictive value of one goal/game of that component",
        "for winning. They are not all 1.0 because the pregame season-to-date estimates differ",
        "in reliability -- special teams regresses hard (low weight), even-strength goaltending",
        "is comparatively stable (higher weight). Because the components scale inversely (a",
        "heavily shrunk component has small magnitude), the weighted *contributions* stay",
        "modest and the total stays play-driven, as the top-10 below shows.",
        "",]
    lines += ["",
        "## Win-prediction performance (rating difference -> home win)", "",
        "| split | n | accuracy | log-loss |", "|---|---|---|---|"]
    for split in ["train", "val", "holdout"]:
        s = metrics.get(split, {})
        if s:
            lines.append(f"| {split} | {s['n']} | {s['accuracy']:.3f} | {s['log_loss']:.4f} |")
    lines.append(f"\nHome-win base rate (train): {metrics['home_win_base_rate']:.3f}.")
    if fin_rows:
        lines += ["", "## Shrinkage tuning (next-season MSE, lower is better)", "",
                  "Finishing: " + ", ".join(f"k={r['k']:g}->{r['mse']:.4f}" for r in fin_rows),
                  "", "Goaltending: " + ", ".join(f"k={r['k']:g}->{r['mse']:.4f}" for r in goal_rows)]
    lines += ["", "## Current top-10 (2025-26)", "",
              "| team_id | GP | total | play | finishing | goaltending | special |",
              "|---|---|---|---|---|---|---|"]
    for _, r in cur.head(10).iterrows():
        lines.append(f"| {int(r['team_id'])} | {int(r['games_played'])} | "
                     f"{r['total_rating']:+.2f} | {r['play_5v5']:+.2f} | {r['finishing']:+.2f} | "
                     f"{r['goaltending']:+.2f} | {r['special_teams']:+.2f} |")
    lines += ["", "## Deserved standings", "",
              "See `models_ml/simulate_deserved.py` and `nhl_models.deserved_standings`:",
              "each played game is replayed 10,000 times with each team's goals Poisson(its",
              "in-game xG); points are awarded by simulated outcomes. Luck delta = actual",
              "minus deserved points.", ""]
    METHODOLOGY.write_text("\n".join(lines) + "\n")
    print(f"Wrote {METHODOLOGY}")


if __name__ == "__main__":
    main()
