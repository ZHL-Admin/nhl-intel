"""Trade-board composition service (Handoff 6) — entity-first surfaces over the shipped Phase D data.

Reads nhl_models.trade_outcomes (one row per trade-team, with JSON asset ledgers + net WAR + bands)
and stg_gm_tenures (curated GM attribution) via bq_service (DuckDB serving). Builds one object per
TRADE with both sides, GM attribution, margin/verdict, and an archetype tag — then the endpoints
filter (board), aggregate per entity (value map, dossier), or aggregate per archetype (patterns).

Nothing here recomputes Phase D; it only composes. A retrospective on realized outcomes, not a grade
of the decision at the time; GM is the decision-maker of record, not the sole one.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache

from models_ml import config
from services.bigquery import bq_service

TB = config.TRADE_BOARD
GM = config.GM_LAYER

CAVEAT = ("A retrospective on realized outcomes, not a grade of the decision at the time. GM attribution "
          "is to the decision-maker of record from curated tenure dates (approximate near handovers); "
          "the GM is not the sole decision-maker. Values are wide-band estimates in WAR.")

ARCHETYPE_LABELS = {
    "player_for_picks": "Player for picks",
    "player_for_player": "Player for player",
    "picks_for_picks": "Picks for picks",
    "blockbuster": "Blockbusters",
    "three_team": "Three-team",
}


def _d(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _hw(lo, hi) -> float:
    if lo is None or hi is None:
        return 0.0
    return abs(float(hi) - float(lo)) / 2.0


# --------------------------------------------------------------------------- reference data
@lru_cache(maxsize=1)
def _team_ids() -> dict:
    rows = bq_service.query(
        f"SELECT team_id, ANY_VALUE(team_abbrev) AS a FROM "
        f"{bq_service.get_full_table_id('mart_team_game_stats')} GROUP BY team_id")
    return {r["a"]: int(r["team_id"]) for r in rows if r.get("a")}


@lru_cache(maxsize=1)
def _gm_tenures() -> dict:
    """team_abbrev -> [ {gm_id, gm_name, start, end} ] sorted by start (end None = current)."""
    rows = bq_service.query(
        f"SELECT gm_id, gm_name, team_abbrev, start_date, end_date FROM "
        f"{bq_service.get_full_table_id('stg_gm_tenures')}")
    by_team: dict[str, list] = {}
    for r in rows:
        by_team.setdefault(r["team_abbrev"], []).append({
            "gm_id": r["gm_id"], "gm_name": r["gm_name"],
            "start": _d(r["start_date"]), "end": _d(r["end_date"])})
    for v in by_team.values():
        v.sort(key=lambda t: t["start"])
    return by_team


def _attribute(team: str, d: date) -> tuple:
    """(gm_id, gm_name, transition) for a team-side on a date; ('unknown', None, False) on a gap."""
    win = GM["TRANSITION_WINDOW_DAYS"]
    for t in _gm_tenures().get(team, []):
        end = t["end"] or date.today()
        if t["start"] <= d <= end:
            transition = (abs((d - t["start"]).days) <= win
                          or (t["end"] is not None and abs((end - d).days) <= win))
            return t["gm_id"], t["gm_name"], transition
    return "unknown", None, False


# --------------------------------------------------------------------------- build
def _verdict(margin: float, band_hw: float) -> str:
    if (margin - band_hw) <= 0 <= (margin + band_hw):
        return "too_close"
    if abs(margin) - band_hw >= TB["DECISIVE_WAR"]:
        return "decisive"
    return "lean"


def _side_kind(assets: list) -> str:
    """player-heavy / pick-heavy / mixed by share of received slot WAR (Other counts toward picks)."""
    total = sum(a["war_slot"] for a in assets)
    if total <= 0:
        return "mixed"
    player = sum(a["war_slot"] for a in assets if a["asset_type"] == "Player")
    if player / total >= TB["ARCHETYPE_SHARE"]:
        return "player"
    if (total - player) / total >= TB["ARCHETYPE_SHARE"]:
        return "pick"
    return "mixed"


@lru_cache(maxsize=1)
def _latest_start_year() -> int:
    rows = bq_service.query(
        f"SELECT MAX(CAST(SUBSTR(season,1,4) AS INT64)) AS y FROM "
        f"{bq_service.get_models_table_id('player_pwar')}")
    return int(rows[0]["y"]) if rows and rows[0].get("y") else 2025


@lru_cache(maxsize=1)
def build_all() -> list:
    """One composed object per trade (both lenses, GM-attributed). Cached for the process."""
    rows = bq_service.query(f"""
        SELECT trade_id, season, trade_date, team, team_count,
               net_war_slot, net_war_slot_low, net_war_slot_high,
               net_war_actual, net_war_actual_low, net_war_actual_high,
               has_pick, has_unresolved, actual_censored, horizon_incomplete, confidence,
               received_ledger, sent_ledger
        FROM {bq_service.get_models_table_id('trade_outcomes')}
    """)
    team_ids = _team_ids()
    latest = _latest_start_year()

    by_trade: dict[str, list] = {}
    for r in rows:
        by_trade.setdefault(r["trade_id"], []).append(r)

    out = []
    for trade_id, srows in by_trade.items():
        meta = srows[0]
        tdate = _d(meta["trade_date"])
        sides = []
        total_war = 0.0
        any_actual_unresolved = False
        for r in srows:
            recv = json.loads(r["received_ledger"]) if r["received_ledger"] else []
            sent = json.loads(r["sent_ledger"]) if r["sent_ledger"] else []
            assets = [{
                "asset_type": e["type"], "label": e["asset"],
                "war_slot": float(e.get("slot_war") or 0.0),
                "war_actual": (None if (e.get("actual_unresolved") or e.get("unresolved"))
                               else float(e.get("actual_war") or 0.0)),
                "resolved": not (e.get("actual_unresolved") or e.get("unresolved")),
                "player_id": e.get("player_id"),
                "became_player_id": e.get("became_player_id"),
                "became_player_name": e.get("became_player_name"),
                "conditional": bool(e.get("conditional")),
            } for e in recv]
            recv_slot = sum(a["war_slot"] for a in assets)
            recv_actual = sum((a["war_actual"] or 0.0) for a in assets)
            sent_slot = sum(float(e.get("slot_war") or 0.0) for e in sent)
            sent_actual = sum(float(e.get("actual_war") or 0.0) for e in sent)
            side_unresolved = any(e.get("actual_unresolved") or e.get("unresolved") for e in recv + sent)
            any_actual_unresolved = any_actual_unresolved or side_unresolved
            gm_id, gm_name, transition = _attribute(r["team"], tdate)
            total_war += recv_slot
            sides.append({
                "team_id": team_ids.get(r["team"]),
                "team_abbrev": r["team"],
                "gm_id": gm_id, "gm_name": gm_name, "gm_transition": transition,
                "slot_war_received": round(recv_slot, 2),
                "actual_war_received": round(recv_actual, 2),
                "sent_slot": sent_slot, "sent_actual": sent_actual,
                "net_slot": float(r["net_war_slot"] or 0.0),
                "net_slot_hw": _hw(r["net_war_slot_low"], r["net_war_slot_high"]),
                "net_actual": float(r["net_war_actual"] or 0.0),
                "net_actual_hw": _hw(r["net_war_actual_low"], r["net_war_actual_high"]),
                "kind": _side_kind(assets),
                "assets": assets,
            })

        # winner / margin under each lens = the side with the highest net
        win_slot = max(range(len(sides)), key=lambda i: sides[i]["net_slot"])
        margin_slot = sides[win_slot]["net_slot"]
        band_hw_slot = sides[win_slot]["net_slot_hw"]
        verdict = _verdict(margin_slot, band_hw_slot)
        winner = sides[win_slot] if verdict != "too_close" else None

        actual_ok = not any_actual_unresolved
        margin_actual = band_hw_actual = None
        if actual_ok:
            wa = max(range(len(sides)), key=lambda i: sides[i]["net_actual"])
            margin_actual = sides[wa]["net_actual"]
            band_hw_actual = sides[wa]["net_actual_hw"]

        # archetype (single primary tag) + the is_player_for_picks flag (independent)
        kinds = [s["kind"] for s in sides]
        is_pfp = (meta["team_count"] == 2 and {"player", "pick"} <= set(kinds))
        if meta["team_count"] >= 3:
            archetype = "three_team"
        elif total_war >= TB["BLOCKBUSTER_WAR"]:
            archetype = "blockbuster"
        elif is_pfp:
            archetype = "player_for_picks"
        elif all(k == "player" for k in kinds):
            archetype = "player_for_player"
        elif all(k == "pick" for k in kinds):
            archetype = "picks_for_picks"
        else:
            archetype = "player_for_player"   # mixed fallback (a player is involved on a side)

        realized_year = max(0, min(TB["REALIZED_HORIZON_YEARS"],
                                   latest - int(meta["season"][:4]) + 1))
        conf_rank = {"low": 0, "medium": 1, "high": 2}
        confidence = min((r["confidence"] for r in srows), key=lambda c: conf_rank.get(c, 0))

        out.append({
            "trade_id": trade_id, "date": str(tdate), "season": meta["season"],
            "team_count": int(meta["team_count"]), "sides": sides,
            "margin_slot": round(margin_slot, 2), "band_hw_slot": round(band_hw_slot, 2),
            "margin_actual": (round(margin_actual, 2) if margin_actual is not None else None),
            "band_hw_actual": (round(band_hw_actual, 2) if band_hw_actual is not None else None),
            "winner_team_id": winner["team_id"] if winner else None,
            "winner_gm_id": winner["gm_id"] if winner else None,
            "winner_idx_slot": win_slot if winner else None,
            "verdict": verdict,
            "incomplete": bool(meta["horizon_incomplete"]),
            "realized_year": realized_year,
            "is_player_for_picks": is_pfp,
            "archetype": archetype,
            "confidence": confidence,
            "total_war": round(total_war, 2),
            "actual_ok": actual_ok,
        })
    return out


# --------------------------------------------------------------------------- board API shapes
def _to_board_item(t: dict) -> dict:
    """Strip the internal build fields down to the TradeBoardItem shape."""
    return {
        "trade_id": t["trade_id"], "date": t["date"], "season": t["season"],
        "team_count": t["team_count"],
        "sides": [{
            "team_id": s["team_id"], "team_abbrev": s["team_abbrev"],
            "gm_id": s["gm_id"], "gm_name": s["gm_name"], "gm_transition": s["gm_transition"],
            "slot_war_received": s["slot_war_received"],
            "actual_war_received": (s["actual_war_received"] if t["actual_ok"] else None),
            "assets": s["assets"],
        } for s in t["sides"]],
        "margin_slot": t["margin_slot"], "band_hw_slot": t["band_hw_slot"],
        "margin_actual": t["margin_actual"], "band_hw_actual": t["band_hw_actual"],
        "winner_team_id": t["winner_team_id"], "winner_gm_id": t["winner_gm_id"],
        "verdict": t["verdict"], "incomplete": t["incomplete"], "realized_year": t["realized_year"],
        "is_player_for_picks": t["is_player_for_picks"], "archetype": t["archetype"],
        "confidence": t["confidence"],
    }


def _season_ok(t: dict, sf: str | None, st: str | None) -> bool:
    return (not sf or t["season"] >= sf) and (not st or t["season"] <= st)


def board(sort="lopsided", lens="slot", archetype=None, include_incomplete=False,
          season_from=None, season_to=None, limit=40, offset=0) -> list:
    items = [t for t in build_all()
             if (include_incomplete or not t["incomplete"])
             and _season_ok(t, season_from, season_to)
             and (not archetype or t["archetype"] == archetype or
                  (archetype == "player_for_picks" and t["is_player_for_picks"]))]
    m = "margin_actual" if lens == "actual" else "margin_slot"
    if sort == "recent":
        items.sort(key=lambda t: t["date"], reverse=True)
    elif sort == "closest":
        items.sort(key=lambda t: (t.get(m) if t.get(m) is not None else 1e9))
    else:  # lopsided
        items.sort(key=lambda t: (t.get(m) if t.get(m) is not None else -1e9), reverse=True)
    return [_to_board_item(t) for t in items[offset:offset + limit]]


def get_trade(trade_id: str) -> dict | None:
    for t in build_all():
        if t["trade_id"] == trade_id:
            return _to_board_item(t)
    return None


# --------------------------------------------------------------------------- value map / dossier
def _record_bucket(side_net: float, verdict: str, is_winner: bool) -> str:
    if verdict == "too_close":
        return "too_close"
    if is_winner:
        return "decisive_wins" if verdict == "decisive" else "leans"
    return "losses"


def _entity_sides(kind: str, lens: str, sf, st):
    """Yield (entity_id, label, color_abbrev, side, trade) for each entity-side under the filter."""
    for t in build_all():
        if t["incomplete"] or not _season_ok(t, sf, st):
            continue
        for i, s in enumerate(t["sides"]):
            if kind == "team":
                yield s["team_abbrev"], s["team_abbrev"], s["team_abbrev"], i, s, t
            else:
                if not s["gm_id"] or s["gm_id"] == "unknown":
                    continue
                yield s["gm_id"], (s["gm_name"] or s["gm_id"]), s["team_abbrev"], i, s, t


def value_map(kind="team", lens="slot", season_from=None, season_to=None) -> list:
    net_k = "net_actual" if lens == "actual" else "net_slot"
    hw_k = "net_actual_hw" if lens == "actual" else "net_slot_hw"
    sent_k = "sent_actual" if lens == "actual" else "sent_slot"
    recv_k = "actual_war_received" if lens == "actual" else "slot_war_received"
    agg: dict = {}
    for eid, label, color, idx, s, t in _entity_sides(kind, lens, season_from, season_to):
        a = agg.setdefault(eid, {"kind": kind, "id": eid, "label": label,
                                 "team_abbrev_for_color": color, "given_up_war": 0.0, "gained_war": 0.0,
                                 "net_war": 0.0, "var": 0.0, "trade_count": 0,
                                 "record": {"decisive_wins": 0, "leans": 0, "too_close": 0, "losses": 0},
                                 "_last": t["date"]})
        a["given_up_war"] += float(s[sent_k] or 0.0)
        a["gained_war"] += float(s[recv_k] or 0.0)
        a["net_war"] += float(s[net_k] or 0.0)
        a["var"] += float(s[hw_k] or 0.0) ** 2
        a["trade_count"] += 1
        if t["date"] >= a["_last"]:               # GM bubble colored by most-recent stint's team
            a["_last"], a["team_abbrev_for_color"] = t["date"], color
        is_winner = (t["winner_idx_slot"] == idx)
        a["record"][_record_bucket(0, t["verdict"], is_winner)] += 1
    out = []
    for a in agg.values():
        out.append({k: a[k] for k in ("kind", "id", "label", "team_abbrev_for_color", "trade_count")}
                   | {"given_up_war": round(a["given_up_war"], 1), "gained_war": round(a["gained_war"], 1),
                      "net_war": round(a["net_war"], 1), "net_band_hw": round(a["var"] ** 0.5, 1),
                      "record": a["record"]})
    out.sort(key=lambda x: x["net_war"], reverse=True)
    return out


def _gm_tenure_rows(gm_id: str) -> list:
    out = []
    for team, tens in _gm_tenures().items():
        for t in tens:
            if t["gm_id"] == gm_id:
                out.append({"team_abbrev": team, "start_date": str(t["start"]),
                            "end_date": (str(t["end"]) if t["end"] else None), "title": None})
    out.sort(key=lambda r: r["start_date"])
    return out


def dossier(kind: str, entity_id: str, lens="slot") -> dict | None:
    net_k = "net_actual" if lens == "actual" else "net_slot"
    hw_k = "net_actual_hw" if lens == "actual" else "net_slot_hw"
    rows = [(idx, s, t) for eid, label, color, idx, s, t in _entity_sides(kind, lens, None, None)
            if eid == entity_id]
    if not rows:
        return None
    label = (rows[0][1]["team_abbrev"] if kind == "team"
             else (rows[0][1]["gm_name"] or entity_id))
    rows.sort(key=lambda x: x[2]["date"])
    net = sum(float(s[net_k] or 0.0) for _, s, _ in rows)
    var = sum(float(s[hw_k] or 0.0) ** 2 for _, s, _ in rows)
    record = {"decisive_wins": 0, "leans": 0, "too_close": 0, "losses": 0}
    timeline, cum = [], 0.0
    for idx, s, t in rows:
        cum += float(s[net_k] or 0.0)
        record[_record_bucket(0, t["verdict"], t["winner_idx_slot"] == idx)] += 1
        regime = (s["gm_id"] or "unknown") if kind == "team" else s["team_abbrev"]
        timeline.append({"date": t["date"], "cumulative_net_war": round(cum, 1),
                         "trade_id": t["trade_id"], "regime_key": regime})
    ranked = sorted(rows, key=lambda x: float(x[1][net_k] or 0.0), reverse=True)
    deal_ids = [t["trade_id"] for _, _, t in ranked]
    tenures = (_gm_tenure_rows(entity_id) if kind == "gm"
               else [{"team_abbrev": entity_id, "start_date": rows[0][2]["date"],
                      "end_date": None, "title": None}])
    return {
        "kind": kind, "id": entity_id, "label": label, "tenures": tenures,
        "net_war": round(net, 1), "net_band_hw": round(var ** 0.5, 1), "trade_count": len(rows),
        "record": record, "timeline": timeline,
        "best": deal_ids[:2], "worst": deal_ids[-2:][::-1] if len(deal_ids) > 1 else [],
        "deals": deal_ids, "caveat": CAVEAT,
    }


# --------------------------------------------------------------------------- archetypes
def _matches_archetype(t: dict, arch: str) -> bool:
    if arch == "player_for_picks":
        return t["is_player_for_picks"]
    if arch == "blockbuster":
        return t["total_war"] >= TB["BLOCKBUSTER_WAR"]
    if arch == "three_team":
        return t["team_count"] >= 3
    return t["archetype"] == arch


def archetypes(lens="slot", season_from=None, season_to=None) -> list:
    pool = [t for t in build_all() if not t["incomplete"] and _season_ok(t, season_from, season_to)]
    out = []
    for arch in ("player_for_picks", "player_for_player", "picks_for_picks", "blockbuster", "three_team"):
        ts = [t for t in pool if _matches_archetype(t, arch)]
        if not ts:
            continue
        won = lost = even = 0
        for t in ts:
            if t["verdict"] == "too_close":
                even += 1
            elif arch == "player_for_picks":
                # did the player-heavy side win?
                wi = t["winner_idx_slot"]
                won += 1 if (wi is not None and t["sides"][wi]["kind"] == "player") else 0
                lost += 1 if (wi is not None and t["sides"][wi]["kind"] != "player") else 0
            else:
                won += 1  # "decisive/lean" trades have a winner; framed as won/even below
        n = len(ts)
        if arch == "player_for_picks":
            split = {"player_side_won_pct": round(100 * won / n), "pick_side_won_pct": round(100 * lost / n),
                     "even_pct": round(100 * even / n)}
        else:
            decisive = sum(1 for t in ts if t["verdict"] != "too_close")
            split = {"decisive_pct": round(100 * decisive / n), "even_pct": round(100 * even / n)}
        srt = sorted(ts, key=lambda t: t["margin_slot"], reverse=True)
        # biggest_for_a / biggest_for_b: the two ends; closest: smallest margin
        exemplars = {"biggest_for_a": srt[0]["trade_id"], "biggest_for_b": srt[-1]["trade_id"],
                     "closest": min(ts, key=lambda t: t["margin_slot"])["trade_id"]}
        out.append({"archetype": arch, "label": ARCHETYPE_LABELS[arch], "trade_count": n,
                    "split": split, "exemplars": exemplars})
    return out
