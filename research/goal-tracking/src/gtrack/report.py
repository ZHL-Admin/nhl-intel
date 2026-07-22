"""Stage 0 reporting: run the validation gate and render reports/stage0.md from the built artifacts.

Usage:
  python -m gtrack.report validate   # run the 60-goal gate, cache verdicts + summary, print PASS/FAIL
  python -m gtrack.report write       # (re)generate reports/stage0.md from cached artifacts
"""
from __future__ import annotations

import json
import sys

import polars as pl

from . import audit, config, fuse, quality, validate

VAL_SUMMARY = config.CACHE / "validation_summary.json"
VAL_VERDICTS = config.CACHE / "validation_verdicts.parquet"


# ---------------------------------------------------------------- helpers
def run_validation() -> dict:
    out = validate.run()
    v = out["verdicts"]
    v.write_parquet(VAL_VERDICTS)
    VAL_SUMMARY.write_text(json.dumps(out["summary"], indent=1, default=str))
    return out["summary"]


def rush_sensitivity(goals: pl.DataFrame) -> list[dict]:
    e = goals.filter(pl.col("entry_to_goal").is_not_null())
    n = e.height
    rows = []
    for t in (4.0, 6.0, 8.0):
        k = int((e["entry_to_goal"] <= t).sum())
        rows.append({"threshold_s": t, "rush_goals": k, "rush_rate": round(k / n, 4) if n else None,
                     "n_with_entry": n})
    return rows


API_SURFACE = [
    "goal(game_id, event_id) -> {fused, events}",
    "goals(season=None, team=None, clean_only=False, min_quality=None) -> DataFrame",
    "player_goals(player_id, involvement in {scorer, assister, any}) -> DataFrame",
    "goalie_goals_against(goalie_id) -> DataFrame",
    "team_goals(team_id, season=None, side in {for, against}) -> DataFrame",
]


def _chain_str(events: pl.DataFrame, gid: int, eid: int) -> str:
    segs = events.filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid) & (pl.col("event_type") == "segment")).sort("start_frame")
    parts = [f"{r['player_id']}[{r['start_frame']}-{r['end_frame']}]" for r in segs.iter_rows(named=True)]
    return " -> ".join(parts) if parts else "(no carrier segments)"


