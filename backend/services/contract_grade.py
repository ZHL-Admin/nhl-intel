"""Contract Grader service — grade an actual or hypothetical contract for any player.

Reuses the exact batch model (models_ml.compute_contract_value): a player's current WAR is aged
forward each year by their archetype curve, priced by the league's monotone market curve into an
expected AAV, and compared to the proposed cap hit to get present-valued surplus. The only piece the
batch persists per-player (player_contract_value) is the ACTUAL deal; here we refit the market curve
from the league sample (cached) and project ANY (cap_hit, term), so the user can build/grade
hypothetical or newly-announced contracts. No batch-job changes.

Grade is derived from PV surplus relative to the deal's PV cost (see grade_from_surplus): a steal
returns far more value than it costs; a bad deal far less.
"""
from __future__ import annotations

import json
import math
from datetime import date
from functools import lru_cache

import pandas as pd

from services.bigquery import bq_service


def _cv():
    from models_ml import config
    return config


@lru_cache(maxsize=4)
def _market_for(season: str):
    """Refit the league market curve (expected cap-share vs WAR, per position) — cached per season.
    Mirrors compute_contract_value.compute()'s market fit: grounded matched players in the season."""
    from models_ml.compute_contract_value import fit_market_curves, pos_group, CAP_CURRENT
    mart = bq_service.get_full_table_id("mart_player_contracts")
    gar = bq_service.get_models_table_id("player_gar")
    ggar = bq_service.get_models_table_id("goalie_gar")
    rows = bq_service.query(f"""
        WITH latest AS (
            SELECT * FROM {mart}
            WHERE as_of_date = (SELECT MAX(as_of_date) FROM {mart}) AND remaining_years >= 1
        ),
        war AS (
            SELECT player_id, position, war FROM {gar} WHERE season_window = '{season}'
            UNION ALL
            SELECT goalie_id AS player_id, 'G' AS position, war FROM {ggar} WHERE season_window = '{season}'
        )
        SELECT c.contract_pos, w.position, w.war, c.cap_hit, c.is_elc
        FROM latest c JOIN war w USING (player_id)
        WHERE w.war IS NOT NULL AND c.cap_hit IS NOT NULL
    """)
    df = pd.DataFrame(rows)
    df["pg"] = df.apply(lambda r: pos_group(r.get("position"), r.get("contract_pos")), axis=1)
    df["war"] = pd.to_numeric(df["war"]).astype("float64")
    df["cap_share"] = pd.to_numeric(df["cap_hit"]).astype("float64") / float(CAP_CURRENT)
    return fit_market_curves(df[["pg", "war", "cap_share", "is_elc"]])   # ELCs filtered inside the fit


