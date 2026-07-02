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
import statistics
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
def _timing_bucket(d: date) -> str:
    """Trade context by date (we have dates, not cap/expiry — an honest proxy, not a rental tag).
    deadline: Feb 15 - Mar 15; draft: June; offseason: Jul-Sep; else in-season."""
    m, day = d.month, d.day
    if (m == 2 and day >= 15) or (m == 3 and day <= 15):
        return "deadline"
    if m == 6:
        return "draft"
    if m in (7, 8, 9):
        return "offseason"
    return "in_season"


def _verdict(margin: float, band_hw: float) -> str:
    """Three-tier, realized-only, evaluated in this order (margin = realized net, band_hw = its half-width):
      decisive  — |margin| - band_hw >= DECISIVE_WAR (a confident call; the only tier the band must clear)
      even      — |margin| < EDGE_FLOOR_WAR (the realized value came out level)
      edge      — otherwise (the sign of the realized margin is known and exceeds the floor, but it does not
                  clear the band; a directional-but-uncertain call)."""
    if abs(margin) - band_hw >= TB["DECISIVE_WAR"]:
        return "decisive"
    if abs(margin) < TB["EDGE_FLOOR_WAR"]:
        return "even"
    return "edge"


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
    """One composed object per trade (value-based slot net, GM-attributed). Cached for the process."""
    rows = bq_service.query(f"""
        SELECT trade_id, season, trade_date, team, team_count,
               net_war_slot, net_war_slot_low, net_war_slot_high,
               has_pick, has_unresolved, horizon_incomplete, window_progress, confidence,
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
        for r in srows:
            recv = json.loads(r["received_ledger"]) if r["received_ledger"] else []
            assets = [{
                "asset_type": e["type"], "label": e["asset"],
                "war_slot": float(e.get("slot_war") or 0.0),
                "player_id": e.get("player_id"),
                "conditional": bool(e.get("conditional")),
                "unvaluable": bool(e.get("unvaluable")),
                "retention": bool(e.get("retention")),
                "retained_pct": e.get("retained_pct"),
            } for e in recv]
            recv_slot = sum(a["war_slot"] for a in assets)
            sent_slot = sum(float(e.get("slot_war") or 0.0) for e in json.loads(r["sent_ledger"] or "[]"))
            gm_id, gm_name, transition = _attribute(r["team"], tdate)
            total_war += recv_slot
            sides.append({
                "team_id": team_ids.get(r["team"]),
                "team_abbrev": r["team"],
                "gm_id": gm_id, "gm_name": gm_name, "gm_transition": transition,
                "slot_war_received": round(recv_slot, 2),
                "sent_slot": sent_slot,
                "net_slot": float(r["net_war_slot"] or 0.0),
                "net_slot_hw": _hw(r["net_war_slot_low"], r["net_war_slot_high"]),
                "kind": _side_kind(assets),
                "assets": assets,
            })

        # winner / margin = the side with the highest net (single value-based verdict)
        win_slot = max(range(len(sides)), key=lambda i: sides[i]["net_slot"])
        margin_slot = sides[win_slot]["net_slot"]
        band_hw_slot = sides[win_slot]["net_slot_hw"]
        verdict = _verdict(margin_slot, band_hw_slot)
        winner = sides[win_slot] if verdict != "even" else None

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

        # window_progress (seasons of the horizon observed) is written by the model; realized_year is the
        # same quantity kept for back-compat. Both equal k in "still maturing — year k of H".
        wp = meta.get("window_progress")
        realized_year = (int(wp) if wp is not None
                         else max(0, min(TB["REALIZED_HORIZON_YEARS"], latest - int(meta["season"][:4]) + 1)))
        conf_rank = {"low": 0, "medium": 1, "high": 2}
        confidence = min((r["confidence"] for r in srows), key=lambda c: conf_rank.get(c, 0))

        out.append({
            "trade_id": trade_id, "date": str(tdate), "season": meta["season"],
            "team_count": int(meta["team_count"]), "sides": sides,
            "margin_slot": round(margin_slot, 2), "band_hw_slot": round(band_hw_slot, 2),
            "winner_team_id": winner["team_id"] if winner else None,
            "winner_gm_id": winner["gm_id"] if winner else None,
            "winner_idx_slot": win_slot if winner else None,
            "verdict": verdict,
            # a trade is still maturing if EITHER side's window is unfinished (one side can be settled
            # — e.g. picks only — while the other holds a player still accruing).
            "incomplete": any(bool(r["horizon_incomplete"]) for r in srows),
            "realized_year": realized_year,
            "window_progress": realized_year,
            "is_player_for_picks": is_pfp,
            "archetype": archetype,
            "confidence": confidence,
            "total_war": round(total_war, 2),
            "timing": _timing_bucket(tdate),
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
            "net_war_slot": round(s["net_slot"], 2),
            "assets": s["assets"],
        } for s in t["sides"]],
        "margin_slot": t["margin_slot"], "band_hw_slot": t["band_hw_slot"],
        "winner_team_id": t["winner_team_id"], "winner_gm_id": t["winner_gm_id"],
        "verdict": t["verdict"], "incomplete": t["incomplete"], "realized_year": t["realized_year"],
        "window_progress": t["window_progress"],
        "is_player_for_picks": t["is_player_for_picks"], "archetype": t["archetype"],
        "confidence": t["confidence"],
    }


def _season_ok(t: dict, sf: str | None, st: str | None) -> bool:
    return (not sf or t["season"] >= sf) and (not st or t["season"] <= st)


def board(sort="lopsided", archetype=None, season_from=None, season_to=None, limit=40, offset=0) -> list:
    """The trade list. Shows EVERYTHING — settled and still-maturing — with no toggle; maturing trades
    carry their own inline callout (dashed bar, widened band, "still maturing" tag) and always sort last
    so they never interleave with settled verdicts."""
    items = [t for t in build_all()
             if _season_ok(t, season_from, season_to)
             and (not archetype or t["archetype"] == archetype or
                  (archetype == "player_for_picks" and t["is_player_for_picks"]))]
    if sort == "recent":
        items.sort(key=lambda t: t["date"], reverse=True)
    elif sort == "closest":
        items.sort(key=lambda t: t["margin_slot"])
    else:  # lopsided
        items.sort(key=lambda t: t["margin_slot"], reverse=True)
    # maturing trades always sort last (stable sort preserves the per-bucket order above).
    items.sort(key=lambda t: t["incomplete"])
    return [_to_board_item(t) for t in items[offset:offset + limit]]


def get_trade(trade_id: str) -> dict | None:
    for t in build_all():
        if t["trade_id"] == trade_id:
            return _to_board_item(t)
    return None


# --------------------------------------------------------------------------- value map / dossier
def _record_bucket(side_net: float, verdict: str, is_winner: bool) -> str:
    if verdict == "even":
        return "even"
    if is_winner:
        return "decisive_wins" if verdict == "decisive" else "edge"
    return "losses"


def _apply_ranking(entities: list) -> dict:
    """Add confidence-aware ranking fields to a list of entity dicts (one kind), IN PLACE: rank_value
    (the shrunk record — the default sort key), z (standardized distance from even, net/band_hw),
    separation ("clear"|"leans"|"noise"), and low_n. band_hw is the native uncertainty unit — no
    normal-interval factor. Returns {mu, tau2, var, mean_b2, b_range} for reporting/telemetry.

    The point-estimate spread is mostly noise, so empirical-Bayes shrinks records toward the league mean:
    tau2 (estimated true between-entity variance) is small relative to band_hw^2, B_i is small, and the
    middle of the pack collapses toward mu (~0) while genuinely separated entities keep more of their net.
    """
    cfg = TB.get("RANKING", {})
    method = cfg.get("method", "eb")
    min_settled = cfg.get("MIN_SETTLED", 5)
    clear_z, leans_z = cfg.get("CLEAR_Z", 2.0), cfg.get("LEANS_Z", 1.0)
    nets = [float(e["net_war"]) for e in entities]
    bands = [float(e["net_band_hw"]) for e in entities]
    n = len(nets)
    mu = statistics.fmean(nets) if n else 0.0
    var = statistics.variance(nets) if n > 1 else 0.0
    mean_b2 = statistics.fmean([b * b for b in bands]) if n else 0.0
    tau2 = max(0.0, var - mean_b2)        # method-of-moments true variance (clamped at 0 = "all noise")
    b_lo, b_hi = 1.0, 0.0
    for e in entities:
        b = float(e["net_band_hw"]); net = float(e["net_war"])
        z = net / b if b > 0 else 0.0
        if method == "net_minus_k":
            k = cfg.get("K", 1.0)
            rv = (1.0 if net >= 0 else -1.0) * max(0.0, abs(net) - k * b)
            B = None
        else:                              # empirical-Bayes (default)
            B = tau2 / (tau2 + b * b) if (tau2 + b * b) > 0 else 0.0
            rv = mu + B * (net - mu)
            b_lo, b_hi = min(b_lo, B), max(b_hi, B)
        e["rank_value"] = round(rv, 2)
        e["z"] = round(z, 2)
        e["separation"] = "clear" if abs(z) >= clear_z else "leans" if abs(z) >= leans_z else "noise"
        e["low_n"] = int(e.get("settled_count", 0)) < min_settled
    return {"mu": round(mu, 3), "tau2": round(tau2, 3), "var": round(var, 3),
            "mean_b2": round(mean_b2, 3), "b_range": (round(b_lo, 3), round(b_hi, 3)) if method == "eb" else None}


def _entity_sides(kind: str, sf, st, include_incomplete: bool = False):
    """Yield (entity_id, label, color_abbrev, side_idx, side, trade) for each entity-side under the
    filter. Incomplete (still-maturing) trades are yielded only when include_incomplete is set; callers
    that aggregate settled-by-default pass True and gate on t["incomplete"] themselves so they can still
    count incomplete trades without letting them contribute to the net."""
    for t in build_all():
        if not _season_ok(t, sf, st):
            continue
        if t["incomplete"] and not include_incomplete:
            continue
        for i, s in enumerate(t["sides"]):
            if kind == "team":
                yield s["team_abbrev"], s["team_abbrev"], s["team_abbrev"], i, s, t
            else:
                if not s["gm_id"] or s["gm_id"] == "unknown":
                    continue
                yield s["gm_id"], (s["gm_name"] or s["gm_id"]), s["team_abbrev"], i, s, t


def value_map(kind="team", season_from=None, season_to=None) -> list:
    """One bubble per entity. Nets/records are SETTLED-ONLY (a still-maturing trade never contributes as if
    it were settled — preserves the player-still-accruing vs pick-already-full anti-bias). settled_count /
    maturing_count are returned alongside so the denominator is explicit in the UI."""
    agg: dict = {}
    # walk every side (settled + maturing) so maturing trades can be COUNTED; only settled ones aggregate.
    for eid, label, color, idx, s, t in _entity_sides(kind, season_from, season_to, include_incomplete=True):
        a = agg.setdefault(eid, {"kind": kind, "id": eid, "label": label,
                                 "team_abbrev_for_color": color, "given_up_war": 0.0, "gained_war": 0.0,
                                 "net_war": 0.0, "var": 0.0, "trade_count": 0,
                                 "settled_count": 0, "maturing_count": 0,
                                 "record": {"decisive_wins": 0, "edge": 0, "even": 0, "losses": 0},
                                 "_last": t["date"]})
        if t["date"] >= a["_last"]:               # GM bubble colored by most-recent stint's team
            a["_last"], a["team_abbrev_for_color"] = t["date"], color
        if t["incomplete"]:
            a["maturing_count"] += 1              # counted for the denominator, never in the net/record
            continue
        a["settled_count"] += 1
        a["given_up_war"] += float(s["sent_slot"] or 0.0)
        a["gained_war"] += float(s["slot_war_received"] or 0.0)
        a["net_war"] += float(s["net_slot"] or 0.0)
        a["var"] += float(s["net_slot_hw"] or 0.0) ** 2
        a["trade_count"] += 1
        is_winner = (t["winner_idx_slot"] == idx)
        a["record"][_record_bucket(0, t["verdict"], is_winner)] += 1
    out = []
    for a in agg.values():
        out.append({k: a[k] for k in ("kind", "id", "label", "team_abbrev_for_color", "trade_count",
                                      "settled_count", "maturing_count")}
                   | {"given_up_war": round(a["given_up_war"], 1), "gained_war": round(a["gained_war"], 1),
                      "net_war": round(a["net_war"], 1), "net_band_hw": round(a["var"] ** 0.5, 1),
                      "record": a["record"]})
    _apply_ranking(out)                   # adds rank_value / z / separation / low_n (confidence-aware)
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


def dossier(kind: str, entity_id: str) -> dict | None:
    """A team or GM's full record. Net / record / partners and the cumulative TIMELINE LINE are
    SETTLED-ONLY (preserves the maturing-trade anti-bias); the deal LIST shows EVERYTHING (settled +
    maturing, the latter flagged), and the timeline plots all trades as points while the cumulative
    advances only on settled ones. settled_count / maturing_count make the denominator explicit."""
    all_rows = [(idx, s, t) for eid, label, color, idx, s, t
                in _entity_sides(kind, None, None, include_incomplete=True) if eid == entity_id]
    if not all_rows:
        return None
    all_rows.sort(key=lambda x: x[2]["date"])
    settled_rows = [r for r in all_rows if not r[2]["incomplete"]]
    settled_count = len(settled_rows)
    maturing_count = len(all_rows) - settled_count
    label = (all_rows[0][1]["team_abbrev"] if kind == "team"
             else (all_rows[0][1]["gm_name"] or entity_id))

    # rollups: net / band / record over SETTLED rows only
    net = sum(float(s["net_slot"] or 0.0) for _, s, _ in settled_rows)
    var = sum(float(s["net_slot_hw"] or 0.0) ** 2 for _, s, _ in settled_rows)
    record = {"decisive_wins": 0, "edge": 0, "even": 0, "losses": 0}
    for idx, s, t in settled_rows:
        record[_record_bucket(0, t["verdict"], t["winner_idx_slot"] == idx)] += 1

    # timeline: plot ALL trades as points; the cumulative line advances only on settled trades, so a
    # maturing point sits at the carried-forward cumulative and is flagged.
    timeline, cum = [], 0.0
    for idx, s, t in all_rows:
        if not t["incomplete"]:
            cum += float(s["net_slot"] or 0.0)
        regime = (s["gm_id"] or "unknown") if kind == "team" else s["team_abbrev"]
        timeline.append({"date": t["date"], "cumulative_net_war": round(cum, 1),
                         "trade_id": t["trade_id"], "regime_key": regime, "incomplete": t["incomplete"]})

    # deal list shows EVERYTHING (ranked by realized-to-date net); best/worst are SETTLED verdicts only.
    ranked_all = sorted(all_rows, key=lambda x: float(x[1]["net_slot"] or 0.0), reverse=True)
    deal_ids = [t["trade_id"] for _, _, t in ranked_all]
    deal_items = [_to_board_item(t) for _, _, t in ranked_all]
    ranked_settled = [t["trade_id"] for _, _, t in
                      sorted(settled_rows, key=lambda x: float(x[1]["net_slot"] or 0.0), reverse=True)]

    # matchup layer (settled only): this entity's net against each opposing TEAM
    pacc: dict = {}
    for idx, s, t in settled_rows:
        net_side = float(s["net_slot"] or 0.0)
        for j, opp in enumerate(t["sides"]):
            if j == idx:
                continue
            p = pacc.setdefault(opp["team_abbrev"],
                                {"opponent": opp["team_abbrev"], "kind": "team",
                                 "trade_count": 0, "net_war": 0.0, "var": 0.0})
            p["trade_count"] += 1
            p["net_war"] += net_side
            p["var"] += float(s["net_slot_hw"] or 0.0) ** 2
    partners = sorted(
        ({"opponent": p["opponent"], "kind": p["kind"], "trade_count": p["trade_count"],
          "net_war": round(p["net_war"], 1), "band_hw": round(p["var"] ** 0.5, 1)} for p in pacc.values()),
        key=lambda p: (-p["trade_count"], -abs(p["net_war"])))
    tenures = (_gm_tenure_rows(entity_id) if kind == "gm"
               else [{"team_abbrev": entity_id, "start_date": all_rows[0][2]["date"],
                      "end_date": None, "title": None}])
    return {
        "kind": kind, "id": entity_id, "label": label, "tenures": tenures,
        "net_war": round(net, 1), "net_band_hw": round(var ** 0.5, 1), "trade_count": settled_count,
        "settled_count": settled_count, "maturing_count": maturing_count,
        "record": record, "timeline": timeline,
        "best": ranked_settled[:2], "worst": ranked_settled[-2:][::-1] if len(ranked_settled) > 1 else [],
        "deals": deal_ids, "deal_items": deal_items, "partners": partners, "caveat": CAVEAT,
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


def archetypes(season_from=None, season_to=None) -> list:
    # splits/exemplars/timing are SETTLED-ONLY; maturing trades are only COUNTED for the denominator note.
    scoped = [t for t in build_all() if _season_ok(t, season_from, season_to)]
    pool = [t for t in scoped if not t["incomplete"]]
    maturing = [t for t in scoped if t["incomplete"]]
    out = []
    for arch in ("player_for_picks", "player_for_player", "picks_for_picks", "blockbuster", "three_team"):
        ts = [t for t in pool if _matches_archetype(t, arch)]
        if not ts:
            continue
        maturing_n = sum(1 for t in maturing if _matches_archetype(t, arch))
        won = lost = even = 0
        for t in ts:
            if t["verdict"] == "even":
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
            decisive = sum(1 for t in ts if t["verdict"] != "even")
            split = {"decisive_pct": round(100 * decisive / n), "even_pct": round(100 * even / n)}
        # Exemplars as a labeled, de-duplicated list. margin_slot is always the WINNER's non-negative
        # net, so "the other way" only means something where the archetype has a real two-sided axis
        # (player vs picks). Symmetric archetypes (player-for-player, picks-for-picks, blockbuster,
        # three-team) have no such axis, so we show the two most lopsided results and the closest call
        # instead of a meaningless "other way" (which used to duplicate the closest call).
        def _ex(label, t):
            return {"label": label, "trade_id": t["trade_id"]}

        if arch == "player_for_picks":
            def _pnet(t):                                   # signed: + = the player-receiving side ahead
                ps = next((s for s in t["sides"] if s["kind"] == "player"), None)
                return ps["net_slot"] if ps else 0.0
            by = sorted(ts, key=_pnet)
            cands = [_ex("Player side's biggest win", by[-1]),
                     _ex("Pick side's biggest win", by[0]),
                     _ex("Closest call", min(ts, key=lambda t: abs(_pnet(t))))]
        else:
            srt = sorted(ts, key=lambda t: t["margin_slot"], reverse=True)
            cands = [_ex("Most lopsided", srt[0])]
            if len(srt) > 2:
                cands.append(_ex("Another lopsided result", srt[1]))
            cands.append(_ex("Closest call", min(ts, key=lambda t: t["margin_slot"])))
        seen, exemplars = set(), []
        for c in cands:                                     # distinct trades only (no duplicate cards)
            if c["trade_id"] not in seen:
                seen.add(c["trade_id"])
                exemplars.append(c)
        # timing breakdown (by date context, an honest proxy for rentals; we have dates, not cap)
        timing = []
        for b in ("deadline", "draft", "offseason", "in_season"):
            bt = [t for t in ts if t["timing"] == b]
            if bt:
                dec = sum(1 for t in bt if t["verdict"] != "even")
                timing.append({"bucket": b, "count": len(bt), "decisive_pct": round(100 * dec / len(bt))})
        out.append({"archetype": arch, "label": ARCHETYPE_LABELS[arch], "trade_count": n,
                    "settled_count": n, "maturing_count": maturing_n,
                    "split": split, "exemplars": exemplars, "timing": timing})
    return out


def thesis_summary() -> dict:
    """Headline figures for the Overview hero band — frames the dataset and the founding question.

    Every trade is graded on realized-to-date value (trades_graded = all). The decisive/edge/even SPLITS
    are computed over SETTLED trades only (an unfinished window has no hard verdict yet); settled_count and
    maturing_count are returned so the denominator behind the percentages is explicit, not hidden."""
    allt = build_all()
    graded = len(allt)
    settled = [t for t in allt if not t["incomplete"]]
    maturing_n = graded - len(settled)
    n = len(settled)                      # denominator for the verdict splits (settled only)
    if not n:
        return {"trades_graded": graded, "settled_count": 0, "maturing_count": maturing_n}
    decisive = sum(1 for t in settled if t["verdict"] == "decisive")
    edge = sum(1 for t in settled if t["verdict"] == "edge")
    even = sum(1 for t in settled if t["verdict"] == "even")
    directional = decisive + edge                 # a known directional call (clears the floor)
    fleece = max(settled, key=lambda t: t["margin_slot"])
    fleece_win = next((s for s in fleece["sides"] if s["team_id"] == fleece["winner_team_id"]), None)
    pfp = [t for t in settled if t["is_player_for_picks"]]
    pf_won = sum(1 for t in pfp if t["winner_idx_slot"] is not None
                 and t["sides"][t["winner_idx_slot"]]["kind"] == "player")
    pk_won = sum(1 for t in pfp if t["winner_idx_slot"] is not None
                 and t["sides"][t["winner_idx_slot"]]["kind"] != "player"
                 and t["verdict"] != "even")
    pfp_even = sum(1 for t in pfp if t["verdict"] == "even")
    pn = max(1, len(pfp))
    return {
        "trades_graded": graded,
        "settled_count": n,
        "maturing_count": maturing_n,
        # three-tier split over settled, with raw counts and a directional total (decisive + edge)
        "decisive_count": decisive, "edge_count": edge, "even_count": even,
        "directional_count": directional,
        "decisive_pct": round(100 * decisive / n),
        "edge_pct": round(100 * edge / n),
        "even_pct": round(100 * even / n),
        "directional_pct": round(100 * directional / n),
        "biggest_fleece": {"trade_id": fleece["trade_id"],
                           "winner": (fleece_win["team_abbrev"] if fleece_win else None),
                           "margin": fleece["margin_slot"], "date": fleece["date"]},
        "player_for_picks": {"trade_count": len(pfp),
                             "player_side_won_pct": round(100 * pf_won / pn),
                             "pick_side_won_pct": round(100 * pk_won / pn),
                             "even_pct": round(100 * pfp_even / pn)},
        "caveat": CAVEAT,
    }
