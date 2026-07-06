"""Player Assessment (Layer 1 spine): tier + confidence + role, one row per (player, window).

The page-level "how good is he" verdict over the value lenses. The point estimate for skaters
comes from the bakeoff-selected estimator (config.ASSESSMENT["POINT_ESTIMATOR"], swappable via
value_lens WITHOUT any schema change); goalies carry goalie_gar's already-shrunk value through.
Tiers are league job-count RANK ceilings within a position group + window (spec 6.2). Shrinkage
moves the POINT; the band stays sampling uncertainty (war_sd = gar_sd / GOALS_PER_WIN).

READS ONLY: nhl_models.player_gar, goalie_gar, player_archetypes, player_radar. Writes
nhl_models.player_assessment (DuckDB serving file when SERVING_BACKEND=duckdb, else BigQuery),
append/replace of the whole table (a derived summary — it carries no rows other tables lack).

Run:  python -m models_ml.compute_assessment [--dry-run]   (make assessment)
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from statistics import NormalDist

import numpy as np
import pandas as pd

from models_ml import bq, config, baselines, value_lens as VL

CFG = config.ASSESSMENT
GPW = config.GAR_CONFIG["GOALS_PER_WIN"]
SK_FLOOR = config.GAR_CONFIG["MIN_TOI_5V5_FOR_RANKING"]
G_FLOOR = config.GOALIE_GAR_CONFIG["MIN_GAMES_FOR_RANKING"]
MODEL_VERSION = CFG["MODEL_VERSION"]


# --------------------------------------------------------------------------- helpers
def _end_year(window: str) -> int:
    end = window.split("_")[1] if "_" in window else window
    return int(end[:4])


def _window_years(window: str) -> list[int]:
    if "_" in window:
        a, b = window.split("_")
        return list(range(int(a[:4]), int(b[:4]) + 1))
    return [int(window[:4])]


def _pos_group(position: str) -> str:
    return "G" if position == "G" else ("D" if position == "D" else "F")


def _dependence_map(wowy: pd.DataFrame, windows: list[str]) -> dict:
    """{(player_id, season_window) -> dependence fields} from mart_player_wowy (spec 7.3). D17: only
    partners with toi_together_sec >= 3000 across the window count. dependence_index = TOI-weighted
    mean of `together_minus_focal_alone` (positive = better with help). top_partner_toi_sec is
    returned so the caller can divide by the focal's window 5v5 TOI for the share."""
    if wowy is None or wowy.empty:
        return {}
    w = wowy.copy()
    w["yr"] = w["season"].str[:4].astype(int)
    w["toi"] = pd.to_numeric(w["toi_together_sec"], errors="coerce").fillna(0.0)
    w["tmfa"] = pd.to_numeric(w["together_minus_focal_alone"], errors="coerce").fillna(0.0)
    w["wtmfa"] = w["toi"] * w["tmfa"]
    out = {}
    for win in windows:
        yrs = set(_window_years(win))
        sub = w[w["yr"].isin(yrs)]
        if sub.empty:
            continue
        g = sub.groupby(["player_id", "partner_id"]).agg(
            toi=("toi", "sum"), wtmfa=("wtmfa", "sum")).reset_index()
        g = g[g["toi"] >= 3000.0]                              # D17 small-sample floor
        if g.empty:
            continue
        for pid, pg in g.groupby("player_id"):
            top = pg.loc[pg["toi"].idxmax()]
            tot = float(pg["toi"].sum())
            out[(int(pid), win)] = {
                "top_partner_id": int(top["partner_id"]),
                "top_partner_toi_sec": float(top["toi"]),
                "dependence_index": round(float(pg["wtmfa"].sum() / tot), 4) if tot > 0 else None,
                "dependence_n_partners": int(len(pg)),
            }
    return out


def _tier_bands(wars: list[float], pos_group: str, pool_size: int):
    """Ordered [(tier, lo, hi)] high->low, plus tier_mode. Rank ceilings when the pool is deep
    enough, else percentile-equivalent cuts against the reference pool (spec 6.2)."""
    ladder = CFG["TIER_RANKS"][pos_group]
    deepest = max((c for _t, c in ladder if c is not None), default=0)
    wars_sorted = sorted(wars, reverse=True)
    n = len(wars_sorted)
    mode = "rank"
    bounds = []
    if pool_size >= deepest:
        for _tier, ceil in ladder:
            bounds.append(None if (ceil is None or ceil >= n)
                          else (wars_sorted[ceil - 1] + wars_sorted[ceil]) / 2.0)
    else:
        mode = "percentile_fallback"
        ref = CFG["TIER_REFERENCE_POOL"][pos_group]
        arr = np.array(wars_sorted)
        for _tier, ceil in ladder:
            if ceil is None:
                bounds.append(None)
            else:
                q = 1.0 - min(ceil / ref, 1.0)          # ceil-th best -> upper-tail quantile
                bounds.append(float(np.quantile(arr, q)))
    bands, hi = [], float("inf")
    for (tier, _ceil), b in zip(ladder, bounds):
        lo = b if b is not None else float("-inf")
        bands.append((tier, lo, hi))
        hi = lo if b is not None else hi
    return bands, mode


