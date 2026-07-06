"""Shared 3-candidate skater-WAR estimator interface for the assessment (spec 6.1, revised).

The 2026-07-03 audit found there is no single existing lens to "factor out" — the offseason
forecast shrinks total WAR toward replacement, and the per-component method lives elsewhere. So
the assessment's point estimator is chosen by a bakeoff (models_ml/validate_assessment.py, ship
gate G1 + the preregistered selection rule). This module exposes all three candidates behind ONE
signature so the validator, and later compute_assessment, call them identically.

Each candidate: given a skater season `panel` (from baselines.skater_panel) and an `as_of_yr`,
returns {player_id -> (assessed_war_rate, war_sd_rate)} where rate is WAR per 5v5 hour. The
harness multiplies by realized next-season 5v5 TOI, de-confounding TOI (spec 5.2 T1). No aging
is applied in any candidate (spec D4).

  C1 c1_r_shrink      NET-NEW. Per-component shrink of a single season's player_gar component
                      rates toward the position-group mean by the measured GAR_STABILITY_YOY
                      r-values (production 0.66, RAPM 0.38); the finishing residual (goals-ixg)
                      is shrunk toward 0 by 0.35. Sustainable production and finishing are split
                      so finishing is not regressed twice.
  C2 c2_roster_player WRAP of project_roster_player._project_skater_components (per-component,
                      sample-size shrink toward a position prior) with aging zeroed.
  C3 c3_blended       WRAP of compute_contract_value.blended_war_rate (total-WAR shrink toward
                      replacement by sample size). Its per-82 WAR level is divided by the same
                      recency/games-weighted 5v5 hours to yield a per-hour rate.

Goalies are NOT part of the bakeoff (goalie_gar is already reliability-shrunk and carried
through, spec 6.1); this module is skaters only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models_ml import config
from models_ml import project_roster_player as RP
from models_ml.compute_contract_value import blended_war_rate

GPW = config.GAR_CONFIG["GOALS_PER_WIN"]
R = config.GAR_STABILITY_YOY                       # production_r, rapm_r, finishing_r
QUAL_MIN = config.GAR_CONFIG["MIN_TOI_5V5_FOR_RANKING"]

PROD = ["ev_offense", "pp"]
RAPM = ["ev_defense", "pk"]
PASS = ["penalty", "faceoff"]
SK_COMPONENTS = PROD + RAPM + PASS

# Mirror blended_war_rate's internal PROJ["SEASON_WEIGHTS"] so the C3 rate conversion (per-82
# WAR / per-82 5v5 hours) uses the exact same weighting as the level it divides.
_C3_SEASON_W = [5.0, 4.0, 3.0, 2.0, 1.0]

# V1_TRIO = the original gate-G1 incumbent candidates. C4 is scored alongside but its promotion
# is decided by the separate v2.5 rule (see validate_assessment), so it is not in the v1 gate.
V1_TRIO = ["c1_r_shrink", "c2_roster_player", "c3_blended"]
CANDIDATES = V1_TRIO + ["c4_r_speed"]


def _wmean(values: pd.Series, weights: pd.Series) -> float:
    ok = np.isfinite(values) & (weights > 0)
    return float(np.average(values[ok], weights=weights[ok])) if ok.any() else 0.0


def c1_r_shrink(panel: pd.DataFrame, as_of_yr: int) -> dict:
    """Single-season (as_of) per-component r-shrink toward the position-group mean; finishing
    toward 0. Sustainable production and finishing are separated so finishing is regressed once."""
    df = panel[(panel["yr"] == as_of_yr) & (panel["toi_5v5"] > 0)].copy()
    if df.empty:
        return {}
    h = df["toi_5v5"] / 60.0                                       # 5v5 hours
    for c in SK_COMPONENTS:
        df[c + "_r"] = df[c] / h                                   # goals per 5v5 hour
    df["fin_r"] = (df["goals"] - df["ixg"]) / h                    # finishing luck (goals/5v5-hr)
    df["prod_r"] = df["ev_offense_r"] + df["pp_r"]
    df["sust_r"] = df["prod_r"] - df["fin_r"]                      # production minus finishing luck
    df["rapm_rr"] = df["ev_defense_r"] + df["pk_r"]
    df["pass_r"] = df["penalty_r"] + df["faceoff_r"]

    out = {}
    for pg, sub in df.groupby("pos_group"):
        pool = sub[sub["toi_5v5"] >= QUAL_MIN]                     # mean over the qualified pool
        if pool.empty:
            pool = sub
        m_sust = _wmean(pool["sust_r"], pool["toi_5v5"])
        m_rapm = _wmean(pool["rapm_rr"], pool["toi_5v5"])
        for _, r in sub.iterrows():
            g_rate = (
                m_sust + R["production_r"] * (r["sust_r"] - m_sust)      # sustainable prod -> mean
                + R["finishing_r"] * r["fin_r"]                          # finishing -> 0
                + m_rapm + R["rapm_r"] * (r["rapm_rr"] - m_rapm)         # RAPM-borrowed -> mean
                + r["pass_r"]                                            # penalty/faceoff pass through
            )
            war_rate = g_rate / GPW
            sd_rate = (r["gar_sd"] / GPW) / (r["toi_5v5"] / 60.0)        # band = sampling sd (rate)
            out[int(r["player_id"])] = (float(war_rate), float(sd_rate))
    return out


def _rp_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Columns project_roster_player expects, with age NaN so no aging is applied."""
    cols = ["player_id", "yr", "pos_group", "ev_offense", "pp", "ev_defense", "pk",
            "penalty", "faceoff", "toi_5v5", "pp_toi", "pk_toi", "games", "war"]
    p = panel[cols].copy()
    p["pg"] = p["pos_group"]
    p["age"] = np.nan
    return p


