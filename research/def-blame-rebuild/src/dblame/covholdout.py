"""COVERAGE-ledger blind holdout · deterministic fresh-goal selection for a cold owner tape-review.

The final coverage gate before aggregation: the coverage ledger gained FAILURE-TO-ACCOUNT and the rush-guard
since the last coverage holdout, and neither has been cold-tested on unseen goals. Selects 12 5v5 tracked
goals (n_def=5) DETERMINISTICALLY (md5(game_id-event_id) order), first 12 that are NOT in ANY previously
surfaced set (validation, prior holdout, pinned-rush, and both turnover blind samples). Two separated outputs:
  (a) reports/cov_holdout_blindsheet.md          — goals by id/date/matchup/scorer/period-clock, NO model output.
  (b) reports/cov_holdout_model_answers_WITHHELD.md — the COVERAGE ledger per goal (per-player events + shares,
                                                     all detectors incl FTA + rush-guard flag), written but NOT
                                                     shown until the owner's cold rulings are in.
Selection is not model-chosen: md5 ordering + tracking-occupancy eligibility only.
"""
from __future__ import annotations

import hashlib

import polars as pl

from . import config as C, events2 as E2
from .data import universe
from .tracks import TRACKS

BLINDSHEET = C.REPORTS / "cov_holdout_blindsheet.md"
WITHHELD = C.REPORTS / "cov_holdout_model_answers_WITHHELD.md"
N = 12

VALIDATION = {(2025020152, 309), (2025020711, 112), (2025020520, 1017), (2025020985, 153),
              (2025020390, 554), (2025020332, 299), (2025020798, 697), (2025020754, 381)}
PRIOR_HOLDOUT = {(2025021201, 516), (2025020505, 552), (2025020473, 841), (2025020899, 530), (2025020530, 1098),
                 (2025021187, 121), (2025020870, 917), (2025020662, 682), (2025020517, 56), (2025020850, 875),
                 (2025021306, 492), (2025020969, 484)}
PLBLIND_NEW = {(2023021038, 987), (2024020835, 415), (2024020053, 443), (2024020989, 882), (2024020119, 704),
               (2025021152, 551), (2023020547, 698), (2025030111, 851), (2023021066, 673), (2023020848, 631)}
PLBLIND_OLD = {(2024020981, 427), (2023020725, 734), (2023021063, 1024), (2023020738, 218), (2025020609, 631),
               (2025020851, 201), (2023020437, 215), (2024020262, 798), (2025021297, 756), (2025021279, 120)}


# canonical NHL API team_id -> abbrev (stable), used as a fallback for franchises absent from the CURRENT
# roster table (e.g. Arizona 53, relocated to Utah 59) so cross-season matchups resolve on the blind sheet.
TEAM_ABBR = {1: "NJD", 2: "NYI", 3: "NYR", 4: "PHI", 5: "PIT", 6: "BOS", 7: "BUF", 8: "MTL", 9: "OTT",
             10: "TOR", 12: "CAR", 13: "FLA", 14: "TBL", 15: "WSH", 16: "CHI", 17: "DET", 18: "NSH", 19: "STL",
             20: "CGY", 21: "COL", 22: "EDM", 23: "VAN", 24: "ANA", 25: "DAL", 26: "LAK", 28: "SJS", 29: "CBJ",
             30: "MIN", 52: "WPG", 53: "ARI", 54: "VGK", 55: "SEA", 59: "UTA"}


def _md5(gid, eid) -> str:
    return hashlib.md5(f"{gid}-{eid}".encode()).hexdigest()


def _pinned() -> set:
    p = C.REPORTS / "rushdef_pinned.csv"
    return {(r["game_id"], r["event_id"]) for r in pl.read_csv(p).iter_rows(named=True)} if p.exists() else set()


def excluded() -> set:
    return VALIDATION | PRIOR_HOLDOUT | PLBLIND_NEW | PLBLIND_OLD | _pinned()


def select() -> list:
    kept = pl.read_parquet(TRACKS).select("game_id", "event_id").unique()
    u = universe().join(kept, on=["game_id", "event_id"], how="inner")   # 5v5 tracked, n_def=5 domain
    excl = excluded()
    rows = [(r["game_id"], r["event_id"]) for r in u.select("game_id", "event_id").unique().iter_rows(named=True)]
    rows = [ge for ge in rows if ge not in excl]
    rows.sort(key=lambda ge: _md5(ge[0], ge[1]))
    return rows[:N]


