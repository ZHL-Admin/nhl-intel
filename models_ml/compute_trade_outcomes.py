"""Trade-outcome retrospective (Handoff 5, Phase D) — who won each past trade, in realized WAR.

For every historical trade (stg_trades), value each moved asset two ways and net per team per trade
under each lens, in the SAME WAR units as mart_tradeable_assets, with wide bands combined in quadrature
(the trade engine's band propagation). This is a RETROSPECTIVE on realized outcomes, never a grade of
the decision at the time — the information available then was different. Output nhl_models.trade_outcomes,
one row per (trade, team).

Two lenses, per asset:
  * Player asset (both lenses): realized pwar_hat summed over REALIZED_HORIZON_YEARS seasons from the
    trade date. Unmatched / never-played = 0 (not missing).
  * Pick asset, SLOT lens (headline): the empirical pick_value_curve career-extrapolated value at the
    pick's round midpoint, with its band. No censoring; isolates the trade decision (what the slot was
    worth), not the drafting execution.
  * Pick asset, ACTUAL lens (secondary): resolve the pick to the giving team's own pick that year/round
    (stg_draft_results) and take THAT player's realized pwar over their first REALIZED_HORIZON_YEARS
    post-draft seasons. Conflates trade and drafting; flags the own-pick assumption; censors 2019+ drafts
    (incomplete careers).
  * Other ("Future Considerations"): value 0, labeled (not a missing player).
  * Conditional picks (notes flag): valued at expectation under both lenses, flagged conditional.

from_team (who SENT each asset): the other team in a two-team trade (stg_trades.giving_team); for
three-team trades, the player's pre-trade NHL team (players) — picks/other in 3-team deals are flagged.

Run:
    python -m models_ml.compute_trade_outcomes --dry-run
    python -m models_ml.compute_trade_outcomes --sample 50      # first 50 trades (slice-verify)
    python -m models_ml.compute_trade_outcomes                  # writes nhl_models.trade_outcomes
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd

from models_ml import bq, config

T = config.TRADE_OUTCOMES
H = T["REALIZED_HORIZON_YEARS"]


# --------------------------------------------------------------------------- inputs
def _load():
    P = bq.project()
    trades = bq.query_df(f"""
        select trade_id, season, trade_date, trade_label, acquiring_team, giving_team, team_count,
               asset_type, asset, position, pos_group, is_conditional, is_retention, retained_pct,
               pick_year, pick_round, pick_overall_mid, resolved_player_id, match_method
        from `{P}.nhl_staging.stg_trades`
        order by trade_date, trade_id
    """)
    pwar = bq.query_df(f"""
        select player_id, cast(substr(season,1,4) as int64) as start_year, pwar_hat, pwar_sd
        from `{P}.nhl_models.player_pwar`
    """)
    curve = bq.query_df(f"""
        select overall_pick, ev_mean_smooth, p10_smooth, p90_smooth, career_extrap_factor
        from `{P}.nhl_models.pick_value_curve`
    """)
    draft = bq.query_df(f"""
        select draft_year, round, draft_team_abbrev, resolved_player_id, full_name
        from `{P}.nhl_staging.stg_draft_results`
        where resolved_player_id is not null
    """)
    return trades, pwar, curve, draft


def _pwar_index(pwar: pd.DataFrame) -> dict:
    """player_id -> {start_year: (pwar_hat, pwar_sd)}."""
    idx: dict[int, dict[int, tuple[float, float]]] = {}
    for r in pwar.itertuples(index=False):
        idx.setdefault(int(r.player_id), {})[int(r.start_year)] = (
            float(r.pwar_hat or 0.0), float(r.pwar_sd or 0.0))
    return idx


def _curve_index(curve: pd.DataFrame) -> tuple[dict, float]:
    factor = float(curve["career_extrap_factor"].iloc[0] or 1.0)
    idx = {int(r.overall_pick): (float(r.ev_mean_smooth), float(r.p10_smooth), float(r.p90_smooth))
           for r in curve.itertuples(index=False)}
    return idx, factor


def _draft_index(draft: pd.DataFrame) -> dict:
    """(draft_year, round, team_abbrev) -> [(player_id, name), ...] (the team's picks that round)."""
    idx: dict[tuple, list[tuple]] = {}
    for r in draft.itertuples(index=False):
        idx.setdefault((int(r.draft_year), int(r.round), r.draft_team_abbrev), []).append(
            (int(r.resolved_player_id), r.full_name))
    return idx


# --------------------------------------------------------------------------- horizon / valuation
def _pick_slot(cidx: dict, factor: float, overall: int) -> tuple[float, float, float]:
    """Career-extrapolated slot value + band at an overall pick (clamped to the curve domain)."""
    if overall not in cidx:
        keys = cidx.keys()
        overall = min(max(overall, min(keys)), max(keys))
    mean, p10, p90 = cidx[overall]
    return mean * factor, p10 * factor, p90 * factor


def _hw(lo, hi) -> float:
    return abs(float(hi) - float(lo)) / 2.0


def _add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:                       # Feb 29 -> Feb 28
        return d.replace(year=d.year + n, day=28)


def _team_id_map() -> dict:
    """Current franchise abbrev -> team_id (most recent abbrev per id). Note: relocated franchises
    (ARI->UTA, ATL->WPG) map the CURRENT abbrev, so pre-relocation games under the old id will not
    match the acquiring team — a documented under-credit edge case for those few clubs."""
    P = bq.project()
    df = bq.query_df(f"""
        select team_id, array_agg(team_abbrev order by game_date desc limit 1)[offset(0)] as abbrev
        from `{P}.nhl_mart.mart_team_game_stats`
        where team_abbrev is not null
        group by team_id
    """)
    return {r.abbrev: int(r.team_id) for r in df.itertuples(index=False)}


def _load_gamelog(player_ids: set) -> dict:
    """player_id -> sorted [(game_date, season, team_id)] over NHL regular+playoff games. The
    game-level player-to-team feed (the substr('02','03') game-type filter) used to cap accrual to a
    player's tenure with the acquiring team and prorate partial seasons by games actually played."""
    if not player_ids:
        return {}
    ids = ",".join(str(int(p)) for p in player_ids)
    P = bq.project()
    df = bq.query_df(f"""
        select player_id, game_date, season, team_id
        from `{P}.nhl_mart.mart_player_game_stats`
        where substr(cast(game_id as string), 5, 2) in ('02', '03')
          and player_id in ({ids})
    """)
    log: dict[int, list] = defaultdict(list)
    for r in df.itertuples(index=False):
        log[int(r.player_id)].append((pd.to_datetime(r.game_date).date(), r.season, int(r.team_id)))
    for v in log.values():
        v.sort()
    return log


def _post_team(log: dict, pid: int | None, anchor: date) -> int | None:
    """The team_id of the player's first NHL game strictly after `anchor` — his real post-trade club.
    Used to tell a salary-retention broker (a team that 'received' a player it never iced) from the
    team that actually acquired him."""
    if pid is None:
        return None
    for (d, _s, tid) in (log.get(pid) or []):
        if d > anchor:
            return tid
    return None


def _tenure_value(log: dict, pidx: dict, pid: int | None, team_id: int | None,
                  anchor: date, horizon_end: date, last_data: date) -> tuple[float, float, bool]:
    """Realized pWAR the acquiring team actually got from a received PLAYER: the player's value while on
    that team, from `anchor` (the trade, or the draft for the pick actual-lens) until the earlier of his
    exit from the team and the horizon cap. Attributed at the game level — only games for `team_id`
    count — and partial seasons prorate by games played for that team over the player's total games that
    season. never-played / unmatched / unmapped -> 0 (not missing).

    Exit = the first game the player plays for a DIFFERENT team after the anchor (roster feed is the
    source of truth; this captures trade-driven and free-agent departures alike). After he leaves, he
    has no games for the team, so a later return (a separate stint) is correctly excluded."""
    if pid is None or team_id is None:
        return 0.0, 0.0, True
    games = log.get(pid)
    if not games:
        return 0.0, 0.0, True
    exit_date = None
    for (d, _s, tid) in games:
        if d > anchor and tid != team_id:
            exit_date = d
            break
    cap = horizon_end if exit_date is None else min(exit_date, horizon_end)
    gft: dict[str, int] = defaultdict(int)   # games for the team, in [anchor, cap], per season
    tot: dict[str, int] = defaultdict(int)   # the player's total games per season (the proration base)
    for (d, s, tid) in games:
        tot[s] += 1
        if tid == team_id and anchor <= d <= cap:
            gft[s] += 1
    seasons_pw = pidx.get(pid, {})
    val = var = 0.0
    for s, n in gft.items():
        if n == 0:
            continue
        sy = int(s[:4])
        if sy in seasons_pw:
            v, sd = seasons_pw[sy]
            frac = n / tot[s] if tot[s] else 0.0
            val += v * frac
            var += (sd * frac) ** 2
    # complete once we have observed his exit (tenure fully seen) or the horizon has elapsed in our data
    complete = (exit_date is not None) or (horizon_end <= last_data)
    return val, math.sqrt(var), complete


# --------------------------------------------------------------------------- pre-trade team (3-team)
def _pretrade_teams(trades: pd.DataFrame) -> dict:
    """For player assets in 3-team trades, the player's last NHL team strictly before the trade date."""
    need = trades[(trades.team_count >= 3) & (trades.asset_type == "Player")
                  & trades.resolved_player_id.notna()][["resolved_player_id", "trade_date"]].drop_duplicates()
    if need.empty:
        return {}
    pairs = ", ".join(
        f"struct({int(r.resolved_player_id)} as pid, date('{pd.to_datetime(r.trade_date).date()}') as td)"
        for r in need.itertuples(index=False))
    P = bq.project()
    df = bq.query_df(f"""
        with need as (select * from unnest([{pairs}])),
        last_team as (
            select n.pid, n.td,
                   array_agg(g.team_id order by g.game_date desc limit 1)[offset(0)] as team_id
            from need n
            join `{P}.nhl_mart.mart_player_game_stats` g
              on g.player_id = n.pid and g.game_date < n.td
            group by 1, 2
        )
        select l.pid, l.td, any_value(t.team_abbrev) as pre_team
        from last_team l
        join `{P}.nhl_mart.mart_team_game_stats` t on t.team_id = l.team_id
        group by 1, 2
    """)
    return {(int(r.pid), pd.to_datetime(r.td).date()): r.pre_team for r in df.itertuples(index=False)}


# --------------------------------------------------------------------------- per-asset valuation
def value_assets(trades, pidx, cidx, factor, didx, pretrade, latest, gamelog, team_ids) -> pd.DataFrame:
    rows = []
    last_data = date(latest + 1, 6, 30)      # ~end of the latest observed season
    for r in trades.itertuples(index=False):
        td = pd.to_datetime(r.trade_date).date()
        acq_id = team_ids.get(r.acquiring_team)
        slot_v = slot_hw = act_v = act_hw = 0.0
        flags = {"unresolved": False, "conditional": bool(r.is_conditional),
                 "actual_censored": False, "own_pick_assumed": False, "actual_unresolved": False,
                 "horizon_incomplete": False, "retention": False}
        is_proxy = False
        label = r.asset
        became_id, became_name = None, None      # the player a pick became (actual lens, for linking)

        if r.asset_type == "Player":
            pid = int(r.resolved_player_id) if pd.notna(r.resolved_player_id) else None
            # Salary-retention broker row: a "X% retained" note where the player's real post-trade club
            # is a DIFFERENT team — the retaining team facilitated the deal, it did not acquire him. It
            # carries no on-ice value and must not show as a second team "receiving" the same player.
            post = _post_team(gamelog, pid, td)
            if bool(r.is_retention) and post is not None and acq_id is not None and post != acq_id:
                flags["retention"] = True
                pct = int(r.retained_pct) if pd.notna(r.retained_pct) else None
                label = f"{r.asset} — {pct}% retained" if pct else f"{r.asset} — retained salary"
                slot_v = act_v = slot_hw = act_hw = 0.0
            else:
                # tenure-capped: only the value the acquiring team realized while he was on it, prorated
                # by games for that team, up to min(exit, trade_date + horizon). Not a flat 5 seasons.
                v, hw, complete = _tenure_value(gamelog, pidx, pid, acq_id, td, _add_years(td, H), last_data)
                slot_v = act_v = v
                slot_hw = act_hw = hw
                flags["unresolved"] = pid is None
                if not complete:
                    # realized window not fully observed yet (recent trade); a row-level recency caveat
                    flags["horizon_incomplete"] = True

        elif r.asset_type == "Draft Pick":
            is_proxy = True
            overall = int(r.pick_overall_mid) if pd.notna(r.pick_overall_mid) else None
            if overall is not None:
                sv, lo, hi = _pick_slot(cidx, factor, overall)
                slot_v, slot_hw = sv, _hw(lo, hi)
            # actual-player lens: the player the ACQUIRING team drafted in that round (the team that
            # received the pick is the one most likely to have used it). Assumption flagged; when the
            # acquirer flipped the pick or made multiple/zero picks in that round it stays unresolved.
            key = (int(r.pick_year), int(r.pick_round), r.acquiring_team) if pd.notna(r.pick_year) else None
            pids = didx.get(key, []) if key else []
            if len(pids) == 1:
                flags["own_pick_assumed"] = True       # resolved via the acquirer's selection that round
                became_id, became_name = pids[0]
                dy = int(r.pick_year)
                # same tenure cap: credit the drafted player's value only while on the drafting team
                # (assumed = the acquirer), from the draft to min(exit, draft + horizon).
                anchor = date(dy, 7, 1)
                av, ahw, complete = _tenure_value(gamelog, pidx, became_id, acq_id, anchor,
                                                  _add_years(anchor, H), last_data)
                act_v, act_hw = av, ahw
                if not complete:
                    flags["actual_censored"] = True   # 2019+ drafts: incomplete realized career
            else:
                flags["actual_unresolved"] = True      # pick flipped / ambiguous / unmatched draft slot

        else:  # Other ("Future Considerations")
            is_proxy = True
            label = r.asset  # value 0 both lenses, labeled

        # who sent this asset (for netting)
        from_team = r.giving_team
        if from_team is None and r.asset_type == "Player" and pd.notna(r.resolved_player_id):
            from_team = pretrade.get((int(r.resolved_player_id), td))
        if flags["retention"]:
            from_team = None     # a retention is a cap mechanism, not a player move charged to a team

        rows.append({
            "trade_id": r.trade_id, "season": r.season, "trade_date": td, "team_count": int(r.team_count),
            "acquiring_team": r.acquiring_team, "from_team": from_team,
            "asset_type": r.asset_type, "label": label, "position": r.position,
            "resolved_player_id": (int(r.resolved_player_id) if pd.notna(r.resolved_player_id) else None),
            "slot_war": round(slot_v, 3), "slot_hw": round(slot_hw, 3),
            "actual_war": round(act_v, 3), "actual_hw": round(act_hw, 3),
            "became_player_id": became_id, "became_player_name": became_name,
            "is_proxy": is_proxy, **flags,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- net per (trade, team)
def _clean_id(v):
    """None for None/NaN (DataFrame.to_dict turns None ids into NaN), else int."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return int(v)


def _clean_str(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return str(v)


def _ledger_entry(a: dict, direction: str) -> dict:
    return {"asset": a["label"], "type": a["asset_type"], "direction": direction,
            "player_id": _clean_id(a["resolved_player_id"]),
            "became_player_id": _clean_id(a["became_player_id"]),
            "became_player_name": _clean_str(a["became_player_name"]),
            "slot_war": a["slot_war"], "actual_war": a["actual_war"],
            "conditional": a["conditional"], "unresolved": a["unresolved"],
            "own_pick_assumed": a["own_pick_assumed"], "actual_unresolved": a["actual_unresolved"],
            "retention": a.get("retention", False)}


def net_trades(av: pd.DataFrame) -> pd.DataFrame:
    out = []
    for trade_id, g in av.groupby("trade_id"):
        teams = set(g["acquiring_team"]) | set(t for t in g["from_team"] if t)
        meta = g.iloc[0]
        for team in sorted(teams):
            recv = g[g.acquiring_team == team]
            sent = g[g.from_team == team]
            acc = {"slot": 0.0, "slot_var": 0.0, "actual": 0.0, "actual_var": 0.0}
            for sub, sign in ((recv, 1.0), (sent, -1.0)):
                acc["slot"] += sign * sub["slot_war"].sum()
                acc["actual"] += sign * sub["actual_war"].sum()
                acc["slot_var"] += (sub["slot_hw"] ** 2).sum()
                acc["actual_var"] += (sub["actual_hw"] ** 2).sum()
            slot_hw, act_hw = math.sqrt(acc["slot_var"]), math.sqrt(acc["actual_var"])
            side = pd.concat([recv, sent])
            has_pick = bool((side.asset_type == "Draft Pick").any())
            has_other = bool((side.asset_type == "Other").any())
            has_unresolved = bool(side["unresolved"].any())
            actual_censored = bool(side["actual_censored"].any()) or bool(side["actual_unresolved"].any())
            horizon_incomplete = bool(side["horizon_incomplete"].any())
            confidence = "low" if (has_pick or has_other or has_unresolved) else "medium"
            out.append({
                "trade_id": trade_id, "season": meta["season"], "trade_date": meta["trade_date"],
                "team": team, "team_count": int(meta["team_count"]),
                "net_war_slot": round(acc["slot"], 3),
                "net_war_slot_low": round(acc["slot"] - slot_hw, 3),
                "net_war_slot_high": round(acc["slot"] + slot_hw, 3),
                "net_war_actual": round(acc["actual"], 3),
                "net_war_actual_low": round(acc["actual"] - act_hw, 3),
                "net_war_actual_high": round(acc["actual"] + act_hw, 3),
                "received_count": int(len(recv)), "sent_count": int(len(sent)),
                "has_pick": has_pick, "has_unresolved": has_unresolved,
                "actual_censored": actual_censored, "horizon_incomplete": horizon_incomplete,
                "confidence": confidence,
                "received_ledger": json.dumps([_ledger_entry(a, "in") for a in recv.to_dict("records")]),
                "sent_ledger": json.dumps([_ledger_entry(a, "out") for a in sent.to_dict("records")]),
                "model_version": T["MODEL_VERSION"],
            })
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- report
def _report(av: pd.DataFrame, outc: pd.DataFrame) -> None:
    print(f"\ntrade_outcomes: {len(outc)} (trade, team) rows over {outc.trade_id.nunique()} trades")
    n_assets = len(av)
    print(f"  assets: {n_assets} | players {int((av.asset_type=='Player').sum())} "
          f"(unresolved {int(av.unresolved.sum())}) | picks {int((av.asset_type=='Draft Pick').sum())} "
          f"(own-pick resolved {int(av.own_pick_assumed.sum())}, actual-unresolved {int(av.actual_unresolved.sum())}) "
          f"| other {int((av.asset_type=='Other').sum())}")
    print(f"  confidence: " + ", ".join(f"{k}={v}" for k, v in outc.confidence.value_counts().items()))
    print("\n  Biggest one-sided wins by net realized WAR (SLOT lens):")
    top = outc.sort_values("net_war_slot", ascending=False).head(8)
    for _, r in top.iterrows():
        print(f"    {r.trade_date} {r.team:4s} +{r.net_war_slot:5.1f} WAR "
              f"[{r.net_war_slot_low:.1f},{r.net_war_slot_high:.1f}] ({r.trade_id})")
    print("\n  Spot-check (actual lens, biggest wins):")
    for _, r in outc.sort_values("net_war_actual", ascending=False).head(5).iterrows():
        print(f"    {r.trade_date} {r.team:4s} +{r.net_war_actual:5.1f} WAR actual ({r.trade_id})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sample", type=int, default=0, help="only the first N trades (slice-verify)")
    args = ap.parse_args()

    trades, pwar, curve, draft = _load()
    if args.sample:
        keep = trades["trade_id"].drop_duplicates().head(args.sample)
        trades = trades[trades.trade_id.isin(keep)]
    latest = int(pwar["start_year"].max())
    pidx = _pwar_index(pwar)
    cidx, factor = _curve_index(curve)
    didx = _draft_index(draft)
    pretrade = _pretrade_teams(trades)
    team_ids = _team_id_map()

    # the players whose tenure we need to value: traded players + the players picks became
    need_ids: set = set()
    for r in trades.itertuples(index=False):
        if r.asset_type == "Player" and pd.notna(r.resolved_player_id):
            need_ids.add(int(r.resolved_player_id))
        elif r.asset_type == "Draft Pick" and pd.notna(r.pick_year) and pd.notna(r.pick_round):
            pids = didx.get((int(r.pick_year), int(r.pick_round), r.acquiring_team), [])
            if len(pids) == 1:
                need_ids.add(pids[0][0])
    gamelog = _load_gamelog(need_ids)
    print(f"loaded {trades.trade_id.nunique()} trades; latest pwar season start={latest}; "
          f"career-extrap x{factor:.2f}; horizon={H}y; gamelog players={len(gamelog)}")

    av = value_assets(trades, pidx, cidx, factor, didx, pretrade, latest, gamelog, team_ids)
    outc = net_trades(av)
    _report(av, outc)

    if args.dry_run or args.sample:
        print("\n[dry-run/sample] not written")
        return
    bq.write_df(outc, "trade_outcomes", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["team", "season"])
    print(f"\nWrote {len(outc)} rows to nhl_models.trade_outcomes.")


if __name__ == "__main__":
    main()