def _tier_of(war: float, bands) -> str:
    for tier, lo, hi in bands:
        if lo <= war < hi or (hi == float("inf") and war >= lo):
            return tier
    return bands[-1][0]


def _probs(mu: float, sd: float, bands) -> dict:
    nd = NormalDist(mu, max(sd, 1e-6))
    return {tier: ((1.0 if hi == float("inf") else nd.cdf(hi))
                   - (0.0 if lo == float("-inf") else nd.cdf(lo)))
            for tier, lo, hi in bands}


def _round_probs(probs: dict) -> dict:
    """Round to 4dp and absorb the rounding residual into the largest bucket so the stored vector
    sums to exactly 1 (spec invariant: tier_probs sums to 1 +/- 1e-6)."""
    r = {k: round(v, 4) for k, v in probs.items()}
    if r:
        top = max(r, key=r.get)
        r[top] = round(r[top] + (1.0 - sum(r.values())), 4)
    return r


# --------------------------------------------------------------------------- role labels
def _durable_archetypes(arch: pd.DataFrame) -> dict:
    """{(player_id, end_year) -> modal primary_archetype over the player's last 3 seasons <= end}."""
    arch = arch.copy()
    arch["yr"] = arch["season"].str[:4].astype(int)
    by_player = {pid: g.sort_values("yr") for pid, g in arch.groupby("player_id")}
    out = {}
    for pid, g in by_player.items():
        for end in g["yr"].unique():
            recent = g[g["yr"] <= end].tail(3)["primary_archetype"].dropna().tolist()
            if recent:
                out[(int(pid), int(end))] = Counter(recent).most_common(1)[0][0]
    return out


# --------------------------------------------------------------------------- assessed WAR
def _skater_rows(gar: pd.DataFrame, estimator: str, dep_map: dict):
    """Assessed WAR per (skater, season_window) from the swappable value_lens estimator.
    D13: a skater with zero games in the window's MOST RECENT season is INACTIVE -> qualified=false,
    disqualify_reason='inactive', excluded from the tier pool; historical single rows untouched."""
    panel = baselines.skater_panel(gar)
    windows = sorted(gar["season_window"].unique())
    rate_cache = {}
    rows = []
    counts_by_year = panel[panel["toi_5v5"] > 0].groupby("player_id")["yr"].apply(set).to_dict()
    played = panel[panel["games"] > 0]
    games_year = {(int(t.player_id), int(t.yr)): float(t.games) for t in played.itertuples()}
    played_years = played.groupby("player_id")["yr"].apply(lambda s: sorted(set(int(y) for y in s))).to_dict()
    for w in windows:
        end = _end_year(w)
        if end not in rate_cache:
            rate_cache[end] = VL.candidate_rates(estimator, panel, end)
        rates = rate_cache[end]
        wyears = set(_window_years(w))
        sub = gar[gar["season_window"] == w]
        for _, r in sub.iterrows():
            pid = int(r["player_id"])
            if pid not in rates or r["toi_5v5"] <= 0:
                continue
            toi_h = float(r["toi_5v5"]) / 60.0
            # Round at the source so band thresholds, tier assignment, and the stored value all use
            # the SAME number -> exact ties resolve to one tier and monotonicity holds on stored WAR.
            assessed = round(rates[pid][0] * toi_h, 4)
            sd = round(float(r["gar_sd"]) / GPW, 4)
            seasons_present = len(counts_by_year.get(pid, set()) & wyears)
            active = games_year.get((pid, end), 0.0) > 0        # played in the window's latest season
            py = [y for y in played_years.get(pid, []) if y <= end]
            last_played = baselines.season_label(max(py)) if py else None
            qualified = active and bool(r["toi_5v5"] >= SK_FLOOR)
            reason = None if qualified else ("inactive" if not active else "insufficient_sample")
            dep = dep_map.get((pid, w))
            toi_sec = float(r["toi_5v5"]) * 60.0
            share = (round(dep["top_partner_toi_sec"] / toi_sec, 4)
                     if dep and toi_sec > 0 else None)
            rows.append({
                "player_id": pid, "season_window": w, "position": _pos_group(r["position"]),
                "assessed_war": assessed, "war_sd": sd,
                "toi_basis_min": float(r["toi_5v5"]), "seasons_present": max(seasons_present, 1),
                "qualified": qualified, "disqualify_reason": reason, "last_played_season": last_played,
                "top_partner_id": (dep["top_partner_id"] if dep else None),
                "top_partner_toi_share": share,
                "dependence_index": (dep["dependence_index"] if dep else None),
                "dependence_n_partners": (dep["dependence_n_partners"] if dep else None)})
    return pd.DataFrame(rows)


