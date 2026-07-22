"""Deployment-ADJUSTED blame rate, alongside the RAW rate, for the eye-test comparison.

Model (stated explicitly): within each position (D, F), pooled over both seasons, fit
    combined_blame_rate  ~  b0 + b1*oz_start_share + b2*trail_share + b3*qoc + b4*qot + b5*log(toi_dep_min)
by OLS. The fitted value is the player's EXPECTED blame exposure given his deployment (heavy DZ starts, tough
QoC, weak QoT, heavy minutes -> more expected blame). The ADJUSTED rate is the residual (raw - expected):
NEGATIVE = carries LESS blame than his deployment predicts (overperforming a hard role); POSITIVE = more blame
than his role would predict. Lower is better for both raw and adjusted. RAW rate is kept unchanged.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, deploy, leaderboard as LB

FEATURES = ["oz_start_share", "trail_share", "qoc", "qot", "ltoi"]


def build() -> tuple[pl.DataFrame, dict]:
    df = LB.aggregate().join(deploy.load(), on=["player_id", "season"], how="inner")
    df = df.with_columns(ltoi=pl.col("toi_dep_min").log())
    models = {}
    out = []
    for pos in ["D", "F"]:
        sub = df.filter(pl.col("pos") == pos)
        X = np.column_stack([sub[f].to_numpy() for f in FEATURES])
        Xz = (X - X.mean(0)) / X.std(0)
        Xd = np.column_stack([np.ones(len(Xz)), Xz])
        y = sub["combined_rate"].to_numpy()
        beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
        yhat = Xd @ beta
        ss_res = ((y - yhat) ** 2).sum(); ss_tot = ((y - y.mean()) ** 2).sum()
        models[pos] = {"beta": dict(zip(["intercept"] + FEATURES, beta.round(4).tolist())),
                       "r2": round(1 - ss_res / ss_tot, 3), "n": len(y)}
        out.append(sub.with_columns(expected_rate=pl.Series(yhat), adjusted=pl.Series(y - yhat)))
    return pl.concat(out), models


def _tbl(sub: pl.DataFrame, by: str, n: int = 20) -> str:
    s = sub.sort(by).head(n).select(
        player=pl.col("nm") + " #" + pl.col("sw").cast(pl.Int64, strict=False).cast(pl.Utf8),
        raw=pl.col("combined_rate").round(3), adj=pl.col("adjusted").round(3),
        exp=pl.col("expected_rate").round(3), ozs=pl.col("oz_start_share").round(2),
        qoc=pl.col("qoc").round(2), qot=pl.col("qot").round(3), trk_ga="trk_ga", tier="toi_tier")
    with pl.Config(tbl_rows=-1, tbl_cols=-1, fmt_str_lengths=26, tbl_width_chars=220, tbl_hide_dataframe_shape=True):
        return str(s)


def write() -> dict:
    df, models = build()
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    L = []; W = L.append
    W("# Deployment-ADJUSTED vs RAW blame rate — eye-test comparison\n")
    W("**Model (per position, pooled seasons):** combined_rate ~ oz_start_share + trail_share + qoc + qot + "
      "log(toi). Fitted = EXPECTED blame given deployment; **adjusted = raw − expected** (negative = less blame "
      "than the role predicts = overperforming a hard assignment). Lower is better for both. RAW unchanged.\n")
    for pos in ["D", "F"]:
        m = models[pos]
        W(f"- **{pos} model** (n={m['n']}, R²={m['r2']}): " + ", ".join(f"{k} {v:+.3f}" for k, v in m["beta"].items()) +
          " — standardized coefficients; +qoc / −qot / +ltoi / −oz_start means tougher deployment → more expected blame.")
    for pos in ["D", "F"]:
        for season in LB.SEASONS:
            sub = df.filter((pl.col("pos") == pos) & (pl.col("season") == season))
            W(f"\n## {season} · {pos} (n={sub.height})\n")
            W("### RAW — least blame (best 20)\n```"); W(_tbl(sub, "combined_rate")); W("```")
            W("### ADJUSTED — least blame (best 20)\n```"); W(_tbl(sub, "adjusted")); W("```")
            W("### RAW — most blame (worst 20)\n```"); W(_tbl(sub.with_columns(nr=-pl.col("combined_rate")), "nr")); W("```")
            W("### ADJUSTED — most blame (worst 20)\n```"); W(_tbl(sub.with_columns(na=-pl.col("adjusted")), "na")); W("```")
    # biggest raw->adjusted movers per position-season
    df = df.with_columns(
        raw_rank=pl.col("combined_rate").rank().over(["pos", "season"]),
        adj_rank=pl.col("adjusted").rank().over(["pos", "season"]),
        n_grp=pl.len().over(["pos", "season"]))
    df = df.with_columns(move=(pl.col("raw_rank") - pl.col("adj_rank")))   # + = improved (moved toward best) under adjustment
    W("\n## Biggest RAW→ADJUSTED movers (positive = adjustment moved him toward 'better', i.e. his blame was deployment-driven)\n")
    for pos in ["D", "F"]:
        mv = df.filter(pl.col("pos") == pos).sort("move", descending=True)
        up = mv.head(8); dn = mv.tail(8).reverse()
        W(f"**{pos} — most IMPROVED by adjustment (hard deployment excused):**")
        for r in up.iter_rows(named=True):
            W(f"- {r['nm']} #{r['sw']} ({r['season']}): raw#{int(r['raw_rank'])}→adj#{int(r['adj_rank'])} of {int(r['n_grp'])} "
              f"(+{int(r['move'])}); ozs {r['oz_start_share']:.2f} qoc {r['qoc']:.2f} qot {r['qot']:.3f}")
        W(f"\n**{pos} — most PENALIZED by adjustment (soft deployment, blame now stands out):**")
        for r in dn.iter_rows(named=True):
            W(f"- {r['nm']} #{r['sw']} ({r['season']}): raw#{int(r['raw_rank'])}→adj#{int(r['adj_rank'])} of {int(r['n_grp'])} "
              f"({int(r['move'])}); ozs {r['oz_start_share']:.2f} qoc {r['qoc']:.2f} qot {r['qot']:.3f}")
    df.write_parquet(C.PARQUET / "leaderboard_adjusted.parquet")
    (C.REPORTS / "leaderboard_adjusted.md").write_text("\n".join(L))
    return {"models": models}


if __name__ == "__main__":
    import json
    r = write()
    print(json.dumps(r["models"], indent=1))
