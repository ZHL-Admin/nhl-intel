"""
Hold the combined playoff model to the same bar as everything else: joint fit + paired-bootstrap CIs.

Addresses four asks:
 1. JOINT fit — the four component weights and the recent-form trajectory weight are fit TOGETHER in
    one logistic (per fold), not the trajectory weight carried over from the old composite base. We
    report trajectory's jointly-fit weight next to its composite-base weight to expose the overlap
    with finishing's discount.
 2. CI on the improvement — out-of-sample (leave-one-season-out, every weight refit within fold) per-
    series log-loss, then a PAIRED BOOTSTRAP across series for the mean gain over the composite
    baseline, for both the re-weight-only and the combined model. Plus combined-vs-reweight, to test
    whether trajectory adds anything beyond the re-weighting.
 3. The 0.45 Skellam scale is fit to outcome likelihood (build_playoff_weights.py); this validation
    uses a logistic that self-scales, so the scale never enters the reported gain.
 4. No raw inputs — stays on the rating's four components (complexity ceiling at 225 series).

Same regularization (C=1.0, sklearn default) for every model — no per-model tuning. Leakage-free.

Run:  python -m models_ml.analyze_combined_validation
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.linear_model import LogisticRegression

COMPS = ["contrib_play_5v5", "contrib_finishing", "contrib_goaltending", "contrib_special_teams"]
SHORT = ["play_5v5", "finishing", "goaltending", "special_teams"]
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
        s AS (SELECT r.season, r.team_id, r.total_rating, r.trajectory_15d,
                     {', '.join('r.'+x for x in COMPS)},
                     ROW_NUMBER() OVER (PARTITION BY r.season,r.team_id ORDER BY r.game_date DESC) rn
              FROM `{p}.nhl_models.team_ratings` r JOIN cut c ON r.season=c.season AND r.game_date<=c.d)
        SELECT season, team_id, total_rating, trajectory_15d, {', '.join(COMPS)} FROM s WHERE rn=1""")
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
        s = series.setdefault(key, {"season": h.season, "t": (int(h.team_id), at),
                                    "w": {int(h.team_id): 0, at: 0}})
        s["w"][int(h.team_id) if h.goals_for > h.goals_against else at] += 1
    rows = []
    for s in series.values():
        t1, t2 = s["t"]; season = s["season"]
        if (season, t1) not in rmap or (season, t2) not in rmap:
            continue
        a, b = rmap[(season, t1)], rmap[(season, t2)]
        hi, lo = (a, b) if a.total_rating >= b.total_rating else (b, a)
        hi_id = t1 if hi is a else t2; lo_id = t2 if hi is a else t1
        row = {"season": season, "rating_gap": hi.total_rating - lo.total_rating,
               "traj_gap": (hi.trajectory_15d or 0) - (lo.trajectory_15d or 0),
               "hi_won": 1 if s["w"][hi_id] > s["w"][lo_id] else 0}
        for col, short in zip(COMPS, SHORT):
            row[short] = getattr(hi, col) - getattr(lo, col)
        rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def _loso_probs(df, cols):
    """Out-of-sample prob per series: predict each season from a model fit on the others."""
    p = np.full(len(df), np.nan)
    for s in sorted(df.season.unique()):
        tr = df[df.season != s]; te = df[df.season == s]
        if tr.hi_won.nunique() < 2:
            continue
        m = LogisticRegression(C=C, max_iter=6000).fit(tr[cols], tr.hi_won)
        p[te.index] = m.predict_proba(te[cols])[:, 1]
    return np.clip(p, 1e-6, 1 - 1e-6)


def _ll(y, p):
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))      # per-series log-loss


def _boot_diff(d, n=4000, seed=0):
    rng = np.random.default_rng(seed)
    means = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(n)]
    return float(np.mean(d)), float(np.percentile(means, 5)), float(np.percentile(means, 95))