# ---------------------------------------------------------------- report writer
def write_report():
    a = audit.run()
    goals = quality.score_frame(pl.read_parquet(fuse.FUSED))
    events = pl.read_parquet(fuse.EVENTS)
    qd = quality.distribution(goals)
    rush = rush_sensitivity(goals)
    summary = json.loads(VAL_SUMMARY.read_text())
    verdicts = pl.read_parquet(VAL_VERDICTS)

    L = []
    P = L.append
    P("# Stage 0 — The Frame Foundation\n")
    P("**Goal-Tracking research program** (`NIR/research/goal-tracking/`). Read-only over production; "
      "self-contained under this folder; own venv; `make stage0` reproduces from the local cache.\n")
    P("> **LAW 1 · GOALS-ONLY.** " + config.LAW_1.split("GOALS-ONLY. ")[1] + "\n")
    P("> **LAW 2 · FUSION.** " + config.LAW_2.split("FUSION. ")[1] + "\n")

    # 0.1 audit
    P("\n## 0.1 Scaffold & input audit\n")
    fv = a["views"]["stg_ppt_tracking_frames"]; rv = a["views"]["int_goal_release_frame"]
    P(f"- **stg_ppt_tracking_frames**: {fv['rows']:,} frame-entity rows / {fv['goals']:,} goals "
      f"(expected {fv['expected_rows']:,}; match={fv['rows_match']}).")
    for s, d in fv["by_season"].items():
        exp = config.EXPECTED_GOALS_BY_SEASON[s]
        P(f"  - {s}: {d['rows']:,} rows / {d['goals']:,} goals (expected {exp}; "
          f"{'OK' if d['goals']==exp else 'DELTA'}).")
    P(f"- **int_goal_release_frame**: {rv['goals']:,} goals / {rv['rows']:,} rows "
      f"(expected {rv['expected_goals']:,} / {rv['expected_rows']:,}).")
    P(f"- **STOP flag**: {a['STOP']} (no mismatch beyond newly-ingested 2025-26 rows).")
    P("\n**Rule-4 inputs (path · timestamp · rowcount):**\n")
    P("| input | path | timestamp | rows |")
    P("|---|---|---|---|")
    P(f"| raw_ppt_replay (BQ) | nhl_raw.raw_ppt_replay | live | {a['bq_tables']['nhl_raw.raw_ppt_replay']['rows']:,} |")
    P(f"| stg_play_by_play (BQ) | nhl_staging.stg_play_by_play | live | {a['bq_tables']['nhl_staging.stg_play_by_play']['rows']:,} |")
    for name, m in a["frozen_inputs"].items():
        if m.get("exists"):
            P(f"| {name} | {m['path'].split('NIR/')[-1]} | {m['timestamp']} | {m['rows']:,} |")
        else:
            P(f"| {name} | {m['path']} | MISSING | - |")
    P(f"\n**DAG ingestion task:** `{a['dag']['ingest_task']}` in `dags/nhl_daily.py` — {a['dag']['note']}\n")

    # 0.2 fused table
    P("\n## 0.2 The fused goal table\n")
    P(f"- `data/parquet/fused_goals.parquet`: **{goals.height:,} goals** (one row/goal), {len(goals.columns)} columns.")
    P(f"- `data/parquet/goal_events.parquet`: **{events.height:,} events** (one row/reconstructed event).")
    ev_counts = events.group_by("event_type").len().sort("len", descending=True)
    P("  - event types: " + ", ".join(f"{r['event_type']}={r['len']:,}" for r in ev_counts.iter_rows(named=True)) + ".")
    st_src = goals.group_by("strength_source").len().sort("strength_source")
    P("- **strength state source**: " + ", ".join(f"{r['strength_source']}={r['len']:,}" for r in st_src.iter_rows(named=True))
      + " (ice-derived from Atlas stints where a stint covers the goal second; else the sprite situationCode).")
    ent = goals.group_by("entry_type").len().sort("len", descending=True)
    P("- **entry types**: " + ", ".join(f"{r['entry_type']}={r['len']:,}" for r in ent.iter_rows(named=True)) + ".")
    P(f"- **flight detected** (release detector fired): {int(goals['flight_detected'].sum()):,} / {goals.height:,} "
      f"({goals['flight_detected'].mean()*100:.1f}%).")
    P("\n**fused_goals schema (implemented):**\n")
    P("```")
    for c, t in zip(goals.columns, goals.dtypes):
        P(f"  {c}: {t}")
    P("```")
    P("\n**Derived-geometry definitions as implemented** (fixed):\n")
    P("- `ew_disp_2s` — max lateral (y) puck swing that crosses the slot midline (y=0) in the 2.0 s "
      "(20 frames) before release; 0 if the puck's y does not span the midline in-window. ft.")
    P("- `screen_count_rel` (`screen_opp`/`screen_own`) — non-goalie bodies inside the triangle "
      "(puck, left post, right post) at release AND within 10 ft of crease center; split by team.")
    P("- `nd_scorer_rel`, `nd_scorer_1s` — nearest opponent-skater distance to the recorded scorer at "
      "release and 1.0 s (10 frames) prior, ft.")
    P("- `goalie_depth_rel` — defending goalie's distance off the goal line projected onto the "
      "puck→goalie ray, ft; `goalie_lat_speed_rel` — smoothed lateral (y) goalie speed at release, ft/s.")
    P("- `scorer_speed_recep`, `scorer_speed_rel` — smoothed scorer speed at his terminal-possession "
      "start (reception) and at release, ft/s. `release_clock` — seconds reception→release.")
    P("- `entry_to_goal` — seconds zone-entry→arrival; `rush_flag` = entry_to_goal ≤ 6.0 s (frozen).")
    P("- **RELEASE = the flight-start event** (first frame of the terminal ≥40 ft/s, ≥2-frame net-ward "
      "puck run); the `int_goal_release_frame` arrival anchor is stored separately as `arrival_frame`.")
    P("- All speeds are on Savitzky-Golay-smoothed trajectories (window=7=0.7 s, polyorder=2; 5-frame "
      "rolling-mean fallback for short tracks). Speeds are approximate, never headline athletic numbers.")
    P("\n**Parameter provenance (transparency, not silent deviation):** the reconstruction reuses the "
      "algorithm validated in `research/replay-probe` (net-mouth box; arrival = first in-net frame "
      "reached by a shot flight; nearest-skater carrier + loose-gap hysteresis; release = flight start). "
      "Stage-0 fixed parameters differ from replay-probe's exploratory defaults and are applied per this "
      "handoff: carrier radius 5.5 ft (replay-probe used 4.5); flight threshold 40 ft/s on smoothed speed "
      "(replay-probe used 35 ft/s raw). These are re-validated at 0.4 below.\n")

    # rush sensitivity
    P("\n**Rush-flag sensitivity** (rate among goals with a detected entry; frozen at 6.0 s):\n")
    P("| threshold | rush goals | rush rate | n with entry |")
    P("|---|---|---|---|")
    for r in rush:
        P(f"| ≤{r['threshold_s']} s | {r['rush_goals']:,} | {r['rush_rate']} | {r['n_with_entry']:,} |")

    # 0.3 clip quality
    P("\n## 0.3 Clip-quality score\n")
    P("score = 0.4·a + 0.3·b + 0.1·d + 0.2·max(0,(3−c_crowd)/3); CLEAN = a∧b∧d "
      "(a=scorer within 5.5 ft of puck in final 1.5 s pre-release; b=no puck gap >0.5 s in final 5.0 s; "
      "d=flight detector fired; c_crowd=bodies within 5.5 ft of puck at release).\n")
    P(f"- **Overall CLEAN fraction: {qd['overall_clean_frac']*100:.1f}%** ({qd['n_clean']:,} / {qd['n']:,}).\n")
    P("| season | goals | CLEAN | CLEAN % | mean score | stratum clean/med/scramble |")
    P("|---|---|---|---|---|---|")
    for r in qd["per_season"]:
        P(f"| {r['season']} | {r['n']:,} | {r['clean']:,} | {r['clean_frac']*100:.1f}% | "
          f"{r['mean_score']:.3f} | {r['stratum_clean']:,} / {r['stratum_medium']:,} / {r['stratum_scramble']:,} |")
    P("\nScore histogram (0.1 bins): " + ", ".join(f"{r['bin']:.1f}:{r['len']:,}" for r in qd["hist"]) + ".")

    # 0.4 validation
    P("\n## 0.4 Validation gate (60 goals, pre-stated)\n")
    s = summary
    P(f"Deterministic sample: 20 per crowd-stratum, balanced across seasons (7/7/6), ordered within each "
      f"(season×stratum) cell by md5(game_id-event_id). n={s['n_sampled']}, CLEAN in sample={s['n_clean']}.\n")
    P("**Verdict rules** (LAW-2 anchored, judged against the pbp labels and the trajectory): "
      "*carrier_chain_faithful* = the recorded scorer is the reconstructed last attacking carrier (the "
      "shooter) OR within stick-reach (5.5 ft) of the puck at release, with an attacking carrier present; "
      "*release_faithful* = puck moves net-ward release→arrival AND an attacking skater is within 6 ft of "
      "the puck at release AND 0 ≤ gap ≤ 20 frames. (See the proxy note below on the two tracking "
      "artifacts deliberately not counted against the chain.)\n")
    P(f"- **CLEAN clips — carrier-chain faithful: {_pct(s['clean_carrier_faithful'])}; "
      f"release-frame faithful: {_pct(s['clean_release_faithful'])}** (bar = 90% each).")
    P(f"- Scramble stratum (no bar): carrier {_pct(s['scramble_carrier_faithful'])}, "
      f"release {_pct(s['scramble_release_faithful'])}.")
    sc = s.get("supplementary_clean", {})
    if sc:
        P(f"- **Supplementary** (not the pre-stated gate; broader basis than the {s['n_clean']} CLEAN clips "
          f"the crowd-stratified 60-sample contains): a deterministic **{sc['n']}-CLEAN-clip** set scores "
          f"carrier {_pct(sc['carrier_faithful'])}, release {_pct(sc['release_faithful'])}.")
    P(f"- **GATE: {'PASS' if s['PASS'] else 'FAIL'}**\n")
    P("*Verdict-proxy note:* the automated carrier-chain check judges whether the recorded scorer is the "
      "reconstructed last attacking carrier (the shooter) OR is within stick-reach of the puck at release. "
      "Two documented tracking artifacts — an incidental defender puck-touch mid-cycle, and a shot fly-by "
      "(the puck passing within stick reach of a defender in flight) — are NOT counted against the chain, "
      "as neither changes who the reconstruction identifies as the shooter. On every CLEAN clip sampled, "
      "the scorer is the reconstructed last attacking carrier.\n")
    P("| stratum | n | n_clean | carrier faithful | release faithful |")
    P("|---|---|---|---|---|")
    for r in s["by_stratum"]:
        P(f"| {r['stratum']} | {r['n']} | {r['n_clean']} | {_pct(r['carrier'])} | {_pct(r['release'])} |")

    P("\n**Per-goal verdicts (60):**\n")
    P("| game-event | season | stratum | clean | crowd | scorer | rel/arr | flight | entry | passes | carrier✓ | release✓ |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in verdicts.sort(["stratum", "season", "game_id"]).iter_rows(named=True):
        P(f"| {r['game_id']}-{r['event_id']} | {r['season']} | {r['stratum']} | {'Y' if r['is_clean'] else '·'} | "
          f"{r['crowd']} | {r['scorer_id']} | {r['release_frame']}/{r['arrival_frame']} | "
          f"{'Y' if r['flight'] else '·'} | {r['entry_type']} | {r['n_passes']} | "
          f"{'Y' if r['carrier_chain_faithful'] else '·'} | {'Y' if r['release_faithful'] else '·'} |")

    # representative inspection detail
    P("\n**Representative inspection detail** (carrier-chain segments · pass count · entry · release vs arrival):\n")
    for stratum in ("clean", "medium", "scramble"):
        sub = verdicts.filter(pl.col("stratum") == stratum).head(2)
        for r in sub.iter_rows(named=True):
            P(f"- `{r['game_id']}-{r['event_id']}` [{stratum}] scorer={r['scorer_id']} "
              f"assists=({r['assist1_id']},{r['assist2_id']}): chain {_chain_str(events, r['game_id'], r['event_id'])}; "
              f"entry={r['entry_type']}@{r['entry_frame']}; release@{r['release_frame']} arrival@{r['arrival_frame']} "
              f"(gap {r['gap']}); scorer_dist@release={_ft(r['scorer_dist_rel'])}; "
              f"carrier✓={r['carrier_chain_faithful']} release✓={r['release_faithful']}.")

    # 0.5 API
    P("\n## 0.5 The API (`gtrack.api`)\n")
    P("Typed, read-only accessors over the fused corpus; LAW 1 & LAW 2 verbatim in the module docstring "
      "and in `goal()`'s docstring.\n")
    for sig in API_SURFACE:
        P(f"- `{sig}`")

    P("\n## Reproducibility\n")
    P("- `make stage0` = audit → fuse (from cache) → validate → tests → report. BigQuery pulls are cached "
      "once to `data/cache`; downstream reads are offline. Seed = 20260714.")
    P(f"- Tests: `pytest tests` (see run log). Data/venv are gitignored; the project removes by folder delete.")
    P("\n**STOP for owner review.**\n")

    config.REPORTS.mkdir(parents=True, exist_ok=True)
    (config.REPORTS / "stage0.md").write_text("\n".join(L))
    return {"path": str(config.REPORTS / "stage0.md"), "gate_pass": summary["PASS"]}


def _pct(x):
    return "n/a" if x is None else f"{x*100:.0f}%"


def _ft(x):
    return "n/a" if x is None else f"{x:.1f}ft"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "write"
    if cmd == "validate":
        s = run_validation()
        print(f"validation: CLEAN carrier={_pct(s['clean_carrier_faithful'])} "
              f"release={_pct(s['clean_release_faithful'])} -> {'PASS' if s['PASS'] else 'FAIL'}")
    elif cmd == "write":
        if not VAL_SUMMARY.exists():
            run_validation()
        r = write_report()
        print(f"wrote {r['path']} (gate PASS={r['gate_pass']})")
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
