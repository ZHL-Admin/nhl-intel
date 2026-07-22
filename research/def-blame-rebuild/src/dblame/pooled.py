"""Pooled 3-season (2023-26) D-only blame rating — the direct attack on the sample-size ceiling.

The single-season metric fails split-half at min-40 (~0.1) but the exposure sweep hit 0.44 at min-60; pooling
three seasons roughly triples goals-per-player, pushing regulars into the stable regime. Builds the pooled
rate (blame summed / exposure summed over 2023-26), per-goal AND per-shift denominators, D only. Evaluates:
  - qualifying counts at min-60 / min-100 pooled tracked GA
  - split-half (odd/even games across all 3 seasons) vs 2000-perm placebo, 0.30 bar + F25 0.41-0.76 band
  - per-LEDGER decomposition (coverage / turnover / rush) pooled split-half
  - YoY done right: adjacent-season correlation, seasons 1-2 -> season 3, and deployment-change for movers
  - eye test vs defensive reputation (does Slavin rise as his sample grows?)
Nothing promoted.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, deploy, events2 as E2
from .meta import load as load_meta
from .tracks import TRACKS

SEASONS = ["2023-24", "2024-25", "2025-26"]
LEDMAP = {"E1": "cov", "E2": "cov", "E3": "cov", "R3": "cov", "R6": "cov", "FTA": "cov", "OUT_OF_ZONE": "cov",
          "TURNOVER": "turn", "RUSH_DEFENSE": "rush"}


def _bq_toi_game() -> pl.DataFrame:
    from google.cloud import bigquery
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    rows = bq.query(f"""select player_id, game_id, sum(toi_5v5_sec) toi_sec
                        from `{C.BQ_PROJECT}.nhl_staging.int_player_onice_game`
                        where season in ('2023-24','2024-25','2025-26') group by 1,2""").result()
    return pl.DataFrame([{"player_id": r.player_id, "game_id": r.game_id, "toi_sec": r.toi_sec} for r in rows],
                        schema={"player_id": pl.Int64, "game_id": pl.Int64, "toi_sec": pl.Float64})


def _names() -> dict:
    from google.cloud import bigquery
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    rows = bq.query(f"""select player_id, min(concat(first_name,' ',last_name)) nm
                        from `{C.BQ_PROJECT}.nhl_staging.stg_rosters`
                        where season in ('2023-24','2024-25','2025-26') group by 1""").result()
    return {r.player_id: r.nm for r in rows}


def per_game() -> pl.DataFrame:
    """Per (player, season, game), D-only: total blame + per-ledger blame, tracked GA, 5v5 TOI, shifts."""
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "season")
    isdef = load_meta().filter(pl.col("is_def")).select("player_id").with_columns(pl.col("player_id").cast(pl.Int64))
    onice = pl.read_parquet(TRACKS).select("game_id", "event_id", "player_id", "season").unique().join(isdef, on="player_id", how="inner")
    ga = onice.group_by("player_id", "game_id", "season").agg(ga=pl.len())
    rec = pl.read_parquet(E2.REC).join(isdef, on="player_id", how="inner").with_columns(
        lk=pl.col("event_type").replace_strict(LEDMAP, default="cov"))
    blame = rec.group_by("player_id", "game_id").agg(
        blame=pl.col("severity").sum(),
        cov=pl.col("severity").filter(pl.col("lk") == "cov").sum(),
        turn=pl.col("severity").filter(pl.col("lk") == "turn").sum(),
        rush=pl.col("severity").filter(pl.col("lk") == "rush").sum())
    toi = _bq_toi_game()
    sh = (pl.read_parquet(deploy.ATLAS / "shifts.parquet").filter(pl.col("season_label").is_in(SEASONS))
          .group_by("player_id", "game_id").agg(shifts=pl.len()))
    g = (ga.join(blame, on=["player_id", "game_id"], how="left")
         .join(toi, on=["player_id", "game_id"], how="left")
         .join(sh, on=["player_id", "game_id"], how="left")
         .with_columns(pl.col(["blame", "cov", "turn", "rush", "toi_sec"]).fill_null(0.0), shifts=pl.col("shifts").fill_null(0)))
    return g


def _rates(df):
    return df.with_columns(
        per_goal=pl.col("blame") / pl.col("ga"),
        per_shift=pl.col("blame") / (pl.col("shifts") / 100.0),
        cov_pg=pl.col("cov") / pl.col("ga"), turn_pg=pl.col("turn") / pl.col("ga"), rush_pg=pl.col("rush") / pl.col("ga"))


def pooled() -> pl.DataFrame:
    g = per_game()
    p = g.group_by("player_id").agg(pl.col(["blame", "cov", "turn", "rush", "ga", "shifts"]).sum(),
                                    toi_sec=pl.col("toi_sec").sum(), n_games=pl.len())
    nm = _names()
    return _rates(p).with_columns(nm=pl.col("player_id").replace_strict(nm, default=None, return_dtype=pl.Utf8))


def _corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")


def _placebo(a, b, real, n=2000):
    rng = np.random.RandomState(20260716)
    null = np.array([np.corrcoef(a, rng.permutation(b))[0, 1] for _ in range(n)])
    return {"null": round(float(null.mean()), 3), "sd": round(float(null.std()), 3), "p_ge": round(float((null >= real).mean()), 4)}


def split_half(min_ga: int) -> dict:
    g = per_game().sort("player_id", "game_id").with_columns(parity=pl.int_range(pl.len()).over("player_id") % 2)
    half = g.group_by("player_id", "parity").agg(pl.col(["blame", "cov", "turn", "rush", "ga", "shifts"]).sum())
    half = _rates(half)
    tot = g.group_by("player_id").agg(tot_ga=pl.col("ga").sum())
    w = half.pivot(values=["per_goal", "per_shift", "cov_pg", "turn_pg", "rush_pg"], index="player_id", on="parity").join(tot, on="player_id")
    w = w.filter(pl.col("tot_ga") >= min_ga)
    R = {"n": w.height}
    for metric in ["per_goal", "per_shift", "cov_pg", "turn_pg", "rush_pg"]:
        c0 = [c for c in w.columns if c.startswith(metric) and c.endswith("0")][0]
        c1 = [c for c in w.columns if c.startswith(metric) and c.endswith("1")][0]
        s = w.drop_nulls([c0, c1]); a, b = s[c0].to_numpy(), s[c1].to_numpy()
        r = _corr(a, b)
        R[metric] = {"r": round(r, 3), **_placebo(a, b, r)}
    return R


def yoy() -> dict:
    """Per-season D rates -> adjacent-season corr, seasons1-2 mean -> season3, + deployment change for movers."""
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "season")
    isdef = load_meta().filter(pl.col("is_def")).select("player_id").with_columns(pl.col("player_id").cast(pl.Int64))
    onice = pl.read_parquet(TRACKS).select("game_id", "event_id", "player_id", "season").unique().join(isdef, on="player_id", how="inner")
    ga = onice.group_by("player_id", "season").agg(ga=pl.len())
    sm = onice.select("game_id", "event_id", "season").unique()
    rec = pl.read_parquet(E2.REC).join(isdef, on="player_id", how="inner").join(sm, on=["game_id", "event_id"], how="inner")
    blame = rec.group_by("player_id", "season").agg(blame=pl.col("severity").sum())
    s = ga.join(blame, on=["player_id", "season"], how="left").with_columns(
        blame=pl.col("blame").fill_null(0.0), rate=pl.col("blame").fill_null(0.0) / pl.col("ga")).filter(pl.col("ga") >= 40)
    piv = s.pivot(values=["rate", "ga"], index="player_id", on="season")
    rc = {c: c for c in piv.columns}
    r23 = [c for c in piv.columns if c.startswith("rate") and "2023" in c][0]
    r24 = [c for c in piv.columns if c.startswith("rate") and "2024" in c][0]
    r25 = [c for c in piv.columns if c.startswith("rate") and "2025" in c][0]
    out = {}
    a = piv.drop_nulls([r23, r24]); out["adj_23_24"] = {"n": a.height, "r": round(_corr(a[r23].to_numpy(), a[r24].to_numpy()), 3)}
    b = piv.drop_nulls([r24, r25]); out["adj_24_25"] = {"n": b.height, "r": round(_corr(b[r24].to_numpy(), b[r25].to_numpy()), 3)}
    c = piv.drop_nulls([r23, r24, r25]).with_columns(s12=(pl.col(r23) + pl.col(r24)) / 2)
    out["s12_to_s3"] = {"n": c.height, "r": round(_corr(c["s12"].to_numpy(), c[r25].to_numpy()), 3)}
    # movers: biggest |Δrate| 24->25, does it track deployment change?
    dep = deploy.load()
    d = c.with_columns(d_rate=(pl.col(r25) - pl.col(r24)).abs()).sort("d_rate", descending=True).head(8)
    movers = []
    nm = _names()
    for row in d.iter_rows(named=True):
        pid = row["player_id"]
        d24 = dep.filter((pl.col("player_id") == pid) & (pl.col("season") == "2024-25"))
        d25 = dep.filter((pl.col("player_id") == pid) & (pl.col("season") == "2025-26"))
        if d24.height and d25.height:
            doz = d25["oz_start_share"][0] - d24["oz_start_share"][0]
            dqoc = d25["qoc"][0] - d24["qoc"][0]
            dqot = d25["qot"][0] - d24["qot"][0]
            movers.append({"nm": nm.get(pid, pid), "d_rate": round(row[r25] - row[r24], 3),
                           "d_oz": round(doz, 3), "d_qoc": round(dqoc, 2), "d_qot": round(dqot, 3)})
    out["movers"] = movers
    return out


def write() -> dict:
    p = pooled()
    q60 = p.filter(pl.col("ga") >= 60).height
    q100 = p.filter(pl.col("ga") >= 100).height
    sh60, sh100 = split_half(60), split_half(100)
    yy = yoy()
    L = []; W = L.append
    W("# Pooled 3-season (2023-26) D-only blame rating — the sample-size attack. Nothing promoted.\n")
    W(f"Pooled blame / pooled exposure over 3 seasons, D only. **Qualifying D: {p.height} total · "
      f"{q60} with ≥60 pooled tracked GA · {q100} with ≥100** (single-season min-60 gave only ~13).\n")
    W("## Pooled split-half stability (odd/even games, all 3 seasons) vs placebo — 0.30 bar, F25 ref 0.41-0.76\n")
    W("| pool | denominator | n | split-half r | placebo | p(null≥r) | vs 0.30 |")
    W("|---|---|---|---|---|---|---|")
    for tag, sh in [("min-60", sh60), ("min-100", sh100)]:
        for m in ["per_goal", "per_shift"]:
            v = sh[m]; W(f"| {tag} | {m} | {sh['n']} | **{v['r']}** | {v['null']}±{v['sd']} | {v['p_ge']} | {'PASS' if v['r'] >= 0.30 else 'FAIL'} |")
    W("\n## Per-LEDGER decomposition — pooled split-half (which component is the durable signal)\n")
    W("| pool | component | n | split-half r | vs 0.30 |")
    W("|---|---|---|---|---|")
    for tag, sh in [("min-60", sh60), ("min-100", sh100)]:
        for m, lab in [("cov_pg", "coverage"), ("turn_pg", "turnover"), ("rush_pg", "rush")]:
            v = sh[m]; W(f"| {tag} | {lab} | {sh['n']} | **{v['r']}** | {'PASS' if v['r'] >= 0.30 else 'FAIL'} |")
    W("\n## Year-over-year (durable-quality test)\n")
    W(f"- adjacent 2023-24→2024-25: r={yy['adj_23_24']['r']} (n={yy['adj_23_24']['n']}) · "
      f"2024-25→2025-26: r={yy['adj_24_25']['r']} (n={yy['adj_24_25']['n']})")
    W(f"- **seasons 1-2 mean → season 3: r={yy['s12_to_s3']['r']} (n={yy['s12_to_s3']['n']})**")
    W("- biggest movers (24→25) — does the move track a deployment change?")
    for m in yy["movers"]:
        W(f"  - {m['nm']}: Δrate {m['d_rate']:+.3f} | Δoz_start {m['d_oz']:+.3f} Δqoc {m['d_qoc']:+.2f} Δqot {m['d_qot']:+.3f}")
    W("\n## Pooled eye test (D, ≥60 pooled GA) — sort by defensive reputation? does Slavin rise?\n")
    s = p.filter(pl.col("ga") >= 60).with_columns(rk=pl.col("per_shift").rank(), n=pl.len())
    W("- **least blame (best 15, per_shift):** " + ", ".join(f"{r['nm']}" for r in s.sort("per_shift").head(15).iter_rows(named=True)))
    W("- **most blame (worst 15, per_shift):** " + ", ".join(f"{r['nm']}" for r in s.sort("per_shift", descending=True).head(15).iter_rows(named=True)))
    for a in ["Slavin", "Lindholm", "Lindell", "Ekholm", "Tanev", "Karlsson", "Bouchard", "Makar", "Hughes", "Cernak", "Provorov"]:
        for x in s.filter(pl.col("nm").str.contains(a)).iter_rows(named=True):
            W(f"  - {x['nm']}: rank {int(x['rk'])}/{int(x['n'])} ({int(x['rk']/x['n']*100)}%ile), per_shift {x['per_shift']:.3f}, {int(x['ga'])} GA")
    W("\n## STOP — owner reads the pooled outcome.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "pooled_D.md").write_text("\n".join(L))
    return {"qualifying": {"total": p.height, "min60": q60, "min100": q100}, "sh60": sh60, "sh100": sh100, "yoy": yy}


if __name__ == "__main__":
    import json
    r = write()
    print(json.dumps({k: v for k, v in r.items() if k != "yoy"}, indent=1))
    print("YoY:", json.dumps(r["yoy"], indent=1, default=str))
