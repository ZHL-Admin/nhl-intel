"""Stage 3 — the three phase-value fits (deny / suppress / escape) + the rush diagnostic sub-fit.

Reuses the RAPM machinery VERBATIM (models_ml.train_rapm.build_design / cv_alpha / bootstrap_sd —
two-sided sparse ridge, replacement pooling, game-grouped CV, game-resample bootstrap, controls:
score_state / zone / home / b2b / game-time / season FE). The ONLY differences from RAPM are the
target and the weight, which come from the Stage-3 PV design (build_design.py):

  deny     target = episode_starts_nonfo / outside_exposure_sec * 3600   weight = outside_exposure_sec
  suppress target = xg_inzone            / inzone_sec           * 3600   weight = inzone_sec
  escape   target = favorable_ends       / inzone_sec           * 3600   weight = inzone_sec
  deny_rush(diagnostic) target = episode_starts_rush / outside_exposure_sec * 3600  weight = outside_exposure_sec

Each fit is two-sided; the DEFENDING team is the `deff` side, so the component is read off the
centered DEFENCE coefficient `def_c`. Sign convention (PV-D017): deny/suppress SUPPRESS the target
(good defence LOWERS it) -> value = -def_c; escape RAISES the target (a favourable end is the
defender's success) -> value = +def_c. All three end up "higher = better" (methodology §1).

PV-D011: the >= MIN_EXPOSURE_SECONDS floor is applied per fit on the STINT-DIRECTION exposure total
(the row's own weight), never per-episode, so zero-duration goal episodes keep their start (deny) and
their goal xG (suppress). Capture counters (ep_nonfo_zerodur, xg_inzone_zerodur) are carried through.

Report-only here: main() writes NOTHING to BigQuery. It caches the fitted component frames to
artifacts/phase_value/components_<window>.parquet (gitignored) for assemble_phase_value.py, and prints
the wiring-gate (r >= WIRING_GATE_R per target) and defence-coefficient-spread diagnostics.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from models_ml import config
from models_ml import train_rapm as R
from models_ml.phase_value import build_design as BD

CFG = config.PHASE_VALUE_CONFIG
MODEL_VERSION = "phase_value_v1"
MINSEC = CFG["MIN_EXPOSURE_SECONDS"]          # 5 (PV-D002)
WIRING_GATE_R = 0.80                           # hard gate: team-season wiring correlation per target
ARTDIR = "artifacts/phase_value"

# fit name -> (numerator field, exposure field, value sign on the centered defence coef)
FITS = {
    "deny":     ("ep_nonfo",  "outside_sec", -1.0),
    "suppress": ("xg_inzone", "inzone_sec",  -1.0),
    "escape":   ("fav_ends",  "inzone_sec",  +1.0),
}
RUSH_FIT = ("ep_rush", "outside_sec", -1.0)    # diagnostic sub-fit -> deny_rush_coef (event-space, PV-D014)


def _rows_for_fit(dirrows, num_field, expo_field):
    """RAPM-format tuple rows for one fit, applying the PV-D011 stint-direction exposure floor.
    tuple = (game_id, off, deff, target, weight, score_state, zone, home, b2b, season, gt);
    a parallel def_team array is returned for the wiring aggregation."""
    rows, def_teams = [], []
    for d in dirrows:
        e = d[expo_field]
        if e < MINSEC:                          # floor on the stint-direction total, not per-episode
            continue
        target = d[num_field] / e * 3600.0
        weight = e * d["sw"]
        rows.append((d["game_id"], d["off"], d["deff"], target, weight,
                     d["score_state"], d["zone"], d["home"], d["b2b"], d["season"], d["gt"]))
        def_teams.append(d["def_team"])
    return rows, np.array(def_teams, dtype=np.int64)


def _fit(rows, sign, pos):
    """Point fit of one two-sided ridge; return the defence component (sign*centered def_c) plus the
    design bits (kept for the wiring gate and the shared-draw bootstrap). No bootstrap here."""
    X, y, w, games, players, n_players, two_sided = R.build_design(rows, two_sided=True, pos=pos)
    alpha, _ = R.cv_alpha(X, y, w, games)
    m = Ridge(alpha=alpha, solver="lsqr", fit_intercept=True, max_iter=3000)
    m.fit(X, y, sample_weight=w)
    def_c = m.coef_[n_players:2 * n_players]
    def_c = def_c - def_c.mean()
    return dict(players=players, value=sign * def_c, sign=sign, model=m, X=X, y=y, w=w, games=games,
                alpha=alpha, n_players=n_players)


def _shared_bootstrap(fits, kconst, B, seed=7):
    """ONE game-resample bootstrap SHARED across all fits: each draw b samples a single per-game
    multiplier over the union game set and applies it to EVERY fit's weights (same seed, same draw
    sequence). Returns per-fit sd arrays (aligned to each fit's player index) and the composite
    pv_def_g60 sd — the composite priced WITHIN each draw from that draw's deny+suppress coefs
    (§8.1; not quadrature). B refits per fit per window."""
    fd = (kconst["s_out_min_per_60"] / 60.0) * kconst["c_seq_xg_nonfo"] * kconst.get("xg_calibration", 1.0)
    fs = (kconst["s_in_min_per_60"] / 60.0) * kconst.get("xg_calibration", 1.0)
    games_union = np.unique(np.concatenate([f["games"] for f in fits.values()]))
    rng = np.random.default_rng(seed)
    comp_draws = {name: [] for name in fits}          # name -> list of per-draw value arrays
    pv_draws = []                                      # list of per-draw {player_id: pv_def_g60}
    for _ in range(B):
        draw = rng.multinomial(len(games_union), np.full(len(games_union), 1.0 / len(games_union)))
        mult = dict(zip(games_union, draw))
        vb = {}
        for name, f in fits.items():
            wb = f["w"] * np.array([mult[g] for g in f["games"]], dtype="float64")
            coef = R.fit_coefs(f["X"], f["y"], wb, f["alpha"])
            dc = coef[f["n_players"]:2 * f["n_players"]]
            val = f["sign"] * (dc - dc.mean())
            comp_draws[name].append(val)
            vb[name] = dict(zip(f["players"], val))
        dny, sup = vb["deny"], vb["suppress"]
        pv_draws.append({p: fd * dny[p] + fs * sup[p] for p in (dny.keys() & sup.keys())})
    sds = {name: pd.DataFrame({"player_id": fits[name]["players"],
                               f"{name}_sd": np.std(np.array(comp_draws[name]), axis=0)})
           for name in fits}
    pv = pd.DataFrame([(p, np.std([d[p] for d in pv_draws if p in d]))
                       for p in {p for d in pv_draws for p in d}],
                      columns=["player_id", "pv_def_g60_sd"])
    return sds, pv


def _wiring_r(fit, def_teams, seasons_arr):
    """Team-season wiring gate: exposure-weighted actual vs model-predicted target aggregated by
    (defending team, season), correlated across team-seasons (weighted by exposure). r >= gate."""
    pred = fit["model"].predict(fit["X"])
    w = fit["w"]
    d = pd.DataFrame({"team": def_teams, "season": seasons_arr,
                      "yw": fit["y"] * w, "pw": pred * w, "w": w})
    s = d.groupby(["team", "season"], as_index=False)[["yw", "pw", "w"]].sum()
    s = s[s["w"] > 0]
    ay = (s["yw"] / s["w"]).to_numpy()   # exposure-weighted actual team-season mean
    ap = (s["pw"] / s["w"]).to_numpy()   # exposure-weighted predicted team-season mean
    wa = s["w"].to_numpy()
    mp = np.average(ap, weights=wa); my = np.average(ay, weights=wa)
    cov = np.average((ap - mp) * (ay - my), weights=wa)
    sp = np.sqrt(np.average((ap - mp) ** 2, weights=wa))
    sy = np.sqrt(np.average((ay - my) ** 2, weights=wa))
    r = cov / (sp * sy) if sp > 0 and sy > 0 else float("nan")
    return r, len(s)


def fit_window(dirrows, pos, label, bootstrap, kconst):
    """Run all four fits for one window, then ONE shared-draw bootstrap across them (component sds +
    composite pv_def_g60 sd). Returns (frame, diagnostics)."""
    fits, wiring = {}, {}
    for name, (num, expo, sign) in list(FITS.items()) + [("deny_rush", RUSH_FIT)]:
        rows, def_teams = _rows_for_fit(dirrows, num, expo)
        seasons_arr = np.array([r[9] for r in rows])
        fit = _fit(rows, sign, pos)
        fits[name] = fit
        wiring[name] = (_wiring_r(fit, def_teams, seasons_arr), len(rows))

    sds, pv = ({}, None)
    if bootstrap:
        sds, pv = _shared_bootstrap(fits, kconst, bootstrap)

    frame = None
    diags = {}
    for name, fit in fits.items():
        (r_wire, n_ts), n_rows = wiring[name]
        spread = float(np.std(fit["value"]))
        sd_frame = sds.get(name)
        mean_sd = float(sd_frame[f"{name}_sd"].mean()) if sd_frame is not None else float("nan")
        diags[name] = dict(alpha=fit["alpha"], n_rows=n_rows, wiring_r=r_wire, n_team_seasons=n_ts,
                           coef_spread=spread, mean_boot_sd=mean_sd,
                           spread_over_sd=(spread / mean_sd if mean_sd and not np.isnan(mean_sd) else np.nan))
        col = pd.DataFrame({"player_id": fit["players"], name: fit["value"]})
        if sd_frame is not None:
            col = col.merge(sd_frame, on="player_id", how="left")
        else:
            col[f"{name}_sd"] = np.nan
        frame = col if frame is None else frame.merge(col, on="player_id", how="outer")
        print(f"[{label}] {name}: rows={n_rows:,} alpha={fit['alpha']:.0f} "
              f"wiring_r={r_wire:.3f} (n_ts={n_ts}) spread={spread:.4f} mean_sd={mean_sd:.4f}", file=sys.stderr)

    if pv is not None:
        frame = frame.merge(pv, on="player_id", how="left")
    else:
        frame["pv_def_g60_sd"] = np.nan
    frame["season_window"] = label
    frame = frame[frame["player_id"] >= 0].copy()   # drop REPL_F/REPL_D sentinels
    return frame, diags


def _exposures(dirrows):
    """Per-player defence-side exposures + PV-D011 capture counts over the window. Defence-side = the
    player is on the `deff` set; exposure is the ATTACKER's outside/inzone seconds they faced."""
    acc = {}
    for d in dirrows:
        for pid in d["deff"]:
            a = acc.setdefault(pid, dict(def_out_sec=0.0, def_in_sec=0.0, def_ep_nonfo=0.0,
                                         def_ep_nonfo_zerodur=0.0, def_xg_in=0.0, def_xg_in_zerodur=0.0))
            a["def_out_sec"] += d["outside_sec"]; a["def_in_sec"] += d["inzone_sec"]
            a["def_ep_nonfo"] += d["ep_nonfo"]; a["def_ep_nonfo_zerodur"] += d["ep_nonfo_zerodur"]
            a["def_xg_in"] += d["xg_inzone"]; a["def_xg_in_zerodur"] += d["xg_inzone_zerodur"]
    return pd.DataFrame([dict(player_id=k, **v) for k, v in acc.items()])


def _b2b(seasons):
    """RAPM back_to_back, guarded against null team/game ids in stg_games (present for some
    non-regular rows). Same (game_id, team_id) -> 1-if-played-yesterday map."""
    from models_ml import bq
    games = bq.query_df(f"""
        select game_id, game_date, home_team_id, away_team_id
        from `{bq.project()}.nhl_staging.stg_games`
        where season in ({", ".join(f"'{s}'" for s in seasons)})
          and substr(cast(game_id as string), 5, 2) in ('02', '03')
          and home_team_id is not null and away_team_id is not null
    """)
    games["game_date"] = pd.to_datetime(games["game_date"])
    long = pd.concat([
        games[["game_id", "game_date", "home_team_id"]].rename(columns={"home_team_id": "team_id"}),
        games[["game_id", "game_date", "away_team_id"]].rename(columns={"away_team_id": "team_id"}),
    ]).dropna(subset=["game_id", "team_id"])
    long = long.sort_values(["team_id", "game_date"])
    long["prev"] = long.groupby("team_id")["game_date"].shift(1)
    long["b2b"] = ((long["game_date"] - long["prev"]).dt.days == 1).astype("float64")
    return {(int(r.game_id), int(r.team_id)): r.b2b for r in long.itertuples()}


def _windows():
    win = R.SINGLE_SEASONS[-3:]
    yield win, f"{win[0]}_{win[-1]}", dict(zip(win, R.WINDOW_WEIGHTS))
    for s in R.SINGLE_SEASONS:
        yield [s], s, None


def _capture_totals(df, label):
    """Per-EPISODE (k=1) capture totals from the design, for overlap-report (c). These are the true
    denominators — NOT the per-defender ×5 aggregation (PV-D019). Direction-summed home+away = each
    episode once (attacker is home XOR away)."""
    return dict(window=label,
                ep_nonfo=float((df["home_ep_nonfo"] + df["away_ep_nonfo"]).sum()),
                ep_nonfo_zerodur=float((df["home_ep_nonfo_zerodur"] + df["away_ep_nonfo_zerodur"]).sum()),
                xg_inzone=float((df["home_xg_inzone"] + df["away_xg_inzone"]).sum()),
                xg_inzone_zerodur=float((df["home_xg_inzone_zerodur"] + df["away_xg_inzone_zerodur"]).sum()))


def _constants():
    from models_ml import bq
    d = bq.query_df(f"select constant_name, value from `{bq.project()}.nhl_models.phase_league_constants` "
                    f"where model_version='{MODEL_VERSION}'", bq.client())
    return {r.constant_name: float(r.value) for r in d.itertuples()}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None, help="fit one single season (quick test)")
    ap.add_argument("--no-bootstrap", action="store_true")
    ap.add_argument("--bootstrap", type=int, default=100)
    args = ap.parse_args()
    B = 0 if args.no_bootstrap else args.bootstrap
    os.makedirs(ARTDIR, exist_ok=True)

    if args.season:
        windows = [([args.season], args.season, None)]
        b2b = _b2b([args.season])
    else:
        windows = list(_windows())
        b2b = _b2b(R.SINGLE_SEASONS)

    kconst = _constants()
    all_diag = {}
    captures = []
    for seasons, label, sw in windows:
        single_B = min(B, 40) if len(seasons) == 1 else B    # spec: 100 headline window, 40 singles (PV-D019)
        print(f"[{label}] pulling PV design for {seasons} (B={single_B}) ...", file=sys.stderr)
        df = BD.pull(seasons)                       # ONE pull per window, reused by fits + exposures
        dirrows = BD.expand_rows(df, b2b, sw)
        print(f"[{label}] {len(df):,} segments -> {len(dirrows):,} direction-rows", file=sys.stderr)
        pos = R.positions(seasons)
        frame, diags = fit_window(dirrows, pos, label, single_B, kconst)
        expo = _exposures(dirrows)
        frame = frame.merge(expo, on="player_id", how="left")
        frame.to_parquet(f"{ARTDIR}/components_{label}.parquet", index=False)
        captures.append(_capture_totals(df, label))
        all_diag[label] = diags
    pd.DataFrame(captures).to_parquet(f"{ARTDIR}/capture_totals.parquet", index=False)

    # boundary deliverables (d) wiring gate + (e) coef spread vs bootstrap sd, per fit per window
    print("\n=== (d) WIRING GATE  &  (e) DEFENCE-COEF SPREAD vs MEAN BOOTSTRAP SD ===")
    print(f"{'window':<20} {'fit':<10} {'wiring_r':>9} {'gate':>5} {'spread':>8} {'mean_sd':>8} {'spread/sd':>9}")
    for label, diags in all_diag.items():
        for name, dd in diags.items():
            gate = "PASS" if (not np.isnan(dd["wiring_r"]) and dd["wiring_r"] >= WIRING_GATE_R) else "FAIL"
            print(f"{label:<20} {name:<10} {dd['wiring_r']:>9.3f} {gate:>5} "
                  f"{dd['coef_spread']:>8.4f} {dd['mean_boot_sd']:>8.4f} {dd['spread_over_sd']:>9.2f}")
    pd.DataFrame([dict(window=l, fit=n, **d) for l, dd in all_diag.items() for n, d in dd.items()]) \
        .to_parquet(f"{ARTDIR}/diagnostics.parquet", index=False)
    print(f"\nCached component frames + diagnostics to {ARTDIR}/ (nothing written to BigQuery).")


if __name__ == "__main__":
    main()
