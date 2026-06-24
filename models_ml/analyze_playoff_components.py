"""
Should the playoff predictor use the power-rating COMPONENTS directly, re-weighted for the playoffs,
instead of the single composite total_rating (whose weights are fit on regular-season games)?

The four contributions (5v5, finishing, goaltending, special teams) are each in net goals/game and
SUM to total_rating, so a logistic on the four component gaps NESTS the composite model (all four
coefficients equal ⇒ the composite). The test: do unconstrained playoff weights beat the equal-weight
composite OUT OF SAMPLE (leave-one-season-out), on 225 actual playoff series? And what weighting does
the playoff data prefer? Leakage-free: end-of-regular-season snapshot, playoffs are the held-out target.

Run:  python -m models_ml.analyze_playoff_components
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

COMPS = ["contrib_play_5v5", "contrib_finishing", "contrib_goaltending", "contrib_special_teams"]
SHORT = ["5v5", "finishing", "goaltending", "special_teams"]


def _client():
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def _q(c, sql):
    return c.query(sql).to_dataframe(create_bqstorage_client=False)


def _pull(c):
    p = os.environ["GCP_PROJECT_ID"]
    playoff = _q(c, f"""SELECT game_id, season, team_id, home_away, goals_for, goals_against
        FROM `{p}.nhl_mart.mart_team_game_stats`
        WHERE substr(cast(game_id AS string),5,2)='03'""").dropna(subset=["goals_for", "goals_against"])
    snap = _q(c, f"""
        WITH cut AS (SELECT season, MAX(game_date) d FROM `{p}.nhl_mart.mart_team_game_stats`
                     WHERE substr(cast(game_id AS string),5,2)='02' GROUP BY season),
        s AS (SELECT r.season, r.team_id, r.total_rating, {', '.join('r.'+x for x in COMPS)},
                     ROW_NUMBER() OVER (PARTITION BY r.season,r.team_id ORDER BY r.game_date DESC) rn
              FROM `{p}.nhl_models.team_ratings` r JOIN cut c ON r.season=c.season AND r.game_date<=c.d)
        SELECT season, team_id, total_rating, {', '.join(COMPS)} FROM s WHERE rn=1""")
    return playoff, snap


def _build(playoff, snap):
    rmap = {(r.season, r.team_id): r for r in snap.itertuples()}
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
        a, b = rmap[(season, t1)], rmap[(season, t2)]
        hi, lo = (a, b) if a.total_rating >= b.total_rating else (b, a)
        row = {"season": season, "rating_gap": hi.total_rating - lo.total_rating,
               "hi_won": 1 if s["w"][t1 if hi is a else t2] > s["w"][t2 if hi is a else t1] else 0}
        for col, short in zip(COMPS, SHORT):
            row[short] = getattr(hi, col) - getattr(lo, col)
        rows.append(row)
    return pd.DataFrame(rows)


def _loso(df, cols):
    yt, yp = [], []
    for s in sorted(df.season.unique()):
        tr, te = df[df.season != s], df[df.season == s]
        if te.empty or tr.hi_won.nunique() < 2:
            continue
        m = LogisticRegression(C=1.0, max_iter=5000).fit(tr[cols], tr.hi_won)
        yt += list(te.hi_won); yp += list(m.predict_proba(te[cols])[:, 1])
    return log_loss(yt, yp, labels=[0, 1])


def main():
    c = _client()
    print("Composite vs component playoff model (225 series, leave-one-season-out) …")
    playoff, snap = _pull(c)
    df = _build(playoff, snap)
    print(f"  series: {len(df)}  (seasons {df.season.min()}–{df.season.max()})")

    ll_comp = _loso(df, ["rating_gap"])          # composite (current)
    ll_parts = _loso(df, SHORT)                   # unconstrained component weights
    print(f"\n  composite total_rating  LOSO log-loss: {ll_comp:.4f}   (current)")
    print(f"  4 components re-weighted LOSO log-loss: {ll_parts:.4f}   "
          f"({ll_comp - ll_parts:+.4f}  {'better' if ll_parts < ll_comp else 'worse/equal'})")

    # what weighting does the playoff data prefer? fit on all series; show goals-equivalent weights
    # relative to the composite, which weights every component at 1.0 (they already sum to total).
    m = LogisticRegression(C=1.0, max_iter=5000).fit(df[SHORT], df.hi_won)
    scale = np.mean(m.coef_[0])  # normalize so the average component weight = 1 (composite = all 1s)
    rng = np.random.default_rng(0); ss = df.season.unique()
    boot = {k: [] for k in SHORT}
    for _ in range(500):
        bs = df[df.season.isin(rng.choice(ss, len(ss), replace=True))]
        if bs.hi_won.nunique() < 2:
            continue
        mb = LogisticRegression(C=1.0, max_iter=5000).fit(bs[SHORT], bs.hi_won)
        sb = np.mean(mb.coef_[0])
        for k, cf in zip(SHORT, mb.coef_[0]):
            boot[k].append(cf / sb if sb else 1.0)
    print("\n  playoff-preferred component weight (composite = 1.0 each):")
    print(f"  {'component':16s} {'weight':>7s}   90% CI")
    for k, cf in zip(SHORT, m.coef_[0]):
        w = cf / scale if scale else 1.0
        lo, hi = np.percentile(boot[k], [5, 95])
        flag = "" if (lo <= 1 <= hi) else "  <- differs from composite"
        print(f"  {k:16s} {w:>7.2f}   [{lo:+.2f}, {hi:+.2f}]{flag}")

    print("\n  Note: components already sum to total_rating, so the composite is the equal-weight"
          "\n  (all = 1.0) special case. A CI that excludes 1.0 means the playoffs weight that"
          "\n  component differently than the regular season does.")


if __name__ == "__main__":
    main()
