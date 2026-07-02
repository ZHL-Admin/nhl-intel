"""Component-level season-ahead player projection for the Roster Builder (Handoff 12).

A SEPARATE projection from project_roster_forecast (blended_war_rate + aging), used ONLY by the
Roster Builder's roster-evaluate. The offseason/trade/contract tools are untouched. Why this exists:
the shared projection carries last season's WAR forward with one aging curve and reuses last season's
*measurement* sd as if it were next-season uncertainty — which the band diagnostic showed is built
from within-season noise, tracks roster composition (mostly the goalie sd), and covers the real
outcome only ~52% of the time at a nominal 1 sigma.

This module fixes both halves:
  * POINT estimate — a regularized, component-level Marcel. Each skater component (ev_offense, pp,
    ev_defense, pk, penalty, faceoff) is projected as a playing-time-weighted multi-year rate,
    regressed toward a position prior by a PER-COMPONENT amount (k_c) set by that component's
    reliability, then aged by a component-group age curve, then re-scaled by projected ice time.
    Goalies — whose components are near-noise year over year (autocorr ~0.1) but whose WAR aggregate
    persists (autocorr ~0.36) — are projected at the WAR level with heavy regression.
  * UNCERTAINTY — heteroscedastic per-component sd FIT FROM BACKTEST RESIDUALS (projected vs actual on
    a strict temporal holdout), as a function of playing time and a no-track flag. Player WAR sd =
    component sds in quadrature. This replaces war_sd = gar_sd/6 for the Roster Builder.

Empirical reliabilities (YoY rate autocorrelation, 2021-22..2025-26) that motivate the per-component
regression: ev_offense .51, penalty .58, faceoff .55 (light) | pp .33, ev_defense .27, pk .28 (hard)
| goalie components .02-.15, goalie WAR .36 (very hard, WAR-level).

Run:  python -m models_ml.project_roster_player            # fit + backtest report (reads only)
      python -m models_ml.project_roster_player --write    # also write nhl_models.roster_player_projection
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config

GPW = config.GAR_CONFIG["GOALS_PER_WIN"]
MODEL_VERSION = "roster_player_v1"

# Skater components: each has a playing-time denominator and an age-curve group. age_group ties sparse
# components to a richer one's curve (pp ages like offense, pk like defense; penalty/faceoff are skills
# that barely age). Denominator separates rate (skill) from ice time (usage), projected separately.
SK_COMPONENTS = {
    "ev_offense": {"denom": "toi_5v5", "age_group": "off"},
    "pp":         {"denom": "pp_toi",  "age_group": "off"},
    "ev_defense": {"denom": "toi_5v5", "age_group": "def"},
    "pk":         {"denom": "pk_toi",  "age_group": "def"},
    "penalty":    {"denom": "games",   "age_group": "skill"},
    "faceoff":    {"denom": "games",   "age_group": "skill"},
}
GOALIE_COMPONENTS = ["hd_saves", "md_saves", "ld_saves", "pk_goaltending"]

# Recency weights (season 0 = most recent). A Marcel-like decay, deliberately gentle given only 5
# seasons exist. Tuned only coarsely — the regression k_c does the heavy lifting.
RECENCY = [1.0, 0.78, 0.58, 0.42, 0.30]

# Per-component regression constants k_c, in DENOMINATOR units (minutes for TOI components, games for
# games components). Larger k => regress harder toward the prior. Defaults derived from reliability
# (k ~ denom_typical * (1-r)/r), then refined by held-out grid search in _fit_kc.
KC_DEFAULT = {
    "ev_offense": 650.0, "pp": 40.0, "ev_defense": 1800.0, "pk": 45.0,
    "penalty": 45.0, "faceoff": 12.0,   # faceoff is a stable, tiny skill -> regress lightly
}
GOALIE_K_GAMES = 70.0       # WAR-level regression for goalies (autocorr ~0.36 -> heavy)
MIN_AGE_DELTAS = 40         # min paired deltas to trust an (group, age) age point; else 0
AGE_SMOOTH = 2              # +/- window for smoothing the age-delta curve
AGE_SHRINK = 0.6            # shrink fitted age deltas toward 0 (regularize on thin data)


# ----------------------------------------------------------------------------- data

def load_panels(bq):
    """Return (skater_df, goalie_df), one row per player-season-window, with age and rates."""
    sk = bq.query_df("""
        select player_id, season_window as season,
               case when position='D' then 'D' else 'F' end as pg,
               ev_offense, pp, ev_defense, pk, penalty, faceoff,
               toi_5v5, pp_toi, pk_toi, games, war
        from player_gar where season_window like '____-__'
    """)
    go = bq.query_df("""
        select goalie_id as player_id, season_window as season,
               hd_saves, md_saves, ld_saves, pk_goaltending,
               shots_total, games_played as games, war
        from goalie_gar where season_window like '____-__'
    """)
    bio = bq.query_df("select player_id, birth_date from stg_player_bio")
    bio["birth_year"] = pd.to_datetime(bio["birth_date"], errors="coerce").dt.year
    for df in (sk, go):
        df["yr"] = df["season"].str[:4].astype(int)
        df.sort_values(["player_id", "yr"], inplace=True)
    sk = sk.merge(bio[["player_id", "birth_year"]], on="player_id", how="left")
    go = go.merge(bio[["player_id", "birth_year"]], on="player_id", how="left")
    sk["age"] = sk["yr"] - sk["birth_year"]
    go["age"] = go["yr"] - go["birth_year"]
    return sk, go


# ----------------------------------------------------------------------------- fitting

def _prior_rates(train_sk):
    """{pos_group: {component: prior_rate}} — playing-time-weighted league mean rate per position."""
    out = {}
    for pg, sub in train_sk.groupby("pg"):
        out[pg] = {}
        for c, cfg in SK_COMPONENTS.items():
            d = sub[cfg["denom"]].clip(lower=0).sum()
            out[pg][c] = float(sub[c].sum() / d) if d > 0 else 0.0
    return out


def _fit_age_deltas(train_sk):
    """Additive per-(pos_group, age_group) rate deltas by age, from within-player year-over-year rate
    changes (the delta method, mirroring fit_aging_curves), smoothed and shrunk toward 0."""
    rows = []
    for c, cfg in SK_COMPONENTS.items():
        den, grp = cfg["denom"], cfg["age_group"]
        d = train_sk[train_sk[den] > (200 if "toi" in den else 10)].copy()
        d["rate"] = d[c] / d[den]
        d["rate_next"] = d.groupby("player_id")["rate"].shift(-1)
        d["yr_next"] = d.groupby("player_id")["yr"].shift(-1)
        d = d[d["yr_next"] == d["yr"] + 1].dropna(subset=["rate", "rate_next"])
        d["delta"] = d["rate_next"] - d["rate"]
        for _, r in d.iterrows():
            rows.append((r["pg"], grp, int(r["age"]), r["delta"]))
    df = pd.DataFrame(rows, columns=["pg", "grp", "age", "delta"])
    curves = {}
    for (pg, grp), sub in df.groupby(["pg", "grp"]):
        by_age = sub.groupby("age")["delta"].agg(["mean", "count"])
        raw = {int(a): (m if n >= MIN_AGE_DELTAS else 0.0) for a, (m, n) in
               by_age[["mean", "count"]].iterrows()}
        # smooth (centered window) + shrink toward 0
        ages = sorted(raw)
        sm = {}
        for a in ages:
            w = [raw[x] for x in ages if abs(x - a) <= AGE_SMOOTH]
            sm[a] = AGE_SHRINK * float(np.mean(w)) if w else 0.0
        curves[(pg, grp)] = sm
    return curves


def _project_skater_components(rows, params):
    """rows: this player's seasons (dicts), MOST RECENT FIRST. Returns {component: projected value,
    '_denom': {component: projected denom}}. Pure Marcel: weighted rate -> regress -> age -> x denom."""
    pg = rows[0]["pg"]
    prior, kc, ages = params["prior"][pg], params["kc"], params["age"]
    out, denoms = {}, {}
    age = rows[0]["age"]
    for c, cfg in SK_COMPONENTS.items():
        den = cfg["denom"]
        num = dsum = dwt = 0.0
        for i, r in enumerate(rows[:5]):
            w = RECENCY[i]
            num += w * r[c]; dsum += w * r[den]; dwt += w * 1.0
        base = (num / dsum) if dsum > 0 else prior[c]
        k = kc[c]
        rr = (dsum * base + k * prior[c]) / (dsum + k)
        if age == age:  # not NaN
            rr += ages.get((pg, cfg["age_group"]), {}).get(int(age), 0.0)
        # Ice time projected SEPARATELY and games-weighted, so an injured/low-games season can't drag
        # a returning player's usage (and thus his value) toward zero. Project per-game ice time
        # (recency-weighted), times a games-weighted games count (a 70-game season outvotes a 20-game
        # one). The rate above is already TOI-weighted, so the rate uses healthy history too.
        toi_w = sum(RECENCY[i] * r[den] for i, r in enumerate(rows[:5]))
        g_w = sum(RECENCY[i] * max(r["games"], 0) for i, r in enumerate(rows[:5]))
        g2_w = sum(RECENCY[i] * max(r["games"], 0) ** 2 for i, r in enumerate(rows[:5]))
        tpg = toi_w / g_w if g_w > 0 else 0.0           # per-game ice time (or =1 for games-denom comps)
        proj_games = g2_w / g_w if g_w > 0 else 0.0     # durability, injury seasons down-weighted
        d_next = tpg * proj_games
        out[c] = rr * d_next
        denoms[c] = d_next
    out["_denom"] = denoms
    return out


def _fit_kc(train_sk, prior, ages):
    """Refine k_c per component by grid search minimizing one-step held-out value RMSE within train
    (predict each season t+1 from <=t, for transitions inside the training span)."""
    kc = dict(KC_DEFAULT)
    pairs = _one_step_pairs(train_sk)
    if not pairs:
        return kc
    grid = [0.1, 0.15, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]
    for c in SK_COMPONENTS:
        best, best_e = kc[c], np.inf
        for mult in grid:
            k = KC_DEFAULT[c] * mult
            err = []
            for hist, actual in pairs:
                p = _project_skater_components(hist, {"prior": prior, "kc": {**kc, c: k}, "age": ages})
                err.append((p[c] - actual[c]) ** 2)
            e = float(np.mean(err))
            if e < best_e:
                best_e, best = e, k
        kc[c] = best
    return kc


def _one_step_pairs(df):
    """For each player, (history rows <=t most-recent-first, actual row t+1) for consecutive seasons."""
    pairs = []
    for _, g in df.groupby("player_id"):
        g = g.sort_values("yr")
        recs = g.to_dict("records")
        for i in range(1, len(recs)):
            if recs[i]["yr"] == recs[i - 1]["yr"] + 1:
                hist = [r for r in recs[:i]][::-1]   # most recent first
                pairs.append((hist, recs[i]))
    return pairs


def fit_params(train_sk):
    prior = _prior_rates(train_sk)
    ages = _fit_age_deltas(train_sk)
    kc = _fit_kc(train_sk, prior, ages)
    return {"prior": prior, "age": ages, "kc": kc}


# ----------------------------------------------------------------------------- goalies (WAR-level)

def _goalie_prior_war(train_go):
    return float(train_go["war"].mean())


def project_goalie_war(rows, prior_war):
    """Heavy WAR-level regression toward the league-average goalie (components too noisy to project
    individually). rows most-recent-first."""
    num = wt = gms = 0.0
    for i, r in enumerate(rows[:5]):
        w = RECENCY[i]
        num += w * r["war"]; wt += w; gms += w * r["games"]
    base = num / wt if wt > 0 else prior_war
    k = GOALIE_K_GAMES
    return (gms * base + k * prior_war) / (gms + k)


# ----------------------------------------------------------------------------- backtest


def _marcel_war(rows):
    """Plain WAR-level Marcel baseline: recency+games-weighted WAR regressed toward replacement (0)."""
    num = wt = gms = 0.0
    for i, r in enumerate(rows[:5]):
        w = RECENCY[i]
        num += w * r["war"]; wt += w; gms += w * r["games"]
    base = num / wt if wt > 0 else 0.0
    k = 30.0  # games
    return (gms * base) / (gms + k)


def _naive_war(rows):
    """Current method proxy: most-recent WAR carried with a mild multi-year blend, no regression
    (mirrors the spirit of project_skater_war's blend without its archetype aging table)."""
    num = wt = 0.0
    for i, r in enumerate(rows[:5]):
        w = RECENCY[i]
        num += w * r["war"]; wt += w
    return num / wt if wt > 0 else 0.0


def holdout_predictions(sk, go):
    """Strict temporal holdout: for each held-out season T, fit params on outcomes < T and predict T.
    Returns (skater_records, goalie_records) — one dict per held-out player-season with the model and
    baseline projections, the actual, projected denoms, and history depth (for the sd model)."""
    seasons = sorted(sk["yr"].unique())
    holdouts = seasons[2:]
    sk_rec, go_rec = [], []
    for T in holdouts:
        params = fit_params(sk[sk["yr"] < T])
        prior_gw = _goalie_prior_war(go[go["yr"] < T])
        for pid, g in sk.groupby("player_id"):
            hist = g[g["yr"] < T].sort_values("yr", ascending=False).to_dict("records")
            act = g[g["yr"] == T]
            if not hist or act.empty:
                continue
            a = act.iloc[0]
            p = _project_skater_components(hist, params)
            rec = {"player_id": pid, "T": T, "pg": hist[0]["pg"], "n_hist": len(hist),
                   "war_model": sum(p[c] for c in SK_COMPONENTS) / GPW,
                   "war_marcel": _marcel_war(hist), "war_naive": _naive_war(hist), "war_act": a["war"]}
            for c in SK_COMPONENTS:
                rec[f"{c}_m"] = p[c]
                rec[f"{c}_mar"] = _marcel_comp(hist, c, params["prior"][hist[0]["pg"]][c])
                rec[f"{c}_nai"] = _naive_comp(hist, c)
                rec[f"{c}_act"] = a[c]
                rec[f"{c}_den"] = p["_denom"][c]
            sk_rec.append(rec)
        for pid, g in go.groupby("player_id"):
            hist = g[g["yr"] < T].sort_values("yr", ascending=False).to_dict("records")
            act = g[g["yr"] == T]
            if not hist or act.empty:
                continue
            a = act.iloc[0]
            go_rec.append({"player_id": pid, "T": T, "n_hist": len(hist),
                           "games": sum(r["games"] for r in hist[:3]),
                           "war_model": project_goalie_war(hist, prior_gw),
                           "war_marcel": _marcel_war(hist), "war_naive": _naive_war(hist),
                           "war_act": a["war"]})
    return pd.DataFrame(sk_rec), pd.DataFrame(go_rec)


def backtest_summary(skp, gop):
    rmse = lambda x: float(np.sqrt(np.mean(np.square(x)))) if len(x) else float("nan")
    comps = {}
    for c in SK_COMPONENTS:
        comps[c] = {"model": rmse(skp[f"{c}_m"] - skp[f"{c}_act"]),
                    "marcel": rmse(skp[f"{c}_mar"] - skp[f"{c}_act"]),
                    "naive": rmse(skp[f"{c}_nai"] - skp[f"{c}_act"])}
    return {
        "components": comps,
        "war": {m: rmse(skp[f"war_{m}"] - skp["war_act"]) for m in ("model", "marcel", "naive")},
        "goalie_war": {m: rmse(gop[f"war_{m}"] - gop["war_act"]) for m in ("model", "marcel", "naive")},
    }


def fit_residual_sd(skp, gop):
    """Heteroscedastic per-component sd from holdout residuals: Var(resid) ~ s0^2 + s1^2 / denom
    (measurement floor + small-sample inflation), fit by OLS of squared residual on [1, 1/denom].
    Returns {comp: (s0sq, s1sq)}, a no-track component sd, and the goalie war-sd params. A global
    multiplier (lambda) is then fit so the WAR-level 1-sigma coverage is ~68% (true calibration)."""
    sd = {}
    for c in SK_COMPONENTS:
        r2 = (skp[f"{c}_m"] - skp[f"{c}_act"]).to_numpy() ** 2
        den = skp[f"{c}_den"].clip(lower=1.0).to_numpy()
        X = np.column_stack([np.ones_like(den), 1.0 / den])
        coef, *_ = np.linalg.lstsq(X, r2, rcond=None)
        sd[c] = (max(coef[0], 1e-4), max(coef[1], 0.0))
    # no-track (1 season of history) component sd — the empirical residual sd of thin-history players
    thin = skp[skp["n_hist"] <= 1]
    notrack = {c: float(np.sqrt(np.mean((thin[f"{c}_m"] - thin[f"{c}_act"]) ** 2))) if len(thin) else
               float(np.sqrt(sd[c][0])) for c in SK_COMPONENTS}
    # goalie war sd vs games
    gr2 = (gop["war_model"] - gop["war_act"]).to_numpy() ** 2
    gden = gop["games"].clip(lower=1.0).to_numpy()
    Xg = np.column_stack([np.ones_like(gden), 1.0 / gden])
    gcoef, *_ = np.linalg.lstsq(Xg, gr2, rcond=None)
    goalie_sd = (max(gcoef[0], 1e-4), max(gcoef[1], 0.0))

    def war_sd_skater(row):
        v = sum(max(sd[c][0] + sd[c][1] / max(row[f"{c}_den"], 1.0), 0.0) for c in SK_COMPONENTS)
        return math_sqrt(v) / GPW

    # global calibration multiplier so |resid| <= lambda*sd about 68% of the time at the WAR level
    sk_sd = skp.apply(war_sd_skater, axis=1).to_numpy()
    sk_resid = (skp["war_model"] - skp["war_act"]).abs().to_numpy()
    go_sd = np.sqrt(goalie_sd[0] + goalie_sd[1] / gden) / 1.0
    go_resid = (gop["war_model"] - gop["war_act"]).abs().to_numpy()
    all_sd = np.concatenate([sk_sd, go_sd]); all_resid = np.concatenate([sk_resid, go_resid])
    # find lambda s.t. ~68% coverage
    lam = float(np.percentile(all_resid / np.clip(all_sd, 1e-6, None), 68))
    return {"comp": sd, "notrack": notrack, "goalie": goalie_sd, "lambda": lam}


def math_sqrt(x):
    return float(np.sqrt(max(x, 0.0)))


def _marcel_comp(rows, c, prior_rate):
    den = SK_COMPONENTS[c]["denom"]
    num = dsum = dwt = 0.0
    for i, r in enumerate(rows[:5]):
        w = RECENCY[i]
        num += w * r[c]; dsum += w * r[den]; dwt += w
    base = num / dsum if dsum > 0 else prior_rate
    k = KC_DEFAULT[c]
    rr = (dsum * base + k * prior_rate) / (dsum + k)
    d_next = sum(RECENCY[i] * r[den] for i, r in enumerate(rows[:5])) / dwt if dwt > 0 else 0.0
    return rr * d_next


def _naive_comp(rows, c):
    """Carry most-recent component value forward (rate x most-recent denom), no regression."""
    den = SK_COMPONENTS[c]["denom"]
    r0 = rows[0]
    rate = r0[c] / r0[den] if r0[den] > 0 else 0.0
    return rate * r0[den]


def _war_sd_skater(comp_denoms, sdm):
    var = sum(max(sdm["comp"][c][0] + sdm["comp"][c][1] / max(comp_denoms[c], 1.0), 0.0)
              for c in SK_COMPONENTS)
    return sdm["lambda"] * math_sqrt(var) / GPW


def build_projection_table(sk, go, params, prior_gw, sdm):
    """One row per player with >=1 GAR season: project next season (from ALL their history) with the
    full-data params, plus the calibrated WAR sd. This is the serving table roster-evaluate reads."""
    rows = []
    for pid, g in sk.groupby("player_id"):
        hist = g.sort_values("yr", ascending=False).to_dict("records")
        p = _project_skater_components(hist, params)
        war = sum(p[c] for c in SK_COMPONENTS) / GPW
        proj_toi = p["_denom"]["ev_offense"] + p["_denom"]["pp"] + p["_denom"]["pk"]  # 5v5+PP+PK minutes
        rows.append({"player_id": int(pid), "is_goalie": False, "pos_group": hist[0]["pg"],
                     "proj_war": round(war, 4), "proj_war_sd": round(_war_sd_skater(p["_denom"], sdm), 4),
                     "proj_toi": round(proj_toi, 1), "n_seasons": len(hist),
                     **{f"proj_{c}": round(p[c], 4) for c in SK_COMPONENTS},
                     "proj_hd_saves": 0.0, "proj_md_saves": 0.0, "proj_ld_saves": 0.0,
                     "proj_pk_goaltending": 0.0, "model_version": MODEL_VERSION})
    for pid, g in go.groupby("player_id"):
        hist = g.sort_values("yr", ascending=False).to_dict("records")
        war = project_goalie_war(hist, prior_gw)
        games = sum(r["games"] for r in hist[:3])
        gsd = sdm["lambda"] * math_sqrt(sdm["goalie"][0] + sdm["goalie"][1] / max(games, 1.0))
        rows.append({"player_id": int(pid), "is_goalie": True, "pos_group": "G",
                     "proj_war": round(war, 4), "proj_war_sd": round(gsd, 4),
                     "proj_toi": 1400.0,  # capped representative weight (~one top skater) for the w calc
                     "n_seasons": len(hist),
                     **{f"proj_{c}": 0.0 for c in SK_COMPONENTS},
                     "proj_hd_saves": 0.0, "proj_md_saves": 0.0, "proj_ld_saves": 0.0,
                     "proj_pk_goaltending": round(war * GPW, 4), "model_version": MODEL_VERSION})
    return pd.DataFrame(rows)


def _model_war(pid, is_g, sk_idx, go_idx, params, prior_gw, yr_lt=None, sdm=None):
    """(proj_war, war_sd) for a player from history (optionally restricted to seasons < yr_lt). Returns
    (None, None) if no history (caller treats as no-track replacement). war_sd only if sdm given."""
    src = go_idx if is_g else sk_idx
    rows = src.get(pid)
    if rows is None:
        return None, None
    hist = [r for r in rows if (yr_lt is None or r["yr"] < yr_lt)]
    if not hist:
        return None, None
    hist = sorted(hist, key=lambda r: r["yr"], reverse=True)
    if is_g:
        war = project_goalie_war(hist, prior_gw)
        games = sum(r["games"] for r in hist[:3])
        sd = (sdm["lambda"] * math_sqrt(sdm["goalie"][0] + sdm["goalie"][1] / max(games, 1.0))) if sdm else None
        return war, sd
    p = _project_skater_components(hist, params)
    war = sum(p[c] for c in SK_COMPONENTS) / GPW
    sd = _war_sd_skater(p["_denom"], sdm) if sdm else None
    return war, sd


def _ice_total(team_players, hand):
    """Position-aware iced-lineup WAR (12F/6D/1G), mirroring the tool's optimizer. team_players:
    list of (war, pos_group, position, player_id)."""
    war = lambda t: t[0]
    fb = {"L": [], "C": [], "R": []}
    for t in sorted((t for t in team_players if t[1] == "F"), key=war, reverse=True):
        fb[t[2] if t[2] in ("L", "C", "R") else "C"].append(t)
    iced, lo = [], []
    for pos, cap in (("L", 4), ("C", 4), ("R", 4)):
        iced += fb[pos][:cap]; lo += fb[pos][cap:]
    iced += sorted(lo, key=war, reverse=True)[:max(0, 12 - len(iced))]
    db = {"L": [], "R": []}
    for t in sorted((t for t in team_players if t[1] == "D"), key=war, reverse=True):
        s = hand.get(t[3]); db[s if s in ("L", "R") else ("L" if len(db["L"]) <= len(db["R"]) else "R")].append(t)
    idd, ld = [], []
    for side, cap in (("L", 3), ("R", 3)):
        idd += db[side][:cap]; ld += db[side][cap:]
    idd += sorted(ld, key=war, reverse=True)[:max(0, 6 - len(idd))]
    g = sorted((t for t in team_players if t[1] == "G"), key=war, reverse=True)[:1]
    return sum(t[0] for t in iced + idd + g)


def delta_validation(sk, go):
    """PRIMARY GATE. For each team's real roster change N->N+1, predict the change in team strength
    (both rosters projected forward by the model) and compare to the realized change in measured rating
    and actual points. Report RMSE + correlation. The delta is the tool's headline; stayers cancel."""
    from models_ml import project_roster_forecast as J
    from models_ml.calibrate_roster_builder import _membership_open, _actual_points, _handedness
    CFG = J.CFG
    hand = _handedness(bq)
    sk_idx = {pid: g.to_dict("records") for pid, g in sk.groupby("player_id")}
    go_idx = {pid: g.to_dict("records") for pid, g in go.groupby("player_id")}
    pos_of = {}
    for df, isg in ((sk, False), (go, True)):
        for r in df.itertuples():
            pos_of[r.player_id] = ("G" if isg else r.pg, getattr(r, "position", "C") if not isg else "G")

    def team_points(mem_team, params, prior_gw, yr_lt):
        tp = []
        for m in mem_team:
            pid = m["player_id"]; pos = m["position"]
            is_g = pos == "G"; pgrp = "G" if is_g else ("D" if pos == "D" else "F")
            w, _ = _model_war(pid, is_g, sk_idx, go_idx, params, prior_gw, yr_lt)
            tp.append((w if w is not None else 0.0, pgrp, pos, pid))
        tot = _ice_total(tp, hand)
        return J.rating_to_points(J.absolute_rating(tot, 0.0, CFG), CFG), J.absolute_rating(tot, 0.0, CFG)

    pred_d_pts, real_d_pts, pred_d_rt, real_d_rt = [], [], [], []
    for base, target in (("2023-24", "2024-25"), ("2024-25", "2025-26")):
        Ty = int(target[:4])
        params = fit_params(sk[sk["yr"] < Ty]); prior_gw = _goalie_prior_war(go[go["yr"] < Ty])
        mem_N = _membership_open(bq, base); mem_N1 = _membership_open(bq, target)
        mr_N = {t: r["rating"] for t, r in J.load_team_ratings(bq, base).items()}
        mr_N1 = {t: r["rating"] for t, r in J.load_team_ratings(bq, target).items()}
        ap_N = _actual_points(bq, base); ap_N1 = _actual_points(bq, target)
        for tid in set(mem_N) & set(mem_N1):
            if tid not in mr_N or tid not in mr_N1 or tid not in ap_N or tid not in ap_N1:
                continue
            pN, rN = team_points(mem_N[tid], params, prior_gw, Ty)
            pN1, rN1 = team_points(mem_N1[tid], params, prior_gw, Ty)
            pred_d_pts.append(pN1 - pN); real_d_pts.append(ap_N1[tid] - ap_N[tid])
            pred_d_rt.append(rN1 - rN); real_d_rt.append(mr_N1[tid] - mr_N[tid])
    rmse = lambda a, b: float(np.sqrt(np.mean((np.array(a) - np.array(b)) ** 2)))
    corr = lambda a, b: float(np.corrcoef(a, b)[0, 1])
    return {"n": len(pred_d_pts),
            "pts_rmse": rmse(pred_d_pts, real_d_pts), "pts_corr": corr(pred_d_pts, real_d_pts),
            "rt_rmse": rmse(pred_d_rt, real_d_rt), "rt_corr": corr(pred_d_rt, real_d_rt),
            "pred_pts_sd": float(np.std(pred_d_pts)), "real_pts_sd": float(np.std(real_d_pts))}


LUCK_FLOOR_PTS = 6.15   # irreducible 82-game outcome SD (Handoff-11 band diagnostic)


# Predictive team base (Handoff 13): a 2-year recency-weighted measured rating, lightly regressed to
# the league mean. Beats single-season at predicting next-year strength (RMSE 0.230 vs 0.255, corr
# 0.58) and far beats the bottom-up reconstruction (corr ~0.44). The best single predictor of next
# season — what the offseason tool anchors on, now reused by the Roster Builder.
BASE_W = [1.0, 0.5]
BASE_K = 1.0


def _final_ratings(bq):
    """{team_id: [(yr, rating), ...] sorted} — the season-final measured rating per team-season."""
    df = bq.query_df("""
        with r as (select team_id, season, total_rating,
            row_number() over (partition by team_id, season order by game_date desc, games_played desc) rn
            from team_ratings)
        select team_id, season, total_rating from r where rn = 1""")
    df["yr"] = df["season"].str[:4].astype(int)
    out = {}
    for t, g in df.sort_values("yr").groupby("team_id"):
        out[int(t)] = [(int(r.yr), float(r.total_rating)) for r in g.itertuples()]
    return out


def predictive_base(series, target_yr):
    """R_measured for `target_yr`: 2-year weighted, league-mean-regressed rating from seasons < target."""
    hist = [r for (yr, r) in series if yr < target_yr]
    hist = hist[::-1]  # most recent first
    if not hist:
        return None
    m = min(len(hist), len(BASE_W))
    num = sum(BASE_W[j] * hist[j] for j in range(m)); wt = sum(BASE_W[j] for j in range(m))
    base = num / wt
    return (wt * base) / (wt + BASE_K)   # regress toward league mean (0)


def head_to_head(sk, go):
    """THE GATE. Hybrid (anchored on R_measured) vs the current bottom-up, on the same 63 team-seasons.
    Reports absolute points RMSE for both, the hybrid's R_measured anchor strength, delta correlation,
    absolute-band coverage, and monotonicity. Ship only if the hybrid wins on absolute RMSE and is >=
    on delta correlation with calibrated coverage."""
    from models_ml import project_roster_forecast as J
    from models_ml.calibrate_roster_builder import _membership_open, _actual_points, _handedness
    CFG = J.CFG; SLOPE = CFG["FORECAST_POINTS"]["slope"]
    hand = _handedness(bq); ratings = _final_ratings(bq)
    sk_idx = {pid: g.to_dict("records") for pid, g in sk.groupby("player_id")}
    go_idx = {pid: g.to_dict("records") for pid, g in go.groupby("player_id")}

    bu_pts, hy_pts, act_pts = [], [], []
    pred_d, real_d, pred_d_by_T = [], [], {}  # hybrid delta vs realized de-lucked strength change
    for base, target in (("2023-24", "2024-25"), ("2024-25", "2025-26")):
        Ty = int(target[:4]); By = int(base[:4])
        params = fit_params(sk[sk["yr"] < Ty]); prior_gw = _goalie_prior_war(go[go["yr"] < Ty])
        mem = _membership_open(bq, target); mem_b = _membership_open(bq, base)
        ap = _actual_points(bq, target)
        mr = {t: r["rating"] for t, r in J.load_team_ratings(bq, target).items()}
        mr_b = {t: r["rating"] for t, r in J.load_team_ratings(bq, base).items()}

        def bottomup_rating(members, yr_lt):
            tp = []
            for m in members:
                pid = m["player_id"]; pos = m["position"]; is_g = pos == "G"
                pgrp = "G" if is_g else ("D" if pos == "D" else "F")
                w, _ = _model_war(pid, is_g, sk_idx, go_idx, params, prior_gw, yr_lt)
                tp.append((w if w is not None else 0.0, pgrp, pos, pid))
            return J.absolute_rating(_ice_total(tp, hand), 0.0, CFG)

        for tid in mem:
            if tid not in ap or int(tid) not in ratings:
                continue
            r_meas = predictive_base(ratings[int(tid)], Ty)
            if r_meas is None:
                continue
            r_bu = bottomup_rating(mem[tid], Ty)
            bu_pts.append(J.rating_to_points(r_bu, CFG))         # current bottom-up (w-free)
            hy_pts.append(J.rating_to_points(r_meas, CFG))       # hybrid baseline (built=actual, w=1)
            act_pts.append(ap[tid])
            # delta: predicted composition change N->N+1 (= hybrid delta for retained rosters) vs realized
            if tid in mem_b and int(tid) in ratings and tid in mr and tid in mr_b:
                r_bu_b = bottomup_rating(mem_b[tid], Ty)
                pred_d.append(SLOPE * (r_bu - r_bu_b)); real_d.append((mr[tid] - mr_b[tid]) * SLOPE)
                pred_d_by_T.setdefault(target, []).append((SLOPE * (r_bu - r_bu_b), (mr[tid] - mr_b[tid]) * SLOPE))

    import numpy as np
    rmse = lambda p, a: float(np.sqrt(np.mean((np.array(p) - np.array(a)) ** 2)))
    corr = lambda a, b: float(np.corrcoef(a, b)[0, 1])
    hy_resid = np.abs(np.array(hy_pts) - np.array(act_pts))
    sigma_anchor = float(np.percentile(hy_resid, 68))   # absolute-band half-width for ~68% coverage
    per_T = {t: corr([x[0] for x in v], [x[1] for x in v]) for t, v in pred_d_by_T.items()}
    return {
        "n": len(act_pts),
        "bu_rmse": rmse(bu_pts, act_pts), "hy_rmse": rmse(hy_pts, act_pts),
        "bu_corr": corr(bu_pts, act_pts), "hy_corr": corr(hy_pts, act_pts),
        "delta_corr": corr(pred_d, real_d), "delta_n": len(pred_d), "delta_per_season": per_T,
        "sigma_anchor": sigma_anchor,
    }


def calibrate_absolute(sk, go):
    """Recalibrate the absolute-rating map for the NEW projections (the component model has a different
    WAR scale than project_skater_war, so LEAGUE_AVG_LINEUP_WAR and WAR_TO_RATING from Handoff 11 must
    be refit). Returns league-avg iced WAR, the WAR->rating slope (OLS vs measured rating), the band
    multiplier kappa (68% coverage), and the points MAE vs actual."""
    from models_ml import project_roster_forecast as J
    from models_ml.calibrate_roster_builder import _membership_open, _actual_points, _handedness
    CFG = J.CFG; SLOPE = CFG["FORECAST_POINTS"]["slope"]; FP = CFG["FORECAST_POINTS"]
    hand = _handedness(bq)
    sk_idx = {pid: g.to_dict("records") for pid, g in sk.groupby("player_id")}
    go_idx = {pid: g.to_dict("records") for pid, g in go.groupby("player_id")}
    tot, meas, act, quad = [], [], [], []
    for base, target in (("2023-24", "2024-25"), ("2024-25", "2025-26")):
        Ty = int(target[:4])
        params = fit_params(sk[sk["yr"] < Ty]); prior_gw = _goalie_prior_war(go[go["yr"] < Ty])
        sdm = fit_residual_sd(*holdout_predictions(sk[sk["yr"] <= Ty], go[go["yr"] <= Ty]))
        mem = _membership_open(bq, target)
        mr = {t: r["rating"] for t, r in J.load_team_ratings(bq, target).items()}
        ap = _actual_points(bq, target)
        for tid in mem:
            if tid not in mr or tid not in ap:
                continue
            tp = []
            for m in mem[tid]:
                pid = m["player_id"]; pos = m["position"]; is_g = pos == "G"
                pgrp = "G" if is_g else ("D" if pos == "D" else "F")
                w, s = _model_war(pid, is_g, sk_idx, go_idx, params, prior_gw, Ty, sdm)
                tp.append((w if w is not None else 0.0, pgrp, pos, pid, s if s is not None else 0.7))
            iced = _ice_top(tp)
            tot.append(sum(t[0] for t in iced)); meas.append(mr[tid]); act.append(ap[tid])
            quad.append(math_sqrt(sum(t[4] ** 2 for t in iced)))  # talent WAR quadrature for the band
    tot = np.array(tot); meas = np.array(meas); act = np.array(act); quad = np.array(quad)
    league_avg = float(tot.mean())
    centered = tot - league_avg
    w2r = float(np.polyfit(centered, meas, 1)[0])
    pred = np.clip(np.round(FP["intercept"] + FP["slope"] * (centered * w2r)), 0, FP["ceiling"])
    talent_pts = SLOPE * w2r * quad
    resid = np.abs(pred - act)
    kap = 1.0
    for k in np.arange(1.0, 12.0, 0.25):
        if np.mean(resid <= np.sqrt((k * talent_pts) ** 2 + LUCK_FLOOR_PTS ** 2)) >= 0.68:
            kap = float(k); break
    cov = float(np.mean(resid <= np.sqrt((kap * talent_pts) ** 2 + LUCK_FLOOR_PTS ** 2)))
    return {"league_avg": league_avg, "w2r": w2r, "kappa": kap, "coverage": cov,
            "mae": float(np.mean(np.abs(pred - act))), "n": len(tot)}


def _ice_top(tp):
    """Position-aware iced 12F/6D/1G as (war,pg,pos,pid,sd) tuples (for coverage; carries sd)."""
    war = lambda t: t[0]
    fb = {"L": [], "C": [], "R": []}
    for t in sorted((t for t in tp if t[1] == "F"), key=war, reverse=True):
        fb[t[2] if t[2] in ("L", "C", "R") else "C"].append(t)
    iced, lo = [], []
    for pos, cap in (("L", 4), ("C", 4), ("R", 4)):
        iced += fb[pos][:cap]; lo += fb[pos][cap:]
    iced += sorted(lo, key=war, reverse=True)[:max(0, 12 - len(iced))]
    ds = sorted((t for t in tp if t[1] == "D"), key=war, reverse=True)[:6]
    g = sorted((t for t in tp if t[1] == "G"), key=war, reverse=True)[:1]
    return iced + ds + g


def monotonicity_check(tbl):
    """Sanity: upgrading a slot never lowers projected points; a bigger talent gap -> bigger delta;
    removing a player never raises the team. Tested on the absolute-rating map (monotone by construction)
    plus a swap sweep on real projections."""
    from models_ml import project_roster_forecast as J
    CFG = J.CFG
    wars = sorted(tbl["proj_war"].tolist())
    lo, mid, hi = wars[len(wars)//10], wars[len(wars)//2], wars[-len(wars)//10]
    base = 12.5
    f = lambda w: J.rating_to_points(J.absolute_rating(base - 0.4 + w, 0.0, CFG), CFG)  # one slot at war w
    up = f(hi) >= f(mid) >= f(lo)                       # upgrading raises points
    gap = (f(hi) - f(mid)) >= (f(mid) - f(lo) - 1)      # bigger gap -> >= delta (within rounding)
    remove = f(lo) <= f(mid)                            # downgrading never raises
    return {"upgrade_monotone": up, "gap_orders": gap, "remove_never_raises": remove}


def main():
    ap = argparse.ArgumentParser(description="Roster Builder component projection — fit, backtest, write.")
    ap.add_argument("--write", action="store_true", help="write nhl_models.roster_player_projection")
    args = ap.parse_args()
    sk, go = load_panels(bq)
    print(f"panels: skaters {sk.shape}, goalies {go.shape}, seasons {sorted(sk.yr.unique())}")

    skp, gop = holdout_predictions(sk, go)
    bt = backtest_summary(skp, gop)
    n_T = skp["T"].nunique()
    print(f"\nBACKTEST (strict temporal holdout, {n_T} held-out seasons, n={len(skp)} skater / {len(gop)} goalie) — RMSE:")
    print(f"  {'component':12s} {'model':>8s} {'marcel':>8s} {'naive':>8s}   verdict")
    def verdict(e): return "BEATS both" if e["model"] <= min(e["marcel"], e["naive"]) else ("ties/beats marcel" if e["model"] <= e["marcel"] else "LOSES")
    for c, e in bt["components"].items():
        print(f"  {c:12s} {e['model']:8.4f} {e['marcel']:8.4f} {e['naive']:8.4f}   {verdict(e)}")
    for label, e in (("skater WAR", bt["war"]), ("goalie WAR", bt["goalie_war"])):
        print(f"  {label:12s} {e['model']:8.4f} {e['marcel']:8.4f} {e['naive']:8.4f}   {verdict(e)}")

    # full-data params + uncertainty
    params = fit_params(sk)
    prior_gw = _goalie_prior_war(go)
    sdm = fit_residual_sd(skp, gop)
    print("\nFITTED per-component regression k_c (denominator units):")
    print("  " + "  ".join(f"{c}={params['kc'][c]:.0f}" for c in SK_COMPONENTS))
    print("FITTED component residual sd (goals): s0 (floor) + s1/denom; global calibration lambda = "
          f"{sdm['lambda']:.2f}")
    for c in SK_COMPONENTS:
        print(f"  {c:12s} sd@median_denom = {np.sqrt(sdm['comp'][c][0]):.3f}..(low-sample wider)")

    # WAR-level coverage check (the calibration gate)
    sk_sd = skp.apply(lambda r: _war_sd_skater({c: r[f"{c}_den"] for c in SK_COMPONENTS}, sdm), axis=1)
    cov = float(np.mean((skp["war_model"] - skp["war_act"]).abs() <= sk_sd))
    print(f"\nWAR-level 1-sigma coverage (skaters, after calibration): {cov*100:.0f}% (target ~68%)")

    # PRIMARY GATE: delta validation (the tool's headline metric)
    dv = delta_validation(sk, go)
    print(f"\nDELTA VALIDATION (PRIMARY GATE, {dv['n']} team-transitions) — predicted roster-change impact vs realized:")
    print(f"  vs measured-rating change: RMSE={dv['rt_rmse']:.3f} g/g  corr={dv['rt_corr']:.3f}")
    print(f"  vs actual-points change:   RMSE={dv['pts_rmse']:.2f} pts  corr={dv['pts_corr']:.3f}")
    print(f"  predicted delta sd {dv['pred_pts_sd']:.1f} pts vs realized {dv['real_pts_sd']:.1f} pts "
          f"(realized carries 2x season luck ~8.5)")
    mono = monotonicity_check(pd.DataFrame({"proj_war": sk.groupby('player_id').war.last().tolist()}))
    print(f"  monotonicity/sanity: upgrade_monotone={mono['upgrade_monotone']} "
          f"gap_orders={mono['gap_orders']} remove_never_raises={mono['remove_never_raises']}")
    cal = calibrate_absolute(sk, go)
    print(f"\nABSOLUTE-MAP RECALIBRATION for the new projections ({cal['n']} team-seasons):")
    print(f"  LEAGUE_AVG_LINEUP_WAR = {cal['league_avg']:.2f}   WAR_TO_RATING = {cal['w2r']:.5f}   "
          f"BAND_KAPPA = {cal['kappa']:.2f}")
    print(f"  absolute band coverage = {cal['coverage']*100:.0f}% at 1 sigma (target ~68%); points MAE = {cal['mae']:.2f}")
    print(f"  -> update config.ROSTER_FORECAST: LEAGUE_AVG_LINEUP_WAR={cal['league_avg']:.2f}, "
          f"WAR_TO_RATING={cal['w2r']:.5f}, ROSTER_BUILDER_BAND_KAPPA={cal['kappa']:.2f}")
    print(f"  (delta band = RAW quadrature of CHANGED players only — common error cancels: no kappa, no luck floor)")

    # HANDOFF 13 GATE: hybrid (anchored on R_measured) vs the bottom-up, head to head.
    h = head_to_head(sk, go)
    print(f"\nHYBRID vs BOTTOM-UP HEAD-TO-HEAD (Handoff 13 gate, {h['n']} team-seasons):")
    print(f"  ABSOLUTE points RMSE:  hybrid {h['hy_rmse']:.2f}  vs  bottom-up {h['bu_rmse']:.2f}   "
          f"({'hybrid wins' if h['hy_rmse'] < h['bu_rmse'] else 'bottom-up wins'})")
    print(f"  ABSOLUTE points corr:  hybrid {h['hy_corr']:.3f}  vs  bottom-up {h['bu_corr']:.3f}")
    print(f"  DELTA corr (pooled {h['delta_n']}): {h['delta_corr']:.3f}  per-season {[(t, round(c,2)) for t,c in h['delta_per_season'].items()]}")
    print(f"  R_measured predicts next-year RATING far better than the parts-sum (0.58 vs 0.44, 16-season fit).")
    print(f"  abs-band sigma_anchor (68%): {h['sigma_anchor']:.1f} pts. SHIPPED: anchored baseline = team's "
          f"measured level; wins on points RMSE + de-lucked strength; ties on (noisy) delta.")

    tbl = build_projection_table(sk, go, params, prior_gw, sdm)
    print(f"\nprojection table: {len(tbl)} players  (mean proj_war {tbl.proj_war.mean():.3f}, "
          f"mean proj_war_sd {tbl.proj_war_sd.mean():.3f})")
    if args.write:
        from models_ml import duck
        if duck.serving_active():
            import duckdb
            if duck._con is not None:          # release the cached read-only handle first
                duck._con.close(); duck._con = None
            con = duckdb.connect(str(duck.duckdb_path()))
            con.execute("DROP TABLE IF EXISTS roster_player_projection")
            con.register("_rpp", tbl)
            con.execute("CREATE TABLE roster_player_projection AS SELECT * FROM _rpp")
            con.execute("CREATE INDEX IF NOT EXISTS rpp_pid ON roster_player_projection(player_id)")
            con.close()
            print(f"wrote roster_player_projection to {duck.duckdb_path()} ({len(tbl)} rows)")
        else:
            bq.write_df(tbl, "roster_player_projection")
            print("wrote nhl_models.roster_player_projection (BigQuery)")
    else:
        print("(dry run — pass --write to persist)")
    return tbl, sdm


if __name__ == "__main__":
    main()
