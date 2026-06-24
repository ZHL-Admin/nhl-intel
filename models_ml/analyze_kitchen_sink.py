"""
"Supply ALL features, let the model select" — done rigorously. An elastic-net (L1+L2) logistic over
every available leakage-free feature, with NESTED cross-validation (inner CV picks the regularization;
outer leave-one-season-out evaluates), so feature selection and the performance estimate are both
out-of-sample. On 225 playoff series, an unregularized kitchen sink would overfit and hallucinate
signal; the L1 penalty forces sparsity and nested CV keeps the verdict honest.

Compares three models out-of-sample:
  • composite baseline  — rating_gap only
  • current model       — the 4 re-weighted components + recent-form trajectory
  • kitchen sink        — elastic-net over ALL features below, regularization tuned by nested CV

Features (all higher-rated-minus-lower-rated gaps, end-of-regular-season, leakage-free):
  4 rating components, recent-form trajectory, playoff experience, starter GSAx (goaltending level),
  and 5 style/matchup interaction terms. (Goalie-clutch and roster-concentration have short history
  — 2015-16+/2021-22+ — and were tested separately; including them here would shrink the sample to
  ~75 series, so they're excluded from the full-history joint fit.)

Run:  python -m models_ml.analyze_kitchen_sink
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.metrics import log_loss

COMPS = ["contrib_play_5v5", "contrib_finishing", "contrib_goaltending", "contrib_special_teams"]
SHORT = ["play_5v5", "finishing", "goaltending", "special_teams"]
STYLE = [("rush", "rush_share_for", "rush_share_against"),
         ("forecheck", "forecheck_share_for", "forecheck_share_against"),
         ("cycle", "cycle_share_for", "cycle_share_against"),
         ("point_shot", "point_shot_share_for", "point_shot_share_against"),
         ("rebound", "rebound_share_for", "rebound_share_against")]
ALL_FEATS = SHORT + ["traj_gap", "experience_gap", "starter_gsax_gap"] + [k for k, _, _ in STYLE]


def _client():
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def _q(c, s):
    return c.query(s).to_dataframe(create_bqstorage_client=False)


def _pull(c):
    p = os.environ["GCP_PROJECT_ID"]
    playoff = _q(c, f"""SELECT game_id, season, team_id, home_away, goals_for, goals_against
        FROM `{p}.nhl_mart.mart_team_game_stats`
        WHERE substr(cast(game_id AS string),5,2)='03'""").dropna(subset=["goals_for", "goals_against"])
    snap = _q(c, f"""
        WITH cut AS (SELECT season, MAX(game_date) d FROM `{p}.nhl_mart.mart_team_game_stats`
                     WHERE substr(cast(game_id AS string),5,2)='02' GROUP BY season),
        s AS (SELECT r.season, r.team_id, r.total_rating, r.trajectory_15d,
                     {', '.join('r.'+x for x in COMPS)},
                     ROW_NUMBER() OVER (PARTITION BY r.season,r.team_id ORDER BY r.game_date DESC) rn
              FROM `{p}.nhl_models.team_ratings` r JOIN cut c ON r.season=c.season AND r.game_date<=c.d)
        SELECT season, team_id, total_rating, trajectory_15d, {', '.join(COMPS)} FROM s WHERE rn=1""")
    exp = _q(c, f"""
        WITH po AS (SELECT player_id, season, COUNT(DISTINCT game_id) g
            FROM `{p}.nhl_mart.mart_player_game_stats`
            WHERE substr(cast(game_id AS string),5,2)='03' GROUP BY player_id, season),
        ps AS (SELECT DISTINCT player_id, season FROM `{p}.nhl_mart.mart_player_game_stats`),
        car AS (SELECT ps.player_id, ps.season, COALESCE(SUM(po.g),0) prior FROM ps
                LEFT JOIN po ON po.player_id=ps.player_id AND po.season<ps.season
                GROUP BY ps.player_id, ps.season),
        toi AS (SELECT season, team_id, player_id, SUM(toi_5v5) t
                FROM `{p}.nhl_mart.mart_player_game_stats`
                WHERE substr(cast(game_id AS string),5,2)='02' GROUP BY season, team_id, player_id)
        SELECT t.season, t.team_id, SAFE_DIVIDE(SUM(t.t*car.prior),SUM(t.t)) experience
        FROM toi t JOIN car ON car.player_id=t.player_id AND car.season=t.season
        WHERE t.t>0 GROUP BY t.season, t.team_id""")
    gsax = _q(c, f"""
        WITH gp AS (SELECT season, team_id, goalie_id, COUNT(*) g, AVG(gsax) gsax,
                ROW_NUMBER() OVER (PARTITION BY season,team_id ORDER BY COUNT(*) DESC) rn
            FROM `{p}.nhl_mart.mart_goalie_game_stats`
            WHERE substr(cast(game_id AS string),5,2)='02' GROUP BY season,team_id,goalie_id)
        SELECT season, team_id, gsax AS starter_gsax FROM gp WHERE rn=1""")
    cols = ",".join(f"{col}_pctile" for _, f, a in STYLE for col in (f, a))
    ident = _q(c, f"""SELECT season, team_id, {cols} FROM `{p}.nhl_mart.mart_team_identity`
        WHERE window_kind='season'""")
    return playoff, snap, exp, gsax, ident


def _build(playoff, snap, exp, gsax, ident):
    rmap = {(r.season, r.team_id): r for r in snap.itertuples()}
    emap = {(r.season, r.team_id): r.experience for r in exp.itertuples()}
    gmap = {(r.season, r.team_id): r.starter_gsax for r in gsax.itertuples()}
    fp = {(r["season"], r["team_id"]): r for _, r in ident.iterrows()}
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
        t1, t2 = s["t"]; sea = s["season"]
        if (sea, t1) not in rmap or (sea, t2) not in rmap:
            continue
        a, b = rmap[(sea, t1)], rmap[(sea, t2)]
        hi, lo = (t1, t2) if a.total_rating >= b.total_rating else (t2, t1)
        rh, rl = rmap[(sea, hi)], rmap[(sea, lo)]
        fh, fl = fp.get((sea, hi)), fp.get((sea, lo))
        if fh is None or fl is None or None in (emap.get((sea, hi)), emap.get((sea, lo))):
            continue
        row = {"season": sea, "rating_gap": rh.total_rating - rl.total_rating,
               "traj_gap": (rh.trajectory_15d or 0) - (rl.trajectory_15d or 0),
               "experience_gap": emap[(sea, hi)] - emap[(sea, lo)],
               "starter_gsax_gap": (gmap.get((sea, hi)) or 0) - (gmap.get((sea, lo)) or 0),
               "hi_won": 1 if s["w"][hi] > s["w"][lo] else 0}
        for col, short in zip(COMPS, SHORT):
            row[short] = getattr(rh, col) - getattr(rl, col)
        for key, ffor, fag in STYLE:
            hv_f, hv_a = fh.get(f"{ffor}_pctile"), fh.get(f"{fag}_pctile")
            lv_f, lv_a = fl.get(f"{ffor}_pctile"), fl.get(f"{fag}_pctile")
            if any(pd.isna(v) for v in (hv_f, hv_a, lv_f, lv_a)):
                row[key] = 0.0
            else:
                row[key] = (hv_f - .5) * (lv_a - .5) - (lv_f - .5) * (hv_a - .5)
        rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def _loso(df, cols, enet=False):
    """Out-of-sample probs. enet=True → nested CV elastic-net (inner CV tunes C & l1_ratio)."""
    p = np.full(len(df), np.nan)
    sel = {k: 0 for k in cols}
    coef = {k: [] for k in cols}
    for s in sorted(df.season.unique()):
        tr, te = df[df.season != s], df[df.season == s]
        if tr.hi_won.nunique() < 2:
            continue
        if enet:
            pipe = Pipeline([("sc", StandardScaler()),
                             ("lr", LogisticRegression(penalty="elasticnet", solver="saga",
                                                       max_iter=8000))])
            inner = GroupKFold(n_splits=5)
            gs = GridSearchCV(pipe, {"lr__C": [0.05, 0.1, 0.3, 1.0],
                                     "lr__l1_ratio": [0.2, 0.5, 0.8, 1.0]},
                              scoring="neg_log_loss", cv=inner)
            gs.fit(tr[cols], tr.hi_won, groups=tr.season)
            best = gs.best_estimator_
            p[te.index] = best.predict_proba(te[cols])[:, 1]
            for k, cf in zip(cols, best.named_steps["lr"].coef_[0]):
                sel[k] += int(abs(cf) > 1e-6)
                coef[k].append(cf)
        else:
            m = LogisticRegression(C=1.0, max_iter=6000).fit(tr[cols], tr.hi_won)
            p[te.index] = m.predict_proba(te[cols])[:, 1]
    return np.clip(p, 1e-6, 1 - 1e-6), sel, coef


def _boot(diff, n=4000, seed=0):
    rng = np.random.default_rng(seed)
    ms = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)]
    return diff.mean(), np.percentile(ms, 5), np.percentile(ms, 95)


def main():
    c = _client()
    print("Kitchen-sink elastic-net with nested CV (let the model select), 225 series …")
    df = _build(*_pull(c))
    y = df.hi_won.values
    print(f"  series: {len(df)}   features supplied: {len(ALL_FEATS)} → {ALL_FEATS}")

    p_base, _, _ = _loso(df, ["rating_gap"])
    p_cur, _, _ = _loso(df, SHORT + ["traj_gap"])
    p_ks, sel, coef = _loso(df, ALL_FEATS, enet=True)

    Lb = log_loss(y, p_base); Lc = log_loss(y, p_cur); Lk = log_loss(y, p_ks)
    print(f"\n  OUT-OF-SAMPLE log-loss (lower = better):")
    print(f"    composite baseline   {Lb:.4f}")
    print(f"    current model        {Lc:.4f}   ({Lb-Lc:+.4f} vs composite)")
    print(f"    kitchen-sink enet    {Lk:.4f}   ({Lb-Lk:+.4f} vs composite)")

    def pll(p): return -(y*np.log(p)+(1-y)*np.log(1-p))
    m, lo, hi = _boot(pll(p_base) - pll(p_ks))
    print(f"\n  kitchen-sink vs composite:  {m:+.4f}  90% CI [{lo:+.4f}, {hi:+.4f}]  "
          f"{'clears 0' if lo>0 else 'straddles 0'}")
    m, lo, hi = _boot(pll(p_cur) - pll(p_ks))
    print(f"  kitchen-sink vs current  :  {m:+.4f}  90% CI [{lo:+.4f}, {hi:+.4f}]  "
          f"{'kitchen-sink better' if lo>0 else ('current better' if hi<0 else 'no difference')}")

    nf = max(1, len([s for s in sorted(df.season.unique())]))
    print(f"\n  Feature selection — % of {nf} outer folds kept + mean standardized coef (direction):")
    for k in sorted(ALL_FEATS, key=lambda x: -sel[x]):
        bar = "█" * round(10 * sel[k] / nf)
        mc = np.mean(coef[k]) if coef[k] else 0.0
        print(f"    {k:18s} {sel[k]/nf*100:3.0f}%  {bar:<10s}  coef {mc:+.3f}")


if __name__ == "__main__":
    main()