def _goalie_rows(ggar: pd.DataFrame):
    """Goalies carry goalie_gar (already reliability-shrunk) through — point + band unchanged."""
    gp = ggar.copy()
    gp["yr"] = gp["season_window"].apply(lambda s: _end_year(s))
    counts = ggar[ggar["season_window"].str.match(r"^\d{4}-\d{2}$")].copy()
    counts["yr"] = counts["season_window"].str[:4].astype(int)
    played = counts[counts["games_played"] > 0]
    seen = played.groupby("goalie_id")["yr"].apply(set).to_dict()
    games_year = {(int(t.goalie_id), int(t.yr)): float(t.games_played) for t in played.itertuples()}
    rows = []
    for _, r in ggar.iterrows():
        pid = int(r["goalie_id"])
        w = r["season_window"]
        end = _end_year(w)
        wyears = set(_window_years(w))
        active = games_year.get((pid, end), 0.0) > 0            # played in the window's latest season
        py = [y for y in sorted(seen.get(pid, set())) if y <= end]
        last_played = baselines.season_label(max(py)) if py else None
        qualified = active and bool(r["games_played"] >= G_FLOOR)
        reason = None if qualified else ("inactive" if not active else "insufficient_sample")
        rows.append({
            "player_id": pid, "season_window": w, "position": "G",
            "assessed_war": round(float(r["war"]), 4), "war_sd": round(float(r["war_sd"]), 4),
            "toi_basis_min": float(r["shots_total"]),
            "seasons_present": max(len(seen.get(pid, set()) & wyears), 1),
            "qualified": qualified, "disqualify_reason": reason, "last_played_season": last_played,
            "top_partner_id": None, "top_partner_toi_share": None,
            "dependence_index": None, "dependence_n_partners": None})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- stability grade
def _stability_grade(toi_min: float, seasons: int, is_goalie: bool) -> str:
    for grade in ("A", "B", "C"):
        min_toi, min_seasons = CFG["STABILITY_GRADES"][grade]
        if seasons >= min_seasons and (min_toi is None or toi_min >= min_toi):
            g = grade
            break
    else:
        g = "D"
    if is_goalie and g < CFG["GOALIE_MAX_GRADE"]:      # cap goalies (rate reliability ~0.19)
        g = CFG["GOALIE_MAX_GRADE"]
    return g


# --------------------------------------------------------------------------- main compute
def compute(gar, ggar, arch, radar, wowy, estimator: str) -> pd.DataFrame:
    dep_map = _dependence_map(wowy, sorted(gar["season_window"].unique()))
    sk = _skater_rows(gar, estimator, dep_map)
    go = _goalie_rows(ggar)
    allrows = pd.concat([sk, go], ignore_index=True)
    durable = _durable_archetypes(arch)
    radar = radar.copy()
    dep = {(int(r["player_id"]), r["season"]): r["defensive_label"] for _, r in radar.iterrows()}

    inputs_hash = hashlib.sha1(
        f"{MODEL_VERSION}|{estimator}|{sorted(gar['season_window'].unique())}".encode()).hexdigest()[:12]
    now = datetime.now(timezone.utc)
    out = []
    for (w, pg), grp in allrows.groupby(["season_window", "position"]):
        qual = grp[grp["qualified"]]
        pool_size = len(qual)
        bands = mode = None
        if pool_size >= 5:
            bands, mode = _tier_bands(qual["assessed_war"].tolist(), pg, pool_size)
            order = [t for t, _lo, _hi in bands]
        single_season = "_" not in w
        for _, r in grp.iterrows():
            row = {
                "player_id": r["player_id"], "season_window": w, "position": pg,
                "assessed_war": round(float(r["assessed_war"]), 4), "war_sd": round(float(r["war_sd"]), 4),
                "qualified": bool(r["qualified"]), "pool_size": int(pool_size),
                "pool_position_group": pg, "toi_basis_min": round(float(r["toi_basis_min"]), 1),
                "seasons_present": int(r["seasons_present"]), "tier_mode": mode,
                "point_estimator": estimator if pg != "G" else "goalie_gar",
                "role_primary": durable.get((int(r["player_id"]), _end_year(w))),
                "role_deployment": dep.get((int(r["player_id"]),
                                            w.split("_")[1] if "_" in w else w)),
                "disqualify_reason": r.get("disqualify_reason"),
                "last_played_season": r.get("last_played_season"),
                "top_partner_id": (int(r["top_partner_id"]) if pd.notna(r.get("top_partner_id")) else None),
                "top_partner_toi_share": (float(r["top_partner_toi_share"]) if pd.notna(r.get("top_partner_toi_share")) else None),
                "dependence_index": (float(r["dependence_index"]) if pd.notna(r.get("dependence_index")) else None),
                "dependence_n_partners": (int(r["dependence_n_partners"]) if pd.notna(r.get("dependence_n_partners")) else None),
                "inputs_hash": inputs_hash, "model_version": MODEL_VERSION,
                "generated_at": now,
            }
            nd = NormalDist(float(r["assessed_war"]), max(float(r["war_sd"]), 1e-6))
            row["war_p10"] = round(nd.inv_cdf(0.10), 4)
            row["war_p90"] = round(nd.inv_cdf(0.90), 4)
            if r["qualified"] and bands is not None:
                probs = _probs(float(r["assessed_war"]), float(r["war_sd"]), bands)
                tot = sum(probs.values()) or 1.0
                probs = {k: v / tot for k, v in probs.items()}
                tier = _tier_of(float(r["assessed_war"]), bands)
                conf = probs[tier]
                idx = order.index(tier)
                within = sum(probs[order[j]] for j in (idx - 1, idx, idx + 1) if 0 <= j < len(order))
                cl = ("high" if conf >= CFG["CONFIDENCE_CUTS"]["high"]
                      else "medium" if conf >= CFG["CONFIDENCE_CUTS"]["medium"] else "low")
                if single_season:
                    cl = "low"                              # one season of data -> forced low (spec 6.2)
                row.update({
                    "tier": tier, "tier_label": CFG["TIER_LABELS"][tier],
                    "tier_confidence": round(conf, 4), "confidence_label": cl,
                    "tier_prob_within_one": round(within, 4),
                    "tier_probs": json.dumps(_round_probs(probs)),
                    "stability_grade": _stability_grade(
                        float(r["toi_basis_min"]), int(r["seasons_present"]), pg == "G"),
                })
            else:
                row.update({"tier": None, "tier_label": "insufficient sample",
                            "tier_confidence": None, "confidence_label": None,
                            "tier_prob_within_one": None, "tier_probs": None,
                            "stability_grade": "D"})
            out.append(row)
    return pd.DataFrame(out)


