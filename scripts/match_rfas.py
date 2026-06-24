"""Match each pending-RFA row (raw_contracts_rfa) to the canonical player_id.

The RFA feed has NO team column, so this is a TEAM-LESS match (the signed-contract matcher,
scripts/match_contracts.py, leans on name+team). It reuses that matcher's normalization + candidate
dimension and resolves by: unique full name -> name+position -> name+position+age -> last-name +
first-initial + age. Anything it cannot resolve to exactly one player is reported, never guessed —
overwhelmingly these are minor-league RFAs with no NHL game (correctly absent, like prospects).

A hand-maintained override file (models_ml/data/rfa_id_overrides.csv, columns player_name_src,
player_id) resolves the few NHL names the auto-match misses. Writes nhl_models.rfa_player_map.

Run:  python -m scripts.match_rfas [--as-of 2026-06-18] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

from scripts.match_contracts import norm_name, csv_first_last, pos_group, load_candidates, _age

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES = ROOT / "models_ml" / "data" / "rfa_id_overrides.csv"
REPORT = ROOT / "models_ml" / "artifacts" / "rfa_match_report.md"
MAP_TABLE = "rfa_player_map"  # in nhl_models

SCHEMA = [
    bigquery.SchemaField("player_name_src", "STRING"),
    bigquery.SchemaField("season", "STRING"),
    bigquery.SchemaField("as_of_date", "DATE"),
    bigquery.SchemaField("player_id", "INT64"),
    bigquery.SchemaField("match_method", "STRING"),
    bigquery.SchemaField("confidence", "STRING"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", default=None, help="snapshot to match (default: latest in raw_contracts_rfa)")
    ap.add_argument("--dry-run", action="store_true", help="match + report, do not write the map table")
    args = ap.parse_args()

    project = os.environ["GCP_PROJECT_ID"]
    client = bigquery.Client(project=project)
    ref = date.today()

    asof = f"DATE('{args.as_of}')" if args.as_of else \
        f"(SELECT MAX(as_of_date) FROM `{project}.nhl_raw.raw_contracts_rfa`)"
    rfas = client.query(
        f"SELECT player_name_src, pos, age, season, as_of_date "
        f"FROM `{project}.nhl_raw.raw_contracts_rfa` WHERE as_of_date = {asof}"
    ).result().to_dataframe(create_bqstorage_client=False)
    cand = load_candidates(client, project)
    by_name = {k: g for k, g in cand.groupby("nkey")}
    by_last = {k: g for k, g in cand.groupby("lkey")}

    overrides: dict[str, int] = {}
    if OVERRIDES.exists():
        od = pd.read_csv(OVERRIDES, dtype=str).fillna("")
        overrides = {r["player_name_src"].strip(): int(r["player_id"])
                     for _, r in od.iterrows() if r.get("player_id")}

    def age_resolve(df: pd.DataFrame, a):
        if a is None or df.empty:
            return None
        s = df.copy()
        s["d"] = s["birth_date"].map(lambda b: abs((_age(b, ref) or 99) - a))
        near = s[s.d <= 1.0]
        return int(near.iloc[0].player_id) if len(near) == 1 else None

    rows, unmatched = [], []
    for _, c in rfas.iterrows():
        ovr = overrides.get(str(c.player_name_src).strip())
        if ovr is not None:
            rows.append((c.player_name_src, c.season, c.as_of_date, ovr, "override", "high"))
            continue
        nkey = csv_first_last(c.player_name_src)
        pg = pos_group(c.pos)
        a = float(c.age) if str(c.age).strip().replace(".", "").isdigit() else None
        pid, method = None, None
        pool = by_name.get(nkey)
        if pool is not None and len(pool) == 1:
            pid, method = int(pool.iloc[0].player_id), "name-unique"
        elif pool is not None and not pool.empty:
            sub = pool[pool.pg == pg]
            if len(sub) == 1:
                pid, method = int(sub.iloc[0].player_id), "name+pos"
            else:
                r = age_resolve(sub, a) or age_resolve(pool, a)
                if r:
                    pid, method = r, "name+age"
        if pid is None:                                   # last-name + first-initial + age fallback
            lk = norm_name(str(c.player_name_src).split(",", 1)[0])
            ci = norm_name(str(c.player_name_src).split(",", 1)[-1]).strip()[:1]
            lp = by_last.get(lk)
            if lp is not None and ci:
                li = lp[lp.first_name.map(lambda f: norm_name(f)[:1]) == ci]
                r = age_resolve(li[li.pg == pg], a) or age_resolve(li, a)
                if r:
                    pid, method = r, "lastname+initial+age"
        if pid is not None:
            conf = "medium" if method.startswith("lastname") else "high"
            rows.append((c.player_name_src, c.season, c.as_of_date, pid, method, conf))
        else:
            unmatched.append((c.player_name_src, c.pos, c.age))

    map_df = pd.DataFrame(rows, columns=["player_name_src", "season", "as_of_date",
                                         "player_id", "match_method", "confidence"])
    # a player can only map ONCE (dedupe defensively on player_id, keep the higher-confidence method)
    map_df = (map_df.sort_values("confidence")           # 'high' < 'medium' alphabetically -> keep high via last
             .drop_duplicates("player_id", keep="first").drop_duplicates("player_name_src", keep="first"))
    print(f"RFAs={len(rfas)}  matched={len(map_df)}  unmatched={len(unmatched)}")
    print("methods:", map_df["match_method"].value_counts().to_dict() if not map_df.empty else {})

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT, "w") as f:
        f.write(f"# Pending-RFA -> player_id match report ({rfas['as_of_date'].iloc[0]})\n\n")
        f.write(f"- RFAs: **{len(rfas)}**, matched: **{len(map_df)}**, unmatched: **{len(unmatched)}**\n")
        f.write("- Unmatched are overwhelmingly minor-league RFAs with no NHL game (correctly absent, "
                "like prospects). Resolve real NHL misses by adding rows to "
                "`models_ml/data/rfa_id_overrides.csv` (player_name_src, player_id).\n\n")
        f.write("## Unmatched (no unique NHL name match)\n\n| name | pos | age |\n|---|---|---|\n")
        for u in sorted(unmatched):
            f.write(f"| {u[0]} | {u[1]} | {u[2]} |\n")
    print(f"report -> {REPORT}")

    if args.dry_run:
        print("[dry-run] not written")
        return 0

    table_id = f"{project}.nhl_models.{MAP_TABLE}"
    job = client.load_table_from_dataframe(
        map_df, table_id,
        job_config=bigquery.LoadJobConfig(schema=SCHEMA,
                                          write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE))
    job.result()
    print(f"wrote {len(map_df)} rows -> {table_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
