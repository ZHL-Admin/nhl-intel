"""
Does a STYLE matchup swing a playoff SERIES, beyond team strength? — measured, leakage-free.

This answers a specific question: yes, the better-rated team wins more, but *controlling for the
rating gap*, does how two teams' styles match up predict who wins the series — especially in close
matchups? So the unit of analysis is the playoff SERIES (not a single game), and we use the team's
SAME-season fingerprint (the one we actually have at the end of the regular season; styles change
year to year). Predicting playoff outcomes from regular-season rating + regular-season fingerprint
is not leakage — both are known before the playoffs start.

Outputs a console report (the answer) and, if style beats rating-only out-of-sample, persists
goals-equivalent style weights to models_ml/artifacts/style_coeffs.json for the bracket. "Shrink to
what validates": if style adds nothing in leave-one-season-out CV, the shipped weights are 0.

Run:  python -m models_ml.train_style_effect
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

STYLE_PAIRS = [
    ("rush", "rush_share_for", "rush_share_against"),
    ("forecheck", "forecheck_share_for", "forecheck_share_against"),
    ("cycle", "cycle_share_for", "cycle_share_against"),
    ("point_shot", "point_shot_share_for", "point_shot_share_against"),
    ("rebound", "rebound_share_for", "rebound_share_against"),
]
SKEYS = [k for k, _, _ in STYLE_PAIRS]
S_GRID = [round(x, 2) for x in np.arange(0.0, 1.51, 0.1)]
MIN_IMPROVEMENT = 0.0005
ARTIFACT = Path(__file__).parent / "artifacts" / "style_coeffs.json"


def _client():
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def _q(c, sql):
    return c.query(sql).to_dataframe(create_bqstorage_client=False)


def _pull(c):
    p = os.environ["GCP_PROJECT_ID"]
    games = _q(c, f"""
        SELECT game_id, season, team_id, home_away, goals_for, goals_against
        FROM `{p}.nhl_mart.mart_team_game_stats`
        WHERE substr(cast(game_id AS string), 5, 2) = '03'      -- playoff games only
    """)
    # End-of-regular-season rating snapshot per (season, team): the same leakage-free input the
    # live bracket uses (rating as of the last '02' game date).
    ratings = _q(c, f"""
        WITH cut AS (
            SELECT season, MAX(game_date) AS d
            FROM `{p}.nhl_mart.mart_team_game_stats`
            WHERE substr(cast(game_id AS string), 5, 2) = '02' GROUP BY season
        ),
        snap AS (
            SELECT r.season, r.team_id, r.total_rating, ROW_NUMBER() OVER (
                PARTITION BY r.season, r.team_id ORDER BY r.game_date DESC) AS rn
            FROM `{p}.nhl_models.team_ratings` r
            JOIN cut c ON r.season = c.season AND r.game_date <= c.d
        )
        SELECT season, team_id, total_rating FROM snap WHERE rn = 1
    """)
    cols = ",".join(sorted({col for _, f, a in STYLE_PAIRS for col in (f"{f}_pctile", f"{a}_pctile")}))
    ident = _q(c, f"""
        SELECT season, team_id, {cols}
        FROM `{p}.nhl_mart.mart_team_identity` WHERE window_kind = 'season'
    """)
    return games, ratings, ident


def _interactions(hi, lo):
    """Net style features from the higher-rated team's perspective (same-season fingerprints)."""
    out = {}
    for key, ffor, fagainst in STYLE_PAIRS:
        hf, ha = hi.get(f"{ffor}_pctile"), hi.get(f"{fagainst}_pctile")
        lf, la = lo.get(f"{ffor}_pctile"), lo.get(f"{fagainst}_pctile")
        if any(pd.isna(v) for v in (hf, ha, lf, la)):
            return None
        out[key] = (hf - 0.5) * (la - 0.5) - (lf - 0.5) * (ha - 0.5)
    return out


def _build(games, ratings, ident):
    rmap = {(r.season, r.team_id): r.total_rating for r in ratings.itertuples()}
    fp = {(r["season"], r["team_id"]): r for _, r in ident.iterrows()}

    # group playoff games into series by (season, the two team_ids); winner = more wins. Drop any
    # rows without a final score (e.g. the 2019-20 bubble's irregular records).
    games = games.dropna(subset=["goals_for", "goals_against"])
    home = games[games["home_away"] == "home"]
    away = games[games["home_away"] == "away"].set_index("game_id")
    series = {}
    for h in home.itertuples():
        try:
            a = away.loc[h.game_id]
        except KeyError:
            continue
        a_team = int(a["team_id"])
        key = (h.season, frozenset((int(h.team_id), a_team)))
        s = series.setdefault(key, {"season": h.season, "teams": (int(h.team_id), a_team),
                                    "w": {int(h.team_id): 0, a_team: 0}})
        if h.goals_for > h.goals_against:
            s["w"][int(h.team_id)] += 1
        else:
            s["w"][a_team] += 1

    rows = []
    for s in series.values():
        t1, t2 = s["teams"]
        season = s["season"]
        if (season, t1) not in rmap or (season, t2) not in rmap:
            continue
        if (season, t1) not in fp or (season, t2) not in fp:
            continue
        r1, r2 = rmap[(season, t1)], rmap[(season, t2)]
        hi, lo = (t1, t2) if r1 >= r2 else (t2, t1)
        feats = _interactions(fp[(season, hi)], fp[(season, lo)])
        if feats is None:
            continue
        row = {"season": season, "hi": hi, "lo": lo,
               "rating_gap": rmap[(season, hi)] - rmap[(season, lo)],
               "hi_won": 1 if s["w"][hi] > s["w"][lo] else 0}
        row.update(feats)
        rows.append(row)
    return pd.DataFrame(rows)


