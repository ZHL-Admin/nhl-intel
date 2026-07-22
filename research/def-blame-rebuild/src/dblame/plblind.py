"""Puck-loss (TURNOVER ledger) blind sample · deterministic cold-review gate for the newest ledger.

Selects 10 goals the TURNOVER ledger CHARGES (severity >= 0.2), ordered by md5(game_id-event_id), excluding
every previously-surfaced goal (the 8 validation, 12 holdout, 10 pinned-rush, and 10 prior blind-sample
goals) so the set is genuinely cold. Produces two SEPARATED outputs:
  (a) reports/puckloss_blindsample.md          — goal id / teams / scorer / date / clock. NO model answer.
  (b) reports/puckloss_blindsample_WITHHELD.md  — the charged turnover player + severity, WRITTEN but NOT
                                                  shown until the owner's cold rulings are returned.
Selection is not model-chosen: md5 ordering + the sev>=0.2 charge gate only. Scorer resolved season-correct
from stg_rosters (avoids the current-roster cross-season sweater bug).
"""
from __future__ import annotations

import hashlib

import polars as pl

from . import config as C, events2 as E2

BLINDSHEET = C.REPORTS / "puckloss_blindsample.md"
WITHHELD = C.REPORTS / "puckloss_blindsample_WITHHELD.md"
CHARGE_MIN = 0.2
N = 10

# previously-surfaced goals — all excluded so this cold gate is fresh
VALIDATION = {(2025020152, 309), (2025020711, 112), (2025020520, 1017), (2025020985, 153),
              (2025020390, 554), (2025020332, 299), (2025020798, 697), (2025020754, 381)}
HOLDOUT = {(2025021201, 516), (2025020505, 552), (2025020473, 841), (2025020899, 530), (2025020530, 1098),
           (2025021187, 121), (2025020870, 917), (2025020662, 682), (2025020517, 56), (2025020850, 875),
           (2025021306, 492), (2025020969, 484)}
OLD_BLINDSAMPLE = {(2024020981, 427), (2023020725, 734), (2023021063, 1024), (2023020738, 218),
                   (2025020609, 631), (2025020851, 201), (2023020437, 215), (2024020262, 798),
                   (2025021297, 756), (2025021279, 120)}


def _md5(gid, eid) -> str:
    return hashlib.md5(f"{gid}-{eid}".encode()).hexdigest()


def _pinned() -> set:
    p = C.REPORTS / "rushdef_pinned.csv"
    if not p.exists():
        return set()
    return {(r["game_id"], r["event_id"]) for r in pl.read_csv(p).iter_rows(named=True)}


def select() -> list:
    rec = pl.read_parquet(E2.REC)
    charged = rec.filter((pl.col("ledger") == "PUCK_LOSS") & (pl.col("event_type") == "TURNOVER")
                         & (pl.col("severity") >= CHARGE_MIN))
    excl = VALIDATION | HOLDOUT | OLD_BLINDSAMPLE | _pinned()
    rows = [(r["game_id"], r["event_id"]) for r in charged.select("game_id", "event_id").unique().iter_rows(named=True)]
    rows = [ge for ge in rows if ge not in excl]
    rows.sort(key=lambda ge: _md5(ge[0], ge[1]))
    return rows[:N]


