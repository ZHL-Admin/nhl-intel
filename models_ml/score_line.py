"""
Line-fit scoring service (Phase 5.1, blueprint 6.2).

Loads the trained linefit_v1 artifact and scores an arbitrary line (a forward trio, a defense
pair, or a full 5-skater unit) from its members' player-season profiles. Returns the projected
5v5 xGF% (+ xGF/60, xGA/60), a confidence interval, a letter grade, deterministic reasons/risk
(insight_engine/templates/line_fit.py), and — when the exact line has real shared history — the
chemistry-blended projection.

Used by the backend Lineup Lab endpoints (POST /tools/line-fit) and the matchup-preview engine.

    from models_ml.score_line import score_line
    score_line([8478402, 8477934, 8480012], season="2024-25")
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from models_ml import bq, config, linefit_features as lf
from insight_engine.templates import line_fit as tmpl

ARTIFACT = Path(__file__).parent / "artifacts" / f"{config.LINEFIT_ARTIFACT}.joblib"


@lru_cache(maxsize=1)
def _load():
    return joblib.load(ARTIFACT)


@lru_cache(maxsize=4)
def _members(season: str) -> pd.DataFrame:
    return lf.build_member_features([season])


def _grade(xgf_pct: float) -> str:
    for letter, floor in config.LINEFIT_GRADE_BANDS:
        if xgf_pct >= floor:
            return letter
    return "F"


def _observed(line_key: str, season: str) -> dict | None:
    """The line's real shared 5v5 history this season, if it exists (any team)."""
    p = bq.project()
    df = bq.query_df(f"""select minutes, xgf_pct, xgf_per60, xga_per60
        from `{p}.nhl_staging.int_line_seasons`
        where season = '{season}' and line_key = '{line_key}'
        order by minutes desc limit 1""")
    if df.empty:
        return None
    r = df.iloc[0]
    return {"minutes": float(r["minutes"]), "xgf_pct": float(r["xgf_pct"]),
            "xgf_per60": float(r["xgf_per60"]), "xga_per60": float(r["xga_per60"])}


def _score_one(player_ids: list[int], season: str, line_type: str) -> dict:
    art = _load()
    members = _members(season)
    keys = [(int(i), season) for i in player_ids]
    missing = [i for (i, _), present in zip(keys, [k in members.index for k in keys]) if not present]
    if missing:
        raise ValueError(f"no {season} profile for player(s) {missing}")
    mem = members.loc[keys]

    feat = lf.aggregate_line(mem, line_type)
    fcols = art["feature_columns"]
    X = pd.DataFrame([[feat.get(c, 0.0) for c in fcols]], columns=fcols).astype("float64")
    X = X.fillna(0.0)

    pred = {h: float(art["boosters"][h].predict(X)[0]) for h in art["heads"]}

    # contributions from the xGF% head for the explanation (last column is the base value)
    contrib_row = art["boosters"]["xgf_pct"].predict(X, pred_contrib=True)[0]
    contribs = {c: float(contrib_row[i]) for i, c in enumerate(fcols)}

    # confidence interval (residual sd), widened for rookie/extrapolation lines
    min_toi = float(pd.to_numeric(mem["member_toi_5v5"], errors="coerce").min())
    is_rookie = min_toi < config.LINEFIT_ROOKIE_MIN_MINUTES
    mult = config.LINEFIT_ROOKIE_INTERVAL_MULT if is_rookie else 1.0
    half = mult * art["resid_sd"]["xgf_pct"]

    line_key = "-".join(str(i) for i in sorted(int(x) for x in player_ids))
    obs = _observed(line_key, season)
    model_xgf = pred["xgf_pct"]
    final_xgf = model_xgf
    blend = None
    if obs is not None:
        w_obs = obs["minutes"] / (obs["minutes"] + config.LINEFIT_OBS_PRIOR_MINUTES)
        final_xgf = model_xgf * (1 - w_obs) + obs["xgf_pct"] * w_obs
        blend = {"observed_minutes": round(obs["minutes"], 1),
                 "observed_xgf_pct": round(obs["xgf_pct"], 4),
                 "model_xgf_pct": round(model_xgf, 4),
                 "w_obs": round(w_obs, 3)}

    grade = _grade(final_xgf)
    explanation = tmpl.explain(grade=grade, xgf_pct=final_xgf, line_type=line_type,
                               contribs=contribs)

    members_out = []
    for (pid, _), row in mem.iterrows():
        members_out.append({
            "player_id": int(pid),
            "name": row.get("name"),
            "position": row.get("position"),
            "archetype": row.get("primary_archetype"),
            "off_impact": _f(row.get("off_impact")),
            "def_impact": _f(row.get("def_impact")),
            "finishing": _f(row.get("finishing")),
            "toi_5v5": _f(row.get("member_toi_5v5")),
        })

    return {
        "line_type": line_type,
        "player_ids": [int(i) for i in player_ids],
        "grade": grade,
        "projected_xgf_pct": round(final_xgf, 4),
        "interval_low": round(max(0.0, final_xgf - half), 4),
        "interval_high": round(min(1.0, final_xgf + half), 4),
        "xgf_per60": round(pred["xgf_per60"], 3),
        "xga_per60": round(pred["xga_per60"], 3),
        "grade_sentence": explanation["grade_sentence"],
        "reasons": explanation["reasons"],
        "risk": explanation["risk"],
        "observed_blend": blend,
        "deeper_extrapolation": _cross_team(mem),
        "rookie_widened": is_rookie,
        "members": members_out,
        "limitations": tmpl.LIMITATIONS_FOOTER,
    }


def _cross_team(mem: pd.DataFrame) -> bool:
    """Members span more than one team this season -> a deeper extrapolation (blueprint 6.3)."""
    if "team" not in mem.columns:
        return False
    teams = set(mem["team"].dropna().tolist())
    return len(teams) > 1


def _f(v):
    try:
        f = float(v)
        return round(f, 3) if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def score_line(player_ids: list[int], season: str) -> dict:
    """Score a line. 3 ids -> forward trio, 2 -> defense pair, 5 -> split into trio + pair."""
    ids = [int(i) for i in player_ids]
    members = _members(season)
    if len(ids) == 3:
        return _score_one(ids, season, "F3")
    if len(ids) == 2:
        return _score_one(ids, season, "D2")
    if len(ids) == 5:
        pos = {}
        for i in ids:
            key = (i, season)
            pos[i] = members.loc[key]["position"] if key in members.index else None
        fwds = [i for i in ids if pos.get(i) in ("C", "L", "R")]
        defs = [i for i in ids if pos.get(i) == "D"]
        if len(fwds) != 3 or len(defs) != 2:
            raise ValueError(f"a 5-skater unit must be 3 forwards + 2 defensemen; "
                             f"got {len(fwds)}F/{len(defs)}D")
        trio = _score_one(fwds, season, "F3")
        pair = _score_one(defs, season, "D2")
        combined = round(0.6 * trio["projected_xgf_pct"] + 0.4 * pair["projected_xgf_pct"], 4)
        return {
            "line_type": "UNIT5",
            "player_ids": ids,
            "grade": _grade(combined),
            "projected_xgf_pct": combined,
            "forward_trio": trio,
            "defense_pair": pair,
            "limitations": tmpl.LIMITATIONS_FOOTER,
        }
    raise ValueError("line must be 2 (pair), 3 (trio), or 5 (full unit) skaters")
