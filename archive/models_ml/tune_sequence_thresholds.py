"""
Tune sequence-mining window thresholds (Phase 2.1).

The blueprint asks us to choose each window by which definition best predicts goal
rates, then publish the result. We sweep each flag's window independently (the flags are
computed independently in int_shot_sequence, so a joint sweep is unnecessary) over
unblocked shots 2018-19 .. 2024-25 and, for every candidate window, report:

  - flagged share        (what fraction of shots the flag fires on)
  - goal% flagged        P(goal | flag)
  - goal% unflagged       P(goal | not flag)
  - lift                 goal%_flagged / goal%_unflagged   (separation)
  - season share spread  max-min of per-season flagged share (stability)

A good threshold maximises lift (separation between flagged and unflagged shots) while
keeping the category share stable season to season. We print the full table, pick the
winner per flag, and the chosen values are written into dbt_project.yml vars by hand.

Run:  python -m models_ml.tune_sequence_thresholds [--seasons 2018-19 ... ] [--dry-run]
The output table is pasted verbatim into docs/methodology/sequence-mining.md.
"""

from __future__ import annotations

import argparse
import os

from google.cloud import bigquery

STAGING = "nhl_staging"
DEFAULT_SEASONS = [
    "2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25",
]

# Candidate windows per the blueprint.
REBOUND_WINDOWS = [2, 3, 4]
RUSH_WINDOWS = [4, 5, 6, 7]
FORECHECK_WINDOWS = [5, 6, 7]


def _client() -> bigquery.Client:
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def _season_list(seasons: list[str]) -> str:
    return ", ".join(f"'{s}'" for s in seasons)


# A self-contained query that, for ONE flag at ONE window, returns per-season counts of
# shots and goals split by whether the flag fired. Mirrors int_shot_sequence's logic so
# the tuned numbers match the production model. {flag_expr} references columns from the
# `prior`-aggregated CTE (has_rush / has_rebound / has_forecheck booleans).
FLAG_SQL = """
with pbp as (
    select
        game_id, season, event_id, sort_order, type_desc_key,
        event_owner_team_id, zone_code, x_coord, y_coord,
        (period_number - 1) * 1200
            + cast(split(time_in_period, ':')[offset(0)] as int64) * 60
            + cast(split(time_in_period, ':')[offset(1)] as int64) as elapsed_seconds
    from {staging}.stg_play_by_play
    where time_in_period is not null and season in ({seasons})
),
shots as (
    select game_id, season, event_id, sort_order, elapsed_seconds,
           event_owner_team_id as team_id,
           (type_desc_key = 'goal') as is_goal
    from pbp
    where type_desc_key in ('shot-on-goal', 'missed-shot', 'goal')
      and x_coord is not null and y_coord is not null
),
prior as (
    select
        s.game_id, s.event_id, s.season, s.is_goal,
        s.elapsed_seconds - e.elapsed_seconds as dt,
        e.sort_order as e_sort,
        e.type_desc_key as e_type,
        (e.event_owner_team_id = s.team_id) as e_same_team,
        case
            when e.event_owner_team_id = s.team_id then e.zone_code
            when e.zone_code = 'O' then 'D'
            when e.zone_code = 'D' then 'O'
            else 'N'
        end as e_zone_rel
    from shots s
    join pbp e
        on e.game_id = s.game_id
       and e.sort_order < s.sort_order
       and s.elapsed_seconds - e.elapsed_seconds between 0 and {window}
),
prior_w as (
    select *,
        max(if(e_type = 'faceoff', e_sort, null))
            over (partition by game_id, event_id) as fo_sort
    from prior
),
flagged as (
    select s.game_id, s.event_id, s.season, s.is_goal,
        coalesce(logical_or({flag_expr}), false) as flag
    from shots s
    left join prior_w p using (game_id, event_id)
    group by 1, 2, 3, 4
)
select season, flag, count(*) as shots, sum(cast(is_goal as int64)) as goals
from flagged group by season, flag
"""

