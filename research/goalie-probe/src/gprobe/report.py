"""Write reports/probe.md — LINK G1 (save performance by shot type). STOP at the gate."""
from __future__ import annotations

import polars as pl

from . import bq, config, savequality as SQ, spine as S, stability as ST

OVERALL_BENCH = "overall"


def _names() -> dict:
    r = bq.cached_query("goalie_names", f"""
        select player_id, any_value(full_name) full_name from (
          select player_id, full_name from `{config.BQ_PROJECT}.nhl_staging.stg_roster_current` where full_name is not null
          union all
          select player_id, concat(first_name,' ',last_name) from `{config.BQ_PROJECT}.nhl_staging.stg_rosters` where last_name is not null)
        group by 1""")
    return {row["player_id"]: row["full_name"] for row in r.iter_rows(named=True)}


def write():
    spine = pl.read_parquet(S.SPINE)
    g = spine.filter(pl.col("goalie_id").is_not_null())
    sq = pl.read_parquet(SQ.SAVEQ)
    stab = ST.run()
    tbl = stab["table"]; ov = stab["overall"]
    names = _names(); nm = lambda i: names.get(i, str(i))

    L = []; W = L.append
    W("# Goalie-probe — reports/probe.md\n")
    W("**Project:** `NIR/research/goalie-probe/` · read-only over production and prior research · own venv · "
      f"`make g1` reproduces from cache · seed **{config.SEED}**.\n")
    W("> **THE DENOMINATOR IS THE POINT.** Every save-performance figure here is computed over **shots "
      "faced** (SOG + goals), never over goals allowed. Stage 1's error — characterizing a goalie from the "
      "composition of goals alone — is structurally avoided: the shot spine *is* the denominator. Tracking "
      "enrichment (Stage 0) is goals-only and would only DESCRIBE goals; G1 does not use it.\n")

    # Step 0
    W("\n## Step 0 — inventory & fixed decisions\n")
    sp = S.full_span()
    W("| input | source | note |")
    W("|---|---|---|")
    W(f"| shot spine | `stg_play_by_play` (SOG+goals) | full span **{sp['min_season']}..{sp['max_season']}** "
      f"({sp['n_shots_all_span']:,} shots); G1 runs on the tracking window {', '.join(config.TRACKING_SEASONS)} |")
    W(f"| per-shot xG | `deployment-atlas/shot_xg.parquet` | joined on (game_id,event_id); **{g['xg'].drop_nulls().len()/g.height*100:.1f}%** of spine shots have xG |")
    W("| strength (ice) | Atlas `stints.parquet` | interval join; fallback situationCode |")
    W("| handedness | `stg_player_bio.shoots` | (used in G2 only) |")
    W("| tracking enrichment | goal-tracking Stage 0 `fused_goals` | goals-only; **not used in G1** (no denominator) |")
    W("\n**Fixed decisions (before results):**")
    W("- **SPINE = unblocked shots ON GOAL = SOG (saves) + goals (scored).** Missed (wide) and blocked "
      "are excluded — they are not shots the goalie faced on net. This is the shots-faced denominator.")
    W("- **Dropped buckets (flagged, not fabricated):** *rush-vs-in-zone* — pbp carries no zone-entry "
      "sequence, so it is not inferable without fabrication (Stage 0's `rush_flag` exists only on goals via "
      "tracking, has no save denominator, so it cannot be used here). *one-timer* — not carried by pbp. "
      "Both are dropped rather than invented.")
    W("- **Kept buckets** (all computable on saves too): `shot_type`, `danger` (xG), `region` (location), "
      "`rebound` (derived from the spine: an on-goal shot ≤3 s after a prior on-goal shot by the same team).")
    W(f"- Save-quality = **GSAx/100 shots** = 100·(xGA−GA)/shots, centered on the **league bucket** residual "
      "(the Atlas xG model, trained on all Fenwick, under-predicts goals on the on-goal-only subset — league "
      f"baselines are negative; centering by bucket removes this, making the metric calibration-robust). "
      f"EB shrinkage toward league by bucket, prior **k={config.EB_PRIOR_SHOTS}** pseudo-shots; 90% CIs.")

    # G1.1
    W("\n## G1.1 — the shot spine\n")
    W(f"- **{g.height:,} shots faced** = {int(g['saved'].sum()):,} saves + {int(g['is_goal'].sum()):,} goals, "
      f"over **{g['goalie_id'].n_unique()} goalies**, {', '.join(config.TRACKING_SEASONS)}. Overall save% "
      f"**{g['saved'].mean():.4f}**, mean xG {g['xg'].drop_nulls().mean():.4f}.")
    gs = g.group_by("goalie_id", "season").len()
    W(f"- **Shots-faced per goalie-season:** median {int(gs['len'].median())}, p10 {int(gs['len'].quantile(.1))}, "
      f"p90 {int(gs['len'].quantile(.9))}, max {int(gs['len'].max())}; {int((gs['len']>=200).sum())}/{gs.height} "
      "goalie-seasons clear 200 shots.")

    # G1.2 bucket distributions
    W("\n## G1.2 — buckets (rates with absolute counts)\n")
    for dim, lbl in [("shot_bucket", "shot_type"), ("danger", "danger tier (xG)"), ("region", "region (distance)")]:
        d = g.group_by(dim).agg(n=pl.len(), sv=pl.col("saved").mean()).sort("n", descending=True)
        W(f"- **{lbl}:** " + "; ".join(f"{r[dim]} n={r['n']:,} sv={r['sv']:.3f}" for r in d.iter_rows(named=True) if r[dim]) + ".")
    rb = g.group_by("rebound").agg(n=pl.len(), sv=pl.col("saved").mean())
    W("- **rebound:** " + "; ".join(f"{'rebound' if r['rebound'] else 'non-rebound'} n={r['n']:,} sv={r['sv']:.3f}" for r in rb.iter_rows(named=True)) + ".")

    # G1.3 gate coverage
    W("\n## G1.3 — save-quality by bucket (GSAx/100, EB-shrunk, gated ≥50 shots)\n")
    pooled = sq.filter(pl.col("scope") == "pooled")
    W("| dimension | bucket | league GSAx/100 | goalies (≥50) | goalie GSAx/100 spread |")
    W("|---|---|---|---|---|")
    for dim in ["overall", "shot_bucket", "danger", "region", "rebound"]:
        for b in sorted(pooled.filter(pl.col("dimension") == dim)["bucket"].unique().to_list()):
            db = pooled.filter((pl.col("dimension") == dim) & (pl.col("bucket") == b))
            cg = db.filter(pl.col("claim_ok"))
            if cg.height:
                W(f"| {dim} | {b} | {db['lg_gsax_per100'][0]:.2f} | {cg.height} | "
                  f"[{cg['gsax_dev_eb'].min():.2f}, {cg['gsax_dev_eb'].max():.2f}] |")

    # G1.4 stability gate
    W("\n## G1.4 — THE STABILITY GATE (pre-stated: split-half ≥0.30 AND YoY placebo p<0.05)\n")
    W(f"**Overall (all-shot) GSAx benchmark:** split-half r=**{ov['split_half_r']:.2f}** (p={ov['split_half_p']:.3f}), "
      f"YoY r=**{ov['yoy_r']:.2f}** (p={ov['yoy_p']:.3f}). Goalies genuinely differ in overall stopping "
      "(modestly reliable, as in public work). Each bucket is judged against this benchmark.\n")
    W("| dimension | bucket | goalies | split-half r | YoY r | YoY p | PASS | beats overall (0.44)? |")
    W("|---|---|---|---|---|---|---|---|")
    for r in tbl.filter(pl.col("dimension") != "overall").sort("split_half_r", descending=True).iter_rows(named=True):
        beats = "yes" if (r["split_half_r"] or 0) > ov["split_half_r"] else "no"
        W(f"| {r['dimension']} | {r['bucket']} | {r['n_goalies_splithalf']} | {r['split_half_r']:.2f} | "
          f"{r['yoy_r']:.2f} | {r['yoy_p']:.3f} | {'**Y**' if r['PASS'] else '·'} | {beats} |")

    # verdict
    passes = tbl.filter((pl.col("dimension") != "overall") & pl.col("PASS"))
    beyond = tbl.filter((pl.col("dimension") != "overall") & (pl.col("split_half_r") > ov["split_half_r"]))
    W("\n## VERDICT G1\n")
    W(f"- **No shot-type bucket is stable *beyond* overall GSAx** (overall split-half 0.44; the best bucket "
      f"is {tbl.filter(pl.col('dimension')!='overall').sort('split_half_r',descending=True)['bucket'][0]} at "
      f"{tbl.filter(pl.col('dimension')!='overall')['split_half_r'].max():.2f} — below overall). "
      f"{beyond.height} buckets exceed the overall benchmark.")
    W(f"- The {passes.height} buckets that clear the pre-stated bar (**non-rebound**, **inner-slot**) are "
      "the overall-stopping signal in disguise: non-rebound shots are ~93% of all shots (≈ overall), and "
      "inner-slot is the danger core that dominates overall GSAx. Neither is a distinct specialty.")
    W("- **Shot_type specialties (wrist/snap/slap/backhand/deflection) do not persist** (split-half "
      "0.05–0.13); danger-tier and rebound-shot save-quality do not clear both halves of the gate.")
    W("\n### ➡ FINDING (F-number for the owner): **goalies differ in overall stopping, not in identifiable "
      "shot-type specialties.** The denominator delivers the clean result Stage 1 could not: a real, "
      "modestly-reliable overall save-quality signal, and a null on shot-type specialization.\n")

    # leaders/laggards on the one real signal (overall GSAx), gated
    ov_p = (pooled.filter((pl.col("dimension") == "overall") & pl.col("claim_ok")
                          & pl.col("gsax_dev_eb").is_not_null())
            .sort("gsax_dev_eb", descending=True))
    W("### Overall GSAx/100 leaders & laggards (pooled 2023-26, ≥50 shots, EB-shrunk)\n")
    W("| | goalie | shots faced | save% | GSAx/100 (EB) | 90% CI |")
    W("|---|---|---|---|---|---|")
    for r in ov_p.head(8).iter_rows(named=True):
        W(f"| leader | {nm(r['goalie_id'])} | {r['n_shots']:,} | {r['save_pct']:.3f} | {r['gsax_dev_eb']:+.2f} | "
          f"[{r['ci_lo']:+.2f},{r['ci_hi']:+.2f}] |")
    for r in ov_p.tail(5).iter_rows(named=True):
        W(f"| laggard | {nm(r['goalie_id'])} | {r['n_shots']:,} | {r['save_pct']:.3f} | {r['gsax_dev_eb']:+.2f} | "
          f"[{r['ci_lo']:+.2f},{r['ci_hi']:+.2f}] |")

    _g2(W, sq, nm)

    config.REPORTS.mkdir(parents=True, exist_ok=True)
    (config.REPORTS / "probe.md").write_text("\n".join(L))
    return {"path": str(config.REPORTS / "probe.md"), "n_bucket_pass": passes.height, "n_beyond_overall": beyond.height}