def _loso(df, feature_cols):
    """Leave-one-season-out CV log-loss for a logistic on feature_cols."""
    seasons = sorted(df["season"].unique())
    y_true, y_pred = [], []
    for s in seasons:
        tr, te = df[df["season"] != s], df[df["season"] == s]
        if te.empty or tr["hi_won"].nunique() < 2:
            continue
        m = LogisticRegression(C=1.0, max_iter=2000).fit(tr[feature_cols], tr["hi_won"])
        y_true += list(te["hi_won"])
        y_pred += list(m.predict_proba(te[feature_cols])[:, 1])
    return log_loss(y_true, y_pred, labels=[0, 1]), np.array(y_true), np.array(y_pred)


def main():
    c = _client()
    print("Pulling playoff games + end-of-regular-season ratings + same-season fingerprints …")
    games, ratings, ident = _pull(c)
    df = _build(games, ratings, ident)
    n = len(df)
    print(f"  playoff series with full inputs: {n}  (seasons {df['season'].min()}–{df['season'].max()})")

    base = df["hi_won"].mean()
    print(f"\n[baseline] higher-rated team wins the series: {base*100:.1f}% of the time")

    # rating-only vs rating+style, leave-one-season-out.
    ll_rate, _, _ = _loso(df, ["rating_gap"])
    ll_both, _, _ = _loso(df, ["rating_gap"] + SKEYS)
    print(f"[series, LOSO CV] rating-only log-loss {ll_rate:.4f}  |  rating+style {ll_both:.4f}"
          f"  (improvement {ll_rate - ll_both:+.4f})")

    # CLOSE series: smallest-half rating gaps. Does the style edge pick the winner above 50%?
    med = df["rating_gap"].median()
    close = df[df["rating_gap"] <= med].copy()
    m_all = LogisticRegression(C=1.0, max_iter=2000).fit(df[["rating_gap"] + SKEYS], df["hi_won"])
    gamma = m_all.coef_[0][1:]
    close["style_score"] = close[SKEYS].values @ gamma
    style_pick_hi = (close["style_score"] > 0)
    acc = ((style_pick_hi == (close["hi_won"] == 1))).mean()
    print(f"[close series] n={len(close)}, higher-rated wins {close['hi_won'].mean()*100:.1f}%; "
          f"style-sign picks the winner {acc*100:.1f}% of the time (50% = no signal)")

    # bootstrap the style contribution's CV improvement to judge if it's real.
    rng = np.random.default_rng(0)
    improms = []
    seasons = df["season"].unique()
    for _ in range(200):
        bs = df[df["season"].isin(rng.choice(seasons, len(seasons), replace=True))]
        try:
            a, _, _ = _loso(bs, ["rating_gap"]); b, _, _ = _loso(bs, ["rating_gap"] + SKEYS)
            improms.append(a - b)
        except Exception:
            pass
    lo_ci, hi_ci = np.percentile(improms, [5, 95]) if improms else (0, 0)
    print(f"[bootstrap] style CV log-loss improvement 90% CI: [{lo_ci:+.4f}, {hi_ci:+.4f}]")

    # ---- Ship weights: scale style by what validates (LOSO). Null -> 0. ----
    validated = (ll_rate - ll_both) >= MIN_IMPROVEMENT
    # pick s* on a season holdout (last 3 seasons) over the rating-only base
    hold = set(sorted(df["season"].unique())[-3:])
    tr, va = df[~df["season"].isin(hold)], df[df["season"].isin(hold)]
    m0 = LogisticRegression(C=1.0, max_iter=2000).fit(tr[["rating_gap"]], tr["hi_won"])
    m1 = LogisticRegression(C=1.0, max_iter=2000).fit(tr[["rating_gap"] + SKEYS], tr["hi_won"])
    b_r = float(m0.coef_[0][0]); g1 = m1.coef_[0][1:]
    base_logit = m0.decision_function(va[["rating_gap"]]); sscore = va[SKEYS].values @ g1

    def vloss(s):
        z = base_logit + s * sscore
        return log_loss(va["hi_won"], 1 / (1 + np.exp(-z)), labels=[0, 1])

    s_star = min(S_GRID, key=vloss)
    shipped = s_star if (validated and (vloss(0.0) - vloss(s_star)) >= MIN_IMPROVEMENT) else 0.0
    weights = [(shipped * float(g)) / b_r for g in g1] if b_r else [0.0] * len(g1)

    artifact = {
        "method": "playoff-series, same-season fingerprint, rating-controlled, LOSO-validated",
        "feature_keys": SKEYS,
        "for_against": [[f, a] for _, f, a in STYLE_PAIRS],
        "weights_goals": weights,
        "style_validated": bool(validated),
        "style_scale": shipped,
        "rating_logit_per_goal": b_r,
        "clamp_goals": 0.6,
        "n_series": int(n),
        "diagnostics": {
            "higher_rated_series_win_rate": round(float(base), 4),
            "loso_logloss_rating_only": round(float(ll_rate), 4),
            "loso_logloss_with_style": round(float(ll_both), 4),
            "close_series_style_pick_accuracy": round(float(acc), 4),
            "bootstrap_improvement_ci90": [round(float(lo_ci), 4), round(float(hi_ci), 4)],
        },
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(artifact, indent=2))
    print(f"\n[ship] style_validated={validated}  shipped_scale={shipped}  "
          f"weights_goals={[round(w,4) for w in weights]}")
    print(f"  wrote {ARTIFACT}")


if __name__ == "__main__":
    main()
