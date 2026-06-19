"""
Trade evaluation engine (backend + model; no UI).

A trade is a set of asset MOVEMENTS among N teams. The engine nets each team's incoming vs outgoing
assets on two SEPARATE axes — talent (projected WAR over the control window) and cost-efficiency
(surplus, in cap-share and dollars) — models retention as a value lever, overlays fit, and flags cap
compliance as a SOFT approximation. Every team gets its own multi-axis decomposition; the verdict is
never collapsed to one number. Uncertainty bands are propagated through the netting and surfaced.

Reads the built value foundation (mart_tradeable_assets, mart_player_contracts) via bq_service, which
serves from the local DuckDB file. No fake data: an unknown asset is an error, not a guess.

Phases: P1 spec/contract+load, P2 netting, P3 retention, P4 cap soft-flag, P5 fit, P6 verdict.
"""
from __future__ import annotations

import math
from typing import Optional

from services.bigquery import bq_service
from models_ml import config

MAX_RETAINED_PCT = 0.50
MAX_RETAINED_CONTRACTS = 3
CAP_CAVEAT = "Approximate: sums cap hits only; LTIR, bonuses, and roster size are not modeled."


def _season() -> str:
    rows = bq_service.query(
        f"SELECT MAX(season) AS s FROM {bq_service.get_full_table_id('mart_player_contracts')}")
    return rows[0]["s"] if rows and rows[0].get("s") else "2025-26"


def _abbrevs(team_ids: list[int]) -> dict[int, str]:
    if not team_ids:
        return {}
    ids = ",".join(str(int(t)) for t in set(team_ids))
    rows = bq_service.query(
        f"SELECT team_id, ANY_VALUE(team_abbrev) AS a FROM "
        f"{bq_service.get_full_table_id('mart_team_game_stats')} WHERE team_id IN ({ids}) GROUP BY team_id")
    return {int(r["team_id"]): r["a"] for r in rows}


def _load_assets(asset_ids: list[str]) -> dict[str, dict]:
    """Fetch the moved assets from the unified layer, keyed by asset_id. Unknown ids are reported."""
    if not asset_ids:
        return {}
    quoted = ",".join("'" + a.replace("'", "''") + "'" for a in set(asset_ids))
    rows = bq_service.query(f"""
        SELECT asset_id, asset_type, player_id, label, org_team, pos_or_slot,
               value_war, value_war_low, value_war_high,
               surplus_dollars, surplus_low, surplus_high,
               surplus_capshare, surplus_capshare_low, surplus_capshare_high,
               cap_hit, remaining_years, cost_dollars, confidence, note
        FROM {bq_service.get_full_table_id('mart_tradeable_assets')}
        WHERE asset_id IN ({quoted})""")
    return {r["asset_id"]: r for r in rows}


# ------------------------------------------------------------------------------------- validation
def _validate(req: dict, assets: dict[str, dict]) -> None:
    teams = req["team_ids"]
    if len(set(teams)) < 2:
        raise ValueError("a trade needs at least 2 distinct teams")
    teamset = set(teams)
    if not req["movements"]:
        raise ValueError("a trade needs at least one asset movement")

    seen_assets = set()
    for m in req["movements"]:
        if m["from_team_id"] == m["to_team_id"]:
            raise ValueError(f"asset {m['asset_id']} moves from a team to itself")
        if m["from_team_id"] not in teamset or m["to_team_id"] not in teamset:
            raise ValueError(f"asset {m['asset_id']} moves to/from a team not in team_ids")
        if m["asset_id"] not in assets:
            raise ValueError(f"unknown asset_id '{m['asset_id']}' (not in the tradeable-asset layer)")
        if m["asset_id"] in seen_assets:
            raise ValueError(f"asset {m['asset_id']} moved more than once")
        seen_assets.add(m["asset_id"])

    # retention rules: <= 50% per contract, <= 3 retained contracts per team, retainer == source team
    by_team: dict[int, int] = {}
    move_from = {m["asset_id"]: m["from_team_id"] for m in req["movements"]}
    for ret in req.get("retentions", []):
        if not (0.0 < ret["retained_pct"] <= MAX_RETAINED_PCT):
            raise ValueError(f"retained_pct for player {ret['player_id']} must be in (0, {MAX_RETAINED_PCT}]")
        aid = f"player:{ret['player_id']}"
        if aid not in assets or aid not in move_from:
            raise ValueError(f"retention references player {ret['player_id']} who is not a moved player")
        if move_from[aid] != ret["retaining_team_id"]:
            raise ValueError(f"player {ret['player_id']} can only be retained by its source team")
        by_team[ret["retaining_team_id"]] = by_team.get(ret["retaining_team_id"], 0) + 1
    for tid, n in by_team.items():
        if n > MAX_RETAINED_CONTRACTS:
            raise ValueError(f"team {tid} retains {n} contracts (max {MAX_RETAINED_CONTRACTS})")


