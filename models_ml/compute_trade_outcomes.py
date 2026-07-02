"""Trade-outcome retrospective (Handoff 5, Phase D) — who won each past trade, in realized WAR.

For every historical trade (stg_trades), value each moved asset on ONE value-based lens, net per team
per trade, in the SAME WAR units as mart_tradeable_assets, with wide bands combined in quadrature (the
trade engine's band propagation). A RETROSPECTIVE on realized outcomes, never a grade of the decision at
the time. Output nhl_models.trade_outcomes, one row per (trade, team).

Per asset:
  * Player asset: realized pwar_hat the acquiring team actually got, TENURE-CAPPED — summed only over
    the games he played for that team, from the trade until min(exit, trade + REALIZED_HORIZON_YEARS),
    prorating partial seasons by games for that team (_tenure_value). Unmatched player -> 0 value with a
    widened band / low confidence (never silently zero in a way that flips a verdict).
  * Pick asset: the empirical pick_value_curve value at the pick's round midpoint, career-extrapolated,
    with its band (_pick_slot). This values the SLOT — what a pick at that round is worth — and isolates
    the trade decision from the drafting that followed. A pick with no parseable round, or a draft year
    earlier than the trade, is a bad input and flagged unvaluable (distinct from a normal 0-value asset).
  * Other ("Future Considerations"): value 0, labeled (not a missing player).
  * Salary retention ("X% retained" broker row whose real post-trade club is another team): value 0,
    flagged; a cap mechanism, not an acquisition.

EVERY trade is graded on its realized-to-date value — including those whose REALIZED_HORIZON_YEARS window
has not fully elapsed. An incomplete trade is NOT dropped or zeroed: it keeps its realized-to-date net and
is flagged horizon_incomplete with window_progress (seasons observed), and its net band is WIDENED by a
maturity factor tied to how much of the horizon remains (net_trades). This is realized-only honesty about
what has happened so far — there is NO projection or expected-future value anywhere in this model.

The realized "what the pick actually became" analysis (resolving a pick to the player drafted with it)
is a SEPARATE, deferred asset-lineage tool fed by stg_draft_results — deliberately NOT part of this
value verdict, which judges the slot, not the drafting.

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
    return trades, pwar, curve


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
    that team, from `anchor` (the trade date) until the earlier of his exit from the team and the horizon
    cap. Attributed at the game level — only games for `team_id`
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
def value_assets(trades, pidx, cidx, factor, pretrade, latest, gamelog, team_ids) -> pd.DataFrame:
    rows = []
    last_data = date(latest + 1, 6, 30)      # ~end of the latest observed season
    for r in trades.itertuples(index=False):
        td = pd.to_datetime(r.trade_date).date()
        acq_id = team_ids.get(r.acquiring_team)
        slot_v = slot_hw = 0.0
        flags = {"unresolved": False, "conditional": bool(r.is_conditional),
                 "horizon_incomplete": False, "retention": False, "unvaluable": False}
        is_proxy = False
        label = r.asset
        retained_pct = None                       # % salary retained on a retention broker row

        if r.asset_type == "Player":
            pid = int(r.resolved_player_id) if pd.notna(r.resolved_player_id) else None
            # Salary-retention broker row: a "X% retained" note where the player's real post-trade club
            # is a DIFFERENT team — the retaining team facilitated the deal, it did not acquire him. It
            # carries no on-ice value and must not show as a second team "receiving" the same player.
            post = _post_team(gamelog, pid, td)
            if bool(r.is_retention) and post is not None and acq_id is not None and post != acq_id:
                flags["retention"] = True
                retained_pct = int(r.retained_pct) if pd.notna(r.retained_pct) else None
                slot_v = slot_hw = 0.0
            else:
                # tenure-capped: only the value the acquiring team realized while he was on it, prorated
                # by games for that team, up to min(exit, trade_date + horizon). Not a flat 5 seasons.
                v, hw, complete = _tenure_value(gamelog, pidx, pid, acq_id, td, _add_years(td, H), last_data)
                slot_v, slot_hw = v, hw
                flags["unresolved"] = pid is None     # unmatched player -> 0 value, widened band below
                if not complete:
                    # realized window not fully observed yet (recent trade); a row-level recency caveat
                    flags["horizon_incomplete"] = True

        elif r.asset_type == "Draft Pick":
            is_proxy = True
            overall = int(r.pick_overall_mid) if pd.notna(r.pick_overall_mid) else None
            # bad input (not a lens state): no parseable round, or a draft earlier than the trade itself
            bad = (overall is None
                   or (pd.notna(r.pick_year) and int(r.pick_year) < int(str(r.season)[:4])))
            if not bad:
                sv, lo, hi = _pick_slot(cidx, factor, overall)
                slot_v, slot_hw = sv, _hw(lo, hi)
            else:
                flags["unvaluable"] = True            # unparseable / impossible pick — flag, value 0

        else:  # Other ("Future Considerations")
            is_proxy = True
            label = r.asset  # value 0, labeled

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
            "retained_pct": retained_pct,
            "is_proxy": is_proxy, **flags,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- net per (trade, team)
def _clean_id(v):
    """None for None/NaN (DataFrame.to_dict turns None ids into NaN), else int."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return int(v)


