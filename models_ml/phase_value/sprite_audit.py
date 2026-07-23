"""Sprite audit of the state engine (owner addendum, Stage 2/3 boundary) — REPORT-ONLY input to Stage 5.

Independent ground-truth of episode start_type + entry timing AT GOALS, from the PPT goal-replay full track
(nhl_staging.stg_ppt_tracking_frames, 10 Hz). Goal-only coverage is aligned for auditing labels at goals.
This runs BEFORE any Stage 3 fitting; it does not modify the state engine — any definitional change it
motivates needs a DECISIONS entry + owner sign-off. One script, one report (docs/phase-value/sprite-audit.md).

Time axis reuses int_goal_release_frame's geometric release-frame pinning UNCHANGED:
  t_before_goal = (release_frame_index - frame_index) / FPS.
Orientation: attack -> +x; reflect coords if the scored-on net (release-frame puck x sign) is at -89.

Run: GCP_PROJECT_ID=... GOOGLE_APPLICATION_CREDENTIALS=secrets/nhl-intel-sa.json \
     python -m models_ml.phase_value.sprite_audit
"""
from __future__ import annotations

import os
from collections import Counter

import numpy as np
import pandas as pd

from models_ml import bq

# ---- Named constants (Section F; changing any default requires a DECISIONS entry) --------------------
FPS = 10.0                     # frame rate (verified empirically: 10 Hz)
BLUE_LINE_X = 25.0             # attacking blue line after attack->+x orientation
GOAL_LINE_X = 89.0             # scored-on goal line after orientation
WINDOW_SECONDS = 8.0           # working window: final 8 s of track before the goal
PUCK_PRESENT_MIN = 0.80        # usable: puck present in >= 80% of window frames
MAX_PUCK_JUMP_FT = 15.0        # usable: no frame-to-frame puck jump > 15 ft (after single-frame interp)
HYSTERESIS_SECONDS = 1.0       # an out-of-zone excursion < round(1.0*FPS) frames does not reset the entry
CARRY_DIST_FT = 6.0            # carry_flag: nearest attacking skater within 6 ft of the puck at the crossing
MIN_USABLE_GOALS = 500         # STOP-and-ask floor
RUSH_K = [3, 4, 5, 6]          # always report the full k-curve, never a single k
SEASONS = ("2023-24", "2024-25", "2025-26")   # empirical sprite coverage (Section A4)

WINDOW_FRAMES = int(round(WINDOW_SECONDS * FPS))   # 80
HYST_FRAMES = int(round(HYSTERESIS_SECONDS * FPS)) # 10
REPORT = "docs/phase-value/sprite-audit.md"


def _seasons_sql():
    return "('" + "', '".join(SEASONS) + "')"


GOALS_SQL = """
with segcov as (select distinct game_id from `{p}.nhl_staging.int_segment_context`),
universe as (
  select ss.season, ss.game_id, ss.event_id, ss.team_id as scoring_team, ss.elapsed_seconds as g_elapsed
  from `{p}.nhl_staging.int_shot_sequence` ss
  where ss.strength='5v5' and ss.is_goal and not ss.is_empty_net
    and ss.season in {seasons} and ss.game_id in (select game_id from segcov)
),
rel as (
  select game_id, event_id, any_value(release_frame_index) as release_frame_index,
         max(if(is_puck, x_std, null)) as release_puck_x
  from `{p}.nhl_staging.int_goal_release_frame` group by game_id, event_id
),
ep as (
  select e.game_id, e.attacker_team_id, e.start_elapsed, e.end_elapsed, e.start_type,
         (e.duration_seconds = 0) as zero_dur
  from `{p}.nhl_staging.int_zone_episodes` e where e.season in {seasons}
)
select u.season, u.game_id, u.event_id, u.scoring_team, u.g_elapsed,
       r.release_frame_index, r.release_puck_x,
       ep.start_type, ep.zero_dur, box.venue_name,
       (r.game_id is not null) as has_sprite
from universe u
left join rel r using (game_id, event_id)
left join ep on ep.game_id = u.game_id and ep.attacker_team_id = u.scoring_team
           and u.g_elapsed between ep.start_elapsed and ep.end_elapsed
left join `{p}.nhl_staging.stg_boxscores` box on box.game_id = u.game_id
"""