# ------------------------------------------------------------------------------------- ledger
def _part(asset: dict, direction: str) -> dict:
    return {
        "asset_id": asset["asset_id"], "asset_type": asset["asset_type"],
        "label": asset["label"], "direction": direction,
        "value_war": asset.get("value_war"),
        "value_war_low": asset.get("value_war_low"), "value_war_high": asset.get("value_war_high"),
        "surplus_dollars": _as_int(asset.get("surplus_dollars")),
        "surplus_capshare": asset.get("surplus_capshare"),
        "confidence": asset.get("confidence"), "note": asset.get("note"),
    }


def _as_int(x):
    return int(x) if x is not None else None


def _team_ledgers(req: dict, assets: dict[str, dict], retentions: list[dict]) -> dict[int, dict]:
    """Per team: the incoming and outgoing AssetValuePart lists (retained players annotated)."""
    ret_by_player = {r["player_id"]: r for r in retentions}
    abbr = _abbrevs([r["from_team"] for r in retentions])
    ledgers = {int(t): {"incoming": [], "outgoing": []} for t in req["team_ids"]}
    for m in req["movements"]:
        a = assets[m["asset_id"]]
        rin, rout = _part(a, "in"), _part(a, "out")
        r = ret_by_player.get(a.get("player_id"))
        if r:
            tag = f"{int(r['pct']*100)}% retained by {abbr.get(r['from_team'], r['from_team'])}"
            # receiver pays less (surplus up); retainer carries dead money (surplus down)
            rin["surplus_dollars"] = _as_int((rin["surplus_dollars"] or 0) + r["retained_dollars"])
            rin["note"] = tag
            rout["note"] = tag
        ledgers[m["to_team_id"]]["incoming"].append(rin)
        ledgers[m["from_team_id"]]["outgoing"].append(rout)
    return ledgers


# ------------------------------------------------------------------------------------- retention (P3)
def _retentions(req: dict, assets: dict[str, dict]) -> list[dict]:
    """Resolve each retention election into a value shift. When the SOURCE team retains X% of a
    traded contract, the receiving team pays only (1-X) of the cost (its surplus improves by X*cost)
    and the retaining team keeps X*cost as DEAD MONEY with no player (its surplus drops by X*cost).
    Talent is unaffected (it moves fully with the player)."""
    move_to = {m["asset_id"]: int(m["to_team_id"]) for m in req["movements"]}
    out = []
    for ret in req.get("retentions", []):
        aid = f"player:{ret['player_id']}"
        a = assets[aid]
        pct = float(ret["retained_pct"])
        cost = float(a.get("cost_dollars") or 0.0)
        retained_dollars = pct * cost
        out.append({
            "player_id": int(ret["player_id"]), "label": a.get("label"),
            "pct": pct, "from_team": int(ret["retaining_team_id"]), "to_team": move_to[aid],
            "retained_dollars": retained_dollars,
            "retained_capshare": retained_dollars / config.CAP_UPPER_LIMIT_BY_SEASON["2025-26"],
            # current-year cap hit retained (for the cap soft-flag in P4)
            "retained_cap_hit": pct * float(a.get("cap_hit") or 0.0),
        })
    return out


# ------------------------------------------------------------------------------------- netting (P2)
def _hw(lo, hi) -> float:
    """Half-width of a [low, high] band (0 if either bound is missing)."""
    if lo is None or hi is None:
        return 0.0
    return abs(float(hi) - float(lo)) / 2.0