def write() -> dict:
    from google.cloud import bigquery
    picked = select()
    keys = pl.DataFrame(picked, schema=["game_id", "event_id"], orient="row")
    rec = pl.read_parquet(E2.REC)
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "season", "game_date", "home_team_id",
                                               "away_team_id", "scoring_team_id", "scorer_id", "period",
                                               "game_clock_seconds").join(keys, on=["game_id", "event_id"], how="inner")
    fmap = {(r["game_id"], r["event_id"]): r for r in fused.iter_rows(named=True)}

    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    tm = {r.team_id: r.team_abbrev for r in bq.query(
        f"select distinct team_id, team_abbrev from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where team_abbrev is not null").result()}

    def scn(pid, season):
        if pid is None:
            return ("?", "?")
        q = list(bq.query(f"select min(concat(first_name,' ',last_name)) n, max(sweater_number) sw "
                          f"from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where player_id={pid} and season='{season}'").result())
        return (q[0].n, q[0].sw) if q and q[0].n else (str(pid), "?")

    ordered = sorted(picked, key=lambda ge: _md5(ge[0], ge[1]))

    # (a) BLIND SHEET — no model answer
    B = []; W = B.append
    W("# Puck-loss (TURNOVER ledger) — blind sample of 10 charged turnovers (cold tape-review)\n")
    W(f"The final cold-review gate for the turnover ledger (the newest, now-integrated & deterministic ledger). "
      f"Deterministically selected: goals the turnover ledger CHARGES (severity >= {CHARGE_MIN}), ordered by "
      "md5(game_id-event_id), first 10 excluding every previously-surfaced goal (validation, holdout, "
      "pinned-rush, and the prior blind sample). NOT model-chosen. **No model attribution appears here.**\n")
    W("Rule each goal COLD: **was there a turnover, and by whom?** (a giveaway that directly/dangerously "
      "produced the goal). A goal may legitimately have no turnover. Return your 10 rulings, then the model's "
      "charged player + severity are revealed and graded.\n")
    W("| # | game_id | event_id | date | matchup (defending vs scored) | scorer | period | clock |")
    W("|---|---|---|---|---|---|---|---|")
    for i, (gid, eid) in enumerate(ordered, 1):
        fm = fmap[(gid, eid)]
        home, away = tm.get(fm["home_team_id"], str(fm["home_team_id"])), tm.get(fm["away_team_id"], str(fm["away_team_id"]))
        scoring = tm.get(fm["scoring_team_id"], str(fm["scoring_team_id"]))
        defending = away if fm["scoring_team_id"] == fm["home_team_id"] else home
        sc = scn(fm["scorer_id"], fm["season"])
        mm, ss = divmod(int(fm["game_clock_seconds"]), 60)
        W(f"| {i} | {gid} | {eid} | {fm['game_date']} | {away}@{home} ({defending} defending, {scoring} scored) "
          f"| {sc[0]} #{sc[1]} | P{fm['period']} | {mm:02d}:{ss:02d} |")
    W("\n## STOP — cold owner review. Return your 10 turnover rulings before the model's answers are revealed.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    BLINDSHEET.write_text("\n".join(B))

    # (b) WITHHELD — charged turnover player + severity, written but not shown
    from .meta import load as load_meta
    nm = {r["player_id"]: (r["full_name"], r["sweater"]) for r in load_meta().to_dicts()}
    M = []; A = M.append
    A("# Puck-loss blind sample — MODEL ANSWERS (WITHHELD until owner's cold rulings are in)\n")
    A(f"Do not open until the owner's 10 cold turnover rulings are returned. Charge gate sev>={CHARGE_MIN}.\n")
    for i, (gid, eid) in enumerate(ordered, 1):
        fm = fmap[(gid, eid)]
        rr = rec.filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid)
                        & (pl.col("event_type") == "TURNOVER")).sort("severity", descending=True)
        ans = "; ".join(f"{nm.get(x['player_id'], (x['player_id'], '?'))[0]} #{nm.get(x['player_id'], ('', '?'))[1]} "
                        f"(sev {x['severity']:.2f})" for x in rr.iter_rows(named=True)) or "(none)"
        A(f"{i}. {gid}-{eid}: TURNOVER -> {ans}")
    WITHHELD.write_text("\n".join(M))
    return {"picked": len(ordered), "ids": ordered, "blindsheet": str(BLINDSHEET), "withheld": str(WITHHELD)}


if __name__ == "__main__":
    r = write()
    print(f"selected {r['picked']} charged turnovers | blind sheet: {r['blindsheet']} | withheld: {r['withheld']}")
    print("ids:", r["ids"])