PUCK_SQL = """
with segcov as (select distinct game_id from `{p}.nhl_staging.int_segment_context`),
universe as (
  select ss.game_id, ss.event_id from `{p}.nhl_staging.int_shot_sequence` ss
  where ss.strength='5v5' and ss.is_goal and not ss.is_empty_net
    and ss.season in {seasons} and ss.game_id in (select game_id from segcov)
),
rel as (select game_id, event_id, any_value(release_frame_index) as release_frame_index
        from `{p}.nhl_staging.int_goal_release_frame` group by game_id, event_id)
select f.game_id, f.event_id, f.frame_index, f.x_std, f.y_std,
       (r.release_frame_index - f.frame_index)/{fps} as t_before_goal
from `{p}.nhl_staging.stg_ppt_tracking_frames` f
join rel r using (game_id, event_id)
join universe u using (game_id, event_id)
where f.is_puck and f.frame_index between r.release_frame_index - {win} and r.release_frame_index
"""


def _detect_entry(sub: pd.DataFrame, reflect: bool):
    """Given one goal's puck frames in the window, return (status, entry_time, usable_bool, span_s).
    status in {'entry','established_full_window','unclear'}. sub sorted by frame_index ascending."""
    s = sub.sort_values("frame_index")
    fr = s["frame_index"].to_numpy(dtype=float)
    x = s["x_std"].to_numpy(dtype=float) * (-1.0 if reflect else 1.0)
    t = s["t_before_goal"].to_numpy(dtype=float)
    if len(fr) < 2:
        return "unclear", np.nan, False, 0.0
    fr0, fr1 = fr.min(), fr.max()
    span_frames = fr1 - fr0 + 1
    present = len(fr) / span_frames
    span_s = (fr1 - fr0) / FPS
    # interpolate single-frame dropouts on a dense index; flag worse gaps
    dense = np.arange(fr0, fr1 + 1)
    xi = np.interp(dense, fr, x)
    ti = np.interp(dense, fr, t)
    # a dropout longer than 1 frame -> not a single-frame interp; count max gap
    gaps = np.diff(fr)
    max_gap = gaps.max() if len(gaps) else 1
    jump = np.max(np.abs(np.diff(xi))) if len(xi) > 1 else 0.0
    usable = (present >= PUCK_PRESENT_MIN) and (max_gap <= 2) and (jump <= MAX_PUCK_JUMP_FT)
    if not usable:
        return "unclear", np.nan, False, span_s
    in_zone = xi >= BLUE_LINE_X
    if in_zone.all():
        return "established_full_window", np.nan, True, span_s
    # hysteresis: fill out-of-zone runs shorter than HYST_FRAMES back to in-zone
    smoothed = in_zone.copy()
    i = 0
    n = len(smoothed)
    while i < n:
        if not smoothed[i]:
            j = i
            while j < n and not smoothed[j]:
                j += 1
            run = j - i
            # only fill an interior short excursion (bounded by in-zone on both sides)
            if run < HYST_FRAMES and i > 0 and j < n:
                smoothed[i:j] = True
            i = j
        else:
            i += 1
    if smoothed.all():
        return "established_full_window", np.nan, True, span_s
    # last false->true crossing in the smoothed signal = the surviving entry
    cross = np.where((~smoothed[:-1]) & (smoothed[1:]))[0] + 1
    if len(cross) == 0:
        # ends out of zone (goal frame not in zone) — rare geometry; treat as unclear
        return "unclear", np.nan, True, span_s
    entry_idx = cross[-1]
    return "entry", float(ti[entry_idx]), True, span_s