def _net(req: dict, assets: dict[str, dict], retentions: list[dict]) -> dict[int, dict]:
    """Per team, net incoming minus outgoing on TWO separate axes — talent (WAR) and surplus (dollars
    and cap-share) — propagating each asset's uncertainty band by combining VARIANCES (incoming and
    outgoing both add uncertainty), so a prospect/pick-heavy side shows a wide net band. Retention
    then shifts surplus only: the receiver saves X*cost, the retaining team eats X*cost dead money."""
    acc = {int(t): {"war": 0.0, "war_var": 0.0, "sd": 0.0, "sd_var": 0.0, "sc": 0.0, "sc_var": 0.0}
           for t in req["team_ids"]}
    for m in req["movements"]:
        a = assets[m["asset_id"]]
        war = float(a.get("value_war") or 0.0)
        sd = float(a.get("surplus_dollars") or 0.0)
        sc = float(a.get("surplus_capshare") or 0.0)
        war_v = _hw(a.get("value_war_low"), a.get("value_war_high")) ** 2
        sd_v = _hw(a.get("surplus_low"), a.get("surplus_high")) ** 2
        sc_v = _hw(a.get("surplus_capshare_low"), a.get("surplus_capshare_high")) ** 2
        for tid, sign in ((int(m["to_team_id"]), +1.0), (int(m["from_team_id"]), -1.0)):
            d = acc[tid]
            d["war"] += sign * war; d["sd"] += sign * sd; d["sc"] += sign * sc
            d["war_var"] += war_v; d["sd_var"] += sd_v; d["sc_var"] += sc_v
    # retention: receiver saves the retained cost, retainer carries it as dead money (no talent shift)
    for r in retentions:
        acc[r["to_team"]]["sd"] += r["retained_dollars"]; acc[r["to_team"]]["sc"] += r["retained_capshare"]
        acc[r["from_team"]]["sd"] -= r["retained_dollars"]; acc[r["from_team"]]["sc"] -= r["retained_capshare"]
    out = {}
    for tid, d in acc.items():
        war_hw, sd_hw, sc_hw = math.sqrt(d["war_var"]), math.sqrt(d["sd_var"]), math.sqrt(d["sc_var"])
        out[tid] = {
            "talent_delta_war": round(d["war"], 2),
            "talent_delta_war_low": round(d["war"] - war_hw, 2),
            "talent_delta_war_high": round(d["war"] + war_hw, 2),
            "surplus_delta_dollars": round(d["sd"]),
            "surplus_delta_dollars_low": round(d["sd"] - sd_hw),
            "surplus_delta_dollars_high": round(d["sd"] + sd_hw),
            "surplus_delta_capshare": round(d["sc"], 4),
            "surplus_delta_capshare_low": round(d["sc"] - sc_hw, 4),
            "surplus_delta_capshare_high": round(d["sc"] + sc_hw, 4),
        }
    return out


# ------------------------------------------------------------------------------------- cap flag (P4)
def _committed_caps(abbrevs: list[str]) -> dict[str, int]:
    """Each team's currently committed cap = sum of cap hits on the latest contract snapshot."""
    abbrevs = [a for a in set(abbrevs) if a]
    if not abbrevs:
        return {}
    quoted = ",".join("'" + a.replace("'", "''") + "'" for a in abbrevs)
    mpc = bq_service.get_full_table_id("mart_player_contracts")
    rows = bq_service.query(f"""
        SELECT contract_team, SUM(cap_hit) AS committed FROM {mpc}
        WHERE as_of_date = (SELECT MAX(as_of_date) FROM {mpc}) AND contract_team IN ({quoted})
        GROUP BY contract_team""")
    return {r["contract_team"]: int(r["committed"] or 0) for r in rows}


