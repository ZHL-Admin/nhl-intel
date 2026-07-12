"""Phase 3.5 — stability tests.

(a) Year-over-year correlation of estimated SYSTEM effects (deployment fingerprints) within
    CONTINUING regimes vs across coach CHANGES: a real system signal should persist while the
    coach persists and move when he changes.
(b) Interaction-term stability across era splits (2010-17 vs 2018-26) for Design B
    (type x deployment) and the opponent track (style interactions); anything that does not
    replicate across eras is flagged unstable.
"""
from __future__ import annotations

import math

import numpy as np
import polars as pl
from sklearn.linear_model import Ridge

from . import config, design_b as DB, opponent as OPP, phase2 as P2, regime_ledger as R, team_season as TS

ERA1 = [f"{y}-{str(y+1)[2:]}" for y in range(2010, 2017)]   # 2010-11 … 2016-17
ERA2 = [f"{y}-{str(y+1)[2:]}" for y in range(2017, 2026)]   # 2017-18 … 2025-26


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs); syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None


# ---------------------------------------------------------------- (a) regime persistence
def regime_persistence() -> dict:
    fp = pl.read_parquet(TS.FP_PARQUET)
    syear = {s: 2010 + i for i, s in enumerate(config.SEASONS_ALL)}
    fp = fp.with_columns(syear=pl.col("season_label").replace_strict(syear, return_dtype=pl.Int64))
    # team-season modal coach from the consolidated regimes
    gc = R.assemble_game_coaches(); tg = R.to_team_games(gc)
    raw = R.build_ledger(tg.filter(pl.col("coach").is_not_null()))
    raw_annot, _ = R.consolidate_ledger(raw, k=4)
    reg = P2.consolidated_regime_games(tg, raw_annot)
    coach = (reg.group_by("team_id", "season_label")
             .agg(coach=pl.col("coach").mode().first(),
                  cons=pl.col("consolidated_start_game_id").mode().first()))
    d = fp.join(coach, on=["team_id", "season_label"], how="left")
    rows = {(r["team_id"], r["syear"]): r for r in d.to_dicts()}
    axes = TS.DEPLOY_AXES
    cont = {a: ([], []) for a in axes}; chg = {a: ([], []) for a in axes}
    cont_absdelta = {a: [] for a in axes}; chg_absdelta = {a: [] for a in axes}
    for (team, yr), r in rows.items():
        nxt = rows.get((team, yr + 1))
        if not nxt or r.get("coach") is None or nxt.get("coach") is None:
            continue
        same = (r["coach"] == nxt["coach"]) and (r["cons"] == nxt["cons"])
        for a in axes:
            if r.get(a) is not None and nxt.get(a) is not None:
                (cont if same else chg)[a][0].append(r[a])
                (cont if same else chg)[a][1].append(nxt[a])
                (cont_absdelta if same else chg_absdelta)[a].append(abs(nxt[a] - r[a]))
    out = {"note": "YoY corr of deployment fingerprint: continuing regime (same coach) vs coach change"}
    for a in axes:
        out[a] = {
            "continuing": {"n_pairs": len(cont[a][0]), "yoy_corr": _r3(_pearson(*cont[a])),
                           "mean_abs_delta": _r5(_mean(cont_absdelta[a]))},
            "coach_change": {"n_pairs": len(chg[a][0]), "yoy_corr": _r3(_pearson(*chg[a])),
                             "mean_abs_delta": _r5(_mean(chg_absdelta[a]))},
        }
    return out


# ---------------------------------------------------------------- (b) interaction stability
def designB_interaction_stability() -> dict:
    def fit_era(seasons):
        d = DB.player_season_table(seasons)
        q = d["q"].to_numpy(); y = d["xg_share"].to_numpy()
        A = np.column_stack([np.ones(len(q)), q]); c, *_ = np.linalg.lstsq(A, y, rcond=None)
        resid = y - A @ c
        X, cols = DB._design_matrix(d)
        m = Ridge(alpha=300.0).fit(X, resid)
        return dict(zip(cols, m.coef_))
    c1, c2 = fit_era(ERA1), fit_era(ERA2)
    inter = [k for k in c1 if ":x:" in k and k in c2 and k.split(":x:")[1] in TS.DEPLOY_AXES]
    x = [c1[k] for k in inter]; y = [c2[k] for k in inter]
    return {"n_interactions": len(inter), "cross_era_corr": _r3(_pearson(x, y)),
            "era1": f"{ERA1[0]}..{ERA1[-1]}", "era2": f"{ERA2[0]}..{ERA2[-1]}",
            "per_term": {k: {"era1": _r5(c1[k]), "era2": _r5(c2[k])} for k in inter}}


def opponent_interaction_stability() -> dict:
    def fit_era(seasons):
        d = OPP._assemble(seasons)
        y = d["xg_share"].to_numpy()
        X, cols, *_ = OPP._features(d)
        m = Ridge(alpha=10.0).fit(X, y)
        return dict(zip(cols, m.coef_))
    e1 = [s for s in ERA1 if s in OPP.FIT_SEASONS] or ERA1
    e2 = [s for s in ERA2 if s in OPP.FIT_SEASONS]
    c1, c2 = fit_era(e1), fit_era(e2)
    inter = [k for k in c1 if "__x__" in k and k in c2]
    x = [c1[k] for k in inter]; y = [c2[k] for k in inter]
    return {"n_interactions": len(inter), "cross_era_corr": _r3(_pearson(x, y)),
            "era1": f"{e1[0]}..{e1[-1]}", "era2": f"{e2[0]}..{e2[-1]}",
            "strength_cross_era": _strength_stab(c1, c2)}


def _strength_stab(c1, c2):
    ks = [k for k in c1 if "strength" in k and k in c2]
    return {k: {"era1": _r5(c1[k]), "era2": _r5(c2[k])} for k in ks}


def run() -> dict:
    out = {
        "regime_persistence": regime_persistence(),
        "designB_interaction_stability": designB_interaction_stability(),
        "opponent_interaction_stability": opponent_interaction_stability(),
    }
    (config.REPORTS / "phase3_stability.json").write_text(__import__("json").dumps(out, indent=2, default=str))
    return out


def _mean(x): return sum(x) / len(x) if x else None
def _r3(x): return round(x, 3) if x is not None else None
def _r5(x): return round(float(x), 5) if x is not None else None


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2, default=str))
