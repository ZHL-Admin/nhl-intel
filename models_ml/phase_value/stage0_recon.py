"""Stage 0 reconnaissance for phase_value (see docs/methodology/phase-value.md spec, Section 4.2).

Read-only. Answers the eight empirical verifications against the last two complete seasons and
prints a report block. Two checks are STOP-gated (Section 4.2 items 2 and 3): if faceoff-owner or
blocked-shot-owner semantics are ambiguous (< 90% consistency in the cross-checks) we surface the
numbers and STOP rather than guess. Results are transcribed into docs/phase-value/schema-map.md.

Run:  GCP_PROJECT_ID=... GOOGLE_APPLICATION_CREDENTIALS=secrets/nhl-intel-sa.json \
      python -m models_ml.phase_value.stage0_recon
"""
from __future__ import annotations

import os

from google.cloud import bigquery

from models_ml import config

SEASONS = ("2023-24", "2024-25")  # last two complete seasons (dev scope)
PBP = "nhl_staging.stg_play_by_play"
BOX = "nhl_staging.stg_boxscores"
SEG = "nhl_staging.int_segment_context"   # dbt intermediate models materialize to +schema: staging -> nhl_staging
SHOT_XG = f"{config.MODELS_DATASET}.shot_xg"
GATE = 0.90


def _client() -> bigquery.Client:
    return bigquery.Client(project=os.environ[config.GCP_PROJECT_ENV])


def _seasons_sql() -> str:
    return "('" + "', '".join(SEASONS) + "')"


def _q(c, sql):
    return list(c.query(sql).result())


def check1_event_types(c):
    rows = _q(c, f"""
        SELECT type_desc_key, COUNT(*) n
        FROM {PBP} WHERE season IN {_seasons_sql()}
        GROUP BY 1 ORDER BY n DESC
    """)
    print("\n[1] type_desc_key frequencies (last 2 seasons):")
    total = sum(r.n for r in rows)
    for r in rows:
        print(f"    {r.type_desc_key:<20} {r.n:>10,}  ({r.n/total*100:5.2f}%)")
    return {r.type_desc_key for r in rows}


def check2_faceoff_owner(c):
    """Is event_owner_team_id on a faceoff the WINNER? Cross-check: the owner's team should own the
    NEXT possession-indicating event far more than 50% of the time (Section 4.2 item 2)."""
    rows = _q(c, f"""
        WITH ev AS (
          SELECT game_id, event_id, sort_order, season, type_desc_key, event_owner_team_id,
                 LEAD(event_owner_team_id) OVER (PARTITION BY game_id ORDER BY sort_order) AS next_owner,
                 LEAD(type_desc_key)       OVER (PARTITION BY game_id ORDER BY sort_order) AS next_type
          FROM {PBP} WHERE season IN {_seasons_sql()}
        )
        SELECT
          COUNTIF(event_owner_team_id = next_owner) AS same,
          COUNT(*) AS n
        FROM ev
        WHERE type_desc_key = 'faceoff'
          AND next_owner IS NOT NULL
          AND next_type IN ('shot-on-goal','missed-shot','goal','giveaway','takeaway','hit','blocked-shot')
    """)
    r = rows[0]
    frac = r.same / r.n if r.n else 0.0
    print(f"\n[2] Faceoff owner == owner of next possession event: {frac:.3f}  (n={r.n:,})")
    print(f"    -> interpretation: high fraction confirms event_owner_team_id(faceoff) = WINNING team.")
    return ("faceoff_owner_is_winner", frac, r.n)


def check3_blocked_owner(c):
    """Is event_owner_team_id on blocked-shot the SHOOTING or BLOCKING team? Two cross-checks
    (Section 4.2 item 3): (a) which detail player id (shooting vs blocking) is populated and whether it
    aligns with owner; (b) zone_code distribution — from the shooting team's perspective blocks are 'O',
    from the blocking team's 'D'."""
    zone = _q(c, f"""
        SELECT zone_code, COUNT(*) n
        FROM {PBP} WHERE season IN {_seasons_sql()} AND type_desc_key = 'blocked-shot'
        GROUP BY 1 ORDER BY n DESC
    """)
    print("\n[3] blocked-shot zone_code distribution (owner-relative):")
    ztot = sum(r.n for r in zone)
    o = next((r.n for r in zone if r.zone_code == 'O'), 0)
    d = next((r.n for r in zone if r.zone_code == 'D'), 0)
    for r in zone:
        print(f"    zone {str(r.zone_code):<5} {r.n:>10,}  ({r.n/ztot*100:5.2f}%)")
    # detail-id population: for blocked-shot, which id column is present?
    ids = _q(c, f"""
        SELECT
          COUNTIF(shooting_player_id IS NOT NULL) AS has_shooter,
          COUNTIF(blocking_player_id IS NOT NULL) AS has_blocker,
          COUNT(*) n
        FROM {PBP} WHERE season IN {_seasons_sql()} AND type_desc_key = 'blocked-shot'
    """)[0]
    print(f"    detail ids: shooting_player_id present {ids.has_shooter/ids.n*100:.1f}% | "
          f"blocking_player_id present {ids.has_blocker/ids.n*100:.1f}%  (n={ids.n:,})")
    # If owner were the SHOOTING team, blocks would be ~'O' (attacking end). If the BLOCKING team, ~'D'.
    o_frac = o / ztot if ztot else 0.0
    d_frac = d / ztot if ztot else 0.0
    verdict = "SHOOTING team" if o_frac >= GATE else ("BLOCKING team" if d_frac >= GATE else "AMBIGUOUS")
    print(f"    -> O={o_frac:.3f} D={d_frac:.3f}  verdict: event_owner_team_id(blocked-shot) = {verdict}")
    return ("blocked_owner", verdict, max(o_frac, d_frac), ids)