def write() -> dict:
    from google.cloud import bigquery
    from .meta import load as load_meta
    picked = sorted(select(), key=lambda ge: _md5(ge[0], ge[1]))
    keys = pl.DataFrame(picked, schema=["game_id", "event_id"], orient="row")
    rec = pl.read_parquet(E2.REC)
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "season", "game_date", "home_team_id",
                                               "away_team_id", "scoring_team_id", "scorer_id", "period",
                                               "game_clock_seconds").join(keys, on=["game_id", "event_id"], how="inner")
    fmap = {(r["game_id"], r["event_id"]): r for r in fused.iter_rows(named=True)}
    # rush-guard context: a fresh rush (entry within 4s of the goal) suppresses FTA
    uu = universe().select("game_id", "event_id", "entry_frame", "goal_frame").join(keys, on=["game_id", "event_id"], how="inner")
    rushg = {(r["game_id"], r["event_id"]): (r["entry_frame"] is not None and (r["goal_frame"] - r["entry_frame"]) <= int(4 * C.HZ))
             for r in uu.iter_rows(named=True)}

    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    tm = dict(TEAM_ABBR)   # canonical fallback (incl. relocated franchises)
    tm.update({r.team_id: r.team_abbrev for r in bq.query(
        f"select distinct team_id, team_abbrev from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where team_abbrev is not null").result()})

    def scn(pid, season):
        if pid is None:
            return ("?", "?")
        q = list(bq.query(f"select min(concat(first_name,' ',last_name)) n, max(sweater_number) sw "
                          f"from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where player_id={pid} and season='{season}'").result())
        return (q[0].n, q[0].sw) if q and q[0].n else (str(pid), "?")

    nm = {r["player_id"]: (r["full_name"], r["sweater"]) for r in load_meta().to_dicts()}

    # (a) BLIND SHEET — no model output
    B = []; W = B.append
    W("# Coverage-ledger blind holdout — 12 fresh goals (cold tape-review sheet)\n")
    W("The final COVERAGE gate before aggregation. The coverage ledger gained FAILURE-TO-ACCOUNT (soft "
      "zone-abandonment leaving a standing-open man) and the rush-guard (a fresh rush's open scorer is "
      "unsettled transition, not a coverage-account failure) since the last coverage holdout — neither has "
      "been cold-tested on unseen goals. Deterministically selected: 5v5 tracked goals (n_def=5), ordered by "
      "md5(game_id-event_id), first 12 NOT in any previously surfaced set. NOT model-chosen. **No model output "
      "here.**\n")
    W("Rule each goal COLD on the **coverage** ledger: who broke down (primary/secondary + mechanism — "
      "containment loss, over-commitment, inside-leverage, failure-to-close, soft-close on the passer, "
      "out-of-zone/over-pinch, or failure-to-account). A goal may legitimately have **no coverage culprit**, "
      "or be a **fresh rush** (transition, not a settled-coverage breakdown).\n")
    W("| # | game_id | event_id | date | matchup (defending vs scored) | scorer | period | clock |")
    W("|---|---|---|---|---|---|---|---|")
    for i, (gid, eid) in enumerate(picked, 1):
        fm = fmap[(gid, eid)]
        home, away = tm.get(fm["home_team_id"], str(fm["home_team_id"])), tm.get(fm["away_team_id"], str(fm["away_team_id"]))
        scoring = tm.get(fm["scoring_team_id"], str(fm["scoring_team_id"]))
        defending = away if fm["scoring_team_id"] == fm["home_team_id"] else home
        sc = scn(fm["scorer_id"], fm["season"])
        mm, ss = divmod(int(fm["game_clock_seconds"]), 60)
        W(f"| {i} | {gid} | {eid} | {fm['game_date']} | {away}@{home} ({defending} defending, {scoring} scored) "
          f"| {sc[0]} #{sc[1]} | P{fm['period']} | {mm:02d}:{ss:02d} |")
    W("\n## STOP — cold owner review. Return your 12 coverage rulings before the model's answers are revealed.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    BLINDSHEET.write_text("\n".join(B))

    # (b) WITHHELD — coverage ledger per goal, written but not shown
    M = []; A = M.append
    A("# Coverage-ledger blind holdout — MODEL ANSWERS (WITHHELD until owner's cold rulings are in)\n")
    A("Do not open until the owner's 12 cold coverage rulings are returned. COVERAGE ledger per goal, "
      "per-player events + shares, all detectors (E1 containment, E2 over-commitment, R3 inside-leverage, "
      "E3 failure-to-close, R6 soft-close, OUT_OF_ZONE, FTA), plus the rush-guard flag (a fresh rush "
      "suppresses FTA and routes the open scorer to transition logic).\n")
    for i, (gid, eid) in enumerate(picked, 1):
        rr = rec.filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid) & (pl.col("ledger") == "COVERAGE")).sort("severity", descending=True)
        rg = "  [RUSH-GUARDED: fresh rush, FTA suppressed]" if rushg.get((gid, eid)) else ""
        if rr.height:
            body = "; ".join(f"{x['event_type']} {nm.get(x['player_id'], (x['player_id'], '?'))[0]} "
                             f"#{nm.get(x['player_id'], ('', '?'))[1]} (sev {x['severity']:.2f}, {x['share']*100:.0f}%)"
                             for x in rr.iter_rows(named=True))
        else:
            body = "(no coverage culprit)"
        A(f"{i}. {gid}-{eid}:{rg} {body}")
    WITHHELD.write_text("\n".join(M))

    excl = excluded()
    return {"picked": len(picked), "ids": picked, "overlap": len(set(picked) & excl),
            "blindsheet": str(BLINDSHEET), "withheld": str(WITHHELD)}


if __name__ == "__main__":
    r = write()
    print(f"selected {r['picked']} coverage-holdout goals | overlap with surfaced sets: {r['overlap']}")
    print(f"blind sheet: {r['blindsheet']} | withheld: {r['withheld']}")
    print("ids:", r["ids"])
