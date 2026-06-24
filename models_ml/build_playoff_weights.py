"""
Build a PLAYOFF-SPECIFIC component re-weighting for the bracket, replacing the composite total_rating
whose weights are fit on regular-season games. Established by analyze_playoff_components.py that the
components beat the composite out-of-sample; this fits stable, regularized, LOSO-validated multipliers
and persists them for the bracket.

playoff_margin(team) = Σ m_k · contrib_k(team),  mean(m_k) = 1  (so m_k all = 1 ⇒ the composite).
The m_k are shrunk (L2, strength chosen by LOSO) and bootstrap-median for stability, then clamped.
Recent-form (trajectory) is re-checked ON TOP of the new base so the two don't double-count.

Run:  python -m models_ml.build_playoff_weights
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

COMPS = ["contrib_play_5v5", "contrib_finishing", "contrib_goaltending", "contrib_special_teams"]
SHORT = ["play_5v5", "finishing", "goaltending", "special_teams"]
C_GRID = [0.03, 0.05, 0.1, 0.2, 0.4, 0.8, 1.5]
CLAMP = (-0.5, 3.0)                       # multiplier bounds (allow finishing to go toward/below 0)
ARTIFACT = Path(__file__).parent / "artifacts" / "playoff_weights.json"


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
    return pd.DataFrame(rows)


def _loso(df, cols, C=1.0):
    yt, yp = [], []
    for s in sorted(df.season.unique()):
        tr, te = df[df.season != s], df[df.season == s]
        if te.empty or tr.hi_won.nunique() < 2:
            continue
        m = LogisticRegression(C=C, max_iter=6000).fit(tr[cols], tr.hi_won)
        yt += list(te.hi_won); yp += list(m.predict_proba(te[cols])[:, 1])
    return log_loss(yt, yp, labels=[0, 1])


def main():
    c = _client()
    print("Building regularized, LOSO-validated playoff component weights …")
    playoff, snap = _pull(c)
    df = _build(playoff, snap)
    print(f"  series: {len(df)}")

    ll_comp = _loso(df, ["rating_gap"])
    print(f"\n  composite LOSO: {ll_comp:.4f}")
    print("  component model by regularization strength:")
    best = (None, 1e9)
    for C in C_GRID:
        ll = _loso(df, SHORT, C=C)
        print(f"    C={C:<5} LOSO {ll:.4f}  ({ll_comp-ll:+.4f})")
        if ll < best[1]:
            best = (C, ll)
    Cs, ll_best = best
    print(f"  -> best C={Cs}  LOSO {ll_best:.4f}  ({ll_comp-ll_best:+.4f} vs composite)")

    # stable multipliers: bootstrap-median of (coef / mean coef) at best C, clamped, mean renormalized.
    rng = np.random.default_rng(0); ss = df.season.unique()
    boot = {k: [] for k in SHORT}
    for _ in range(600):
        bs = df[df.season.isin(rng.choice(ss, len(ss), replace=True))]
        if bs.hi_won.nunique() < 2:
            continue
        mb = LogisticRegression(C=Cs, max_iter=6000).fit(bs[SHORT], bs.hi_won)
        mean_cf = np.mean(mb.coef_[0])
        if mean_cf <= 0:
            continue
        for k, cf in zip(SHORT, mb.coef_[0]):
            boot[k].append(cf / mean_cf)
    mult = {k: float(np.clip(np.median(boot[k]), *CLAMP)) for k in SHORT}
    mean_m = np.mean(list(mult.values()))
    mult = {k: v / mean_m for k, v in mult.items()}      # renormalize so mean = 1 (composite-comparable)

    # Calibrate the playoff-rating SCALE for the bracket's Skellam→bo7 single-game model. Re-weighting
    # widens the rating spread (teams differ most in the up-weighted 5v5), so feeding the raw margin to
    # Skellam over-confident. Find the scale s minimising actual-series log-loss through the SAME
    # Skellam→bo7 the bracket uses, so series probabilities stay calibrated.
    # Calibrate the Skellam SCALE to series-outcome likelihood (1-param MLE, interior), then derive
    # the recent-form (trajectory) goals-weight RE-FIT ON THIS base — but via a stable bootstrap-
    # MEDIAN coefficient ratio (traj per goal of the scaled margin), NOT a full-sample MLE which
    # overfits trajectory to the grid edge. The bracket clamps the per-series effect to ±0.4 goals.
    from insight_engine.templates.playoff_bracket import _series_p
    pr_gap = sum(mult[k] * df[k] for k in SHORT).values
    traj_gap = df["traj_gap"].values
    y = df["hi_won"].values

    def series_logloss(s):
        ps = np.clip([_series_p(s * g, 3.1) for g in pr_gap], 1e-6, 1 - 1e-6)
        return log_loss(y, ps, labels=[0, 1])

    scale = float(min(np.arange(0.30, 1.61, 0.05), key=series_logloss))

    # trajectory goals-weight = median bootstrap(traj_coef / scaled-margin_coef): logit per unit traj
    # divided by logit per goal of the (already goals-scaled) margin → goals-equivalent, on this base.
    dfb = df.copy(); dfb["smargin"] = scale * pr_gap
    rng = np.random.default_rng(0); ss = df.season.unique(); ratios = []
    for _ in range(600):
        bs = dfb[dfb.season.isin(rng.choice(ss, len(ss), replace=True))]
        if bs.hi_won.nunique() < 2:
            continue
        m = LogisticRegression(C=1.0, max_iter=6000).fit(bs[["smargin", "traj_gap"]], bs.hi_won)
        if m.coef_[0][0] > 0.05:
            ratios.append(m.coef_[0][1] / m.coef_[0][0])
    traj_weight_goals = round(float(np.median(ratios)), 3) if ratios else 0.0
    print(f"\n  scale (1-param MLE to outcomes): {scale}")
    print(f"  recent_form_weight_goals (stable median ratio, new base): {traj_weight_goals}")

    # verify the SHIPPED (fixed) multipliers still beat composite OOS, and re-check trajectory on top.
    df["pmargin"] = sum(mult[k] * df[k] for k in SHORT)
    ll_ship = _loso(df, ["pmargin"])
    ll_ship_traj = _loso(df, ["pmargin", "traj_gap"])
    print(f"\n  shipped fixed multipliers: LOSO {ll_ship:.4f}  ({ll_comp-ll_ship:+.4f} vs composite)")
    print(f"  + recent-form trajectory on the new base: LOSO {ll_ship_traj:.4f}  "
          f"({ll_ship-ll_ship_traj:+.4f})")
    print("\n  playoff component multipliers (composite = 1.0 each):")
    for k in SHORT:
        lo, hi = np.percentile(boot[k], [5, 95])
        print(f"    {k:16s} {mult[k]:+.2f}   90% CI [{lo:+.2f}, {hi:+.2f}]")

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps({
        "method": "playoff-specific component re-weighting, regularized + LOSO-validated, 225 series",
        "components": COMPS, "short": SHORT,
        "multipliers": mult,
        "scale": scale,
        # recent-form trajectory weight RE-FIT on this base (replaces the composite-base value).
        "recent_form_weight_goals": traj_weight_goals,
        "recent_form_clamp_goals": 0.4,
        "validated": bool(ll_comp - ll_ship >= 0.0005),
        "loso_composite": round(ll_comp, 4),
        "loso_components": round(ll_ship, 4),
        "improvement_vs_composite": round(ll_comp - ll_ship, 4),
        "best_C": Cs,
    }, indent=2))
    print(f"\n  wrote {ARTIFACT}  (validated={ll_comp - ll_ship >= 0.0005})")


if __name__ == "__main__":
    main()
