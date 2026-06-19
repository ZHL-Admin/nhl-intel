"""Ingest the trade tool's FUTURES inventory — prospects and draft picks (Trade tool P5).

Two tables, both dated snapshots (stamped as_of_date + season so the source can later swap to an
API with no schema change):

  nhl_raw.raw_prospects   — every org's published prospect list (/v1/prospects/{TEAM}), one row per
                            prospect, enriched with draft pedigree (overall pick) from the player
                            landing payload. Bounded to org lists: we never invent prospects.

  nhl_raw.raw_draft_picks — future draft picks as selectable assets. PICK OWNERSHIP IS NOT IN ANY
                            feed we have, so every pick is assumed to belong to its ORIGINAL team
                            (ownership_source='assumed_own') UNLESS a hand-maintained override
                            (models_ml/data/draft_pick_overrides.csv) reassigns a traded pick. This
                            is a KNOWN GAP, flagged loudly here and in the methodology doc — the
                            assumption is recorded in a column, never silently baked in.

Idempotent per snapshot: each table deletes the current as_of_date's rows, then appends.

Run (env: set -a && source .env && set +a && export GOOGLE_APPLICATION_CREDENTIALS=...):
    python -m scripts.ingest_futures                         # today, 2025-26, drafts 2026-2028
    python -m scripts.ingest_futures --pick-years 2026 2027 2028 --workers 12
    python -m scripts.ingest_futures --dry-run               # fetch + print shape, no write
"""
from __future__ import annotations

import argparse
import datetime as _dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

from ingestion.nhl_api import get_prospects, get_player_landing
from models_ml import bq

ROOT = Path(__file__).resolve().parent.parent
PICK_OVERRIDES = ROOT / "models_ml" / "data" / "draft_pick_overrides.csv"
DRAFT_ROUNDS = 7  # the NHL draft is 7 rounds


def _pos_group(code: str) -> str:
    c = (code or "").upper()
    return "G" if c == "G" else ("D" if c == "D" else "F")


def team_abbrevs(season: str) -> list[str]:
    """The current franchises — teams that actually played in the given season (excludes
    relocated/defunct abbrevs like ATL/ARI that linger in the historical mart)."""
    df = bq.query_df(
        f"select distinct team_abbrev from `{bq.project()}.nhl_mart.mart_team_game_stats` "
        f"where team_abbrev is not null and season = '{season}' order by team_abbrev")
    return [a for a in df["team_abbrev"].tolist() if a]


# ------------------------------------------------------------------------------------- prospects
def fetch_team_prospects(abbrev: str) -> list[dict]:
    try:
        d = get_prospects(abbrev)
    except Exception as e:
        print(f"  prospects {abbrev}: skip ({str(e)[:50]})")
        return []
    out = []
    for group in ("forwards", "defensemen", "goalies"):
        for p in d.get(group, []) or []:
            out.append({
                "player_id": int(p["id"]),
                "first_name": (p.get("firstName") or {}).get("default"),
                "last_name": (p.get("lastName") or {}).get("default"),
                "position_code": p.get("positionCode"),
                "pos_group": _pos_group(p.get("positionCode")),
                "shoots": p.get("shootsCatches"),
                "birth_date": p.get("birthDate"),
                "height_in": p.get("heightInInches"),
                "weight_lb": p.get("weightInPounds"),
                "org_team": abbrev,
            })
    return out


def enrich_draft(prospect: dict) -> dict:
    """Attach draft pedigree (overall pick) from the player's landing payload; null if undrafted."""
    dd = None
    try:
        dd = get_player_landing(str(prospect["player_id"])).get("draftDetails")
    except Exception:
        dd = None
    prospect["draft_year"] = (dd or {}).get("year")
    prospect["draft_round"] = (dd or {}).get("round")
    prospect["draft_overall"] = (dd or {}).get("overallPick")
    return prospect


