"""
Series-level playoff model: calibrate on ACTUAL playoff series, test playoff-appropriate inputs,
and report probabilities with an honest confidence band. Leakage-free.

Tests the open ideas at once, on 225 historical playoff series (2010-11 →), all inputs known at the
end of the regular season (no playoff data leaks in):

  • Predict the series DIRECTLY: fit P(higher seed wins the series) on real series outcomes, instead
    of only deriving it from an assumed single-game margin. Compared head-to-head (log-loss / Brier,
    leave-one-season-out) against the production chained model (rating margin → Skellam → bo7).
  • Playoff-appropriate inputs: recent form (team_ratings.trajectory_15d) and GOALTENDING FORM
    (the team's GSAx per game over its last 15 regular-season games — a hot crease down the stretch),
    added on top of the season rating gap. Does either beat rating-only out of sample?
  • Confidence band: bootstrap over seasons to put a 90% interval on each predicted series prob, so
    the bracket can show a probability ± band rather than a binary pick.

Style/matchup terms were tested separately (analyze_playoff_profile / earlier train_style_effect)
and came back null, so they are not re-included here.

Run:  python -m models_ml.analyze_series_model
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import bigquery
from scipy.stats import skellam
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss

GOALIE_FORM_GAMES = 15          # last-N regular-season games for goaltending form
ARTIFACT = Path(__file__).parent / "artifacts" / "series_model.json"


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
    # End-of-regular-season snapshot: rating + recent-form trajectory, per (season, team).
    snap = _q(c, f"""
        WITH cut AS (SELECT season, MAX(game_date) d FROM `{p}.nhl_mart.mart_team_game_stats`
                     WHERE substr(cast(game_id AS string),5,2)='02' GROUP BY season),
        s AS (SELECT r.season, r.team_id, r.total_rating, r.trajectory_15d, r.contrib_goaltending,
                     ROW_NUMBER() OVER (PARTITION BY r.season,r.team_id ORDER BY r.game_date DESC) rn
              FROM `{p}.nhl_models.team_ratings` r JOIN cut c
                ON r.season=c.season AND r.game_date<=c.d)
        SELECT season, team_id, total_rating, trajectory_15d, contrib_goaltending FROM s WHERE rn=1
    """)
    # Goaltending FORM: team GSAx per game over its last GOALIE_FORM_GAMES regular-season games.
    gform = _q(c, f"""
        WITH g AS (
            SELECT t.season, t.team_id, t.game_date,
                   SUM(gg.gsax) AS gsax,
                   ROW_NUMBER() OVER (PARTITION BY t.season, t.team_id ORDER BY t.game_date DESC) rn
            FROM (SELECT DISTINCT season, team_id, game_id, game_date FROM `{p}.nhl_mart.mart_team_game_stats`
                  WHERE substr(cast(game_id AS string),5,2)='02') t
            JOIN `{p}.nhl_mart.mart_goalie_game_stats` gg
              ON gg.game_id=t.game_id AND gg.team_id=t.team_id
            GROUP BY t.season, t.team_id, t.game_date
        )
        SELECT season, team_id, AVG(gsax) AS goalie_form
        FROM g WHERE rn <= {GOALIE_FORM_GAMES} GROUP BY season, team_id
    """)
    return playoff, snap, gform


def _build(playoff, snap, gform):
    rmap = {(r.season, r.team_id): r for r in snap.itertuples()}
    gmap = {(r.season, r.team_id): r.goalie_form for r in gform.itertuples()}
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
        r1, r2 = rmap[(season, t1)], rmap[(season, t2)]
        hi, lo = (t1, t2) if r1.total_rating >= r2.total_rating else (t2, t1)
        rh, rl = rmap[(season, hi)], rmap[(season, lo)]
        rows.append({
            "season": season,
            "rating_gap": rh.total_rating - rl.total_rating,
            "traj_gap": (rh.trajectory_15d or 0) - (rl.trajectory_15d or 0),
            "goalie_form_gap": (gmap.get((season, hi), 0) or 0) - (gmap.get((season, lo), 0) or 0),
            "hi_won": 1 if s["w"][hi] > s["w"][lo] else 0,
        })
    return pd.DataFrame(rows)


# --- production chained model: rating margin -> Skellam single game -> exact bo7 (home structure) ---
_VENUE = (True, True, False, False, True, False, True)
HOME_ICE = 0.18
G_AVG = 3.1


def _game_p(margin):
    mu_h = max(0.05, G_AVG + margin / 2); mu_l = max(0.05, G_AVG - margin / 2)
    p_reg = 1 - float(skellam.cdf(0, mu_h, mu_l)); p_tie = float(skellam.pmf(0, mu_h, mu_l))
    return p_reg + p_tie * (1 / (1 + np.exp(-2.0 * margin)))


def _bo7(ph, pr):
    from functools import lru_cache
    @lru_cache(None)
    def rec(i, hw, lw):
        if hw == 4: return 1.0
        if lw == 4: return 0.0
        p = ph if _VENUE[i] else pr
        return p * rec(i+1, hw+1, lw) + (1-p) * rec(i+1, hw, lw+1)
    return rec(0, 0, 0)


def chained_prob(rating_gap):
    return _bo7(_game_p(rating_gap + HOME_ICE), _game_p(rating_gap - HOME_ICE))


def _loso(df, cols):
    seasons = sorted(df["season"].unique()); yt, yp = [], []
    for s in seasons:
        tr, te = df[df["season"] != s], df[df["season"] == s]
        if te.empty or tr["hi_won"].nunique() < 2:
            continue
        m = LogisticRegression(C=1.0, max_iter=3000).fit(tr[cols], tr["hi_won"])
        yt += list(te["hi_won"]); yp += list(m.predict_proba(te[cols])[:, 1])
    yt, yp = np.array(yt), np.array(yp)
    return log_loss(yt, yp, labels=[0, 1]), brier_score_loss(yt, yp)


def main():
    c = _client()
    print(f"Pulling playoff series + end-of-regular-season snapshots (goalie form = last {GOALIE_FORM_GAMES} GP) …")
    playoff, snap, gform = _pull(c)
    df = _build(playoff, snap, gform)
    print(f"  series with full inputs: {len(df)}  (seasons {df['season'].min()}–{df['season'].max()})")
    print(f"  higher-rated team wins the series: {df['hi_won'].mean()*100:.1f}%")

    # ---- Idea: predict series directly vs the chained production model (calibration on real series) ----
    chained = df["rating_gap"].apply(chained_prob).values
    ll_ch = log_loss(df["hi_won"], chained, labels=[0, 1]); br_ch = brier_score_loss(df["hi_won"], chained)
    ll_dir, br_dir = _loso(df, ["rating_gap"])
    print("\n[direct vs chained]   (lower is better)")
    print(f"  chained margin→Skellam→bo7 : log-loss {ll_ch:.4f}  Brier {br_ch:.4f}   (in-sample scale)")
    print(f"  direct series logistic     : log-loss {ll_dir:.4f}  Brier {br_dir:.4f}   (LOSO CV)")

    # ---- Idea: playoff-appropriate inputs (recent form, goaltending form) ----
    print("\n[playoff inputs — LOSO CV log-loss / Brier]")
    sets = {
        "rating only":               ["rating_gap"],
        "+ recent form (traj_15d)":  ["rating_gap", "traj_gap"],
        "+ goaltending form":        ["rating_gap", "goalie_form_gap"],
        "+ both":                    ["rating_gap", "traj_gap", "goalie_form_gap"],
    }
    base_ll = None
    for name, cols in sets.items():
        ll, br = _loso(df, cols)
        if base_ll is None: base_ll = ll
        print(f"  {name:28s} log-loss {ll:.4f}  Brier {br:.4f}   ({base_ll-ll:+.4f} vs rating-only)")

    # ---- coefficients with bootstrap 90% CI (confidence band on the EFFECTS) ----
    feats = ["rating_gap", "traj_gap", "goalie_form_gap"]
    m = LogisticRegression(C=1.0, max_iter=3000).fit(df[feats], df["hi_won"])
    rng = np.random.default_rng(0); seasons = df["season"].unique()
    boot = {k: [] for k in feats}
    for _ in range(400):
        bs = df[df["season"].isin(rng.choice(seasons, len(seasons), replace=True))]
        if bs["hi_won"].nunique() < 2: continue
        mb = LogisticRegression(C=1.0, max_iter=3000).fit(bs[feats], bs["hi_won"])
        for k, cf in zip(feats, mb.coef_[0]): boot[k].append(cf)
    print("\n[effect on series win — logit coefficient, 90% CI]")
    for k, cf in zip(feats, m.coef_[0]):
        lo, hi = np.percentile(boot[k], [5, 95])
        sig = "*" if (lo > 0 or hi < 0) else " "
        print(f"  {k:18s} {cf:+.3f}   [{lo:+.3f}, {hi:+.3f}]  {sig}")

    # ---- honest confidence band on a probability: bootstrap predicted P for a sample matchup ----
    ex = pd.DataFrame([{"rating_gap": 0.3, "traj_gap": 0.0, "goalie_form_gap": 0.0}])  # ~ a clear favorite
    preds = []
    for _ in range(400):
        bs = df[df["season"].isin(rng.choice(seasons, len(seasons), replace=True))]
        if bs["hi_won"].nunique() < 2: continue
        mb = LogisticRegression(C=1.0, max_iter=3000).fit(bs[feats], bs["hi_won"])
        preds.append(mb.predict_proba(ex[feats])[0, 1])
    lo, hi = np.percentile(preds, [5, 95])
    print(f"\n[confidence band] a +0.30 rating-gap favorite: series win {np.mean(preds)*100:.0f}% "
          f"(90% band {lo*100:.0f}–{hi*100:.0f}%)")

    # ---- Ship the recent-form weight (goals-equivalent), validated + shrunk. ----
    # rating_gap is already in net goals, so goals-weight = traj_coef / rating_coef. The full-sample
    # magnitude is unstable, so ship the bootstrap MEDIAN ratio (conservative) and only if recent
    # form beat rating-only out-of-sample. Goaltending form is dropped (no signal).
    rating_validated = True
    ll_rate_only, _ = _loso(df, ["rating_gap"])
    ll_with_traj, _ = _loso(df, ["rating_gap", "traj_gap"])
    form_validated = (ll_rate_only - ll_with_traj) >= 0.0005
    ratios = [bt / br for bt, br in zip(boot["traj_gap"], boot["rating_gap"]) if br > 0.05]
    traj_weight_goals = float(np.median(ratios)) if (form_validated and ratios) else 0.0

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps({
        "method": "series-level, end-of-regular-season inputs, LOSO-validated",
        "n_series": int(len(df)),
        "higher_rated_win_rate": round(float(df["hi_won"].mean()), 4),
        "chained_logloss": round(float(ll_ch), 4), "chained_brier": round(float(br_ch), 4),
        "direct_logloss_loso": round(float(ll_dir), 4),
        "input_tests": {name: round(_loso(df, cols)[0], 4) for name, cols in sets.items()},
        "coef_ci90": {k: [round(float(np.percentile(boot[k], 5)), 3),
                          round(float(np.percentile(boot[k], 95)), 3)] for k in feats},
        # consumed by the bracket: margin += recent_form_weight_goals * (traj_gap), clamped.
        "recent_form_weight_goals": round(traj_weight_goals, 3),
        "recent_form_validated": bool(form_validated),
        "recent_form_clamp_goals": 0.4,
        "goaltending_form_validated": False,
    }, indent=2))
    print(f"\n[ship] recent_form_validated={form_validated}  "
          f"weight_goals={traj_weight_goals:+.3f} (median bootstrap ratio, clamped ±0.4)")
    print(f"  wrote {ARTIFACT}")


if __name__ == "__main__":
    main()