def c2_roster_player(panel: pd.DataFrame, as_of_yr: int) -> dict:
    """Wrap project_roster_player's per-component Marcel-toward-prior projection, aging zeroed."""
    p = _rp_panel(panel)
    train = p[p["yr"] <= as_of_yr]
    if train.empty:
        return {}
    params = {"prior": RP._prior_rates(train), "kc": dict(RP.KC_DEFAULT), "age": {}}
    out = {}
    for pid, g in train.groupby("player_id"):
        hist = g.sort_values("yr", ascending=False).to_dict("records")
        if not hist:
            continue
        proj = RP._project_skater_components(hist, params)
        war = sum(proj[c] for c in RP.SK_COMPONENTS) / GPW
        h = proj["_denom"]["ev_offense"] / 60.0
        if h <= 0:
            continue
        out[int(pid)] = (float(war / h), None)
    return out


def c3_blended(panel: pd.DataFrame, as_of_yr: int) -> dict:
    """Wrap compute_contract_value.blended_war_rate (per-82 WAR level), converted to a per-5v5-hour
    rate using the same recency/games weighting so the TOI cancels in the harness."""
    p = panel[panel["yr"] <= as_of_yr]
    out = {}
    for pid, g in p.groupby("player_id"):
        g = g.sort_values("yr", ascending=False).head(5)
        seasons = []
        num = den = 0.0
        for _, r in g.iterrows():
            yrs_ago = as_of_yr - int(r["yr"])
            games = float(r["games"])
            if yrs_ago < 0 or yrs_ago >= len(_C3_SEASON_W) or games <= 0:
                continue
            seasons.append((yrs_ago, float(r["war"]), games))
            w = _C3_SEASON_W[yrs_ago] * games
            num += w * (float(r["toi_5v5"]) * 82.0 / games)          # 5v5 minutes per 82 games
            den += w
        if not seasons or den <= 0:
            continue
        per82_war, _ = blended_war_rate(seasons)
        h82 = (num / den) / 60.0                                      # 5v5 hours per 82 games
        if h82 <= 0:
            continue
        out[int(pid)] = (float(per82_war / h82), None)
    return out


def c4_r_speed(panel: pd.DataFrame, as_of_yr: int) -> dict:
    """Single-season per-component shrink like C1, but the trust is SAMPLE-ADAPTIVE:
    reliability = n / (n + K_c) with K_c derived analytically from the measured r
    (K_c = n0*(1-r)/r, n0 = median qualified 5v5 TOI in season S). At the typical sample n0 the
    reliability equals r; high-TOI players are trusted more, low-TOI less. Finishing -> 0."""
    df = panel[(panel["yr"] == as_of_yr) & (panel["toi_5v5"] > 0)].copy()
    if df.empty:
        return {}
    n0 = float(df.loc[df["toi_5v5"] >= QUAL_MIN, "toi_5v5"].median())
    if not np.isfinite(n0) or n0 <= 0:
        n0 = float(df["toi_5v5"].median())
    # K_c = n0*(1-r)/r  -> reliability(n0)=r. finishing (r=0.35) gets the largest K (least trust).
    k_prod = n0 * (1 - R["production_r"]) / R["production_r"]
    k_rapm = n0 * (1 - R["rapm_r"]) / R["rapm_r"]
    k_fin = n0 * (1 - R["finishing_r"]) / R["finishing_r"]

    h = df["toi_5v5"] / 60.0
    for c in SK_COMPONENTS:
        df[c + "_r"] = df[c] / h
    df["fin_r"] = (df["goals"] - df["ixg"]) / h
    df["sust_r"] = df["ev_offense_r"] + df["pp_r"] - df["fin_r"]
    df["rapm_rr"] = df["ev_defense_r"] + df["pk_r"]
    df["pass_r"] = df["penalty_r"] + df["faceoff_r"]

    out = {}
    for pg, sub in df.groupby("pos_group"):
        pool = sub[sub["toi_5v5"] >= QUAL_MIN]
        if pool.empty:
            pool = sub
        m_sust = _wmean(pool["sust_r"], pool["toi_5v5"])
        m_rapm = _wmean(pool["rapm_rr"], pool["toi_5v5"])
        for _, r in sub.iterrows():
            n = float(r["toi_5v5"])
            rel_prod = n / (n + k_prod)
            rel_rapm = n / (n + k_rapm)
            rel_fin = n / (n + k_fin)
            g_rate = (
                m_sust + rel_prod * (r["sust_r"] - m_sust)      # sustainable prod -> mean
                + rel_fin * r["fin_r"]                          # finishing -> 0
                + m_rapm + rel_rapm * (r["rapm_rr"] - m_rapm)   # RAPM-borrowed -> mean
                + r["pass_r"]
            )
            sd_rate = (r["gar_sd"] / GPW) / (r["toi_5v5"] / 60.0)
            out[int(r["player_id"])] = (float(g_rate / GPW), float(sd_rate))
    return out


_DISPATCH = {"c1_r_shrink": c1_r_shrink, "c2_roster_player": c2_roster_player,
             "c3_blended": c3_blended, "c4_r_speed": c4_r_speed}


def candidate_rates(name: str, panel: pd.DataFrame, as_of_yr: int) -> dict:
    """{player_id -> (assessed_war_rate, war_sd_rate|None)} for the named candidate."""
    return _DISPATCH[name](panel, as_of_yr)