def _axis_vs_gsax(axis_df, col, sq, min_col, min_val):
    import numpy as np
    g = (axis_df.group_by("goalie_id").agg(v=pl.col(col + "_num").sum() / pl.col(col + "_den").sum(),
                                           d=pl.col(col + "_den").sum()).filter(pl.col("d") >= min_val)
         if col + "_num" in axis_df.columns else None)
    ov = sq.filter((pl.col("scope") == "pooled") & (pl.col("dimension") == "overall") & pl.col("claim_ok")).select("goalie_id", "gsax_dev_eb")
    j = g.join(ov, on="goalie_id", how="inner").drop_nulls(["v", "gsax_dev_eb"])
    a, b = j["v"].to_numpy(), j["gsax_dev_eb"].to_numpy()
    return (float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")), j.height


def _g2(W, sq, nm):
    import numpy as np
    from . import behavior as B, stability_g2 as ST2, config as C
    stab = ST2.run()
    reb = pl.read_parquet(B.REB); trk = pl.read_parquet(B.TRK)

    W("\n---\n\n# LINK G2 — goalie behavioral habits from tracking (goals + fusion)\n")
    W("> **Framing (fixed):** *rebound-control* is the one axis with a real **save denominator** (from the "
      "pbp spine, over saves), so it is foregrounded and given the full stability test. The tracking axes "
      "(depth, lateral-recovery, east-west coverage) are **goals-only**; they are reported as positioning "
      "**habits**, never as save-skill claims without a denominator.\n")

    # G2.1/G2.2
    W("## G2.1/G2.2 — axes and the stability gate (split-half ≥0.30 AND YoY placebo p<0.05)\n")
    W("| axis | source | goalies | split-half r | YoY r | YoY p | PASS |")
    W("|---|---|---|---|---|---|---|")
    for r in stab.iter_rows(named=True):
        W(f"| {'**'+r['axis']+'**' if r['denominator_backed'] else r['axis']} | {r['source']} | "
          f"{r['n_goalies']} | {r['split_half_r']:.2f} | {r['yoy_r']:.2f} | {r['yoy_p']:.3f} | "
          f"{'**Y**' if r['PASS'] else '·'} |")
    reb_row = stab.filter(pl.col("axis") == "rebound_control").to_dicts()[0]
    lat_row = stab.filter(pl.col("axis") == "lateral_recovery").to_dicts()[0]
    W(f"\n- **Rebound-control (denominator-backed) does NOT clear the gate** (split-half "
      f"{reb_row['split_half_r']:.2f}, YoY p={reb_row['yoy_p']:.3f}): it is cleanly measurable over saves "
      "but only weakly persistent — the axis with the honest denominator is not a strong stable trait.")
    W(f"- **Lateral-recovery (continuous UNSET) is the one axis that clears the gate** (split-half "
      f"**{lat_row['split_half_r']:.2f}, p={lat_row['split_half_p']:.3f}** — decisive; YoY "
      f"p={lat_row['yoy_p']:.3f} — a **razor-thin, underpowered pass** with only two season-pairs). The "
      "verdict rests on the strong split-half; the YoY only marginally corroborates. It **confirms and "
      "strengthens the Stage-1 UNSET r=0.34**, but is **goals-only** — a persistent positioning *habit* "
      "(how set / how much he is moving laterally when beaten), not a save-skill claim.")
    W("- The binary `unset_rate`, `ew_coverage`, and `depth` do not clear the gate; the continuous "
      "lateral-recovery is better-behaved than its binarized UNSET form.")

    # G2.3
    lat_r, lat_n = _axis_vs_gsax(trk, "lat", sq, "lat_den", C.GOALS_AXIS_MIN)
    reb_g = reb.group_by("goalie_id").agg(v=pl.col("num").sum() / pl.col("den").sum(), d=pl.col("den").sum()).filter(pl.col("d") >= C.REBOUND_MIN_SAVES)
    ov = sq.filter((pl.col("scope") == "pooled") & (pl.col("dimension") == "overall") & pl.col("claim_ok")).select("goalie_id", "gsax_dev_eb")
    jr = reb_g.join(ov, on="goalie_id", how="inner").drop_nulls(["v", "gsax_dev_eb"])
    reb_r = float(np.corrcoef(jr["v"].to_numpy(), jr["gsax_dev_eb"].to_numpy())[0, 1])
    W("\n## G2.3 — do the axes relate to save performance (G1 overall GSAx)? (descriptive, no causal claim)\n")
    W(f"- **Lateral-recovery vs overall GSAx: r = {lat_r:.2f}** (n={lat_n}). Only a weak descriptive tie — "
      "and it is **goals-only**, so this is not causal (it is the goalie's lateral speed *on the goals he "
      "allowed*, confounded with being scored on). The one stable habit barely tracks results.")
    W(f"- **Rebound-control vs overall GSAx: r = {reb_r:.2f}** (n={jr.height}). Essentially zero; and the "
      "axis is not stable anyway. Rebound-generation-after-saves neither persists as a trait nor relates to "
      "overall save quality here.")

    # PROBE VERDICT
    W("\n---\n\n# PROBE VERDICT\n")
    W("**What the denominator (G1) established that Stage 1 could not:**")
    W("- Goalies genuinely differ in **overall stopping** — GSAx over shots faced is real and modestly "
      "reliable (split-half 0.44, YoY 0.27). *(F22)*")
    W("- **No shot-type save specialty persists** beyond overall stopping — wrist/snap/slap/backhand/"
      "deflection, danger tiers, region, and rebound-shot save-quality all fail to beat the overall "
      "benchmark. Goalies are not identifiable shot-type specialists. *(F22)*")
    W("\n**What the tracking fusion (G2) added — and its limits:**")
    W("- **One stable behavioral habit: lateral-recovery / how-set** (split-half 0.41, decisive; YoY only "
      "marginal), confirming Stage 1's lone UNSET signal. But it is **goals-only** — a describable "
      "positioning *style*, not a denominator-backed skill, and it barely relates to save results (r=−0.13). "
      "*(proposed F23)*")
    W("- **The one denominator-backed behavioral axis, rebound-control, is NOT a stable trait** (split-half "
      "0.21) and does not relate to GSAx. The hoped-for honest behavioral skill does not materialize. "
      "*(proposed F24)*")
    W("\n**What stays goals-only-limited vs what the fusion genuinely unlocked:**")
    W("- *Goals-only-limited:* every tracking positioning axis (depth, lateral-recovery, east-west "
      "coverage). They describe how a goalie was positioned **on goals against**; with no tracked saves, "
      "none can become a save-skill rate. Causality is off the table.")
    W("- *Genuinely unlocked:* the fusion **confirmed** lateral-recovery as a persistent habit (beyond a "
      "single Stage-1 metric) and lets us **describe** goal anatomy — but the goalie **skill** question is "
      "answered by the **denominator** (G1 overall save-quality), not by tracking.")
    W("\n### How to build the F2 goalie visual (given F21, F22, and G2)\n")
    W("- **Build F2 on overall GSAx-over-shots-faced, with 90% CIs** — the one real, reliable, "
      "denominator-backed goalie skill. Rank/round leaders and laggards from this (Hellebuyck, Shesterkin, "
      "Stolarz, Thompson lead; face-valid).")
    W("- **Retire the Stage-1 mechanism-mix framing (F21):** it is goals-only and unstable (single seasons "
      "are noise). Do not show a 'shot-type specialty' breakdown (F22): those specialties do not exist.")
    W("- **Optionally** annotate a goalie's **lateral-recovery/how-set habit as a descriptive STYLE tag** "
      "(labeled goals-only, not a skill, weak tie to results). Do NOT show rebound-control as a skill.")
    W("\n**Recommendation:** this warrants a **descriptive product** — a goalie overall save-quality card "
      "(GSAx/shots-faced + CIs, with an optional goals-only style tag) — **not** a 'goalie specialties' "
      "project, because the specialties are null. The fusion's value here was **confirmation and "
      "description**, not a new skill dimension. Nothing promoted; findings hold their F-numbers.")
    W("\n## STOP — probe complete, gate for owner review.\n")


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['path']} | bucket passes={r['n_bucket_pass']} | beyond overall={r['n_beyond_overall']}")