def check4_stoppage_reason(c):
    rows = _q(c, f"""
        SELECT reason, COUNT(*) n
        FROM {PBP} WHERE season IN {_seasons_sql()} AND type_desc_key = 'stoppage'
        GROUP BY 1 ORDER BY n DESC LIMIT 20
    """)
    print("\n[4] stoppage `reason` values (top 20):")
    for r in rows:
        print(f"    {str(r.reason):<28} {r.n:>9,}")
    return [r.reason for r in rows]


def check5_strength(c):
    rows = _q(c, f"""
        SELECT strength_state, COUNT(*) n, SUM(segment_duration) secs
        FROM {SEG} WHERE season IN {_seasons_sql()}
        GROUP BY 1 ORDER BY secs DESC LIMIT 12
    """)
    print("\n[5] int_segment_context.strength_state distribution (share of segment-seconds):")
    tot = sum((r.secs or 0) for r in rows)
    for r in rows:
        print(f"    {str(r.strength_state):<10} n={r.n:>8,}  secs={r.secs or 0:>12,.0f}  ({(r.secs or 0)/tot*100:5.2f}%)")
    print("    -> 5v5 filter = strength_state = '5v5' (mirrors int_shot_sequence's home_sk=away_sk=5 & both goalies).")
    return {str(r.strength_state) for r in rows}


def check6_zone_nullness(c):
    rows = _q(c, f"""
        SELECT type_desc_key,
               COUNTIF(zone_code IS NULL) AS z_null,
               COUNT(*) n
        FROM {PBP} WHERE season IN {_seasons_sql()}
        GROUP BY 1 ORDER BY n DESC
    """)
    print("\n[6] zone_code nullness by event type:")
    for r in rows:
        print(f"    {r.type_desc_key:<20} null {r.z_null/r.n*100:5.1f}%  (n={r.n:,})")
    return rows


def check7_shotxg_key(c):
    """Does shot_xg cover unblocked attempts, keyed on (game_id,event_id)?"""
    rows = _q(c, f"""
        WITH att AS (
          SELECT game_id, event_id FROM {PBP}
          WHERE season IN {_seasons_sql()} AND type_desc_key IN ('shot-on-goal','missed-shot','goal')
            AND x_coord IS NOT NULL AND y_coord IS NOT NULL
        ),
        xg AS (SELECT game_id, event_id FROM {SHOT_XG} WHERE season IN {_seasons_sql()})
        SELECT
          (SELECT COUNT(*) FROM att) AS n_att,
          (SELECT COUNT(*) FROM xg)  AS n_xg,
          (SELECT COUNT(*) FROM att a JOIN xg x USING (game_id, event_id)) AS n_join
    """)[0]
    print(f"\n[7] shot_xg coverage: unblocked attempts={rows.n_att:,} | shot_xg rows={rows.n_xg:,} | "
          f"joined on (game_id,event_id)={rows.n_join:,}  ({rows.n_join/rows.n_att*100:.1f}% of attempts matched)")
    return rows


def check8_game_date(c):
    rows = _q(c, f"""
        SELECT COUNTIF(game_date IS NULL) z, COUNT(*) n
        FROM {PBP} WHERE season IN {_seasons_sql()}
    """)[0]
    print(f"\n[8] game_date present on stg_play_by_play: null {rows.z/rows.n*100:.3f}%  (n={rows.n:,}) "
          f"-> {'CONFIRMED on PBP' if rows.z == 0 else 'has nulls; join stg_boxscores'}")
    return rows


def main():
    c = _client()
    print("=" * 78)
    print(f"PHASE_VALUE Stage 0 reconnaissance | seasons={SEASONS} | project={os.environ[config.GCP_PROJECT_ENV]}")
    print("=" * 78)
    check1_event_types(c)
    fo = check2_faceoff_owner(c)
    bl = check3_blocked_owner(c)
    check4_stoppage_reason(c)
    check5_strength(c)
    check6_zone_nullness(c)
    check7_shotxg_key(c)
    check8_game_date(c)

    print("\n" + "=" * 78)
    print("STOP-GATE CHECK (Section 4.2 items 2 & 3):")
    stop = False
    if fo[1] < GATE:
        print(f"  !! Faceoff-owner consistency {fo[1]:.3f} < {GATE} -> STOP, show user.")
        stop = True
    else:
        print(f"  OK faceoff-owner {fo[1]:.3f} >= {GATE}")
    if bl[2] < GATE:
        print(f"  !! Blocked-shot-owner max consistency {bl[2]:.3f} < {GATE} -> STOP, show user.")
        stop = True
    else:
        print(f"  OK blocked-shot-owner ({bl[1]}) {bl[2]:.3f} >= {GATE}")
    print("=" * 78)
    print("STOP: verification 2 or 3 ambiguous — surface numbers to user." if stop
          else "All STOP-gated verifications passed. Transcribe results into schema-map.md.")


if __name__ == "__main__":
    main()
