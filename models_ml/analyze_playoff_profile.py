"""
Do certain team PROFILES (own play-style, and PDO-style luck) over- or under-perform their rating
in the playoffs? — measured, leakage-free.

Different question from the matchup analysis. Here we ask, for each team, a MAIN effect: controlling
for the pregame rating gap, does a team that plays a given style — or that ran hot/lucky in the
regular season — systematically beat or fall short of what its rating predicts once the playoffs
start? If physical/forecheck teams tend to over-perform, "add some"; if high-PDO (lucky) teams
regress, "mark them down".

Inputs (all known before the playoffs, no leakage): end-of-regular-season power rating, same-season
identity fingerprint (own style percentiles), and a regular-season luck measure = goal differential
ABOVE expected, (GF-GA) - (xGF-xGA) per game (the PDO idea in goals — a team that out-scored its
chances ran hot). Unit = playoff game, home perspective; features are home-minus-away so each
coefficient is the own-profile effect. Validated leave-one-season-out; shrink to what validates.

Run:  python -m models_ml.analyze_playoff_profile
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

# Own-style percentiles to test as main effects (from mart_team_identity).
STYLE_KEYS = ["forecheck_share_for", "rush_share_for", "cycle_share_for",
              "pace", "shot_quality", "hits_per60", "shot_volume_per60"]
FEATURES = STYLE_KEYS + ["luck"]            # luck = goal diff above expected, per game
MIN_IMPROVEMENT = 0.0005
ARTIFACT = Path(__file__).parent / "artifacts" / "playoff_adjust.json"


def _client():
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def _q(c, sql):
    return c.query(sql).to_dataframe(create_bqstorage_client=False)


def _pull(c):
    p = os.environ["GCP_PROJECT_ID"]
    games = _q(c, f"""
        SELECT game_id, season, team_id, home_away, goals_for, goals_against
        FROM `{p}.nhl_mart.mart_team_game_stats`
        WHERE substr(cast(game_id AS string), 5, 2) = '03'
    """).dropna(subset=["goals_for", "goals_against"])
    ratings = _q(c, f"""
        WITH cut AS (SELECT season, MAX(game_date) d FROM `{p}.nhl_mart.mart_team_game_stats`
                     WHERE substr(cast(game_id AS string),5,2)='02' GROUP BY season),
        snap AS (SELECT r.season, r.team_id, r.total_rating, ROW_NUMBER() OVER (
                     PARTITION BY r.season,r.team_id ORDER BY r.game_date DESC) rn
                 FROM `{p}.nhl_models.team_ratings` r JOIN cut c
                   ON r.season=c.season AND r.game_date<=c.d)
        SELECT season, team_id, total_rating FROM snap WHERE rn=1
    """)
    # Regular-season luck: (GF-GA) - (xGF-xGA) per game. Positive = out-scored its chances (hot).
    luck = _q(c, f"""
        SELECT season, team_id,
               SAFE_DIVIDE(SUM(goals_for-goals_against) - SUM(xgf-xga), COUNT(*)) AS luck
        FROM `{p}.nhl_mart.mart_team_game_stats`
        WHERE substr(cast(game_id AS string),5,2)='02'
        GROUP BY season, team_id
    """)
    cols = ",".join(f"{k}_pctile" for k in STYLE_KEYS)
    ident = _q(c, f"""
        SELECT season, team_id, {cols}
        FROM `{p}.nhl_mart.mart_team_identity` WHERE window_kind='season'
    """)
    return games, ratings, luck, ident


def _build(games, ratings, luck, ident):
    rmap = {(r.season, r.team_id): r.total_rating for r in ratings.itertuples()}
    lmap = {(r.season, r.team_id): r.luck for r in luck.itertuples()}
    fp = {(r["season"], r["team_id"]): r for _, r in ident.iterrows()}

    def prof(season, tid):
        f = fp.get((season, tid))
        if f is None or (season, tid) not in lmap or (season, tid) not in rmap:
            return None
        d = {k: f.get(f"{k}_pctile") for k in STYLE_KEYS}
        if any(pd.isna(v) for v in d.values()) or pd.isna(lmap[(season, tid)]):
            return None
        d["luck"] = lmap[(season, tid)]
        d["rating"] = rmap[(season, tid)]
        return d

    home = games[games["home_away"] == "home"]
    away = games[games["home_away"] == "away"].set_index("game_id")
    rows = []
    for h in home.itertuples():
        try:
            a = away.loc[h.game_id]
        except KeyError:
            continue
        ph, pa = prof(h.season, int(h.team_id)), prof(h.season, int(a["team_id"]))
        if ph is None or pa is None:
            continue
        row = {"season": h.season, "rating_diff": ph["rating"] - pa["rating"],
               "home_win": 1 if h.goals_for > h.goals_against else 0}
        for k in FEATURES:
            row[k] = ph[k] - pa[k]
        rows.append(row)
    return pd.DataFrame(rows)


def _loso(df, cols):
    seasons = sorted(df["season"].unique())
    yt, yp = [], []
    for s in seasons:
        tr, te = df[df["season"] != s], df[df["season"] == s]
        if te.empty or tr["home_win"].nunique() < 2:
            continue
        m = LogisticRegression(C=1.0, max_iter=3000).fit(tr[cols], tr["home_win"])
        yt += list(te["home_win"]); yp += list(m.predict_proba(te[cols])[:, 1])
    return log_loss(yt, yp, labels=[0, 1])


def main():
    c = _client()
    print("Pulling playoff games + ratings + regular-season luck + same-season fingerprints …")
    games, ratings, luck, ident = _pull(c)
    df = _build(games, ratings, luck, ident)
    print(f"  playoff games with full profile: {len(df)}  (seasons {df['season'].min()}–{df['season'].max()})")

    ll0 = _loso(df, ["rating_diff"])
    ll1 = _loso(df, ["rating_diff"] + FEATURES)
    print(f"\n[LOSO CV] rating-only log-loss {ll0:.4f}  |  rating+profile {ll1:.4f}"
          f"  (improvement {ll0 - ll1:+.4f})")

    # full-sample coefficients + bootstrap 90% CI (season-resampled), reported in GOALS-equivalent.
    m = LogisticRegression(C=1.0, max_iter=3000).fit(df[["rating_diff"] + FEATURES], df["home_win"])
    b_r = float(m.coef_[0][0])
    coefs = dict(zip(FEATURES, m.coef_[0][1:]))
    rng = np.random.default_rng(0)
    seasons = df["season"].unique()
    boot = {k: [] for k in FEATURES}
    for _ in range(300):
        bs = df[df["season"].isin(rng.choice(seasons, len(seasons), replace=True))]
        if bs["home_win"].nunique() < 2:
            continue
        mb = LogisticRegression(C=1.0, max_iter=3000).fit(bs[["rating_diff"] + FEATURES], bs["home_win"])
        brb = mb.coef_[0][0]
        for k, cf in zip(FEATURES, mb.coef_[0][1:]):
            boot[k].append(cf / brb if brb else 0.0)   # goals-equivalent per unit feature

    print("\n  profile effect on playoff over/under-performance (goals-equiv per unit feature):")
    print(f"  {'feature':20s} {'goals':>8s}   90% CI            signal")
    for k in FEATURES:
        g = coefs[k] / b_r if b_r else 0.0
        lo, hi = np.percentile(boot[k], [5, 95]) if boot[k] else (0, 0)
        sig = "*" if (lo > 0 or hi < 0) else " "
        print(f"  {k:20s} {g:+8.3f}   [{lo:+.3f}, {hi:+.3f}]   {sig}")

    validated = (ll0 - ll1) >= MIN_IMPROVEMENT
    # ship only features whose CI excludes zero (and only if the model validates overall).
    weights = {}
    for k in FEATURES:
        lo, hi = np.percentile(boot[k], [5, 95]) if boot[k] else (0, 0)
        weights[k] = (coefs[k] / b_r) if (validated and (lo > 0 or hi < 0) and b_r) else 0.0

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps({
        "method": "playoff own-profile (style + PDO-luck) main effects, rating-controlled, LOSO",
        "style_keys": STYLE_KEYS,
        "weights_goals": weights,           # per-team rating adjustment = Σ w_k * (own profile_k)
        "luck_formula": "(GF-GA - (xGF-xGA)) per regular-season game",
        "validated": bool(validated),
        "n_games": int(len(df)),
        "loso_logloss_rating_only": round(float(ll0), 4),
        "loso_logloss_with_profile": round(float(ll1), 4),
    }, indent=2))
    print(f"\n[ship] validated={validated}  nonzero weights={{k:round(v,3) for k,v in weights.items() if v}}")
    print(f"  wrote {ARTIFACT}")


if __name__ == "__main__":
    main()
