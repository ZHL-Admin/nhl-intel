"""
Goalie leverage-clutch — IMPACT test (the committed next step after the skill passed its
pre-registered repeatability bar in analyze_goalie_clutch.py).

Question: does the projected starter's regular-season clutch_delta improve playoff-SERIES
prediction, beyond the power rating? Pre-registered keep rule: LOSO log-loss improvement ≥ 0.0005
AND bootstrap coefficient CI excluding zero. Leakage-free (clutch measured on same-season regular
season; playoffs are the held-out target). Also reports an even-strength-only robustness cut to
guard against the 6v5/pulled-goalie confound.

Run:  python -m models_ml.analyze_goalie_clutch_impact
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

MIN_TOTAL, MIN_HIGH = 800, 150


def _client():
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def _q(c, sql):
    return c.query(sql).to_dataframe(create_bqstorage_client=False)


def _clutch_by_goalie(c, even_strength_only=False):
    """clutch_delta per (season, goalie): mean GSAx/shot in high-leverage minus low-leverage."""
    p = os.environ["GCP_PROJECT_ID"]
    strength = "AND s.strength = '5v5'" if even_strength_only else ""
    sql = f"""
    WITH prim AS (
        SELECT game_id, team_id, goalie_id, ROW_NUMBER() OVER (
            PARTITION BY game_id, team_id ORDER BY shots_faced DESC) rn
        FROM `{p}.nhl_mart.mart_goalie_game_stats`),
    shots AS (
        SELECT s.game_id, s.event_id, s.season, s.team_id AS shoot_team, s.elapsed_seconds,
               x.xg - CAST(s.is_goal AS INT64) AS gsax
        FROM `{p}.nhl_staging.int_shot_sequence` s
        JOIN `{p}.nhl_models.shot_xg` x USING (game_id, event_id)
        WHERE s.is_empty_net = FALSE AND s.season >= '2015-16'
          AND substr(cast(s.game_id AS string),5,2) = '02' AND x.xg IS NOT NULL {strength}),
    joined AS (
        SELECT sh.season, g.goalie_id, sh.gsax, wp.leverage
        FROM shots sh
        JOIN prim g ON g.game_id=sh.game_id AND g.team_id != sh.shoot_team AND g.rn=1
        JOIN `{p}.nhl_models.win_probability` wp
          ON wp.game_id=sh.game_id AND wp.elapsed_seconds <= sh.elapsed_seconds
        QUALIFY ROW_NUMBER() OVER (PARTITION BY sh.game_id, sh.event_id
                                   ORDER BY wp.elapsed_seconds DESC)=1),
    thr AS (SELECT APPROX_QUANTILES(leverage, 3) q FROM joined)
    SELECT season, goalie_id,
      COUNTIF(leverage >= (SELECT q[OFFSET(2)] FROM thr)) n_high,
      COUNT(*) n_total,
      AVG(IF(leverage >= (SELECT q[OFFSET(2)] FROM thr), gsax, NULL))
        - AVG(IF(leverage <= (SELECT q[OFFSET(1)] FROM thr), gsax, NULL)) AS clutch_delta
    FROM joined GROUP BY season, goalie_id
    """
    d = _q(c, sql)
    return d[(d.n_total >= MIN_TOTAL) & (d.n_high >= MIN_HIGH)][["season", "goalie_id", "clutch_delta"]]


def _starter_clutch(c, clutch):
    """Map clutch_delta to each (season, team)'s projected starter (most regular-season games)."""
    p = os.environ["GCP_PROJECT_ID"]
    starter = _q(c, f"""
        WITH gp AS (SELECT season, team_id, goalie_id, COUNT(*) g, ROW_NUMBER() OVER (
                        PARTITION BY season, team_id ORDER BY COUNT(*) DESC) rn
                    FROM `{p}.nhl_mart.mart_goalie_game_stats`
                    WHERE substr(cast(game_id AS string),5,2)='02'
                    GROUP BY season, team_id, goalie_id)
        SELECT season, team_id, goalie_id FROM gp WHERE rn=1""")
    m = starter.merge(clutch, on=["season", "goalie_id"], how="left")
    return {(r.season, r.team_id): r.clutch_delta for r in m.itertuples()}


