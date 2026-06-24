"""
Test candidate PLAYOFF-SPECIFIC features on actual playoff series, beyond the power rating.

Each is added on top of the end-of-regular-season rating gap and judged by leave-one-season-out CV
log-loss + a season-bootstrap confidence interval on its coefficient (discipline: honest error bars,
ship only what validates out-of-sample). All inputs are regular-season / pre-playoff (no leakage).

Candidates:
  • special_teams_gap  — the special-teams slice of the rating gap. Special teams is the least
    reliable rating component; if it's noise, it should carry a NEGATIVE coefficient on top of the
    full rating gap (i.e. discount it).                                        [all seasons]
  • starter_gsax_gap   — the projected starter's regular-season GSAx/game (the goalie who started
    most regular-season games), opponent-differenced. Goaltending form done right: the starter, not
    a team aggregate.                                                          [all seasons]
  • star_concentration_gap — top-3 share of a team's positive player value (player_composite). Tests
    depth/attrition fragility: are star-concentrated teams more or less robust in the playoffs?
    Sign unknown. player_composite covers only 2021-22+, so this is UNDERPOWERED (~75 series) and
    reported as exploratory.                                                   [2021-22+ only]

Run:  python -m models_ml.analyze_series_features
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss


def _client():
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def _q(c, sql):
    return c.query(sql).to_dataframe(create_bqstorage_client=False)


def _pull(c):
    p = os.environ["GCP_PROJECT_ID"]
    playoff = _q(c, f"""
        SELECT game_id, season, team_id, home_away, goals_for, goals_against
        FROM `{p}.nhl_mart.mart_team_game_stats`
        WHERE substr(cast(game_id AS string),5,2)='03'
    """).dropna(subset=["goals_for", "goals_against"])
    snap = _q(c, f"""
        WITH cut AS (SELECT season, MAX(game_date) d FROM `{p}.nhl_mart.mart_team_game_stats`
                     WHERE substr(cast(game_id AS string),5,2)='02' GROUP BY season),
        s AS (SELECT r.season, r.team_id, r.total_rating, r.contrib_special_teams,
                     ROW_NUMBER() OVER (PARTITION BY r.season,r.team_id ORDER BY r.game_date DESC) rn
              FROM `{p}.nhl_models.team_ratings` r JOIN cut c
                ON r.season=c.season AND r.game_date<=c.d)
        SELECT season, team_id, total_rating, contrib_special_teams FROM s WHERE rn=1
    """)
    # projected starter = most regular-season games; their reg-season GSAx per game.
    starter = _q(c, f"""
        WITH gp AS (
            SELECT season, team_id, goalie_id, COUNT(*) g, AVG(gsax) gsax,
                   ROW_NUMBER() OVER (PARTITION BY season,team_id ORDER BY COUNT(*) DESC) rn
            FROM `{p}.nhl_mart.mart_goalie_game_stats`
            WHERE substr(cast(game_id AS string),5,2)='02'
            GROUP BY season, team_id, goalie_id
        )
        SELECT season, team_id, gsax AS starter_gsax FROM gp WHERE rn=1
    """)
    # star concentration: top-3 share of positive player composite value per team-season (2021-22+).
    conc = _q(c, f"""
        WITH pteam AS (   -- player's primary team per season (most games)
            SELECT season, player_id, team_id, ROW_NUMBER() OVER (
                PARTITION BY season, player_id ORDER BY COUNT(*) DESC) rn
            FROM `{p}.nhl_mart.mart_player_game_stats`
            WHERE substr(cast(game_id AS string),5,2)='02'
            GROUP BY season, player_id, team_id
        ),
        val AS (
            SELECT pt.season, pt.team_id, GREATEST(pc.total, 0) AS v,
                   ROW_NUMBER() OVER (PARTITION BY pt.season, pt.team_id
                                      ORDER BY pc.total DESC) AS vr
            FROM pteam pt
            JOIN `{p}.nhl_models.player_composite` pc
              ON pc.player_id = pt.player_id AND pc.season_window = pt.season
            WHERE pt.rn = 1
        )
        SELECT season, team_id,
               SAFE_DIVIDE(SUM(IF(vr<=3, v, 0)), SUM(v)) AS star_share
        FROM val GROUP BY season, team_id
    """)
    return playoff, snap, starter, conc


def _series_rows(playoff, snap, starter, conc):
    rmap = {(r.season, r.team_id): r for r in snap.itertuples()}
    gmap = {(r.season, r.team_id): r.starter_gsax for r in starter.itertuples()}
    cmap = {(r.season, r.team_id): r.star_share for r in conc.itertuples()}
    home = playoff[playoff["home_away"] == "home"]
    away = playoff[playoff["home_away"] == "away"].set_index("game_id")
    series = {}
    for h in home.itertuples():
        try:
            a = away.loc[h.game_id]
        except KeyError:
            continue
        at = int(a["team_id"])
        key = (h.season, frozenset((int(h.team_id), at)))
        s = series.setdefault(key, {"season": h.season, "teams": (int(h.team_id), at),
                                    "w": {int(h.team_id): 0, at: 0}})
        s["w"][int(h.team_id) if h.goals_for > h.goals_against else at] += 1
    rows = []
    for s in series.values():
        t1, t2 = s["teams"]; season = s["season"]
        if (season, t1) not in rmap or (season, t2) not in rmap:
            continue
        rh_, rl_ = rmap[(season, t1)], rmap[(season, t2)]
        hi, lo = (t1, t2) if rh_.total_rating >= rl_.total_rating else (t2, t1)
        rh, rl = rmap[(season, hi)], rmap[(season, lo)]
        rows.append({
            "season": season,
            "rating_gap": rh.total_rating - rl.total_rating,
            "special_teams_gap": (rh.contrib_special_teams or 0) - (rl.contrib_special_teams or 0),
            "starter_gsax_gap": (gmap.get((season, hi)) or 0) - (gmap.get((season, lo)) or 0),
            "star_concentration_gap": ((cmap.get((season, hi)) - cmap.get((season, lo)))
                                       if (cmap.get((season, hi)) is not None
                                           and cmap.get((season, lo)) is not None) else np.nan),
            "hi_won": 1 if s["w"][hi] > s["w"][lo] else 0,
        })
    return pd.DataFrame(rows)


def _loso(df, cols):
    seasons = sorted(df["season"].unique()); yt, yp = [], []
    for s in seasons:
        tr, te = df[df["season"] != s], df[df["season"] == s]
        if te.empty or tr["hi_won"].nunique() < 2:
            continue
        m = LogisticRegression(C=1.0, max_iter=4000).fit(tr[cols], tr["hi_won"])
        yt += list(te["hi_won"]); yp += list(m.predict_proba(te[cols])[:, 1])
    return log_loss(yt, yp, labels=[0, 1])


def _boot_ci(df, feat, n=400):
    rng = np.random.default_rng(0); seasons = df["season"].unique(); cs = []
    for _ in range(n):
        bs = df[df["season"].isin(rng.choice(seasons, len(seasons), replace=True))]
        if bs["hi_won"].nunique() < 2:
            continue
        m = LogisticRegression(C=1.0, max_iter=4000).fit(bs[["rating_gap", feat]], bs["hi_won"])
        cs.append(m.coef_[0][1])
    return np.percentile(cs, [5, 95]) if cs else (np.nan, np.nan)


def main():
    c = _client()
    print("Pulling playoff series + rating / starter-GSAx / value-concentration inputs …")
    playoff, snap, starter, conc = _pull(c)
    df = _series_rows(playoff, snap, starter, conc)
    print(f"  series: {len(df)}  (seasons {df['season'].min()}–{df['season'].max()})")

    base = _loso(df, ["rating_gap"])
    print(f"\n  rating-only LOSO log-loss: {base:.4f}   (baseline)\n")
    print(f"  {'feature':24s} {'n':>4s}  {'+LOSO vs rating':>15s}   coef 90% CI        verdict")
    full = ["special_teams_gap", "starter_gsax_gap"]
    for feat in full:
        ll = _loso(df, ["rating_gap", feat]); lo, hi = _boot_ci(df, feat)
        val = "VALIDATES" if (base - ll >= 0.0005 and (lo > 0 or hi < 0)) else "no signal"
        print(f"  {feat:24s} {len(df):>4d}  {base-ll:>+15.4f}   [{lo:+.3f}, {hi:+.3f}]   {val}")

    # concentration: only seasons with the feature present (2021-22+) — underpowered, exploratory.
    cdf = df.dropna(subset=["star_concentration_gap"]).copy()
    if len(cdf) >= 20:
        cbase = _loso(cdf, ["rating_gap"])
        cll = _loso(cdf, ["rating_gap", "star_concentration_gap"])
        lo, hi = _boot_ci(cdf, "star_concentration_gap")
        val = "VALIDATES" if (cbase - cll >= 0.0005 and (lo > 0 or hi < 0)) else "no signal (underpowered)"
        print(f"  {'star_concentration_gap':24s} {len(cdf):>4d}  {cbase-cll:>+15.4f}   [{lo:+.3f}, {hi:+.3f}]   {val}")
        print(f"\n  (concentration tested on {len(cdf)} series, {cdf['season'].min()}–{cdf['season'].max()} only — "
              f"player_composite history is short; treat as exploratory.)")
    else:
        print(f"  star_concentration_gap: too few series ({len(cdf)}) to test.")


if __name__ == "__main__":
    main()
