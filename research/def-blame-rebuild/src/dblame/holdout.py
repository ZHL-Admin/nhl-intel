"""Blind holdout · deterministic fresh-goal selection for a cold owner tape-review.

Selects 12 fresh 2025-26 5v5 goals-against DETERMINISTICALLY (md5(game_id-event_id) order, first 12 not in
the validation set), on the assignment's domain (tracked, n_def=5). Produces TWO separated outputs:
  (a) reports/holdout_blindsheet.md          — the 12 goals by game/event/date/teams/scorer/period-clock,
                                                NO model output, for the owner to rule on cold.
  (b) reports/holdout_model_answers_WITHHELD.md — both ledgers per goal, WRITTEN BUT NOT SHOWN until the
                                                owner's fresh rulings are in.
Selection is not model-chosen: md5 hashing + tracking-occupancy eligibility only.
"""
from __future__ import annotations

import hashlib

import polars as pl

from . import config as C, events2 as E2
from .data import universe
from .meta import load as load_meta
from .tracks import TRACKS

VALIDATION_SET = {(2025020152, 309), (2025020711, 112), (2025020520, 1017), (2025020985, 153),
                  (2025020390, 554), (2025020332, 299), (2025020798, 697), (2025020754, 381)}
BLINDSHEET = C.REPORTS / "holdout_blindsheet.md"
WITHHELD = C.REPORTS / "holdout_model_answers_WITHHELD.md"
N = 12


def _md5(gid, eid) -> str:
    return hashlib.md5(f"{gid}-{eid}".encode()).hexdigest()


def _teams():
    from google.cloud import bigquery
    c = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    return {r.team_id: r.team_abbrev for r in c.query(
        f"select distinct team_id, team_abbrev from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where team_abbrev is not null").result()}


def select() -> pl.DataFrame:
    kept = pl.read_parquet(TRACKS).select("game_id", "event_id").unique()
    u = (universe().filter(pl.col("season") == "2025-26").join(kept, on=["game_id", "event_id"], how="inner"))
    rows = [(r["game_id"], r["event_id"]) for r in u.select("game_id", "event_id").iter_rows(named=True)]
    rows = [ge for ge in rows if ge not in VALIDATION_SET]
    rows.sort(key=lambda ge: _md5(ge[0], ge[1]))
    picked = rows[:N]
    return u.filter(pl.struct("game_id", "event_id").map_elements(
        lambda s: (s["game_id"], s["event_id"]) in set(picked), return_dtype=pl.Boolean)).with_columns(
        h=pl.struct("game_id", "event_id").map_elements(lambda s: _md5(s["game_id"], s["event_id"]), return_dtype=pl.Utf8)).sort("h")


def write():
    sel = select()
    nm = {r["player_id"]: (r["full_name"], r["sweater"]) for r in load_meta().to_dicts()}
    tm = _teams()
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "home_team_id", "away_team_id",
                                               "scoring_team_id", "period", "game_clock_seconds")
    sel = sel.join(fused, on=["game_id", "event_id"], how="left")

    # (a) BLIND SHEET — no model output
    B = []; W = B.append
    W("# Blind holdout — the 12 fresh goals (cold tape-review sheet)\n")
    W("Deterministically selected: all 2025-26 5v5 tracked goals (n_def=5), ordered by "
      "md5(game_id-event_id), first 12 not in the 8-goal validation set. NOT model-chosen. **No model "
      "output appears here.** Watch each goal, write your blame ruling (primary/secondary, mechanism) for "
      "each ledger, then return them — only then are the model's answers revealed and graded three-tier.\n")
    W("| # | game_id | event_id | date | matchup (scorer's team defends vs) | scorer | period | clock |")
    W("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(sel.iter_rows(named=True), 1):
        home, away = tm.get(r["home_team_id"], r["home_team_id"]), tm.get(r["away_team_id"], r["away_team_id"])
        scoring = tm.get(r["scoring_team_id"], r["scoring_team_id"])
        defending = away if r["scoring_team_id"] == r["home_team_id"] else home
        sc = nm.get(r["scorer_id"], (str(r["scorer_id"]), "?"))
        mm, ss = divmod(int(r["game_clock_seconds"]), 60)
        W(f"| {i} | {r['game_id']} | {r['event_id']} | {r['game_date']} | {away}@{home} "
          f"({defending} defending, {scoring} scored) | {sc[0]} #{sc[1]} | P{r['period']} | {mm:02d}:{ss:02d} |")
    W("\n**Ledgers to rule on per goal:** PUCK-LOSS (who lost the puck, if anyone) and COVERAGE (who broke "
      "down, primary/secondary + mechanism). A goal may legitimately have an empty ledger.\n")
    W("\n## STOP — cold owner review. Return your 12 rulings before the model's answers are revealed.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    BLINDSHEET.write_text("\n".join(B))

    # (b) WITHHELD model answers — written, NOT shown
    rec = pl.read_parquet(E2.REC)
    keyset = set((r["game_id"], r["event_id"]) for r in sel.select("game_id", "event_id").iter_rows(named=True))
    M = []; A = M.append
    A("# Blind holdout — MODEL ANSWERS (WITHHELD until owner's fresh rulings are in)\n")
    A("Do not open until the owner's cold rulings are returned. Both ledgers per goal, per-player shares.\n")
    for r in sel.iter_rows(named=True):
        gid, eid = r["game_id"], r["event_id"]
        A(f"\n### {gid}-{eid}\n")
        for led in ["PUCK_LOSS", "COVERAGE"]:
            rr = rec.filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid) & (pl.col("ledger") == led)).sort("severity", descending=True)
            if rr.height:
                A(f"**{led}:** " + "; ".join(
                    f"{x['event_type']} {nm.get(x['player_id'], (x['player_id'], '?'))[0]} #{nm.get(x['player_id'], ('', '?'))[1]} "
                    f"(sev {x['severity']:.2f}, {x['share']*100:.0f}%)" for x in rr.iter_rows(named=True)))
            else:
                A(f"**{led}:** (none)")
    WITHHELD.write_text("\n".join(M))
    return {"picked": sel.height, "blindsheet": str(BLINDSHEET), "withheld": str(WITHHELD),
            "ids": [(r["game_id"], r["event_id"]) for r in sel.iter_rows(named=True)]}


if __name__ == "__main__":
    r = write()
    print(f"selected {r['picked']} goals | blind sheet: {r['blindsheet']} | withheld answers: {r['withheld']}")
    print("ids:", r["ids"])
