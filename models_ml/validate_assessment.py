"""Player-assessment validation harness (Workstream 0, spec 5.2).

Reads only (nhl_models.player_gar / goalie_gar, nhl_mart.mart_player_onice via the serving
layer); prints a report to stdout and appends the measured T1 table into
docs/methodology/player-assessment.md. Runs against the local DuckDB serving file by default
(SERVING_BACKEND=duckdb), so it needs no BigQuery credentials.

Tasks (preregistered in docs/methodology/assessment-prereg.md — commit that BEFORE scoring):
  T1 (primary, GATED)  next-season WAR: naive / marcel / C1 / C2 / C3, RMSE+MAE+Spearman.
  T2 (reported)        next-season on-ice 5v5 xGF% from as-of-S assessed WAR vs marcel.
  T4 (reported)        tier + confidence label distribution and tier persistence for the
                       shipped estimator (tier ladder + cuts from spec 6.2).
Ship gate G1 + candidate selection: see SELECTION_RULE below (verbatim from the prereg).

Run:  make assessment-validate      (python -m models_ml.validate_assessment)
"""

from __future__ import annotations

import os
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

os.environ.setdefault("SERVING_BACKEND", "duckdb")   # read the local serving file by default

from models_ml import bq, config, baselines, value_lens as VL

EVAL_SEASONS = ["2024-25", "2025-26"]                           # v1 gate + C4 eval guard
NEW_NONFLAGGED_TARGETS = ["2018-19", "2022-23", "2023-24"]      # prereg v2.5(a)
COVID_YEARS = {2019, 2020}                                      # S/S+1 == 2019-20 / 2020-21 (v2.4)
SKATER_QUAL_MIN = config.GAR_CONFIG["MIN_TOI_5V5_FOR_RANKING"]   # qualified in S
SKATER_NEXT_MIN = 400.0                                          # min 5v5 min in S+1
GOALIE_MIN_GAMES = config.GOALIE_GAR_CONFIG["MIN_GAMES_FOR_RANKING"]
TIE_RMSE = 0.005
METHODS = ["naive", "marcel"] + VL.CANDIDATES                    # includes c4_r_speed
DOC = Path(__file__).resolve().parent.parent / "docs" / "methodology" / "player-assessment.md"

# Tier ladder + confidence cuts (spec 6.2). Duplicated here for the M0 T4 diagnostic ONLY; M1
# centralizes these in config.ASSESSMENT + compute_assessment. Skaters (F/D).
TIER_RANKS = {
    "F": [("elite", 18), ("first_line", 96), ("second_line", 192),
          ("third_line", 288), ("fourth_line", 384), ("fringe", None)],
    "D": [("elite", 12), ("number_one", 32), ("top_pair", 64),
          ("second_pair", 128), ("third_pair", 192), ("fringe", None)],
}
CONFIDENCE_CUTS = {"high": 0.55, "medium": 0.35}

SELECTION_RULE = (
    "Ship the candidate with the lowest mean skater T1 RMSE across both eval seasons, provided "
    "it beats Marcel in both. Ties within 0.005 RMSE prefer C2 -> C3 -> C1. If no candidate "
    "beats Marcel in both seasons, gate G1 fires and Marcel ships as the point estimate."
)
_PREF = {"c2_roster_player": 0, "c3_blended": 1, "c1_r_shrink": 2}


# --------------------------------------------------------------------------- metrics
def _rmse(e):
    return float(np.sqrt(np.mean(np.square(e)))) if len(e) else float("nan")


def _mae(e):
    return float(np.mean(np.abs(e))) if len(e) else float("nan")


def _spearman(a, b):
    if len(a) < 3:
        return float("nan")
    return float(pd.Series(a).corr(pd.Series(b), method="spearman"))


# --------------------------------------------------------------------------- data
def load_panels():
    gar = bq.query_df("select * from nhl_models.player_gar")
    ggar = bq.query_df("select * from nhl_models.goalie_gar")
    return baselines.skater_panel(gar), baselines.goalie_panel(ggar)


def _onice_next():
    """{(season, player_id) -> TOI-weighted on-ice 5v5 xGF%} for T2."""
    df = bq.query_df("select season, player_id, toi_5v5_sec, on_ice_xgf_pct "
                     "from nhl_mart.mart_player_onice where toi_5v5_sec > 0")
    df["w"] = df["toi_5v5_sec"]
    df["wx"] = df["w"] * df["on_ice_xgf_pct"]
    g = df.groupby(["season", "player_id"]).agg(wx=("wx", "sum"), w=("w", "sum")).reset_index()
    g["xgf_pct"] = g["wx"] / g["w"]
    return {(r["season"], int(r["player_id"])): float(r["xgf_pct"]) for _, r in g.iterrows()}