COLS = ["player_id", "season_window", "position", "assessed_war", "war_sd", "war_p10", "war_p90",
        "tier", "tier_label", "tier_confidence", "tier_probs", "tier_prob_within_one", "tier_mode",
        "confidence_label", "stability_grade", "role_primary", "role_deployment", "qualified",
        "disqualify_reason", "last_played_season",
        "top_partner_id", "top_partner_toi_share", "dependence_index", "dependence_n_partners",
        "pool_size", "pool_position_group", "toi_basis_min", "seasons_present", "point_estimator",
        "inputs_hash", "model_version", "generated_at"]


def _write(df: pd.DataFrame):
    from models_ml import duck
    if duck.serving_active():
        import duckdb
        if duck._con is not None:
            duck._con.close(); duck._con = None
        con = duckdb.connect(str(duck.duckdb_path()))
        con.execute("DROP TABLE IF EXISTS player_assessment")
        con.register("_pa", df)
        con.execute("CREATE TABLE player_assessment AS SELECT * FROM _pa")
        con.execute("CREATE INDEX IF NOT EXISTS pa_pid ON player_assessment(player_id, season_window)")
        con.close()
        print(f"wrote player_assessment to {duck.duckdb_path()} ({len(df)} rows)")
    else:
        bq.write_df(df, "player_assessment", write_disposition="WRITE_TRUNCATE",
                    clustering_fields=["season_window", "player_id"])
        print(f"wrote nhl_models.player_assessment (BigQuery, {len(df)} rows)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--estimator", default=CFG["POINT_ESTIMATOR"],
                    help="override the skater point estimator (default from config.ASSESSMENT)")
    args = ap.parse_args()

    gar = bq.query_df("select * from nhl_models.player_gar")
    ggar = bq.query_df("select * from nhl_models.goalie_gar")
    arch = bq.query_df("select player_id, season, primary_archetype from nhl_models.player_archetypes")
    radar = bq.query_df("select player_id, season, defensive_label from nhl_models.player_radar")
    wowy = bq.query_df("select player_id, partner_id, season, toi_together_sec, "
                       "together_minus_focal_alone from nhl_mart.mart_player_wowy")

    df = compute(gar, ggar, arch, radar, wowy, args.estimator)[COLS]
    df["player_id"] = df["player_id"].astype("int64")
    print(f"assessment rows: {len(df)}  (estimator={args.estimator}, "
          f"qualified={int(df['qualified'].sum())}, windows={df['season_window'].nunique()})")
    if args.dry_run:
        print("[dry-run] not written")
        return df
    _write(df)
    return df


if __name__ == "__main__":
    import os
    os.environ.setdefault("SERVING_BACKEND", "duckdb")
    main()