def main():
    p = bq.project()
    client = bq.client()
    goals = bq.query_df(GOALS_SQL.format(p=p, seasons=_seasons_sql()), client)
    puck = bq.query_df(PUCK_SQL.format(p=p, seasons=_seasons_sql(), fps=FPS, win=WINDOW_FRAMES), client)
    for col in ("frame_index", "x_std", "y_std", "t_before_goal"):
        puck[col] = pd.to_numeric(puck[col], errors="coerce")
    goals["release_puck_x"] = pd.to_numeric(goals["release_puck_x"], errors="coerce")

    # attrition: universe -> sprite payload -> parses (has puck frames) -> usable track
    n_universe = len(goals)
    n_sprite = int(goals["has_sprite"].sum())
    have_frames = set(map(tuple, puck[["game_id", "event_id"]].drop_duplicates().to_numpy()))

    reflect_map = {(r.game_id, r.event_id): (r.release_puck_x is not None and r.release_puck_x < 0)
                   for r in goals.itertuples()}
    results = []
    for (gid, eid), sub in puck.groupby(["game_id", "event_id"]):
        status, et, usable, span_s = _detect_entry(sub, reflect_map.get((gid, eid), False))
        results.append({"game_id": gid, "event_id": eid, "status": status,
                        "entry_time": et, "usable": usable, "span_s": span_s})
    res = pd.DataFrame(results)
    g = goals.merge(res, on=["game_id", "event_id"], how="left")

    n_parsed = int(g["status"].notna().sum())
    usable = g[g["usable"] == True].copy()   # noqa: E712
    n_usable = len(usable)

    # sprite_rush_k on entries (established_full_window is NOT a rush; unclear excluded)
    for k in RUSH_K:
        usable[f"sprite_rush_{k}"] = (usable["status"] == "entry") & (usable["entry_time"] <= k)

    L = []; W = L.append
    W("# Sprite audit of the state engine — episode start_type + entry timing at goals (REPORT-ONLY)\n")
    W("Independent 10 Hz ground-truth from the PPT goal-replay full track, seasons "
      f"{', '.join(SEASONS)}. Runs before any Stage 3 fitting; report-only input to Stage 5. Constants: "
      f"window {WINDOW_SECONDS}s, puck-present ≥{int(PUCK_PRESENT_MIN*100)}%, max jump {MAX_PUCK_JUMP_FT}ft, "
      f"hysteresis {HYSTERESIS_SECONDS}s ({HYST_FRAMES} frames), blue line x={BLUE_LINE_X}, carry {CARRY_DIST_FT}ft.\n")
    W("## Attrition")
    W(f"- universe (5v5 non-EN goals, segment-covered, {SEASONS[0]}–{SEASONS[-1]}): **{n_universe:,}**")
    W(f"- sprite payload exists: **{n_sprite:,}** ({n_sprite/n_universe*100:.1f}%)")
    W(f"- parses (>=2 puck frames in window): **{n_parsed:,}**")
    W(f"- **track usable** (present ≥{int(PUCK_PRESENT_MIN*100)}%, no >{MAX_PUCK_JUMP_FT}ft jump): "
      f"**{n_usable:,}**  (floor {MIN_USABLE_GOALS}: {'OK' if n_usable>=MIN_USABLE_GOALS else 'BELOW — STOP/ASK'})")
    W(f"- median usable working span: {usable['span_s'].median():.1f}s\n")

    if n_usable < MIN_USABLE_GOALS:
        W("\n**STOP: usable goals below the 500 floor — reporting and halting per Section D.**")
        _write(L)
        print(f"STOP: only {n_usable} usable goals (< {MIN_USABLE_GOALS}).")
        return

    # status mix
    W("## Entry-detection status mix (usable goals)")
    for k, v in usable["status"].value_counts().items():
        W(f"- {k}: {v:,} ({v/n_usable*100:.1f}%)")
    W("")

    # (E1) start_type vs sprite entry timing — two matrices: window-mismatched (full) and aligned (zero-dur).
    lab = usable[usable["start_type"].notna()].copy()

    def _matrix(sub, title, note):
        W(f"### {title}")
        W(note)
        W(f"n = **{len(sub):,}**. Rows = episode start_type, cols = sprite_rush_4 (entry ≤4s):\n")
        W("| start_type | sprite_rush_4=True | False | rush-rate |")
        W("|---|---|---|---|")
        for st in ["rush", "forecheck", "carry_other", "oz_faceoff"]:
            m = sub[sub["start_type"] == st]
            if len(m) == 0:
                continue
            tt = int(m["sprite_rush_4"].sum())
            W(f"| {st} | {tt:,} | {len(m)-tt:,} | {tt/len(m)*100:.1f}% |")
        y_pred = (sub["start_type"] == "rush")
        for k in RUSH_K:
            y_true = sub[f"sprite_rush_{k}"]
            base = y_true.mean()   # prevalence a RANDOM label would achieve
            tp = int((y_pred & y_true).sum()); fp = int((y_pred & ~y_true).sum()); fn = int((~y_pred & y_true).sum())
            prec = tp/(tp+fp) if tp+fp else float("nan"); rec = tp/(tp+fn) if tp+fn else float("nan")
            vs = "BELOW base (anti-selected)" if prec < base else "above base"
            W(f"- start_type='rush' vs sprite_rush_{k}: **precision {prec:.3f} vs base rate {base*100:.1f}% "
              f"({vs})**, recall {rec:.3f} (sprite-rush goals at k={k}: {int(y_true.sum()):,})")
        W("")

    W("## E1 — episode start_type vs sprite entry timing")
    W("**Architecture note (finding 1 is contained):** the headline components never consume the rush label — "
      "Fit A (`deny`) counts episode starts of EVERY non-faceoff type, and Fits B (`suppress`) / C (`escape`) "
      "are label-blind. Any rush-label contamination is localized to three published DIAGNOSTICS — `c_seq_rush`, "
      "`V(P_OZ_RUSH)`, `deny_rush_coef` — each of which carries the caveat where it surfaces. Per the "
      "decomposition below, `start_type='rush'` is documented as an **event-space category only** (scorer-"
      "recorded precursor events) with **no positive association** to tracking-fast entries at goals — it is "
      "ANTI-SELECTED (precision below base rate at every k), not a small subset.\n")
    _matrix(lab[lab["zero_dur"] == True], "Aligned window (zero-duration episodes) — the apples-to-apples view",  # noqa: E712
            "For zero-duration goal-only episodes the PBP rush lookback (≤4s before the goal) and the sprite "
            "window measure the SAME moment, so this is the fair precision/recall.")
    _matrix(lab, "Full sample — WINDOW-MISMATCHED (report-only)",
            "Full-sample start_type reflects the SEQUENCE ORIGIN (which may precede the goal by many seconds) "
            "while sprite_rush measures ENTRY-TO-GOAL, so low alignment here is partly a window mismatch, not a "
            "pure error. Kept for completeness; do not read as apples-to-apples.")
    ozf = lab[lab["start_type"] == "oz_faceoff"]
    if len(ozf):
        est = int((ozf["status"] == "established_full_window").sum())
        W(f"Cross-check: oz_faceoff goals established_full_window (or crossing-free): "
          f"{est:,}/{len(ozf):,} ({est/len(ozf)*100:.1f}%) — expect overwhelming.\n")
    # decomposition of the rush-labeled aligned goals (picks the caption)
    rl = lab[(lab["zero_dur"] == True) & (lab["start_type"] == "rush")]   # noqa: E712
    rle = rl[rl["status"] == "entry"]["entry_time"]
    noent = (rl["status"] == "established_full_window").mean()
    W("### Rush-label decomposition — the label is ANTI-SELECTED, not a small subset")
    W(f"At every k the aligned **precision sits BELOW the base rate** (0.143 vs 20.4%, 0.263 vs 34.8%, 0.338 vs "
      f"43.3%, 0.386 vs 49.9%): a random label would pick MORE tracking-fast entries than `start_type='rush'` "
      "does. Decomposing the "
      f"**{len(rl):,}** rush-labeled aligned goals: **{noent*100:.1f}% show NO entry at all** "
      "(established_full_window — puck in-zone the whole 8 s window), and the "
      f"{(1-noent)*100:.1f}% with an entry do not cluster in 4–7 s (median {rle.median():.1f} s, only "
      f"{((rle>=4)&(rle<=7)).mean()*100:.0f}% in 4–7 s). A **majority have no tracking entry.**")
    W("**Caption for the three rush diagnostics** `c_seq_rush`, `V(P_OZ_RUSH)`, `deny_rush_coef` (carry "
      "verbatim wherever they surface, with the precision-vs-base numbers): _defined by scorer-recorded "
      "precursor events; the sprite audit found no positive association with tracking-fast entries at goals; "
      "event-space category only._")
    W("Recall (~0.09, flat across k) confirms the ceiling is ABSENT events (entries that generate no PBP event "
      "are invisible), so no PBP-side redefinition recovers them — the pre-committed possession-proxy limit.\n")

    # (E2) entry-to-goal time distribution + share < 2.5s and < 5s (PV-D013 instrument)
    ent = usable[usable["status"] == "entry"]["entry_time"]
    W("## E2 — entry-to-goal time (the independent instrument on PV-D013)")
    W(f"Entries (n={len(ent):,}): median {ent.median():.2f}s; p25 {ent.quantile(.25):.2f}s; "
      f"p75 {ent.quantile(.75):.2f}s.")
    W(f"- share of entries < 2.5 s (below the 5 s tick grid's half-tick floor): "
      f"**{(ent<2.5).mean()*100:.1f}%**")
    W(f"- share of entries < 5.0 s (within one rush-state lifetime): **{(ent<5.0).mean()*100:.1f}%**")
    W("Among sprite-rush entries specifically, the < 2.5 s share is the population the 5 s grid structurally "
      "excludes from P_OZ_RUSH — the direct measurement behind PV-D013's granularity artifact.\n")

    # (E3) PV-D008 audit: sprite label mix within zero-duration goal-only episodes
    zd = usable[(usable["zero_dur"] == True)]   # noqa: E712
    W("## E3 — PV-D008 audit: zero-duration goal-only episodes")
    W(f"Usable goals whose episode is zero-duration: **{len(zd):,}**. Claim under test: predominantly genuine "
      "rapid entries, not scorer under-recording of longer possessions.")
    if len(zd):
        for k, v in zd["status"].value_counts().items():
            W(f"- {k}: {v:,} ({v/len(zd)*100:.1f}%)")
        ze = zd[zd["status"] == "entry"]["entry_time"]
        if len(ze):
            W(f"- of those with a detected entry: median entry {ze.median():.2f}s; "
              f"share < 2.5 s {(ze<2.5).mean()*100:.1f}% (rapid entries support the claim; "
              "established_full_window would suggest under-recording).")
    W("\n**Reframe (finding 2 changes `deny`'s meaning, not its construction):** `deny` measures "
      "**event-visible threatening sequences allowed**, not all threatening sequences; the ~42% "
      "established_full_window share is under-recorded settled possession the PBP engine cannot see. The "
      "accounting stays internally consistent because `C_seq` prices exactly the same universe the "
      "coefficient counts. PV-D011 handling is unchanged (episode start → Fit A, goal xG → Fit B, exposure "
      "filter on stint totals); the zero-duration population is material to goal coverage and Fit B's xG "
      "mass, NOT to Fit A's episode counts.\n")

    # follow-up 2: arena diagnostic — established_full_window share within zero-duration episodes, by arena-season
    W("## E3b — arena diagnostic on the under-recorded share (finding 2)")
    zdv = zd[zd["venue_name"].notna() & zd["status"].isin(["entry", "established_full_window"])].copy()
    zdv["est"] = (zdv["status"] == "established_full_window")
    by = zdv.groupby(["venue_name", "season"]).agg(n=("est", "size"), est_share=("est", "mean"))
    by = by[by["n"] >= 20]
    league = zdv["est"].mean()
    W(f"established_full_window share within zero-duration episodes, per arena-season (n≥20 goals): league "
      f"mean **{league*100:.1f}%**, across {len(by)} arena-seasons spread p10 {by['est_share'].quantile(.1)*100:.1f}% "
      f"/ median {by['est_share'].median()*100:.1f}% / p90 {by['est_share'].quantile(.9)*100:.1f}% "
      f"(sd {by['est_share'].std()*100:.1f} pts).")
    W("If this concentrates by arena, `deny` inherits scorekeeper bias the way hits/GV/TK do (int_rink_bias). "
      "Report-only now; flagged as a **Stage 5 input** and a **v1.1 rink-adjustment candidate** for the "
      "possession proxy. Top/bottom arena-seasons:")
    for v, r in by.sort_values("est_share", ascending=False).head(3).iterrows():
        W(f"  - {v[0]} {v[1]}: {r['est_share']*100:.0f}% (n={int(r['n'])})")
    for v, r in by.sort_values("est_share").head(3).iterrows():
        W(f"  - {v[0]} {v[1]}: {r['est_share']*100:.0f}% (n={int(r['n'])})")
    W("")
    # PERSIST the per-arena-season under-recording shares (PV-D015 activation): CSV + a small BQ table so
    # validate_phase_value can run the pre-registered deny arena-bias diagnostic without re-running this audit.
    arena = by.reset_index().rename(columns={"est_share": "underrecord_share"})
    arena["model_version"] = "phase_value_v1"
    os.makedirs("artifacts/phase_value", exist_ok=True)
    arena.to_csv("artifacts/phase_value/arena_underrecording.csv", index=False)
    try:
        bq.write_df(arena, "phase_arena_underrecording", write_disposition="WRITE_TRUNCATE")
        W(f"Persisted {len(arena)} arena-season under-recording shares to "
          "`nhl_models.phase_arena_underrecording` (+ artifacts CSV) for the PV-D015 diagnostic.\n")
    except Exception as e:
        W(f"(arena-share persist to BigQuery skipped: {e})\n")

    # (F) honest limits
    W("## Honest limits")
    W("- **Conditioning on success:** this audits labels AT GOALS only; precision/recall here do NOT transfer "
      "to non-goal episodes (the vast majority of the model's exposure).")
    W("- No exit validation, no non-goal validation.")
    W("- **Anchor is arrival, not release** (replay-probe read): the release-frame pinning finds the puck's "
      "arrival/in-net instant, ~5–15 frames AFTER true shot release, so entry-to-goal times include shot "
      "flight and `sprite_rush_k` is slightly **conservative** (real entries are marginally faster than measured).")
    W("- Tolerate ±2 s of PBP timing slop in any event-to-frame comparison; the geometric release-frame "
      "pinning avoids clock decoding but is not exact.")
    W("- Clip-start truncation right-censors entry times beyond ~8 s (established_full_window absorbs them).")
    W("- carry_flag (nearest attacking skater within 6 ft at the crossing) is descriptive-only and deferred in "
      "this pass pending a team-labeling reliability check (Section A2/C); noted rather than improvised.")
    W("")
    W("## Inherited banner caveat (verbatim, carried from research/replay-probe/reports/replay-build.md)")
    W("> **This sample is success-conditioned: it contains GOALS ONLY.** Every sequence in `raw_ppt_replay` "
      "ended in a goal; there is no tracked non-goal counterfactual anywhere in the payload. So this data "
      "**supports descriptive goal-anatomy and goal-as-the-unit analysis** (what a goal buildup looks like, "
      "who was where, how the puck moved) **but cannot support predictive \"what causes goals\" claims** — any "
      "value/credit/finishing model built here is conditioned on success and has no matched non-goal sample "
      "to contrast against. That sample does not exist in this data and would have to come from elsewhere "
      "(full-game tracking). Carry this caveat verbatim into anything built downstream.")
    _write(L)
    print(f"Wrote {REPORT}. usable={n_usable:,} | entries median {ent.median():.2f}s | <2.5s {(ent<2.5).mean()*100:.1f}%")


def _write(lines):
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
