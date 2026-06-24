"""
Does PLAYOFF EXPERIENCE predict playoff-series outcomes beyond team strength? Leakage-free, tested
on the same 225-series framework with LOSO + a paired bootstrap CI on the coefficient.

Team playoff experience (season-end, pre-playoffs): the regular-season-TOI-weighted average of each
roster player's PRIOR-playoff games (playoff games in earlier seasons only — no current-playoff
leakage). experience_gap = higher-rated team − lower-rated team. Sign unknown; keep only if its CI
excludes zero (discipline #11). Caveat: playoff data starts 2010-11, so experience for players who
debuted earlier is truncated — a consistent under-count, fine for relative comparison in recent years.

Run:  python -m models_ml.analyze_playoff_experience
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

C = 1.0


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
        s AS (SELECT r.season, r.team_id, r.total_rating, ROW_NUMBER() OVER (
                  PARTITION BY r.season,r.team_id ORDER BY r.game_date DESC) rn
              FROM `{p}.nhl_models.team_ratings` r JOIN cut c ON r.season=c.season AND r.game_date<=c.d)
        SELECT season, team_id, total_rating FROM s WHERE rn=1""")
    exp = _q(c, f"""
        WITH po AS (   -- playoff games per (player, season)
            SELECT player_id, season, COUNT(DISTINCT game_id) po_gp
            FROM `{p}.nhl_mart.mart_player_game_stats`
            WHERE substr(cast(game_id AS string),5,2)='03' GROUP BY player_id, season),
        ps AS (SELECT DISTINCT player_id, season FROM `{p}.nhl_mart.mart_player_game_stats`),
        career AS (   -- prior-playoff GP per (player, season): playoff games in EARLIER seasons
            SELECT ps.player_id, ps.season, COALESCE(SUM(po.po_gp), 0) prior_po_gp
            FROM ps LEFT JOIN po ON po.player_id=ps.player_id AND po.season < ps.season
            GROUP BY ps.player_id, ps.season),
        ptoi AS (   -- regular-season TOI per (season, team, player)
            SELECT season, team_id, player_id, SUM(toi_5v5) toi
            FROM `{p}.nhl_mart.mart_player_game_stats`
            WHERE substr(cast(game_id AS string),5,2)='02' GROUP BY season, team_id, player_id)
        SELECT t.season, t.team_id,
               SAFE_DIVIDE(SUM(t.toi * c2.prior_po_gp), SUM(t.toi)) AS po_experience
        FROM ptoi t JOIN career c2 ON c2.player_id=t.player_id AND c2.season=t.season
        WHERE t.toi > 0 GROUP BY t.season, t.team_id""")
    return playoff, snap, exp


def _build(playoff, snap, exp):
    rmap = {(r.season, r.team_id): r.total_rating for r in snap.itertuples()}
    emap = {(r.season, r.team_id): r.po_experience for r in exp.itertuples()}
    home = playoff[playoff.home_away == "home"]
    away = playoff[playoff.home_away == "away"].set_index("game_id")
    series = {}
    for h in home.itertuples():
        try:
            a = away.loc[h.game_id]
        except KeyError:
            continue
        at = int(a["team_id"]); key = (h.season, frozenset((int(h.team_id), at)))
        s = series.setdefault(key, {"season": h.season, "t": (int(h.team_id), at),
                                    "w": {int(h.team_id): 0, at: 0}})
        s["w"][int(h.team_id) if h.goals_for > h.goals_against else at] += 1
    rows = []
    for s in series.values():
        t1, t2 = s["t"]; season = s["season"]
        if (season, t1) not in rmap or (season, t2) not in rmap:
            continue
        hi, lo = (t1, t2) if rmap[(season, t1)] >= rmap[(season, t2)] else (t2, t1)
        eh, el = emap.get((season, hi)), emap.get((season, lo))
        if eh is None or el is None:
            continue
        rows.append({"season": season, "rating_gap": rmap[(season, hi)] - rmap[(season, lo)],
                     "exp_gap": eh - el, "hi_won": 1 if s["w"][hi] > s["w"][lo] else 0})
    return pd.DataFrame(rows).reset_index(drop=True)


def _loso_probs(df, cols):
    p = np.full(len(df), np.nan)
    for s in sorted(df.season.unique()):
        tr, te = df[df.season != s], df[df.season == s]
        if tr.hi_won.nunique() < 2:
            continue
        m = LogisticRegression(C=C, max_iter=5000).fit(tr[cols], tr.hi_won)
        p[te.index] = m.predict_proba(te[cols])[:, 1]
    return np.clip(p, 1e-6, 1 - 1e-6)


def main():
    c = _client()
    print("Playoff-experience test (LOSO + bootstrap CI) …")
    playoff, snap, exp = _pull(c)
    df = _build(playoff, snap, exp)
    y = df.hi_won.values
    print(f"  series: {len(df)}  (seasons {df.season.min()}–{df.season.max()})")
    print(f"  experience gap: mean {df.exp_gap.mean():+.1f} prior-playoff GP "
          f"(higher-rated team − lower), SD {df.exp_gap.std():.1f}")

    base = _loso_probs(df, ["rating_gap"]); both = _loso_probs(df, ["rating_gap", "exp_gap"])
    ll_b = log_loss(y, base); ll_e = log_loss(y, both)
    print(f"\n  LOSO log-loss: rating-only {ll_b:.4f} → + experience {ll_e:.4f}  ({ll_b-ll_e:+.4f})")

    # paired bootstrap on the per-series improvement + bootstrap CI on the coefficient
    Lb = -(y*np.log(base)+(1-y)*np.log(1-base)); Le = -(y*np.log(both)+(1-y)*np.log(1-both))
    rng = np.random.default_rng(0)
    diff = Lb - Le
    ms = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(4000)]
    print(f"  improvement vs rating-only: {diff.mean():+.4f}  90% CI [{np.percentile(ms,5):+.4f}, "
          f"{np.percentile(ms,95):+.4f}]  {'clears 0' if np.percentile(ms,5)>0 else 'straddles 0'}")

    ss = df.season.unique(); coefs = []
    for _ in range(600):
        bs = df[df.season.isin(rng.choice(ss, len(ss), replace=True))]
        if bs.hi_won.nunique() < 2:
            continue
        coefs.append(LogisticRegression(C=C, max_iter=5000)
                     .fit(bs[["rating_gap", "exp_gap"]], bs.hi_won).coef_[0][1])
    full = LogisticRegression(C=C, max_iter=5000).fit(df[["rating_gap", "exp_gap"]], y).coef_[0][1]
    lo, hi = np.percentile(coefs, [5, 95])
    print(f"  experience coefficient: {full:+.4f}  90% CI [{lo:+.4f}, {hi:+.4f}]  "
          f"{'SIGNIFICANT' if (lo>0 or hi<0) else 'not significant'}")


if __name__ == "__main__":
    main()