def build_prospects(teams: list[str], workers: int) -> pd.DataFrame:
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in as_completed([ex.submit(fetch_team_prospects, t) for t in teams]):
            rows.extend(fut.result())
    # de-dup: a player can appear on only one org list, but guard anyway (keep first)
    seen, uniq = set(), []
    for r in rows:
        if r["player_id"] in seen:
            continue
        seen.add(r["player_id"])
        uniq.append(r)
    print(f"prospects: {len(uniq)} across {len(teams)} orgs; fetching draft pedigree ...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        uniq = list(ex.map(enrich_draft, uniq))
    df = pd.DataFrame(uniq)
    # nullable ints (undrafted prospects have no pedigree); birth_date stays a source string (cast in stg)
    for c in ["player_id", "height_in", "weight_lb", "draft_year", "draft_round", "draft_overall"]:
        df[c] = pd.array(pd.to_numeric(df[c], errors="coerce"), dtype="Int64")
    df["birth_date"] = df["birth_date"].astype("string")
    drafted = df["draft_overall"].notna().sum()
    print(f"  draft pedigree: {drafted}/{len(df)} drafted, {len(df) - drafted} undrafted (free-agent prospects)")
    return df


# ------------------------------------------------------------------------------------- draft picks
def build_picks(teams: list[str], years: list[int]) -> pd.DataFrame:
    """One row per (team, year, round) under the own-picks assumption, then apply overrides."""
    ov = pd.read_csv(PICK_OVERRIDES, dtype=str).fillna("") if PICK_OVERRIDES.exists() else pd.DataFrame()
    ov_map: dict[tuple[int, int, str], tuple[str, str]] = {}
    for _, r in ov.iterrows():
        if r.get("owner_team"):
            ov_map[(int(r["draft_year"]), int(r["round"]), r["original_team"].strip())] = (
                r["owner_team"].strip(), r.get("note", "").strip())

    rows = []
    for yr in years:
        for rd in range(1, DRAFT_ROUNDS + 1):
            for team in teams:
                owner, src, note = team, "assumed_own", ""
                if (yr, rd, team) in ov_map:
                    owner, note = ov_map[(yr, rd, team)]
                    src = "override"
                rows.append({
                    "draft_year": yr, "round": rd,
                    "original_team": team, "owner_team": owner,
                    "ownership_source": src, "note": note,
                })
    df = pd.DataFrame(rows)
    print(f"draft picks: {len(df)} ({len(teams)} teams x {DRAFT_ROUNDS} rounds x {len(years)} years); "
          f"{(df.ownership_source == 'override').sum()} overridden, rest assumed-own")
    return df


# ------------------------------------------------------------------------------------- write
PROSPECTS_SCHEMA = [
    bigquery.SchemaField("player_id", "INTEGER"),
    bigquery.SchemaField("first_name", "STRING"),
    bigquery.SchemaField("last_name", "STRING"),
    bigquery.SchemaField("position_code", "STRING"),
    bigquery.SchemaField("pos_group", "STRING"),
    bigquery.SchemaField("shoots", "STRING"),
    bigquery.SchemaField("birth_date", "STRING"),
    bigquery.SchemaField("height_in", "INTEGER"),
    bigquery.SchemaField("weight_lb", "INTEGER"),
    bigquery.SchemaField("org_team", "STRING"),
    bigquery.SchemaField("draft_year", "INTEGER"),
    bigquery.SchemaField("draft_round", "INTEGER"),
    bigquery.SchemaField("draft_overall", "INTEGER"),
    bigquery.SchemaField("as_of_date", "DATE"),
    bigquery.SchemaField("season", "STRING"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
]
PICKS_SCHEMA = [
    bigquery.SchemaField("draft_year", "INTEGER"),
    bigquery.SchemaField("round", "INTEGER"),
    bigquery.SchemaField("original_team", "STRING"),
    bigquery.SchemaField("owner_team", "STRING"),
    bigquery.SchemaField("ownership_source", "STRING"),
    bigquery.SchemaField("note", "STRING"),
    bigquery.SchemaField("as_of_date", "DATE"),
    bigquery.SchemaField("season", "STRING"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
]


def _stamp(df: pd.DataFrame, as_of: str, season: str) -> pd.DataFrame:
    df = df.copy()
    df["as_of_date"] = pd.to_datetime(as_of).date()
    df["season"] = season
    df["ingested_at"] = pd.Timestamp.utcnow()
    return df


def _write(df: pd.DataFrame, table: str, schema: list, as_of: str) -> None:
    client = bq.client()
    table_id = f"{bq.project()}.nhl_raw.{table}"
    try:
        client.get_table(table_id)
    except Exception:
        client.create_table(bigquery.Table(table_id, schema=schema))
        print(f"created {table_id}")
    client.query(f"DELETE FROM `{table_id}` WHERE as_of_date = DATE('{as_of}')").result()
    client.load_table_from_dataframe(
        df, table_id,
        job_config=bigquery.LoadJobConfig(schema=schema,
                                          write_disposition=bigquery.WriteDisposition.WRITE_APPEND),
    ).result()
    n = list(client.query(f"SELECT COUNT(*) n FROM `{table_id}`").result())[0].n
    print(f"loaded {len(df)} -> {table_id} (now {n} rows total)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", default=_dt.date.today().isoformat())
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--pick-years", type=int, nargs="+", default=[2026, 2027, 2028])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    teams = team_abbrevs(args.season)
    print(f"current franchises: {len(teams)}")
    prospects = _stamp(build_prospects(teams, args.workers), args.as_of, args.season)
    picks = _stamp(build_picks(teams, args.pick_years), args.as_of, args.season)

    print(f"\nprospects rows={len(prospects)}  picks rows={len(picks)}  as_of={args.as_of} season={args.season}")
    if args.dry_run:
        print(prospects[["player_id", "last_name", "org_team", "pos_group", "draft_overall"]].head(5).to_string(index=False))
        print("[dry-run] not written")
        return 0

    _write(prospects, "raw_prospects", PROSPECTS_SCHEMA, args.as_of)
    _write(picks, "raw_draft_picks", PICKS_SCHEMA, args.as_of)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
