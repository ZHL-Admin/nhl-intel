"""Targeted cold blind samples for the two NEWEST coverage detectors — FTA and the rush-guard — which a
random holdout barely exercises (FTA fires on ~0.8% of goals; the rush-guard only acts on fresh rushes).

Two separate ~6-goal blind samples, md5-deterministic within each subset, excluding every previously surfaced
goal (validation, both holdouts, pinned-rush, both turnover samples):
  (A) FTA-FIRING: goals where FAILURE-TO-ACCOUNT fired in the ledger. Cold test: does FTA fire only on real
      soft-abandonment-leaving-an-open-man, or are there false positives?
  (B) RUSH-GUARDED: goals where FTA would have fired but the rush-guard suppressed it (fresh rush, entry <=4s).
      Cold test: is each a genuine rush (correct suppression) or a settled play the guard wrongly spared
      (an FTA false-negative)?
Each: a blind sheet (goals only, no model output) + a withheld answers file (the FTA/would-be-FTA player +
severity + the coverage ledger). Selection is not model-chosen.
"""
from __future__ import annotations

import hashlib

import polars as pl

from . import config as C, events2 as E2
from .covholdout import TEAM_ABBR, excluded as _base_excluded
from .meta import load as load_meta

FTA_SHEET = C.REPORTS / "cov_targeted_FTA_blindsheet.md"
FTA_WITHHELD = C.REPORTS / "cov_targeted_FTA_WITHHELD.md"
RG_SHEET = C.REPORTS / "cov_targeted_rushguard_blindsheet.md"
RG_WITHHELD = C.REPORTS / "cov_targeted_rushguard_WITHHELD.md"
N = 6

# the 12-goal coverage blind holdout just issued — also excluded so these stay cold
COV_HOLDOUT_12 = {(2023020260, 809), (2024020569, 679), (2023020729, 782), (2024021065, 374), (2023020311, 160),
                  (2023020960, 858), (2023020662, 1054), (2024020174, 2281092), (2024020612, 434),
                  (2024020688, 882), (2023020450, 98), (2023020287, 331)}


def _md5(gid, eid) -> str:
    return hashlib.md5(f"{gid}-{eid}".encode()).hexdigest()


def excluded() -> set:
    return _base_excluded() | COV_HOLDOUT_12


def _pick(goals: list) -> list:
    excl = excluded()
    rows = [ge for ge in goals if ge not in excl]
    rows.sort(key=lambda ge: _md5(ge[0], ge[1]))
    return rows[:N]


def _resolve(bq, picked):
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "season", "game_date", "home_team_id",
                                               "away_team_id", "scoring_team_id", "scorer_id", "period",
                                               "game_clock_seconds")
    keys = pl.DataFrame(picked, schema=["game_id", "event_id"], orient="row")
    fmap = {(r["game_id"], r["event_id"]): r for r in fused.join(keys, on=["game_id", "event_id"], how="inner").iter_rows(named=True)}
    tm = dict(TEAM_ABBR)
    tm.update({r.team_id: r.team_abbrev for r in bq.query(
        f"select distinct team_id, team_abbrev from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current` where team_abbrev is not null").result()})

    def scn(pid, season):
        if pid is None:
            return ("?", "?")
        q = list(bq.query(f"select min(concat(first_name,' ',last_name)) n, max(sweater_number) sw "
                          f"from `{C.BQ_PROJECT}.nhl_staging.stg_rosters` where player_id={pid} and season='{season}'").result())
        return (q[0].n, q[0].sw) if q and q[0].n else (str(pid), "?")
    return fmap, tm, scn


def _sheet_rows(picked, fmap, tm, scn):
    out = []
    for i, (gid, eid) in enumerate(picked, 1):
        fm = fmap[(gid, eid)]
        home, away = tm.get(fm["home_team_id"], str(fm["home_team_id"])), tm.get(fm["away_team_id"], str(fm["away_team_id"]))
        scoring = tm.get(fm["scoring_team_id"], str(fm["scoring_team_id"]))
        defending = away if fm["scoring_team_id"] == fm["home_team_id"] else home
        sc = scn(fm["scorer_id"], fm["season"]); mm, ss = divmod(int(fm["game_clock_seconds"]), 60)
        out.append(f"| {i} | {gid} | {eid} | {fm['game_date']} | {away}@{home} ({defending} defending, "
                   f"{scoring} scored) | {sc[0]} #{sc[1]} | P{fm['period']} | {mm:02d}:{ss:02d} |")
    return out