# --------------------------------------------------------------------------- T1
def _skater_rates(panel, s_yr, s1_label):
    """Every method's as-of-S WAR rate, keyed by player_id."""
    s_rows = panel[panel["yr"] == s_yr].set_index("player_id")
    rates = {"naive": {int(i): float(r["war_rate"]) for i, r in s_rows.iterrows()
                       if r["toi_5v5"] > 0 and np.isfinite(r["war_rate"])}}
    mar = baselines.marcel_skaters(panel, s1_label)
    rates["marcel"] = {int(i): float(v) for i, v in mar["marcel_rate"].items()}
    for cand in VL.CANDIDATES:
        rates[cand] = {pid: rt for pid, (rt, _sd) in VL.candidate_rates(cand, panel, s_yr).items()}
    return rates


def _score_target(panel, s1_label):
    """One walk-forward transition S->S+1: every method uses only data before S+1 (spec v2.3)."""
    s1_yr = baselines.season_year(s1_label)
    s_yr = s1_yr - 1
    s_rows = panel[panel["yr"] == s_yr].set_index("player_id")
    s1_rows = panel[panel["yr"] == s1_yr].set_index("player_id")
    if s_rows.empty or s1_rows.empty:
        return None
    universe = [int(i) for i in s_rows.index
                if s_rows.loc[i, "toi_5v5"] >= SKATER_QUAL_MIN
                and i in s1_rows.index and s1_rows.loc[i, "toi_5v5"] >= SKATER_NEXT_MIN]
    if len(universe) < 20:
        return None
    rates = _skater_rates(panel, s_yr, s1_label)
    common = [p for p in universe if all(p in rates[m] for m in METHODS)]
    if len(common) < 20:
        return None
    realized = {p: (float(s1_rows.loc[p, "war"]), float(s1_rows.loc[p, "toi_5v5"]) / 60.0)
                for p in common}
    res = {}
    for m in METHODS:
        pred = np.array([rates[m][p] * realized[p][1] for p in common])
        act = np.array([realized[p][0] for p in common])
        res[m] = {"rmse": _rmse(pred - act), "mae": _mae(pred - act),
                  "spearman": _spearman(pred, act), "n": len(common)}
    covid = (s_yr in COVID_YEARS) or (s1_yr in COVID_YEARS)
    return {"covid": covid, "methods": res}


def t1(panel):
    """Score every walk-forward transition the panel supports. {s1_label: {covid, methods}}."""
    yrs = sorted(int(y) for y in panel["yr"].unique())
    out = {}
    for s1_yr in yrs:
        if (s1_yr - 1) not in yrs:
            continue
        lab = baselines.season_label(s1_yr)
        r = _score_target(panel, lab)
        if r:
            out[lab] = r
    return out


def select(per_target):
    """v1 gate G1 on the eval seasons (candidates C1/C2/C3 only). Returns (winner, reason)."""
    if not all(s in per_target for s in EVAL_SEASONS):
        return "marcel", "Eval seasons missing; cannot run v1 gate."
    marcel = {s: per_target[s]["methods"]["marcel"]["rmse"] for s in EVAL_SEASONS}
    eligible = []
    for c in VL.V1_TRIO:
        beats = all(per_target[s]["methods"][c]["rmse"] < marcel[s] for s in EVAL_SEASONS)
        mean_rmse = float(np.mean([per_target[s]["methods"][c]["rmse"] for s in EVAL_SEASONS]))
        if beats:
            eligible.append((c, mean_rmse))
    if not eligible:
        return "marcel", "No candidate beat Marcel in both eval seasons -> G1 fires; Marcel ships."
    best = min(m for _, m in eligible)
    tied = sorted([c for c, m in eligible if m - best <= TIE_RMSE], key=lambda c: _PREF[c])
    winner = tied[0]
    note = "tie-break C2>C3>C1" if len(tied) > 1 else "lowest mean RMSE, beats Marcel in both"
    return winner, f"{winner} wins ({note}); eval mean RMSE {dict(eligible)[winner]:.4f}."