def _ledger_entry(a: dict, direction: str) -> dict:
    return {"asset": a["label"], "type": a["asset_type"], "direction": direction,
            "player_id": _clean_id(a["resolved_player_id"]),
            "slot_war": a["slot_war"],
            "conditional": a["conditional"], "unresolved": a["unresolved"],
            "unvaluable": a.get("unvaluable", False),
            "retention": a.get("retention", False), "retained_pct": _clean_id(a.get("retained_pct"))}


def net_trades(av: pd.DataFrame, latest: int) -> pd.DataFrame:
    out = []
    scale = float(T.get("MATURITY_BAND_SCALE", 1.0))
    for trade_id, g in av.groupby("trade_id"):
        teams = set(g["acquiring_team"]) | set(t for t in g["from_team"] if t)
        meta = g.iloc[0]
        # seasons of the horizon observed in our data so far (clamped to [0, H]). A trade from the latest
        # season is 1 in; older trades are further along; >= H means the window has fully elapsed.
        season_start = int(str(meta["season"])[:4])
        years_elapsed = max(0, min(H, latest - season_start + 1))
        # remaining-window fraction (0 when settled, ->1 for a brand-new trade); widens the band only.
        maturity = (H - years_elapsed) / H if H else 0.0
        for team in sorted(teams):
            recv = g[g.acquiring_team == team]
            sent = g[g.from_team == team]
            net = var = 0.0
            for sub, sign in ((recv, 1.0), (sent, -1.0)):
                net += sign * sub["slot_war"].sum()
                var += (sub["slot_hw"] ** 2).sum()
            hw = math.sqrt(var)
            side = pd.concat([recv, sent])
            has_pick = bool((side.asset_type == "Draft Pick").any())
            has_other = bool((side.asset_type == "Other").any())
            # unmatched PLAYER on this side -> wider band / lower confidence (never a flipped verdict)
            has_unresolved = bool(side["unresolved"].any())
            horizon_incomplete = bool(side["horizon_incomplete"].any())
            # Maturity band: an unfinished window keeps its realized-to-date net but the band is widened
            # to reflect value still accruing (realized-only honesty, NOT a projection of future value).
            # Added uncertainty scales with how much of the horizon remains, combined in quadrature.
            if horizon_incomplete and maturity > 0:
                extra = scale * maturity * abs(net)
                hw = math.sqrt(hw ** 2 + extra ** 2)
            confidence = "low" if (has_pick or has_other or has_unresolved or horizon_incomplete) else "medium"
            out.append({
                "trade_id": trade_id, "season": meta["season"], "trade_date": meta["trade_date"],
                "team": team, "team_count": int(meta["team_count"]),
                "net_war_slot": round(net, 3),
                "net_war_slot_low": round(net - hw, 3),
                "net_war_slot_high": round(net + hw, 3),
                "received_count": int(len(recv)), "sent_count": int(len(sent)),
                "has_pick": has_pick, "has_unresolved": has_unresolved,
                "horizon_incomplete": horizon_incomplete,
                "window_progress": years_elapsed,   # seasons of the horizon observed (k in "year k of H")
                "confidence": confidence,
                "received_ledger": json.dumps([_ledger_entry(a, "in") for a in recv.to_dict("records")]),
                "sent_ledger": json.dumps([_ledger_entry(a, "out") for a in sent.to_dict("records")]),
                "model_version": T["MODEL_VERSION"],
            })
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- report
def _report(av: pd.DataFrame, outc: pd.DataFrame) -> None:
    print(f"\ntrade_outcomes: {len(outc)} (trade, team) rows over {outc.trade_id.nunique()} trades")
    # graded funnel: every trade is graded on realized-to-date value; settled = window fully elapsed,
    # incomplete = still maturing (graded with a widened band, not dropped).
    per_trade = outc.groupby("trade_id")["horizon_incomplete"].any()
    graded = int(per_trade.size)
    incomplete = int(per_trade.sum())
    settled = graded - incomplete
    print(f"  graded: {graded} (all trades) | settled (window elapsed): {settled} | "
          f"incomplete (still maturing): {incomplete}")
    print(f"  assets: {len(av)} | players {int((av.asset_type=='Player').sum())} "
          f"(unmatched {int(av.unresolved.sum())}) | picks {int((av.asset_type=='Draft Pick').sum())} "
          f"(unvaluable {int(av.unvaluable.sum())}) | other {int((av.asset_type=='Other').sum())}")
    print(f"  confidence: " + ", ".join(f"{k}={v}" for k, v in outc.confidence.value_counts().items()))
    print("\n  Biggest one-sided wins by net realized WAR (settled):")
    settled_rows = outc[~outc.horizon_incomplete]
    for _, r in settled_rows.sort_values("net_war_slot", ascending=False).head(8).iterrows():
        print(f"    {r.trade_date} {r.team:4s} +{r.net_war_slot:5.1f} WAR "
              f"[{r.net_war_slot_low:.1f},{r.net_war_slot_high:.1f}] ({r.trade_id})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sample", type=int, default=0, help="only the first N trades (slice-verify)")
    args = ap.parse_args()

    trades, pwar, curve = _load()
    if args.sample:
        keep = trades["trade_id"].drop_duplicates().head(args.sample)
        trades = trades[trades.trade_id.isin(keep)]
    latest = int(pwar["start_year"].max())
    pidx = _pwar_index(pwar)
    cidx, factor = _curve_index(curve)
    pretrade = _pretrade_teams(trades)
    team_ids = _team_id_map()

    # the players whose tenure we need to value: the traded PLAYER assets (picks are valued by slot)
    need_ids = {int(r.resolved_player_id) for r in trades.itertuples(index=False)
                if r.asset_type == "Player" and pd.notna(r.resolved_player_id)}
    gamelog = _load_gamelog(need_ids)
    print(f"loaded {trades.trade_id.nunique()} trades; latest pwar season start={latest}; "
          f"career-extrap x{factor:.2f}; horizon={H}y; gamelog players={len(gamelog)}")

    av = value_assets(trades, pidx, cidx, factor, pretrade, latest, gamelog, team_ids)
    outc = net_trades(av, latest)
    _report(av, outc)

    if args.dry_run or args.sample:
        print("\n[dry-run/sample] not written")
        return
    bq.write_df(outc, "trade_outcomes", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["team", "season"])
    print(f"\nWrote {len(outc)} rows to nhl_models.trade_outcomes.")


if __name__ == "__main__":
    main()