FLAG_EXPRS = {
    "rebound": "p.e_type in ('shot-on-goal','missed-shot','goal') and p.e_same_team and p.dt <= {w}",
    "rush": "p.e_zone_rel in ('D','N') and p.dt <= {w} and (p.fo_sort is null or p.e_sort > p.fo_sort)",
    "forecheck": (
        "p.e_zone_rel = 'O' and p.dt <= {w} and "
        "((p.e_type='takeaway' and p.e_same_team) or (p.e_type='giveaway' and not p.e_same_team))"
    ),
}


def sweep_flag(client, flag: str, windows: list[int], seasons: list[str]) -> list[dict]:
    rows = []
    for w in windows:
        sql = FLAG_SQL.format(
            staging=STAGING,
            seasons=_season_list(seasons),
            window=w,
            flag_expr=FLAG_EXPRS[flag].format(w=w),
        )
        per_season = {}
        agg = {True: [0, 0], False: [0, 0]}  # flag -> [shots, goals]
        for r in client.query(sql).result():
            agg[r.flag][0] += r.shots
            agg[r.flag][1] += r.goals
            ps = per_season.setdefault(r.season, [0, 0])  # [flagged_shots, total_shots]
            ps[1] += r.shots
            if r.flag:
                ps[0] += r.shots
        f_shots, f_goals = agg[True]
        u_shots, u_goals = agg[False]
        total = f_shots + u_shots
        gr_f = f_goals / f_shots if f_shots else 0.0
        gr_u = u_goals / u_shots if u_shots else 0.0
        shares = [ps[0] / ps[1] for ps in per_season.values() if ps[1]]
        rows.append({
            "flag": flag, "window": w,
            "share": f_shots / total if total else 0.0,
            "goal_pct_flagged": 100 * gr_f,
            "goal_pct_unflagged": 100 * gr_u,
            "lift": gr_f / gr_u if gr_u else float("nan"),
            "season_share_spread": (max(shares) - min(shares)) if shares else 0.0,
        })
    return rows


def print_table(rows: list[dict]) -> None:
    print(f"{'flag':10} {'win':>3} {'share':>7} {'goal%F':>7} {'goal%U':>7} "
          f"{'lift':>5} {'seas_spread':>11}")
    for r in rows:
        print(f"{r['flag']:10} {r['window']:>3} {100*r['share']:>6.1f}% "
              f"{r['goal_pct_flagged']:>6.2f}% {r['goal_pct_unflagged']:>6.2f}% "
              f"{r['lift']:>5.2f} {100*r['season_share_spread']:>10.2f}%")


def recommend(rows: list[dict]) -> dict[str, int]:
    """Pick, per flag, the window with the highest lift whose season-share spread stays
    within 2 percentage points of the most-stable candidate (separation, then stability)."""
    best = {}
    by_flag: dict[str, list[dict]] = {}
    for r in rows:
        by_flag.setdefault(r["flag"], []).append(r)
    for flag, cands in by_flag.items():
        min_spread = min(c["season_share_spread"] for c in cands)
        stable = [c for c in cands if c["season_share_spread"] <= min_spread + 0.02]
        best[flag] = max(stable, key=lambda c: c["lift"])["window"]
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="*", default=DEFAULT_SEASONS)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the SQL for one flag and exit (no BigQuery cost)")
    args = ap.parse_args()

    if args.dry_run:
        print(FLAG_SQL.format(staging=STAGING, seasons=_season_list(args.seasons),
                              window=5, flag_expr=FLAG_EXPRS["rush"].format(w=5)))
        return

    client = _client()
    all_rows = []
    print(f"Sweeping over seasons: {', '.join(args.seasons)}\n")
    all_rows += sweep_flag(client, "rebound", REBOUND_WINDOWS, args.seasons)
    all_rows += sweep_flag(client, "rush", RUSH_WINDOWS, args.seasons)
    all_rows += sweep_flag(client, "forecheck", FORECHECK_WINDOWS, args.seasons)
    print_table(all_rows)
    print("\nRecommended windows (max lift among season-stable candidates):")
    for flag, w in recommend(all_rows).items():
        print(f"  {flag}_window_seconds: {w}")


if __name__ == "__main__":
    main()