def c4_promotion(per_target, incumbent):
    """prereg v2.5: C4 displaces C2 only if (a) it beats C2 on mean RMSE across the NEW non-flagged
    targets, AND (b) it is not worse than C2 by >0.005 in either eval season. Ties keep C2."""
    if incumbent != "c2_roster_player":
        return incumbent, f"Incumbent is {incumbent}, not C2 -> C4 promotion rule N/A."
    missing = [t for t in NEW_NONFLAGGED_TARGETS if t not in per_target]
    if missing:
        have = [t for t in NEW_NONFLAGGED_TARGETS if t in per_target]
        return incumbent, (f"C4 promotion UNDECIDED -> missing new targets {missing} (need 2015-16 "
                           f"backfill). Scored new targets so far: {have or 'none'}.")
    rmse = lambda t, m: per_target[t]["methods"][m]["rmse"]
    new = [t for t in NEW_NONFLAGGED_TARGETS if not per_target[t]["covid"]]
    c4m = float(np.mean([rmse(t, "c4_r_speed") for t in new]))
    c2m = float(np.mean([rmse(t, "c2_roster_player") for t in new]))
    beats = (c2m - c4m) > TIE_RMSE
    guard = all(rmse(s, "c4_r_speed") - rmse(s, "c2_roster_player") <= TIE_RMSE for s in EVAL_SEASONS)
    if beats and guard:
        return "c4_r_speed", f"C4 PROMOTED (new-target mean {c4m:.4f} < C2 {c2m:.4f}; eval guard holds)."
    why = "does not beat C2 by >0.005" if not beats else "fails eval guard"
    return incumbent, f"C4 NOT promoted ({why}; new-target C4 {c4m:.4f} vs C2 {c2m:.4f}). C2 ships."


# --------------------------------------------------------------------------- T2
def t2(panel, onice):
    rows = {}
    for s1 in EVAL_SEASONS:
        s_yr = baselines.season_year(s1) - 1
        rates = _skater_rates(panel, s_yr, s1)
        for m in ["marcel"] + VL.CANDIDATES:
            pairs = [(rates[m][p], onice[(s1, p)]) for p in rates[m] if (s1, p) in onice]
            rows.setdefault(m, []).extend(pairs)
    return {m: {"spearman": _spearman([a for a, _ in v], [b for _, b in v]), "n": len(v)}
            for m, v in rows.items()}


# --------------------------------------------------------------------------- T4
def _assess_levels(panel, estimator, s_yr):
    """{player_id -> (assessed_war_level, war_sd, pos_group)} for one season, using data as of S."""
    s_rows = panel[panel["yr"] == s_yr].set_index("player_id")
    if estimator == "marcel":
        rate = {int(i): float(v) for i, v in
                baselines.marcel_skaters(panel, baselines.season_label(s_yr + 1))["marcel_rate"].items()}
        sd_rate = {}
    else:
        cr = VL.candidate_rates(estimator, panel, s_yr)
        rate = {p: rt for p, (rt, _sd) in cr.items()}
        sd_rate = {p: sd for p, (_rt, sd) in cr.items()}
    out = {}
    for i, r in s_rows.iterrows():
        p = int(i)
        if p not in rate or r["toi_5v5"] <= 0:
            continue
        h = float(r["toi_5v5"]) / 60.0
        level = rate[p] * h
        sd = (sd_rate[p] * h) if sd_rate.get(p) else float(r["gar_sd"]) / VL.GPW
        out[p] = (level, max(sd, 1e-6), r["pos_group"])
    return out


def _tier_bands(levels_pg):
    """Ordered [(tier, war_low, war_high)] high->low for one pos-group pool (list of war levels)."""
    wars = sorted(levels_pg, reverse=True)
    n = len(wars)
    ladder = TIER_RANKS["F"] if _tier_bands.pg == "F" else TIER_RANKS["D"]
    bounds = []
    for _tier, ceil in ladder:
        if ceil is None or ceil >= n:
            bounds.append(None)
        else:
            bounds.append((wars[ceil - 1] + wars[ceil]) / 2.0)   # midpoint rank ceil / ceil+1
    bands = []
    hi = float("inf")
    for (tier, _ceil), b in zip(ladder, bounds):
        lo = b if b is not None else float("-inf")
        bands.append((tier, lo, hi))
        hi = lo if b is not None else hi
    return bands


_tier_bands.pg = "F"


def _tier_of(war, bands):
    for tier, lo, hi in bands:
        if lo <= war < hi or (hi == float("inf") and war >= lo):
            return tier
    return bands[-1][0]


