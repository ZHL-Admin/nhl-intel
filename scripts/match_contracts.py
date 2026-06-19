"""Match each raw_contracts row to the canonical player_id used across the marts.

This is the highest-risk step: a wrong match silently corrupts a player's contract. So matching is
deterministic and conservative — it matches on normalized name + team + position group with AGE as a
tiebreaker (the two "Sebastian Aho"s, for example, separate by position F/D), and ANYTHING it cannot
resolve to exactly one player is reported for manual resolution, never guessed.

Resolution loop (stable across re-runs):
  1. Auto-match (deterministic) against a player dimension built from stg_rosters + bio.
  2. Apply a hand-maintained override file (models_ml/data/contract_id_overrides.csv) on top.
  3. Write the resolved map to nhl_models.contract_player_map.
  4. Write the unmatched + ambiguous report to models_ml/artifacts/contract_match_report.md.

Signed prospects on entry-level deals (no NHL footprint) are EXPECTED to land in the unmatched
report — they are picked up by the prospect/pick layer (Phases 5-6), not forced to a wrong NHL id.

Run:  python -m scripts.match_contracts [--as-of 2026-06-18] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES = ROOT / "models_ml" / "data" / "contract_id_overrides.csv"
REPORT = ROOT / "models_ml" / "artifacts" / "contract_match_report.md"
MAP_TABLE = "contract_player_map"  # in nhl_models


def norm_name(s: str) -> str:
    """Accent-fold, drop suffixes/punctuation, lowercase, collapse whitespace."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", " ", s)
    s = re.sub(r"[^a-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pos_group(pos: str) -> str:
    p = (pos or "").upper()
    if "G" in p:
        return "G"
    # multi-position contracts ("C, LW") are forwards unless purely D
    return "D" if (p.replace(" ", "").replace(",", "") == "D") else "F"


def _age(birth_date, ref: date) -> float | None:
    if birth_date is None or pd.isna(birth_date):
        return None
    bd = pd.to_datetime(birth_date).date()
    return (ref - bd).days / 365.25


def csv_first_last(name_src: str) -> str:
    """'Last, First' -> normalized 'first last'."""
    parts = str(name_src).split(",", 1)
    if len(parts) == 2:
        last, first = parts[0], parts[1]
    else:
        last, first = parts[0], ""
    return norm_name(f"{first} {last}")


def load_candidates(client: bigquery.Client, project: str) -> pd.DataFrame:
    """One row per NHL player: latest name/position/team + birth date (canonical player_id)."""
    sql = f"""
    WITH tm AS (
        SELECT team_id, ANY_VALUE(team_abbrev) AS abbrev
        FROM `{project}.nhl_mart.mart_team_game_stats` GROUP BY team_id
    ),
    latest AS (
        SELECT player_id,
               ARRAY_AGG(STRUCT(first_name, last_name, position_code, team_id) ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS r
        FROM `{project}.nhl_staging.stg_rosters`
        WHERE SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
        GROUP BY player_id
    )
    SELECT l.player_id, l.r.first_name AS first_name, l.r.last_name AS last_name,
           l.r.position_code AS position_code, tm.abbrev AS team_abbrev, b.birth_date
    FROM latest l LEFT JOIN tm ON l.r.team_id = tm.team_id
    LEFT JOIN `{project}.nhl_staging.stg_player_bio` b USING (player_id)
    """
    df = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
    df["nkey"] = df.apply(lambda r: norm_name(f"{r.first_name} {r.last_name}"), axis=1)
    df["lkey"] = df["last_name"].map(norm_name)
    df["pg"] = df["position_code"].map(pos_group)
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", default=None, help="snapshot to match (default: latest in raw_contracts)")
    ap.add_argument("--dry-run", action="store_true", help="match + report, do not write the map table")
    args = ap.parse_args()

    project = os.environ["GCP_PROJECT_ID"]
    client = bigquery.Client(project=project)
    ref = date.today()

    asof_filter = f"WHERE as_of_date = DATE('{args.as_of}')" if args.as_of else \
        "WHERE as_of_date = (SELECT MAX(as_of_date) FROM `%s.nhl_raw.raw_contracts`)" % project
    contracts = client.query(
        f"SELECT player_name_src, team, pos, age, season, as_of_date "
        f"FROM `{project}.nhl_raw.raw_contracts` {asof_filter}"
    ).result().to_dataframe(create_bqstorage_client=False)
    cand = load_candidates(client, project)

    # index candidates by normalized full name and by normalized last name
    by_name: dict[str, pd.DataFrame] = {k: g for k, g in cand.groupby("nkey")}
    by_last: dict[str, pd.DataFrame] = {k: g for k, g in cand.groupby("lkey")}

    # hand-maintained overrides: (player_name_src, team) -> player_id
    overrides: dict[tuple[str, str], int] = {}
    if OVERRIDES.exists():
        od = pd.read_csv(OVERRIDES, dtype=str).fillna("")
        for _, r in od.iterrows():
            if r.get("player_id"):
                overrides[(r["player_name_src"].strip(), r["team"].strip())] = int(r["player_id"])

    rows, unmatched, ambiguous = [], [], []
    for _, c in contracts.iterrows():
        nkey = csv_first_last(c.player_name_src)
        team = (c.team or "").strip()
        pg = pos_group(c.pos)
        csv_age = float(c.age) if str(c.age).strip().replace(".", "").isdigit() else None

        ovr = overrides.get((c.player_name_src.strip(), team))
        if ovr is not None:
            rows.append((c.player_name_src, team, c.season, c.as_of_date, ovr, "override", "high"))
            continue

        def pick(df: pd.DataFrame):
            return int(df.iloc[0].player_id) if len(df) == 1 else None

        def age_resolve(df: pd.DataFrame):
            if csv_age is None or df.empty:
                return None
            s = df.copy()
            s["agediff"] = s["birth_date"].map(lambda b: abs((_age(b, ref) or 99) - csv_age))
            near = s[s.agediff <= 1.0]
            return pick(near)

        pid, method = None, None
        pool = by_name.get(nkey)
        if pool is not None and not pool.empty:
            # tier 1: name + team + pos ; 2: name + team ; 3: name + pos ; 4: unique name ; age tiebreak
            for sub, mth in [(pool[(pool.team_abbrev == team) & (pool.pg == pg)], "name+team+pos"),
                             (pool[pool.team_abbrev == team], "name+team"),
                             (pool[pool.pg == pg], "name+pos")]:
                pid = pick(sub)
                if pid is not None:
                    method = mth
                    break
            if pid is None and len(pool) == 1:
                pid, method = int(pool.iloc[0].player_id), "name-unique"
            if pid is None:
                for sub in (pool[(pool.team_abbrev == team) & (pool.pg == pg)], pool[pool.pg == pg], pool):
                    pid = age_resolve(sub)
                    if pid is not None:
                        method = "name+age"
                        break

        # last-name fallback (bounded to the contract team) — resolves nickname/transliteration
        # gaps like "Nicholas"->Nick Paul, "Sam"->Samuel, "Dmitriy"->Dmitri without fuzzy guessing.
        # GUARDED by a matching FIRST INITIAL so a prospect is never matched to a retired veteran
        # who merely shares a surname (e.g. Cole Knuble != Mike Knuble, Riley != Nate Thompson):
        # every real nickname keeps the initial, every cross-person surname collision changes it.
        csv_first = norm_name(str(c.player_name_src).split(",", 1)[-1]).strip()
        csv_init = csv_first[:1]
        csv_last = norm_name(str(c.player_name_src).split(",", 1)[0])
        lpool = by_last.get(csv_last)
        if pid is None and csv_init and lpool is not None and not lpool.empty:
            li = lpool[lpool.first_name.map(lambda f: norm_name(f)[:1]) == csv_init]
            lm = li[(li.team_abbrev == team) & (li.pg == pg)]
            pid = pick(lm)
            if pid is not None:
                method = "lastname+initial+team+pos"
            else:
                la = age_resolve(lm) or age_resolve(li[li.team_abbrev == team])
                if la is not None:
                    pid, method = la, "lastname+initial+team+age"

        if pid is not None:
            # surname-tier matches are well-guarded but indirect -> medium so they stay auditable.
            conf = "medium" if method.startswith("lastname") else "high"
            rows.append((c.player_name_src, team, c.season, c.as_of_date, pid, method, conf))
            continue

        # Unresolved: ambiguous only if a genuine candidate existed — a full-name match, or a
        # same-team surname match. A surname that only collides on OTHER teams is a prospect, not
        # an ambiguity, so it falls through to unmatched (picked up by the prospect layer).
        if pool is not None and not pool.empty:
            cand_pool = pool
        elif lpool is not None and not (lpool[lpool.team_abbrev == team]).empty:
            cand_pool = lpool[lpool.team_abbrev == team]
        else:
            cand_pool = None
        if cand_pool is None or cand_pool.empty:
            unmatched.append((c.player_name_src, team, c.pos, c.age))
        else:
            cands = "; ".join(f"{r.player_id}/{r.team_abbrev}/{r.pg}/{(_age(r.birth_date, ref) or 0):.0f}y"
                              for r in cand_pool.itertuples())
            ambiguous.append((c.player_name_src, team, c.pos, c.age, cands))

    map_df = pd.DataFrame(rows, columns=["player_name_src", "team", "season", "as_of_date",
                                         "player_id", "match_method", "confidence"])
    n_total = len(contracts)
    print(f"contracts={n_total}  matched={len(map_df)}  unmatched={len(unmatched)}  ambiguous={len(ambiguous)}")
    print("methods:", map_df["match_method"].value_counts().to_dict() if not map_df.empty else {})

    # report
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT, "w") as f:
        f.write(f"# Contract -> player_id match report ({contracts['as_of_date'].iloc[0]})\n\n")
        f.write(f"- contracts: **{n_total}**, matched: **{len(map_df)}**, "
                f"unmatched: **{len(unmatched)}**, ambiguous: **{len(ambiguous)}**\n")
        f.write("- Unmatched are mostly signed prospects with no NHL game (handled in the prospect "
                "layer). Resolve real misses by adding rows to `models_ml/data/contract_id_overrides.csv`.\n\n")
        f.write("## Ambiguous (multiple candidates, age did not resolve)\n\n")
        f.write("| contract | team | pos | age | candidates (id/team/pos/age) |\n|---|---|---|---|---|\n")
        for a in ambiguous:
            f.write(f"| {a[0]} | {a[1]} | {a[2]} | {a[3]} | {a[4]} |\n")
        f.write("\n## Unmatched (no NHL name match — likely prospects)\n\n")
        f.write("| contract | team | pos | age |\n|---|---|---|---|\n")
        for u in unmatched:
            f.write(f"| {u[0]} | {u[1]} | {u[2]} | {u[3]} |\n")
    print(f"report -> {REPORT}")

    if args.dry_run:
        return 0
    from models_ml import bq
    bq.write_df(map_df, MAP_TABLE)
    print(f"wrote nhl_models.{MAP_TABLE} ({len(map_df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
