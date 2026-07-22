"""Stage 1 reconciliation (spec Section 5.5): the dbt SQL must conform to the Python reference.

Samples random games per season, pulls int_phase_events, runs the pure-Python reference state machine
(tests/phase_value/reference_state_machine.py) PER PERIOD, and diffs:
  - per-event state (poss_after, zone_abs, is_live)   HARD GATE: mismatch <= RECONCILE_EVENT_GATE (0.5%)
  - episode count (5v5-scoped, both sides)            HARD GATE: mismatch <= RECONCILE_EPISODE_GATE (2%)

The reference is the spec; a mismatch means the SQL is wrong. Read-only. Invoke explicitly (not pytest):
  GCP_PROJECT_ID=... GOOGLE_APPLICATION_CREDENTIALS=secrets/nhl-intel-sa.json \
  python -m models_ml.phase_value.stage1_reconcile --seasons 2024-25 --n 25
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

from google.cloud import bigquery

from models_ml import config

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "phase_value"))
import reference_state_machine as ref  # noqa: E402

SEED = config.PHASE_VALUE_CONFIG["SEED"]
EVENT_GATE = config.PHASE_VALUE_CONFIG["RECONCILE_EVENT_GATE"]
EP_GATE = config.PHASE_VALUE_CONFIG["RECONCILE_EPISODE_GATE"]


def _client():
    return bigquery.Client(project=os.environ[config.GCP_PROJECT_ENV])


def _sample_games(c, season, n):
    q = f"""
        SELECT game_id FROM (SELECT DISTINCT game_id FROM nhl_staging.int_phase_events WHERE season='{season}')
        ORDER BY FARM_FINGERPRINT(CAST(game_id AS STRING) || '{SEED}') LIMIT {n}
    """
    return [r.game_id for r in c.query(q).result()]


def _events(c, game_id):
    q = f"""
        SELECT period_number, sort_order, elapsed_seconds, type_desc_key, event_owner_team_id AS owner,
               zone_code, is_5v5, home_team_id, away_team_id, poss_after, zone_abs, is_live
        FROM nhl_staging.int_phase_events WHERE game_id={game_id}
        ORDER BY period_number, sort_order
    """
    return list(c.query(q).result())


def _dbt_ep_count(c, game_id):
    q = f"SELECT COUNT(*) n FROM nhl_staging.int_zone_episodes WHERE game_id={game_id}"
    return list(c.query(q).result())[0].n


def reconcile_game(c, game_id):
    rows = _events(c, game_id)
    if not rows:
        return None
    home, away = rows[0].home_team_id, rows[0].away_team_id
    ev_mismatch = 0
    n_events = 0
    ref_ep = 0
    by_period = defaultdict(list)
    for r in rows:
        by_period[r.period_number].append(r)
    for period, prs in by_period.items():
        events = [{"t": r.elapsed_seconds, "type": r.type_desc_key, "owner": r.owner, "zone": r.zone_code}
                  for r in prs]
        is5 = [r.is_5v5 for r in prs]
        res = ref.run(events, home, away, is_5v5=is5)
        # per-event state
        for r, pe in zip(prs, res["per_event"]):
            n_events += 1
            if (pe["poss"] != r.poss_after) or (pe["zone"] != r.zone_abs) or (pe["live"] != r.is_live):
                ev_mismatch += 1
        # 5v5-scoped episodes (kept if start OR terminating in-zone event is 5v5)
        ref_ep += sum(1 for e in res["episodes"] if e["keep_5v5"])
    dbt_ep = _dbt_ep_count(c, game_id)
    return {"game_id": game_id, "n_events": n_events, "ev_mismatch": ev_mismatch,
            "ref_ep": ref_ep, "dbt_ep": dbt_ep}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=["2024-25"])
    ap.add_argument("--n", type=int, default=25)
    args = ap.parse_args()
    c = _client()

    tot_ev = tot_mis = 0
    tot_ref_ep = tot_dbt_ep = 0
    worst = []
    for season in args.seasons:
        games = _sample_games(c, season, args.n)
        print(f"\n=== {season}: {len(games)} games ===")
        for g in games:
            r = reconcile_game(c, g)
            if r is None:
                continue
            tot_ev += r["n_events"]; tot_mis += r["ev_mismatch"]
            tot_ref_ep += r["ref_ep"]; tot_dbt_ep += r["dbt_ep"]
            emr = r["ev_mismatch"] / max(r["n_events"], 1)
            if r["ev_mismatch"] or abs(r["ref_ep"] - r["dbt_ep"]) > 0:
                worst.append((emr, r))
    ev_rate = tot_mis / max(tot_ev, 1)
    ep_rate = abs(tot_ref_ep - tot_dbt_ep) / max(tot_dbt_ep, 1)
    print("\n" + "=" * 66)
    print(f"PER-EVENT STATE mismatch: {tot_mis:,}/{tot_ev:,} = {ev_rate*100:.4f}%  (gate <= {EVENT_GATE*100:.2f}%)  "
          f"{'PASS' if ev_rate <= EVENT_GATE else 'FAIL'}")
    print(f"EPISODE COUNT: ref(5v5)={tot_ref_ep:,} dbt={tot_dbt_ep:,}  mismatch={ep_rate*100:.4f}%  "
          f"(gate <= {EP_GATE*100:.2f}%)  {'PASS' if ep_rate <= EP_GATE else 'FAIL'}")
    print("=" * 66)
    if worst:
        worst.sort(key=lambda x: x[0], reverse=True)
        print("\nTop discrepancy games:")
        for emr, r in worst[:8]:
            print(f"  game {r['game_id']}: ev {r['ev_mismatch']}/{r['n_events']} ({emr*100:.3f}%) "
                  f"ep ref={r['ref_ep']} dbt={r['dbt_ep']}")
    ok = ev_rate <= EVENT_GATE and ep_rate <= EP_GATE
    print(f"\n{'RECONCILIATION PASSED' if ok else 'RECONCILIATION FAILED — debug (reference is the spec)'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