def t4(panel, estimator):
    """Distribution of confidence labels per pos-group/season + tier persistence S->S+1."""
    seasons = sorted(panel["yr"].unique())
    assess = {y: _assess_levels(panel, estimator, y) for y in seasons}
    # tier + confidence per (season, player)
    label = {}   # (y, pid) -> (tier, conf_label, within_one_tiers set)
    dist = {}    # (y, pg) -> Counter of conf_label
    for y in seasons:
        for pg in ("F", "D"):
            pool = {p: v for p, v in assess[y].items() if v[2] == pg}
            if len(pool) < 5:
                continue
            _tier_bands.pg = pg
            bands = _tier_bands([v[0] for v in pool.values()])
            order = [t for t, _lo, _hi in bands]
            for p, (mu, sd, _pg) in pool.items():
                probs = {}
                nd = NormalDist(mu, sd)
                for tier, lo, hi in bands:
                    probs[tier] = ((1.0 if hi == float("inf") else nd.cdf(hi))
                                   - (0.0 if lo == float("-inf") else nd.cdf(lo)))
                tier = _tier_of(mu, bands)
                conf = probs[tier]
                cl = "high" if conf >= CONFIDENCE_CUTS["high"] else (
                    "medium" if conf >= CONFIDENCE_CUTS["medium"] else "low")
                idx = order.index(tier)
                neigh = {order[j] for j in (idx - 1, idx, idx + 1) if 0 <= j < len(order)}
                label[(y, p)] = (tier, cl, neigh)
                dist.setdefault((y, pg), {}).setdefault(cl, 0)
                dist[(y, pg)][cl] += 1
    # persistence among high-confidence labels
    persist = {}
    for y in seasons[:-1]:
        hi = [(p, lab) for (yy, p), lab in label.items() if yy == y and lab[1] == "high"]
        same = one = tot = 0
        for p, (tier, _cl, _neigh) in hi:
            if (y + 1, p) in label:
                tot += 1
                t2_, _c2, _n2 = label[(y + 1, p)]
                same += int(t2_ == tier)
                one += int(t2_ in _neigh)
        if tot:
            persist[baselines.season_label(y)] = {"n": tot, "same": same / tot, "within_one": one / tot}
    return dist, persist


# --------------------------------------------------------------------------- T5 tier-bucket bias
def t5(panel):
    """Prereg v3: bucket skaters by the as-of-S C2 tier (walk-forward), report mean SIGNED error
    (predicted - realized S+1 WAR) per bucket, per F/D, for C2 and Marcel. Headline = non-COVID."""
    from models_ml import compute_assessment as CA
    T5_METHODS = ["c2_roster_player", "marcel"]
    acc = {}   # (pg, tier, method) -> {"hd": [err...], "flag": [err...]}
    yrs = sorted(int(y) for y in panel["yr"].unique())
    for s1_yr in yrs:
        if (s1_yr - 1) not in yrs:
            continue
        s_yr = s1_yr - 1
        s1_label = baselines.season_label(s1_yr)
        s_rows = panel[panel["yr"] == s_yr].set_index("player_id")
        s1_rows = panel[panel["yr"] == s1_yr].set_index("player_id")
        universe = [int(i) for i in s_rows.index
                    if s_rows.loc[i, "toi_5v5"] >= SKATER_QUAL_MIN
                    and i in s1_rows.index and s1_rows.loc[i, "toi_5v5"] >= SKATER_NEXT_MIN]
        if len(universe) < 20:
            continue
        covid = (s_yr in COVID_YEARS) or (s1_yr in COVID_YEARS)
        rates = _skater_rates(panel, s_yr, s1_label)
        # bucket = C2 tier at S (leak-free: data through S only)
        levels = _assess_levels(panel, "c2_roster_player", s_yr)
        bucket = {}
        for pg in ("F", "D"):
            pool = {p: v for p, v in levels.items() if v[2] == pg}
            if len(pool) < 5:
                continue
            bands, _m = CA._tier_bands([v[0] for v in pool.values()], pg, len(pool))
            for p, (mu, _sd, _pg) in pool.items():
                bucket[p] = (pg, CA._tier_of(mu, bands))
        for p in universe:
            if p not in bucket:
                continue
            pg, tier = bucket[p]
            war_s1 = float(s1_rows.loc[p, "war"]); toi_h = float(s1_rows.loc[p, "toi_5v5"]) / 60.0
            for m in T5_METHODS:
                if p in rates[m]:
                    err = rates[m][p] * toi_h - war_s1
                    d = acc.setdefault((pg, tier, m), {"hd": [], "flag": []})
                    d["flag" if covid else "hd"].append(err)
    return acc