@lru_cache(maxsize=2)
def _caliber_market(season: str):
    """The market 'going rate' as a continuous function of a player's CALIBER, per position (caliber =
    a blend of TOI/game and multi-season blended-WAR percentile within position). Pulls the inputs for
    this season and delegates the fit to compute_contract_value.build_caliber_market, so the live
    grader and the batch job share one implementation and cannot drift."""
    from models_ml.compute_contract_value import (
        blended_war_rate, season_str, pos_group, build_caliber_market, CAP_CURRENT)
    y = int(season[:4])
    windows = {season_str(y - k): k for k in range(5)}
    inlist = ",".join(f"'{w}'" for w in windows)
    gar = bq_service.get_models_table_id("player_gar")
    ggar = bq_service.get_models_table_id("goalie_gar")
    war_rows = bq_service.query(f"""
        SELECT player_id, season_window, position, war, games FROM {gar} WHERE season_window IN ({inlist})
        UNION ALL
        SELECT goalie_id AS player_id, season_window, 'G' AS position, war, games_played AS games
        FROM {ggar} WHERE season_window IN ({inlist})""")
    toi_rows = bq_service.query(f"""
        SELECT player_id, SAFE_DIVIDE(toi_minutes, games) tpg
        FROM {bq_service.get_models_table_id('player_situation_toi')}
        WHERE season = '{season}' AND situation = 'all' AND games > 0""")
    mart = bq_service.get_full_table_id("mart_player_contracts")
    contracts = bq_service.query(f"""SELECT player_id, cap_hit FROM {mart}
        WHERE as_of_date = (SELECT MAX(as_of_date) FROM {mart})
          AND remaining_years >= 1 AND NOT is_elc AND cap_hit IS NOT NULL""")

    # per-player blended multi-season WAR + position -> the caliber reference pool
    wdf = pd.DataFrame(war_rows)
    prof = []
    for pid, g in wdf.groupby("player_id"):
        seasons, pos = [], None
        for _, r in g.iterrows():
            k = windows.get(r["season_window"])
            if k is not None and r["war"] is not None:
                seasons.append((k, float(r["war"]), float(r.get("games") or 0)))
                if k == 0:
                    pos = r["position"]
        if not seasons:
            continue
        bw, _ = blended_war_rate(seasons)
        prof.append({"player_id": pid, "pg": pos_group(pos or g.iloc[0]["position"], None), "war": bw})
    profiles = pd.DataFrame(prof)
    toi = {r["player_id"]: float(r["tpg"]) for r in toi_rows}
    profiles["toi"] = profiles["player_id"].map(toi)
    fit_contracts = pd.DataFrame(contracts)
    cm = build_caliber_market(profiles, fit_contracts, float(CAP_CURRENT))
    # attach per-player caliber (the role+production percentile blend) for the comparables lookup
    profiles["caliber"] = profiles.apply(
        lambda r: cm["caliber_of"](r["pg"], r["toi"] if pd.notna(r["toi"]) else None, r["war"]), axis=1)
    cm["profiles"] = profiles
    return cm


def _caliber_market_share(cm: dict, pg: str, toi, war: float):
    """Predicted market cap-share for a player's caliber (delegates to the shared model)."""
    from models_ml.compute_contract_value import caliber_market_share
    return caliber_market_share(cm, pg, toi, war)


@lru_cache(maxsize=2)
def _comp_pool(season: str) -> tuple:
    """Real signed non-ELC deals (the market sample) with name + AAV + term + stored surplus/cost for a
    grade — the pool the per-player comparables are drawn from. Cached per season."""
    mart = bq_service.get_full_table_id("mart_player_contracts")
    ros = bq_service.get_models_table_id("dim_current_roster")
    pcv = bq_service.get_models_table_id("player_contract_value")
    rows = bq_service.query(f"""
        SELECT c.player_id, r.full_name AS name, c.cap_hit, c.remaining_years,
               v.total_discounted_surplus AS s, v.cost_dollars AS cost
        FROM {mart} c JOIN {ros} r USING (player_id)
        LEFT JOIN {pcv} v ON c.player_id = v.player_id AND c.as_of_date = v.as_of_date
        WHERE c.as_of_date = (SELECT MAX(as_of_date) FROM {mart})
          AND c.remaining_years >= 1 AND NOT c.is_elc AND c.contract_status = 'signed'
          AND c.cap_hit IS NOT NULL""")
    return tuple(rows)


def _comparables(season: str, pg: str, target_caliber: float, exclude_pid: int, n: int = 5) -> list:
    """The ~n real signed deals nearest this player by CALIBER within the same POSITION — the concrete
    'what the market pays for this kind of player', each with its own grade."""
    cm = _caliber_market(season)
    prof = cm.get("profiles")
    if prof is None or target_caliber is None:
        return []
    cal_by_pid = dict(zip(prof["player_id"], prof["caliber"]))
    pg_by_pid = dict(zip(prof["player_id"], prof["pg"]))
    out = []
    for r in _comp_pool(season):
        pid = r["player_id"]
        if pid == exclude_pid or pg_by_pid.get(pid) != pg:
            continue
        cal = cal_by_pid.get(pid)
        if cal is None:
            continue
        grade = (grade_from_surplus(r["s"], r["cost"])["grade"]
                 if r.get("s") is not None and r.get("cost") else None)
        out.append({"player_id": int(pid), "name": r["name"], "aav": int(r["cap_hit"]),
                    "term": int(r["remaining_years"]), "grade": grade,
                    "caliber": round(float(cal), 3), "_d": abs(float(cal) - target_caliber)})
    out.sort(key=lambda x: x["_d"])
    for o in out:
        o.pop("_d")
    return out[:n]