def _cap(req: dict, assets: dict[str, dict], retentions: list[dict], abbr: dict[int, str],
         season: str) -> dict[int, dict]:
    """SOFT, approximate cap flag per team. Net current-year cap-hit change (an incoming player adds
    (1-X) of their cap hit; the source sheds (1-X) and keeps X*cap_hit dead money; prospects/picks
    are treated as cap-neutral) applied to the committed cap, vs the season ceiling. Never a gate."""
    pct = {r["player_id"]: r["pct"] for r in retentions}
    ceiling = int(config.CAP_UPPER_LIMIT_BY_SEASON.get(season, config.CAP_UPPER_LIMIT_BY_SEASON["2025-26"]))
    committed = _committed_caps([abbr.get(int(t)) for t in req["team_ids"]])
    change = {int(t): 0.0 for t in req["team_ids"]}
    for m in req["movements"]:
        a = assets[m["asset_id"]]
        eff = (1.0 - float(pct.get(a.get("player_id"), 0.0))) * float(a.get("cap_hit") or 0.0)
        change[int(m["to_team_id"])] += eff
        change[int(m["from_team_id"])] -= eff
    out = {}
    for tid in req["team_ids"]:
        tid = int(tid)
        before = committed.get(abbr.get(tid), 0)
        after = round(before + change[tid])
        out[tid] = {
            "committed_before": before, "cap_hit_change": round(change[tid]),
            "committed_after": after, "ceiling": ceiling, "margin": ceiling - after,
            "over_cap": after > ceiling, "approximate": True, "caveat": CAP_CAVEAT,
        }
    return out


# ------------------------------------------------------------------------------------- fit (P5)
def _fit(req: dict, assets: dict[str, dict]) -> dict[int, dict]:
    """Per team, overlay how the INCOMING PLAYERS fit that team's needs (models_ml.score_team_fit
    vs nhl_models.team_needs). Picks and prospects carry no immediate fit (no current profile), so
    they are skipped and noted. fit_delta is the mean incoming fit centered at 50 (neutral)."""
    from models_ml.score_team_fit import score_team_fit

    incoming_players: dict[int, list[int]] = {int(t): [] for t in req["team_ids"]}
    for m in req["movements"]:
        a = assets[m["asset_id"]]
        if a.get("asset_type") == "player" and a.get("player_id") is not None:
            incoming_players[int(m["to_team_id"])].append(int(a["player_id"]))

    out = {}
    for tid in req["team_ids"]:
        tid = int(tid)
        details, scores = [], []
        for pid in incoming_players[tid]:
            try:
                f = score_team_fit(pid, tid, None)   # None -> score_team_fit's latest team_needs season
            except Exception:
                continue                              # no current profile (e.g. a listed prospect) -> no fit
            scores.append(float(f["overall_score"]))
            details.append({"player_id": pid, "player_name": f.get("player_name"),
                            "fit_score": round(float(f["overall_score"]), 1), "grade": f.get("overall_grade"),
                            "summary": f.get("verdict_sentence")})
        fit_delta = round(sum(scores) / len(scores) - 50.0, 1) if scores else None
        out[tid] = {"fit_delta": fit_delta, "fit_details": details}
    return out


# ------------------------------------------------------------------------------------- orchestration
def evaluate(req: dict, season: Optional[str] = None) -> dict:
    """Evaluate a proposed trade -> the multi-team, multi-axis decomposition (see schemas)."""
    season = season or req.get("season") or _season()
    asset_ids = [m["asset_id"] for m in req["movements"]]
    assets = _load_assets(asset_ids)
    _validate(req, assets)

    abbr = _abbrevs(req["team_ids"])
    retentions = _retentions(req, assets)
    ledgers = _team_ledgers(req, assets, retentions)
    nets = _net(req, assets, retentions)
    caps = _cap(req, assets, retentions, abbr, season)
    fits = _fit(req, assets)

    teams = []
    for tid in req["team_ids"]:
        tid = int(tid)
        teams.append({
            "team_id": tid, "team_abbrev": abbr.get(tid),
            **nets[tid],                              # talent + surplus deltas with bands (P2/P3)
            **fits[tid],                              # fit delta + per-player fit detail (P5)
            "cap": caps[tid],                         # soft, approximate cap flag (P4)
            "incoming": ledgers[tid]["incoming"], "outgoing": ledgers[tid]["outgoing"],
            # confidence + summary filled by P6
        })

    caveats = [
        "Cap compliance is approximate (cap hits only; no LTIR, bonuses, or roster size).",
        "Prospect and pick values are wide-band proxies; bands widen confidence on those sides.",
    ]
    return {"season": season, "teams": teams, "summary": [], "caveats": caveats}
