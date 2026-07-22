"""Stage 2 — the state value function V(state) and league accounting constants (spec Sections 6.2-6.3).

V(state) = tick-duration-weighted mean of net goals (possessing team minus opponent) over the forward
window (t, t+H] within the same period, across all live-5v5 ticks in that state. Pure counting, no model.
v1 counts ALL non-shootout goals in the window regardless of mid-window strength (PV-A4). Primary scope:
2015-16 onward (PRIMARY_SCOPE_START). Uncertainty: cluster bootstrap by game_id (200 resamples).

Writes nhl_models.state_values and nhl_models.phase_league_constants (WRITE_TRUNCATE — single-scope v1).
HARD GATE: V(P_OZ_EST) > V(P_NZ) > V(P_OWN_D) — else STOP.

Run: GCP_PROJECT_ID=... GOOGLE_APPLICATION_CREDENTIALS=secrets/nhl-intel-sa.json \
     python -m models_ml.phase_value.compute_state_values
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from models_ml import config, bq

CFG = config.PHASE_VALUE_CONFIG
H = CFG["H_SECONDS"]
SCOPE_START = CFG["PRIMARY_SCOPE_START"]
N_BOOT = 200
SEED = CFG["SEED"]
MODEL_VERSION = "phase_value_v1"
STATES = ["P_OWN_D", "P_NZ", "P_OZ_RUSH", "P_OZ_EST"]

# per (game, state) weighted outcome over the forward window; goals = all non-shootout (PV-A4)
PER_GAME_SQL = """
with goals as (
  select game_id, period_number, event_owner_team_id as scoring_team,
    (period_number-1)*1200 + cast(split(time_in_period, ':')[offset(0)] as int64)*60
      + cast(split(time_in_period, ':')[offset(1)] as int64) as elapsed
  from `{p}.nhl_staging.stg_play_by_play`
  where type_desc_key = 'goal' and coalesce(period_type,'') != 'SO' and time_in_period is not null
),
tk as (
  select game_id, season, period_number, tick_elapsed, tick_duration, possession_team_id, state
  from `{p}.nhl_staging.int_phase_ticks`
  where season >= '{scope}'
),
per_tick as (
  select tk.game_id, tk.season, tk.state, tk.tick_duration,
    coalesce(sum(case when g.scoring_team = tk.possession_team_id then 1
                      when g.scoring_team is not null then -1 else 0 end), 0) as net
  from tk left join goals g
    on g.game_id = tk.game_id and g.period_number = tk.period_number
   and g.elapsed > tk.tick_elapsed and g.elapsed <= tk.tick_elapsed + {h}
  group by tk.game_id, tk.season, tk.state, tk.period_number, tk.tick_elapsed,
           tk.possession_team_id, tk.tick_duration
)
select game_id, season, state, sum(net * tick_duration) as wsum, sum(tick_duration) as wdur, count(*) as n
from per_tick group by game_id, season, state
"""


def _v_from(df: pd.DataFrame) -> dict:
    g = df.groupby("state").agg(wsum=("wsum", "sum"), wdur=("wdur", "sum"))
    return {s: (g.loc[s, "wsum"] / g.loc[s, "wdur"]) for s in g.index}


def compute_v(client):
    df = bq.query_df(PER_GAME_SQL.format(p=bq.project(), scope=SCOPE_START, h=H), client)
    pooled = _v_from(df)
    n_ticks = df.groupby("state")["n"].sum().to_dict()

    # vectorized cluster bootstrap by game: pivot to (game x state) weighted sums, resample game rows.
    wsum = (df.pivot_table(index="game_id", columns="state", values="wsum", aggfunc="sum", fill_value=0.0)
              .reindex(columns=STATES, fill_value=0.0).values)
    wdur = (df.pivot_table(index="game_id", columns="state", values="wdur", aggfunc="sum", fill_value=0.0)
              .reindex(columns=STATES, fill_value=0.0).values)
    rng = np.random.default_rng(SEED)
    G = wsum.shape[0]
    boot_v = np.empty((N_BOOT, len(STATES)))
    for i in range(N_BOOT):
        idx = rng.integers(0, G, G)
        boot_v[i] = wsum[idx].sum(0) / wdur[idx].sum(0)
    se = boot_v.std(axis=0)
    rows = [{"state": s, "scope": f"{SCOPE_START}+", "v": float(pooled.get(s, np.nan)),
             "se": float(se[j]), "n_ticks": int(n_ticks.get(s, 0)),
             "h_seconds": H, "model_version": MODEL_VERSION} for j, s in enumerate(STATES)]
    v_df = pd.DataFrame(rows)

    seas = []
    for season, sub in df.groupby("season"):
        vs = _v_from(sub)
        for s in STATES:
            seas.append({"season": season, "state": s, "v": float(vs.get(s, np.nan))})
    return v_df, pd.DataFrame(seas)


LEAGUE_SQL = """
with ep as (select * from `{p}.nhl_staging.int_zone_episodes` where season >= '{scope}'),
spell5 as (
  select game_id, poss_team_id, state_rel, duration_seconds
  from `{p}.nhl_staging.int_phase_spells` where is_5v5 and is_live and season >= '{scope}'
),
game5 as (select game_id, sum(duration_seconds) as sec_5v5 from spell5 group by game_id),
outside as (select game_id, poss_team_id, sum(duration_seconds) as sec
            from spell5 where state_rel in ('P_OWN_D','P_NZ') group by game_id, poss_team_id),
