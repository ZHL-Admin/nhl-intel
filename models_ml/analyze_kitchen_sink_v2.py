"""
Kitchen sink v2 — add the features I had excluded (goalie-clutch) and let the regularized model
decide, on the window where they exist (2015-16+, ~146 series). Answers directly: does supplying
goalie-clutch — a proven repeatable skill — alongside everything else improve playoff prediction, or
does it (and the smaller sample) hurt? Elastic-net + nested CV, same honest protocol.

Run:  python -m models_ml.analyze_kitchen_sink_v2
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from models_ml.analyze_kitchen_sink import _pull, _client, _loso, COMPS, SHORT, STYLE, ALL_FEATS
from models_ml.analyze_goalie_clutch_impact import _clutch_by_goalie, _starter_clutch


def _build_with_clutch(playoff, snap, exp, gsax, ident, starter_clutch):
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
        if sea < "2015-16" or (sea, t1) not in rmap or (sea, t2) not in rmap:
            continue
        a, b = rmap[(sea, t1)], rmap[(sea, t2)]
        hi, lo = (t1, t2) if a.total_rating >= b.total_rating else (t2, t1)
        rh, rl = rmap[(sea, hi)], rmap[(sea, lo)]
        fh, fl = fp.get((sea, hi)), fp.get((sea, lo))
        ch, cl = starter_clutch.get((sea, hi)), starter_clutch.get((sea, lo))
        if fh is None or fl is None or None in (emap.get((sea, hi)), emap.get((sea, lo))):
            continue
        if ch is None or cl is None or (isinstance(ch, float) and np.isnan(ch)) or \
                (isinstance(cl, float) and np.isnan(cl)):
            continue
        row = {"season": sea, "rating_gap": rh.total_rating - rl.total_rating,
               "traj_gap": (rh.trajectory_15d or 0) - (rl.trajectory_15d or 0),
               "experience_gap": emap[(sea, hi)] - emap[(sea, lo)],
               "starter_gsax_gap": (gmap.get((sea, hi)) or 0) - (gmap.get((sea, lo)) or 0),
               "goalie_clutch_gap": ch - cl,
               "hi_won": 1 if s["w"][hi] > s["w"][lo] else 0}
        for col, short in zip(COMPS, SHORT):
            row[short] = getattr(rh, col) - getattr(rl, col)
        for key, ffor, fag in STYLE:
            hv_f, hv_a = fh.get(f"{ffor}_pctile"), fh.get(f"{fag}_pctile")
            lv_f, lv_a = fl.get(f"{ffor}_pctile"), fl.get(f"{fag}_pctile")
            row[key] = 0.0 if any(pd.isna(v) for v in (hv_f, hv_a, lv_f, lv_a)) \
                else (hv_f - .5) * (lv_a - .5) - (lv_f - .5) * (hv_a - .5)
        rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def main():
    c = _client()
    print("Kitchen sink v2 (2015-16+) — adding goalie-clutch to the feature set …")
    playoff, snap, exp, gsax, ident = _pull(c)
    clutch = _clutch_by_goalie(c)              # starter clutch_delta per (season, goalie)
    sc = _starter_clutch(c, clutch)            # mapped to (season, team)
    df = _build_with_clutch(playoff, snap, exp, gsax, ident, sc)
    y = df.hi_won.values
    feats_all = ALL_FEATS + ["goalie_clutch_gap"]
    print(f"  series (2015-16+, all features present): {len(df)}   features: {len(feats_all)}")

    sets = {
        "composite [rating]":            ["rating_gap"],
        "core enet [comps+traj]":        SHORT + ["traj_gap"],
        "core + goalie_clutch":          SHORT + ["traj_gap", "goalie_clutch_gap"],
        "FULL kitchen sink + clutch":    feats_all,
    }
    preds = {}
    for name, cols in sets.items():
        enet = name != "composite [rating]"
        p, sel, coef = _loso(df, cols, enet=enet)
        preds[name] = (p, sel, coef, cols)
        print(f"  {name:30s} LOSO {log_loss(y, p):.4f}")

    def pll(p): return -(y*np.log(p)+(1-y)*np.log(1-p))
    base = preds["core enet [comps+traj]"][0]
    rng = np.random.default_rng(0)
    for name in ["core + goalie_clutch", "FULL kitchen sink + clutch"]:
        d = pll(base) - pll(preds[name][0])
        ms = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(4000)]
        lo, hi = np.percentile(ms, [5, 95])
        print(f"\n  {name} vs core: {d.mean():+.4f}  90% CI [{lo:+.4f}, {hi:+.4f}]  "
              f"{'helps' if lo > 0 else ('hurts' if hi < 0 else 'no difference')}")

    # did goalie-clutch get kept, and with what sign?
    _, sel, coef, cols = preds["FULL kitchen sink + clutch"]
    nf = len(sorted(df.season.unique()))
    print(f"\n  goalie_clutch_gap selection: kept {100*sel['goalie_clutch_gap']/nf:.0f}% of folds, "
          f"mean coef {np.mean(coef['goalie_clutch_gap']):+.3f}")


if __name__ == "__main__":
    main()