def _fmt_t5(acc):
    from models_ml import compute_assessment as CA
    lines = []
    for pg in ("F", "D"):
        order = [t for t, _c in CA.CFG["TIER_RANKS"][pg]]
        lines.append(f"  --- {pg} (mean signed error = predicted - realized S+1 WAR; + = over-predicts) ---")
        lines.append(f"    {'bucket':14s} {'C2 err':>8s} {'Marcel err':>11s} {'n':>5s}")
        for tier in order:
            hd_c2 = acc.get((pg, tier, "c2_roster_player"), {}).get("hd", [])
            hd_ma = acc.get((pg, tier, "marcel"), {}).get("hd", [])
            if not hd_c2:
                continue
            lines.append(f"    {tier:14s} {np.mean(hd_c2):+8.3f} {np.mean(hd_ma):+11.3f} {len(hd_c2):>5d}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- goalies (report only)
def goalie_t1(gpanel):
    per = {}
    for s1 in EVAL_SEASONS:
        s1_yr = baselines.season_year(s1)
        s_yr = s1_yr - 1
        s_rows = gpanel[gpanel["yr"] == s_yr].set_index("goalie_id")
        s1_rows = gpanel[gpanel["yr"] == s1_yr].set_index("goalie_id")
        uni = [int(i) for i in s_rows.index
               if s_rows.loc[i, "games_played"] >= GOALIE_MIN_GAMES
               and i in s1_rows.index and s1_rows.loc[i, "games_played"] >= GOALIE_MIN_GAMES]
        mar = baselines.marcel_goalies(gpanel, s1)
        rates = {
            "naive": {int(i): float(s_rows.loc[i, "war_rate"]) for i in uni
                      if s_rows.loc[i, "shots_total"] > 0},
            "marcel": {int(i): float(mar.loc[i, "marcel_rate"]) for i in uni if i in mar.index},
            "goalie_gar": {int(i): float(s_rows.loc[i, "war_rate"]) for i in uni
                           if s_rows.loc[i, "shots_total"] > 0},   # already reliability-shrunk
        }
        common = [p for p in uni if all(p in rates[m] for m in rates)]
        real = {p: (float(s1_rows.loc[p, "war"]), float(s1_rows.loc[p, "shots_total"])) for p in common}
        res = {}
        for m in rates:
            pred = np.array([rates[m][p] * real[p][1] for p in common])
            act = np.array([real[p][0] for p in common])
            res[m] = {"rmse": _rmse(pred - act), "mae": _mae(pred - act), "n": len(common)}
        per[s1] = res
    return per


# --------------------------------------------------------------------------- report
def _fmt_t1(per_target):
    """Methods x transitions RMSE table; COVID transitions flagged with * (excluded from decisions)."""
    targets = list(per_target.keys())
    hdr = f"{'method (RMSE)':16s} " + " ".join(
        f"{(t + '*' if per_target[t]['covid'] else t):>10s}" for t in targets)
    lines = [hdr]
    for m in METHODS:
        lines.append(f"{m:16s} " + " ".join(
            f"{per_target[t]['methods'][m]['rmse']:10.4f}" for t in targets))
    lines.append(f"{'n (common)':16s} " + " ".join(
        f"{per_target[t]['methods'][METHODS[0]]['n']:10d}" for t in targets))
    lines.append("(* = COVID-flagged transition, excluded from headline/decision metrics)")
    return "\n".join(lines)


def refresh_r_values(panel):
    """INFORMATIONAL r refresh over available history (frozen GAR_STABILITY_YOY is NOT changed).
    Proxies from player_gar: ev_offense rate and finishing residual rate (RAPM off rate needs
    player_impact and is reported by validate_gar, not here)."""
    q = panel[panel["toi_5v5"] >= SKATER_QUAL_MIN].copy()
    h = q["toi_5v5"] / 60.0
    q["ev_off_r"] = q["ev_offense"] / h
    q["fin_r"] = (q["goals"] - q["ixg"]) / h
    yrs = sorted(int(y) for y in q["yr"].unique())

    def yoy(col):
        cs = []
        for a, b in zip(yrs, yrs[1:]):
            if b != a + 1:
                continue
            ja = q[q["yr"] == a].set_index("player_id")[col]
            jb = q[q["yr"] == b].set_index("player_id")[col]
            j = pd.concat([ja, jb], axis=1).dropna()
            if len(j) > 30:
                cs.append(j.iloc[:, 0].corr(j.iloc[:, 1]))
        return float(np.mean(cs)) if cs else float("nan")

    return {"ev_offense_rate": yoy("ev_off_r"), "finishing_residual": yoy("fin_r"),
            "seasons": [baselines.season_label(y) for y in yrs]}


_T1_HEADING = "## T1 next-season WAR (assessment-validate)"


def _append_doc(per_target, shipped, gate_reason, promo_reason):
    DOC.parent.mkdir(parents=True, exist_ok=True)
    header = "# Player Assessment — Methodology\n\n(Model metrics below are appended by " \
             "`models_ml/validate_assessment.py`.)\n"
    base = DOC.read_text() if DOC.exists() else header
    base = base.split("\n" + _T1_HEADING)[0].rstrip()   # idempotent: drop a prior T1 section
    block = ["", "", _T1_HEADING, "",
             "```", _fmt_t1(per_target), "```",
             f"\n**v1 gate G1 (eval seasons):** {gate_reason}",
             f"\n**C4 promotion (prereg v2.5):** {promo_reason}",
             f"\n**point_estimator = `{shipped}`**\n"]
    DOC.write_text(base + "\n" + "\n".join(block))


def main():
    spanel, gpanel = load_panels()
    print(f"panels: skaters {spanel.shape}, goalies {gpanel.shape}, "
          f"seasons {sorted(spanel['yr'].unique())}")

    print("\n=== T1 (PRIMARY, GATED) — next-season WAR, rate x realized S+1 TOI, all transitions ===")
    per_target = t1(spanel)
    print(_fmt_t1(per_target))
    winner, gate_reason = select(per_target)
    shipped, promo_reason = c4_promotion(per_target, winner)
    print(f"\nv1 GATE G1 (eval): {gate_reason}")
    print(f"C4 PROMOTION (v2.5): {promo_reason}")
    print(f"point_estimator = {shipped}")

    print("\n=== goalie T1 (report only) — rate x realized S+1 shots ===")
    for s1, res in goalie_t1(gpanel).items():
        cells = "  ".join(f"{m} RMSE {r['rmse']:.3f} MAE {r['mae']:.3f}" for m, r in res.items())
        print(f"  {s1} (n={list(res.values())[0]['n']}): {cells}")

    print("\n=== T2 (reported) — Spearman(as-of-S assessed WAR rate, next-season on-ice xGF%) ===")
    try:
        for m, r in t2(spanel, _onice_next()).items():
            print(f"  {m:16s} rho {r['spearman']:.3f}  (n={r['n']})")
    except Exception as e:
        print(f"  T2 skipped: {e}")

    print(f"\n=== T4 (reported) — tier/confidence for shipped estimator ({shipped}) ===")
    dist, persist = t4(spanel, shipped)
    eval_yrs = {baselines.season_year(s) for s in EVAL_SEASONS}
    for (y, pg), c in sorted(dist.items()):
        if y in eval_yrs:
            tot = sum(c.values())
            print(f"  {baselines.season_label(y)} {pg}: " +
                  ", ".join(f"{k} {v} ({v/tot:.0%})" for k, v in sorted(c.items())))
    print("  tier persistence (high-confidence at S -> S+1):")
    for s, r in persist.items():
        print(f"    {s}->next: n={r['n']}  same-tier {r['same']:.0%}  within-one {r['within_one']:.0%}")

    print("\n=== T5 (reported, prereg v3) — mean signed error by as-of-S C2 tier bucket ===")
    acc = t5(spanel)
    print(_fmt_t5(acc))
    flagged = {k: v for k, v in acc.items() if v["flag"]}
    if flagged:
        n_flag = sum(len(v["flag"]) for v in flagged.values())
        print(f"  (COVID-flagged sensitivity set: {n_flag} player-transitions across buckets, "
              f"excluded from the headline above)")

    print("\n=== r-value refresh (INFORMATIONAL; frozen GAR_STABILITY_YOY unchanged) ===")
    rr = refresh_r_values(spanel)
    print(f"  seasons: {rr['seasons']}")
    print(f"  ev_offense rate YoY r = {rr['ev_offense_rate']:.3f}  "
          f"(shipped production_r {config.GAR_STABILITY_YOY['production_r']})")
    print(f"  finishing residual YoY r = {rr['finishing_residual']:.3f}  "
          f"(shipped finishing_r {config.GAR_STABILITY_YOY['finishing_r']})")

    _append_doc(per_target, shipped, gate_reason, promo_reason)
    print(f"\nappended T1 table to {DOC}")


if __name__ == "__main__":
    main()
