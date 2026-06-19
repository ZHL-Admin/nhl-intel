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
               cap_hit, remaining_years, confidence, note
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


def _team_ledgers(req: dict, assets: dict[str, dict]) -> dict[int, dict]:
    """Per team: the incoming and outgoing AssetValuePart lists."""
    ledgers = {int(t): {"incoming": [], "outgoing": []} for t in req["team_ids"]}
    for m in req["movements"]:
        a = assets[m["asset_id"]]
        ledgers[m["to_team_id"]]["incoming"].append(_part(a, "in"))
        ledgers[m["from_team_id"]]["outgoing"].append(_part(a, "out"))
    return ledgers


# ------------------------------------------------------------------------------------- orchestration
def evaluate(req: dict, season: Optional[str] = None) -> dict:
    """Evaluate a proposed trade -> the multi-team, multi-axis decomposition (see schemas)."""
    season = season or req.get("season") or _season()
    asset_ids = [m["asset_id"] for m in req["movements"]]
    assets = _load_assets(asset_ids)
    _validate(req, assets)

    abbr = _abbrevs(req["team_ids"])
    ledgers = _team_ledgers(req, assets)

    teams = []
    for tid in req["team_ids"]:
        tid = int(tid)
        teams.append({
            "team_id": tid, "team_abbrev": abbr.get(tid),
            "incoming": ledgers[tid]["incoming"], "outgoing": ledgers[tid]["outgoing"],
            # axes filled by later phases (P2 netting, P3 retention, P4 cap, P5 fit, P6 verdict)
            "cap": {"approximate": True, "caveat": CAP_CAVEAT},
        })

    caveats = [
        "Cap compliance is approximate (cap hits only; no LTIR, bonuses, or roster size).",
        "Prospect and pick values are wide-band proxies; bands widen confidence on those sides.",
    ]
    return {"season": season, "teams": teams, "summary": [], "caveats": caveats}