def _player_inputs(player_id: int, season: str) -> dict:
    """WAR, age, position group, archetype aging curve + grounding/confidence for one player —
    mirrors the per-player logic of compute_contract_value.compute(), for ANY player (not only
    those with a contract on file)."""
    from models_ml.compute_contract_value import pos_group, blended_war_rate, season_str
    CV = _cv().CONTRACT_VALUE
    gar = bq_service.get_models_table_id("player_gar")
    ggar = bq_service.get_models_table_id("goalie_gar")
    y = int(season[:4])
    windows = {season_str(y - k): k for k in range(5)}   # up to 5 single-season windows
    inlist = ",".join(f"'{w}'" for w in windows)
    war_rows = bq_service.query(f"""
        SELECT season_window, position, war, war_sd, games FROM {gar}
        WHERE season_window IN ({inlist}) AND player_id = {int(player_id)}
        UNION ALL
        SELECT season_window, 'G' AS position, war, war_sd, games_played AS games FROM {ggar}
        WHERE season_window IN ({inlist}) AND goalie_id = {int(player_id)}
    """)
    bio = bq_service.query(f"""
        SELECT birth_date FROM {bq_service.get_full_table_id('stg_player_bio')}
        WHERE player_id = {int(player_id)} LIMIT 1""")
    arch = bq_service.query(f"""
        SELECT primary_archetype FROM {bq_service.get_models_table_id('player_archetypes')}
        WHERE season = '{season}' AND player_id = {int(player_id)} LIMIT 1""")
    curves = bq_service.query(f"""
        SELECT archetype, age, curve_value FROM {bq_service.get_models_table_id('aging_curves')}""")
    toi = bq_service.query(f"""
        SELECT SAFE_DIVIDE(toi_minutes, games) AS tpg FROM
        {bq_service.get_models_table_id('player_situation_toi')}
        WHERE season = '{season}' AND player_id = {int(player_id)} AND situation = 'all' AND games > 0
        LIMIT 1""")

    by_win = {r["season_window"]: r for r in war_rows}
    cur = by_win.get(season_str(y), {})
    position = cur.get("position") or (war_rows[0]["position"] if war_rows else None)
    pg = pos_group(position, None)

    start_year = y
    age = 27
    if bio and bio[0].get("birth_date"):
        bd = pd.to_datetime(bio[0]["birth_date"])
        age = int((pd.Timestamp(date(start_year, 10, 1)) - bd).days // 365.25)

    archetype = arch[0]["primary_archetype"] if arch else None
    curve_map: dict[str, dict[int, float]] = {}
    for c in curves:
        curve_map.setdefault(c["archetype"], {})[int(c["age"])] = float(c["curve_value"])
    curve = curve_map.get(archetype) or curve_map.get(CV["AGE_FALLBACK"].get(pg))
    toi_per_game = float(toi[0]["tpg"]) if toi and toi[0].get("tpg") is not None else None

    # multi-season recency/games-weighted projection base (no single down year dominates)
    from models_ml.compute_contract_value import PROJ
    seasons = [(yrs, float(by_win[win]["war"]), float(by_win[win].get("games") or 0))
               for win, yrs in windows.items() if win in by_win and by_win[win].get("war") is not None]
    # component windows for the value-derivation panel (label, war, games), most recent first
    war_windows = [{"season_window": win, "war": round(float(by_win[win]["war"]), 2),
                    "games": int(by_win[win].get("games") or 0)}
                   for win, yrs in sorted(windows.items(), key=lambda kv: kv[1])
                   if win in by_win and by_win[win].get("war") is not None]
    grounded = bool(seasons)
    if grounded:
        blended_war, tot_games = blended_war_rate(seasons)
        shrink_factor = tot_games / (tot_games + PROJ["REGRESS_GAMES"]) if tot_games else 0.0
        sd = float(cur.get("war_sd") or CV["PROXY_WAR_BAND"])
        band = CV["BAND_SDS"] * sd
        confidence = "high" if (tot_games >= CV["GROUNDED_MIN_GAMES"] * 2 and pg != "G") else "medium"
    else:
        blended_war = CV["REPLACEMENT_WAR"]; band = CV["PROXY_WAR_BAND"]; confidence = "proxy"
        tot_games = 0.0; shrink_factor = 0.0; sd = CV["PROXY_WAR_BAND"]

    return {"blended_war": blended_war, "band": band, "age": age, "pg": pg, "curve": curve,
            "confidence": confidence, "grounded": grounded, "games": tot_games,
            "toi_per_game": toi_per_game, "archetype": archetype, "position": position,
            "war_windows": war_windows, "shrink_factor": shrink_factor, "war_sd": sd}


def grade_contract(player_id: int, cap_hit: float, term_years: int,
                   season: str | None = None) -> dict:
    """Grade an actual or hypothetical (cap_hit, term_years) deal for a player. Returns the value/
    cost/surplus decomposition, a per-year schedule, a letter grade + verdict, and a confidence band."""
    from models_ml.compute_contract_value import (
        project_one, build_cap_ceilings, value_effective_war, market_cap_share, CAP_CURRENT, SEASON)
    CV = _cv().CONTRACT_VALUE
    season = season or SEASON
    if term_years < 1 or term_years > 8:
        raise ValueError("term must be 1–8 years")
    if cap_hit <= 0:
        raise ValueError("cap hit must be positive")

    p = _player_inputs(player_id, season)
    market = _market_for(season)
    cm = _caliber_market(season)

    # Value = the HIGHER of what his production is worth (intrinsic, keeps the elite uncompressed)
    # and what his caliber's market pays (a floor that lifts players the WAR model underrates). Then
    # run the existing aging/projection by inverting that value share to an effective WAR.
    if p["grounded"]:
        war = value_effective_war(market, cm, p["pg"], p["blended_war"], p["toi_per_game"])
    else:
        war = p["blended_war"]

    # derivation: where the value came from (intrinsic worth vs the caliber-market floor) + caliber pct
    caliber_pct = cm["caliber_of"](p["pg"], p["toi_per_game"], p["blended_war"]) if p["grounded"] else None
    if p["grounded"] and p["pg"] != "G":
        intrinsic_share = market_cap_share(market, p["pg"], p["blended_war"])
        caliber_share, _ = _caliber_market_share(cm, p["pg"], p["toi_per_game"], p["blended_war"])
        value_basis = "caliber-floor" if (caliber_share or 0.0) > intrinsic_share else "intrinsic"
    else:
        value_basis = "intrinsic"

    confidence = p["confidence"]
    band = p["band"]
    if p["grounded"] and war >= market["top_war"].get(p["pg"], 99.0):
        band *= CV["TOP_DECILE_BAND_MULT"]
        confidence = "medium"

    caps = build_cap_ceilings(horizon=term_years + 2)
    start_year = int(season[:4])
    args = (p["age"], term_years, p["pg"], p["curve"], float(cap_hit), market,
            CV["DISCOUNT"], start_year, caps)
    mid = project_one(war, *args)
    lo = project_one(war - band, *args)
    hi = project_one(war + band, *args)
    # flat-cap baseline (cap frozen at current) to decompose the cap-growth component of the surplus —
    # the part that comes purely from a flat $ cap hit shrinking against a rising ceiling. Real asset
    # value (kept in the grade), exposed separately so the value panel can attribute it.
    flat_caps = {y: float(CAP_CURRENT) for y in caps}
    flat = project_one(war, p["age"], term_years, p["pg"], p["curve"], float(cap_hit), market,
                       CV["DISCOUNT"], start_year, flat_caps)

    surplus = mid["total_discounted_surplus"]
    cost = mid["cost_dollars"]
    cap_growth_surplus = surplus - flat["total_discounted_surplus"]
    g = grade_from_surplus(surplus, cost)

    # break-even AAV over the term = the flat AAV whose PV cost zeroes PV surplus (value / Σdiscount);
    # Σdiscount = cost/cap_hit, so break-even = value_dollars * cap_hit / cost. Distinct from the
    # point-in-time (now) fair AAV, which is the year-0 expected value.
    break_even_aav = (mid["value_dollars"] * float(cap_hit) / cost) if cost > 0 else mid["expected_value_now"]
    val_lo = min(lo["value_dollars"], hi["value_dollars"])
    val_hi = max(lo["value_dollars"], hi["value_dollars"])
    # enrich the per-year schedule with a running cumulative surplus (nominal $ that season)
    sched = mid["schedule"]
    cum = 0.0
    for s in sched:
        cum += float(s.get("surplus_dollars", 0.0))
        s["cumulative_surplus_dollars"] = round(cum)
    comparables = _comparables(season, p["pg"], caliber_pct, int(player_id)) if p["grounded"] else []

    return {
        "player_id": player_id,
        "cap_hit": int(round(cap_hit)),
        "term_years": term_years,
        "season": season,
        "position": p["pg"],
        "war_now": round(war, 2),
        "blended_war": round(p["blended_war"], 2),
        "shrink_factor": round(p.get("shrink_factor", 0.0), 3),
        "caliber_pct": round(caliber_pct, 3) if caliber_pct is not None else None,
        "value_basis": value_basis,
        "war_windows": p.get("war_windows", []),
        "fair_aav": int(round(mid["expected_value_now"])),               # point-in-time (now); kept for compat
        "fair_aav_now": int(round(mid["expected_value_now"])),
        "fair_aav_breakeven": int(round(break_even_aav)),
        "value_dollars": int(round(mid["value_dollars"])),
        "value_dollars_low": int(round(val_lo)),
        "value_dollars_high": int(round(val_hi)),
        "war_sd": round(float(p.get("war_sd", 0.0)), 2),
        "cost_dollars": int(round(cost)),
        "total_discounted_surplus": int(round(surplus)),
        "surplus_low": int(round(min(lo["total_discounted_surplus"], hi["total_discounted_surplus"]))),
        "surplus_high": int(round(max(lo["total_discounted_surplus"], hi["total_discounted_surplus"]))),
        "cap_growth_surplus": int(round(cap_growth_surplus)),
        "player_value_surplus": int(round(surplus - cap_growth_surplus)),
        "total_discounted_surplus_capshare": round(mid["total_discounted_surplus_share"], 4),
        "cap_share_schedule": sched,
        "comparables": comparables,
        "confidence": confidence,
        "grounded": p["grounded"],
        "grade": g["grade"],
        "verdict": g["verdict"],
        "tone": g["tone"],
    }


# Grade bands: PV surplus as a fraction of the deal's PV cost. Symmetric around fair (0).
_BANDS = [
    (0.30, "A", "Steal", "positive"),
    (0.12, "B", "Good value", "positive"),
    (-0.12, "C", "Fair", "neutral"),
    (-0.30, "D", "Overpay", "caution"),
]


def grade_from_surplus(surplus: float, cost: float) -> dict:
    """Letter grade + verdict from PV surplus relative to PV cost. >0 surplus = team comes out ahead."""
    ratio = surplus / cost if cost > 0 else 0.0
    grade, label, tone = "F", "Bad deal", "caution"
    for thresh, g, lab, tn in _BANDS:
        if ratio >= thresh:
            grade, label, tone = g, lab, tn
            break
    pctlabel = f"{abs(ratio) * 100:.0f}%"
    if ratio >= 0.05:
        verdict = f"{label}: returns about {pctlabel} more value than it costs."
    elif ratio <= -0.05:
        verdict = f"{label}: costs about {pctlabel} more than the production is worth."
    else:
        verdict = f"{label}: priced about right for the expected production."
    return {"grade": grade, "verdict": verdict, "tone": tone}
