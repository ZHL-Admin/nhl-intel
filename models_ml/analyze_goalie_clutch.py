"""
Goalie leverage-clutch repeatability study — PRE-REGISTERED (see
docs/methodology/goalie-clutch-preregistration.md). Design + thresholds were fixed before any
correlation was computed.

Question: is leverage-weighted goalie GSAx a repeatable skill beyond overall GSAx, and if so does it
improve playoff-series prediction? Regular-season shots only (leakage-free if applied to playoffs).

Pipeline: BigQuery joins shots → xg → goalie-of-record → win-probability leverage, buckets leverage
into league terciles, and aggregates per (goalie, season, split-half, bucket). All statistics
(split-half SB reliability, year-over-year r, permutation/parametric null) are computed here.

Run:  python -m models_ml.analyze_goalie_clutch
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from google.cloud import bigquery

MIN_TOTAL, MIN_HIGH = 800, 150          # pre-registered qualifying thresholds
SB_THRESH, YOY_THRESH = 0.20, 0.15      # pre-registered pass thresholds


def _client():
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def _pull(c):
    p = os.environ["GCP_PROJECT_ID"]
    sql = f"""
    WITH prim AS (   -- goalie of record per (game, team) = most shots faced
        SELECT game_id, team_id, goalie_id, ROW_NUMBER() OVER (
            PARTITION BY game_id, team_id ORDER BY shots_faced DESC) rn
        FROM `{p}.nhl_mart.mart_goalie_game_stats`
    ),
    shots AS (
        SELECT s.game_id, s.event_id, s.season, s.team_id AS shoot_team, s.elapsed_seconds,
               x.xg - CAST(s.is_goal AS INT64) AS gsax,
               MOD(ABS(FARM_FINGERPRINT(CONCAT(CAST(s.game_id AS STRING),'-',CAST(s.event_id AS STRING)))), 2) AS half
        FROM `{p}.nhl_staging.int_shot_sequence` s
        JOIN `{p}.nhl_models.shot_xg` x USING (game_id, event_id)
        WHERE s.is_empty_net = FALSE AND s.season >= '2015-16'
          AND substr(cast(s.game_id AS string),5,2) = '02'   -- regular season only
          AND x.xg IS NOT NULL
    ),
    joined AS (   -- as-of join: each shot gets the most recent win-prob leverage at/<= its time
        SELECT sh.season, g.goalie_id, sh.gsax, sh.half, wp.leverage
        FROM shots sh
        JOIN prim g ON g.game_id = sh.game_id AND g.team_id != sh.shoot_team AND g.rn = 1
        JOIN `{p}.nhl_models.win_probability` wp
          ON wp.game_id = sh.game_id AND wp.elapsed_seconds <= sh.elapsed_seconds
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY sh.game_id, sh.event_id ORDER BY wp.elapsed_seconds DESC) = 1
    ),
    thr AS (SELECT APPROX_QUANTILES(leverage, 3) q FROM joined)
    SELECT j.season, j.goalie_id, j.half,
           CASE WHEN j.leverage <= (SELECT q[OFFSET(1)] FROM thr) THEN 'low'
                WHEN j.leverage >= (SELECT q[OFFSET(2)] FROM thr) THEN 'high'
                ELSE 'mid' END AS bucket,
           COUNT(*) n, SUM(j.gsax) sum_gsax, SUM(j.gsax*j.gsax) sumsq_gsax
    FROM joined j
    GROUP BY j.season, j.goalie_id, j.half, bucket
    """
    return c.query(sql).to_dataframe(create_bqstorage_client=False)


def main():
    c = _client()
    print("Building per-shot goalie GSAx ⋈ leverage in BigQuery, aggregating …")
    agg = _pull(c)
    print(f"  aggregate rows: {len(agg)}")

    # ---- per goalie-season stats from the bucket aggregates ----
    g = agg.groupby(["season", "goalie_id"])
    def cell(df, bucket, half=None):
        d = df[df["bucket"] == bucket]
        if half is not None:
            d = d[d["half"] == half]
        n = d["n"].sum(); s = d["sum_gsax"].sum(); ss = d["sumsq_gsax"].sum()
        return n, s, ss

    rows = []
    for (season, gid), df in g:
        nh, sh, ssh = cell(df, "high"); nl, sl, ssl = cell(df, "low")
        nm = df[df["bucket"] == "mid"]["n"].sum()
        total = nh + nl + nm
        if total < MIN_TOTAL or nh < MIN_HIGH or nl < 1:
            continue
        delta = sh / nh - sl / nl
        # pooled GSAx variance (for the null) from high+low shots
        n2, s2, ss2 = nh + nl, sh + sl, ssh + ssl
        var_gsax = max(1e-9, ss2 / n2 - (s2 / n2) ** 2)
        samp_var = var_gsax * (1 / nh + 1 / nl)        # null sampling var of delta
        # split-half deltas
        def half_delta(hf):
            a = df[(df.bucket == "high") & (df.half == hf)]
            b = df[(df.bucket == "low") & (df.half == hf)]
            if a["n"].sum() < 1 or b["n"].sum() < 1:
                return np.nan
            return a["sum_gsax"].sum() / a["n"].sum() - b["sum_gsax"].sum() / b["n"].sum()
        rows.append({"season": season, "goalie_id": gid, "delta": delta,
                     "samp_var": samp_var, "d0": half_delta(0), "d1": half_delta(1),
                     "n_high": nh, "n_total": total})
    d = pd.DataFrame(rows)
    print(f"  qualifying goalie-seasons (≥{MIN_TOTAL} shots, ≥{MIN_HIGH} high-lev): {len(d)}")
    print(f"  observed clutch_delta: mean {d['delta'].mean():+.4f}, SD {d['delta'].std():.4f} "
          f"(GSAx/shot, high − low leverage)")

    # ---- Test 1: split-half reliability (Spearman-Brown) ----
    sh = d.dropna(subset=["d0", "d1"])
    r_half = np.corrcoef(sh["d0"], sh["d1"])[0, 1]
    sb = 2 * r_half / (1 + r_half) if r_half > -1 else np.nan
    print(f"\n[1] split-half r = {r_half:+.3f}  → Spearman-Brown {sb:+.3f}   "
          f"(pass ≥ {SB_THRESH})  {'PASS' if sb >= SB_THRESH else 'FAIL'}")

    # ---- Test 2: year-over-year persistence ----
    piv = d.pivot_table(index="goalie_id", columns="season", values="delta")
    seasons = sorted(d["season"].unique())
    xs, ys = [], []
    for i in range(len(seasons) - 1):
        s0, s1 = seasons[i], seasons[i + 1]
        if s0 in piv and s1 in piv:
            sub = piv[[s0, s1]].dropna()
            xs += list(sub[s0]); ys += list(sub[s1])
    r_yoy = np.corrcoef(xs, ys)[0, 1] if len(xs) > 2 else np.nan
    print(f"[2] year-over-year r = {r_yoy:+.3f}  (n={len(xs)} pairs)   "
          f"(pass ≥ {YOY_THRESH})  {'PASS' if r_yoy >= YOY_THRESH else 'FAIL'}")

    # ---- Test 3: permutation/parametric null on the cross-goalie spread ----
    rng = np.random.default_rng(0)
    obs_sd = d["delta"].std()
    null_sds = []
    sds = np.sqrt(d["samp_var"].values)
    for _ in range(1000):
        null_sds.append(np.std(rng.normal(0, sds)))
    p95 = np.percentile(null_sds, 95)
    real_spread = obs_sd > p95
    print(f"[3] observed cross-goalie SD {obs_sd:.4f}  vs null p95 {p95:.4f}   "
          f"{'PASS (real spread)' if real_spread else 'FAIL (≈ chance)'}")
    # how much of observed variance is 'true' skill vs sampling?
    true_var = max(0.0, obs_sd**2 - np.mean(d["samp_var"]))
    print(f"    implied true-skill SD {np.sqrt(true_var):.4f}  "
          f"({100*true_var/obs_sd**2:.0f}% of observed variance is signal, rest is noise)")

    passed = (sb >= SB_THRESH) and (r_yoy >= YOY_THRESH) and real_spread
    print(f"\n=== VERDICT: goalie leverage-clutch is "
          f"{'a REPEATABLE skill — proceed to impact test' if passed else 'NOISE (fails pre-registered bar)'} ===")
    return passed


if __name__ == "__main__":
    main()