def write() -> dict:
    from google.cloud import bigquery
    rec = pl.read_parquet(E2.REC)
    fs = pl.read_parquet(C.PARQUET / "fta_sets.parquet")
    nm = {r["player_id"]: (r["full_name"], r["sweater"]) for r in load_meta().to_dicts()}

    fta_goals = [(r["game_id"], r["event_id"]) for r in
                 rec.filter(pl.col("event_type") == "FTA").select("game_id", "event_id").unique().iter_rows(named=True)]
    supp = fs.filter(pl.col("kind") == "suppressed")
    supp_goals = [(r["game_id"], r["event_id"]) for r in supp.select("game_id", "event_id").unique().iter_rows(named=True)]
    supp_player = {(r["game_id"], r["event_id"]): r["player_id"] for r in supp.iter_rows(named=True)}

    fta_pick = _pick(fta_goals)
    rg_pick = _pick(supp_goals)
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    fmap, tm, scn = _resolve(bq, fta_pick + rg_pick)
    C.REPORTS.mkdir(parents=True, exist_ok=True)

    # (A) FTA-FIRING blind sheet
    B = []; W = B.append
    W("# Targeted blind sample A — FTA (failure-to-account) cold test\n")
    W("The model fired FAILURE-TO-ACCOUNT on each goal below — its newest coverage detector (a defender who is "
      "sustained-nearest to an open man in dangerous ice, never closes, and collapses INSIDE his man = "
      "abandonment). Random holdouts barely hit it (~0.8% of goals), so this is a targeted cold test. "
      "Deterministic (md5 order within the FTA-firing set), excluding every surfaced goal. **No model output.**\n")
    W("Rule each COLD: is there a **real soft-abandonment leaving a standing-open man** (and who), or is this a "
      "FALSE POSITIVE (the open man was a rush/transition, a screen, a good finish beating sound coverage)?\n")
    W("| # | game_id | event_id | date | matchup (defending vs scored) | scorer | period | clock |")
    W("|---|---|---|---|---|---|---|---|")
    B += _sheet_rows(fta_pick, fmap, tm, scn)
    W("\n## STOP — cold review. Return your FTA rulings before the model's answers are revealed.\n")
    FTA_SHEET.write_text("\n".join(B))

    # (A) withheld
    M = []; A = M.append
    A("# Targeted FTA sample — MODEL ANSWERS (WITHHELD)\n")
    for i, (gid, eid) in enumerate(fta_pick, 1):
        rr = rec.filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid) & (pl.col("ledger") == "COVERAGE")).sort("severity", descending=True)
        body = "; ".join(f"{x['event_type']} {nm.get(x['player_id'], (x['player_id'], '?'))[0]} #{nm.get(x['player_id'], ('', '?'))[1]} "
                         f"(sev {x['severity']:.2f}, {x['share']*100:.0f}%)" for x in rr.iter_rows(named=True)) or "(none)"
        A(f"{i}. {gid}-{eid}: {body}")
    FTA_WITHHELD.write_text("\n".join(M))

    # (B) RUSH-GUARDED blind sheet
    B = []; W = B.append
    W("# Targeted blind sample B — rush-guard cold test\n")
    W("On each goal below the model would have fired FAILURE-TO-ACCOUNT, but the RUSH-GUARD suppressed it — it "
      "read a fresh rush (zone entry within 4s of the goal) and treated the open scorer as unsettled "
      "transition, not a coverage-account failure. Deterministic (md5 order within the suppressed set), "
      "excluding every surfaced goal. **No model output.**\n")
    W("Rule each COLD: is this a **genuine rush / transition** (the guard correctly suppressed — the open man "
      "is the rush, not an abandoned assignment), or a **settled play** the guard WRONGLY suppressed (a real "
      "coverage abandonment the model now misses = an FTA false-negative)?\n")
    W("| # | game_id | event_id | date | matchup (defending vs scored) | scorer | period | clock |")
    W("|---|---|---|---|---|---|---|---|")
    B += _sheet_rows(rg_pick, fmap, tm, scn)
    W("\n## STOP — cold review. Return your rush-guard rulings before the model's answers are revealed.\n")
    RG_SHEET.write_text("\n".join(B))

    # (B) withheld
    M = []; A = M.append
    A("# Targeted rush-guard sample — MODEL ANSWERS (WITHHELD)\n")
    A("Per goal: the would-be FTA player the rush-guard spared, plus the coverage ledger that DID fire.\n")
    for i, (gid, eid) in enumerate(rg_pick, 1):
        wpid = supp_player.get((gid, eid))
        wnm = nm.get(wpid, (wpid, "?"))
        rr = rec.filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid) & (pl.col("ledger") == "COVERAGE")).sort("severity", descending=True)
        did = "; ".join(f"{x['event_type']} {nm.get(x['player_id'], (x['player_id'], '?'))[0]} #{nm.get(x['player_id'], ('', '?'))[1]} ({x['severity']:.2f})"
                        for x in rr.iter_rows(named=True)) or "(none)"
        A(f"{i}. {gid}-{eid}: would-be FTA = {wnm[0]} #{wnm[1]} (SUPPRESSED by rush-guard); coverage that fired: {did}")
    RG_WITHHELD.write_text("\n".join(M))

    excl = excluded()
    return {"fta_pick": fta_pick, "rg_pick": rg_pick,
            "fta_overlap": len(set(fta_pick) & excl), "rg_overlap": len(set(rg_pick) & excl),
            "cross_overlap": len(set(fta_pick) & set(rg_pick)),
            "pool_fta": len(fta_goals), "pool_rg": len(supp_goals)}


if __name__ == "__main__":
    r = write()
    print(f"FTA sample {len(r['fta_pick'])} (pool {r['pool_fta']}), overlap {r['fta_overlap']}: {r['fta_pick']}")
    print(f"rush-guard sample {len(r['rg_pick'])} (pool {r['pool_rg']}), overlap {r['rg_overlap']}: {r['rg_pick']}")
    print(f"cross-overlap between the two samples: {r['cross_overlap']}")