def _series(c):
    p = os.environ["GCP_PROJECT_ID"]
    playoff = _q(c, f"""SELECT game_id, season, team_id, home_away, goals_for, goals_against
        FROM `{p}.nhl_mart.mart_team_game_stats`
        WHERE substr(cast(game_id AS string),5,2)='03'""").dropna(subset=["goals_for", "goals_against"])
    snap = _q(c, f"""
        WITH cut AS (SELECT season, MAX(game_date) d FROM `{p}.nhl_mart.mart_team_game_stats`
                     WHERE substr(cast(game_id AS string),5,2)='02' GROUP BY season),
        s AS (SELECT r.season, r.team_id, r.total_rating, ROW_NUMBER() OVER (
                  PARTITION BY r.season,r.team_id ORDER BY r.game_date DESC) rn
              FROM `{p}.nhl_models.team_ratings` r JOIN cut c ON r.season=c.season AND r.game_date<=c.d)
        SELECT season, team_id, total_rating FROM s WHERE rn=1""")
    return playoff, snap


def _build(playoff, snap, starter_clutch):
    rmap = {(r.season, r.team_id): r.total_rating for r in snap.itertuples()}
    home = playoff[playoff.home_away == "home"]
    away = playoff[playoff.home_away == "away"].set_index("game_id")
    series = {}
    for h in home.itertuples():
        try:
            a = away.loc[h.game_id]
        except KeyError:
            continue
        at = int(a["team_id"]); key = (h.season, frozenset((int(h.team_id), at)))
        s = series.setdefault(key, {"season": h.season, "teams": (int(h.team_id), at),
                                    "w": {int(h.team_id): 0, at: 0}})
        s["w"][int(h.team_id) if h.goals_for > h.goals_against else at] += 1
    rows = []
    for s in series.values():
        t1, t2 = s["teams"]; season = s["season"]
        if (season, t1) not in rmap or (season, t2) not in rmap:
            continue
        hi, lo = (t1, t2) if rmap[(season, t1)] >= rmap[(season, t2)] else (t2, t1)
        ch, cl = starter_clutch.get((season, hi)), starter_clutch.get((season, lo))
        if ch is None or cl is None or np.isnan(ch) or np.isnan(cl):
            continue
        rows.append({"season": season, "rating_gap": rmap[(season, hi)] - rmap[(season, lo)],
                     "clutch_gap": ch - cl, "hi_won": 1 if s["w"][hi] > s["w"][lo] else 0})
    return pd.DataFrame(rows)


def _loso(df, cols):
    yt, yp = [], []
    for s in sorted(df.season.unique()):
        tr, te = df[df.season != s], df[df.season == s]
        if te.empty or tr.hi_won.nunique() < 2:
            continue
        m = LogisticRegression(C=1.0, max_iter=4000).fit(tr[cols], tr.hi_won)
        yt += list(te.hi_won); yp += list(m.predict_proba(te[cols])[:, 1])
    return log_loss(yt, yp, labels=[0, 1])


def _ci(df, feat, n=500):
    rng = np.random.default_rng(0); ss = df.season.unique(); cs = []
    for _ in range(n):
        bs = df[df.season.isin(rng.choice(ss, len(ss), replace=True))]
        if bs.hi_won.nunique() < 2:
            continue
        m = LogisticRegression(C=1.0, max_iter=4000).fit(bs[["rating_gap", feat]], bs.hi_won)
        cs.append(m.coef_[0][1])
    return np.percentile(cs, [5, 95])


def run(c, even_strength_only, label):
    clutch = _clutch_by_goalie(c, even_strength_only)
    sc = _starter_clutch(c, clutch)
    playoff, snap = _series(c)
    df = _build(playoff, snap, sc)
    base = _loso(df, ["rating_gap"]); both = _loso(df, ["rating_gap", "clutch_gap"])
    lo, hi = _ci(df, "clutch_gap")
    keep = (base - both >= 0.0005) and (lo > 0 or hi < 0)
    print(f"\n[{label}]  series={len(df)} (2015-16+)")
    print(f"  rating-only LOSO {base:.4f} → +clutch {both:.4f}   (improvement {base-both:+.4f})")
    print(f"  clutch_gap coef 90% CI [{lo:+.3f}, {hi:+.3f}]   → {'KEEP' if keep else 'no impact'}")
    return keep


def main():
    c = _client()
    print("Impact test: does starter leverage-clutch improve playoff-series prediction?")
    run(c, False, "all shots")
    run(c, True, "even-strength only (confound robustness)")


if __name__ == "__main__":
    main()