inzone as (select game_id, poss_team_id, sum(duration_seconds) as sec
           from spell5 where state_rel = 'P_OZ' group by game_id, poss_team_id),
cal as (
  select sum(if(ss.is_goal,1,0)) as g, sum(coalesce(x.xg,0)) as xg
  from `{p}.nhl_staging.int_shot_sequence` ss
  left join `{p}.nhl_models.shot_xg` x using (game_id, event_id)
  where ss.strength='5v5' and ss.season >= '{scope}'
)
select
  (select avg(sec) from outside) as outside_sec_per_teamgame,
  (select avg(sec) from inzone)  as inzone_sec_per_teamgame,
  (select avg(sec_5v5) from game5) as game_5v5_sec,
  (select avg(xg_5v5)   from ep where start_type != 'oz_faceoff') as c_seq_xg_nonfo,
  (select avg(goals_5v5) from ep where start_type != 'oz_faceoff') as c_seq_ga_nonfo,
  (select avg(xg_5v5)   from ep where start_type = 'rush')       as c_seq_xg_rush,
  (select avg(xg_5v5)   from ep where start_type = 'forecheck')  as c_seq_xg_forecheck,
  (select avg(xg_5v5)   from ep where start_type = 'carry_other') as c_seq_xg_carry,
  (select avg(xg_5v5)   from ep where start_type = 'oz_faceoff') as c_seq_xg_ozfo,
  (select sum(xg_5v5)/nullif(sum(duration_5v5_seconds),0) from ep) as r_inzone_xg_per_sec,
  (select g from cal) as cal_goals, (select xg from cal) as cal_xg
"""


def compute_constants(client) -> pd.DataFrame:
    r = bq.query_df(LEAGUE_SQL.format(p=bq.project(), scope=SCOPE_START), client).iloc[0]
    game5 = r["game_5v5_sec"]
    xg_cal = r["cal_goals"] / r["cal_xg"] if r["cal_xg"] else 1.0
    cal_applied = xg_cal if abs(xg_cal - 1.0) > CFG["XG_CAL_TOLERANCE"] else 1.0
    vals = {
        "s_out_min_per_60": r["outside_sec_per_teamgame"] / game5 * 60.0,
        "s_in_min_per_60": r["inzone_sec_per_teamgame"] / game5 * 60.0,
        "c_seq_xg_nonfo": r["c_seq_xg_nonfo"], "c_seq_ga_nonfo": r["c_seq_ga_nonfo"],
        "c_seq_xg_rush": r["c_seq_xg_rush"], "c_seq_xg_forecheck": r["c_seq_xg_forecheck"],
        "c_seq_xg_carry": r["c_seq_xg_carry"], "c_seq_xg_ozfo": r["c_seq_xg_ozfo"],
        "r_inzone_xg_per_sec": r["r_inzone_xg_per_sec"],
        "xg_calibration_raw": xg_cal, "xg_calibration": cal_applied,
    }
    return pd.DataFrame([{"constant_name": k, "value": float(v), "scope": f"{SCOPE_START}+",
                          "model_version": MODEL_VERSION} for k, v in vals.items()])


def main():
    client = bq.client()
    print(f"[state_values] scope={SCOPE_START}+ H={H}s bootstrap={N_BOOT}")
    v_df, seas = compute_v(client)
    print(v_df.to_string(index=False))

    v = {r.state: r.v for r in v_df.itertuples()}
    gate = v["P_OZ_EST"] > v["P_NZ"] > v["P_OWN_D"]
    print(f"\nHARD GATE V(P_OZ_EST) > V(P_NZ) > V(P_OWN_D): "
          f"{v['P_OZ_EST']:.5f} > {v['P_NZ']:.5f} > {v['P_OWN_D']:.5f}  -> {'PASS' if gate else 'FAIL'}")
    print(f"(report-only) V(P_OZ_RUSH)={v['P_OZ_RUSH']:.5f}  (expect >= V(P_OZ_EST)={v['P_OZ_EST']:.5f})")
    if not gate:
        print("STOP: hard gate failed — the state engine or the outcome join is wrong, not hockey.")
        sys.exit(1)

    const_df = compute_constants(client)
    print("\nLeague constants:")
    print(const_df.to_string(index=False))

    stamp = datetime.now(timezone.utc)
    v_df["computed_at"] = stamp
    const_df["computed_at"] = stamp
    bq.write_df(v_df, "state_values")
    bq.write_df(const_df, "phase_league_constants")
    os.makedirs("artifacts/phase_value", exist_ok=True)
    seas.to_csv("artifacts/phase_value/state_values_by_season.csv", index=False)
    print("\nWrote nhl_models.state_values, nhl_models.phase_league_constants, "
          "artifacts/phase_value/state_values_by_season.csv")


if __name__ == "__main__":
    main()