def main():
    c = _client()
    print("Joint-fit validation with paired-bootstrap CIs (225 playoff series, LOSO, C=1.0) …")
    playoff, snap = _pull(c)
    df = _build(playoff, snap)
    y = df.hi_won.values
    print(f"  series: {len(df)}")

    p_base = _loso_probs(df, ["rating_gap"])           # composite baseline
    p_rw = _loso_probs(df, SHORT)                       # re-weight only (4 components)
    p_comb = _loso_probs(df, SHORT + ["traj_gap"])      # combined (joint fit)

    Lb, Lr, Lc = _ll(y, p_base), _ll(y, p_rw), _ll(y, p_comb)
    print(f"\n  LOSO mean log-loss:  composite {Lb.mean():.4f}   re-weight {Lr.mean():.4f}   "
          f"combined {Lc.mean():.4f}")

    print("\n  Out-of-sample improvement vs composite (paired bootstrap across series, 90% CI):")
    for name, d in [("re-weight only ", Lb - Lr), ("combined       ", Lb - Lc)]:
        m, lo, hi = _boot_diff(d)
        print(f"    {name}  {m:+.4f}   [{lo:+.4f}, {hi:+.4f}]   "
              f"{'clears 0' if lo > 0 else 'straddles 0'}")
    m, lo, hi = _boot_diff(Lr - Lc)
    print(f"    trajectory adds beyond re-weight  {m:+.4f}   [{lo:+.4f}, {hi:+.4f}]   "
          f"{'clears 0' if lo > 0 else 'straddles 0'}")

    # ---- jointly-fit weights: combined logistic on all data; trajectory vs composite-base ----
    comb = LogisticRegression(C=C, max_iter=6000).fit(df[SHORT + ["traj_gap"]], y)
    cw = dict(zip(SHORT + ["traj_gap"], comb.coef_[0]))
    mean_comp = np.mean([cw[k] for k in SHORT])
    base_traj = LogisticRegression(C=C, max_iter=6000).fit(df[["rating_gap", "traj_gap"]], y).coef_[0][1]

    rng = np.random.default_rng(0); ss = df.season.unique()
    bw = {k: [] for k in SHORT + ["traj_gap"]}; btj_base = []
    for _ in range(600):
        bs = df[df.season.isin(rng.choice(ss, len(ss), replace=True))]
        if bs.hi_won.nunique() < 2:
            continue
        mc = LogisticRegression(C=C, max_iter=6000).fit(bs[SHORT + ["traj_gap"]], bs.hi_won)
        mcoef = dict(zip(SHORT + ["traj_gap"], mc.coef_[0]))
        mm = np.mean([mcoef[k] for k in SHORT])
        for k in SHORT:
            bw[k].append(mcoef[k] / mm if mm else 1.0)
        bw["traj_gap"].append(mcoef["traj_gap"])
        btj_base.append(LogisticRegression(C=C, max_iter=6000)
                        .fit(bs[["rating_gap", "traj_gap"]], bs.hi_won).coef_[0][1])

    print("\n  Jointly-fit component multipliers (composite = 1.0 each), 90% CI:")
    for k in SHORT:
        lo, hi = np.percentile(bw[k], [5, 95])
        print(f"    {k:16s} {cw[k]/mean_comp:+.2f}   [{lo:+.2f}, {hi:+.2f}]")

    tj_lo, tj_hi = np.percentile(bw["traj_gap"], [5, 95])
    bj_lo, bj_hi = np.percentile(btj_base, [5, 95])
    print("\n  Trajectory weight (logit coef) — does it shrink when finishing is in the model?")
    print(f"    composite base [rating, traj]   {base_traj:+.3f}   [{bj_lo:+.3f}, {bj_hi:+.3f}]")
    print(f"    joint  [components, traj]        {cw['traj_gap']:+.3f}   [{tj_lo:+.3f}, {tj_hi:+.3f}]")
    shrink = 100 * (1 - abs(cw["traj_gap"]) / abs(base_traj)) if base_traj else 0
    print(f"    → magnitude change: {shrink:+.0f}% (positive = shrinks; overlap with finishing's discount)")


if __name__ == "__main__":
    main()
