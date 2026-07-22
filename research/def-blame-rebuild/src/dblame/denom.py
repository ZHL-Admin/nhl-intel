"""Three blame-rate DENOMINATORS + split-half stability + eye test (owner follow-up; nothing promoted).

The per-goal rate structurally divides out deployment and is small-sample-noisy (~40 goals). Test larger,
more stable exposure denominators:
  (a) per_goal : combined blame / tracked on-ice 5v5 GA          (current; event-normalized ~40 goals)
  (b) per60    : combined blame / (5v5 TOI minutes / 60)         (blame per 60 min of 5v5; large, stable)
  (c) per_shift: combined blame / (total shifts / 100)           (blame per 100 shifts; largest, stable)
Split-half is by ODD/EVEN GAMES (each game contributes both blame and exposure), min 40 tracked GA, vs a
2000-perm shuffled-identity placebo, against the 0.30 bar. Numerator (tracked-goal blame) is identical across
all three; only the exposure denominator changes.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, deploy, events2 as E2, leaderboard as LB
from .tracks import TRACKS

MIN_GA = 40
SEASONS = ["2024-25", "2025-26"]


def _bq_toi_game() -> pl.DataFrame:
    from google.cloud import bigquery
    bq = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    rows = bq.query(f"""select player_id, game_id, sum(toi_5v5_sec) toi_sec
                        from `{C.BQ_PROJECT}.nhl_staging.int_player_onice_game`
                        where season in ('2024-25','2025-26') group by 1,2""").result()
    return pl.DataFrame([{"player_id": r.player_id, "game_id": r.game_id, "toi_sec": r.toi_sec} for r in rows],
                        schema={"player_id": pl.Int64, "game_id": pl.Int64, "toi_sec": pl.Float64})


def per_game() -> pl.DataFrame:
    """Per (player, season, game): combined blame, tracked GA, 5v5 TOI sec, shift count."""
    onice = pl.read_parquet(TRACKS).select("game_id", "event_id", "player_id", "season").unique()
    gseason = onice.select("game_id", "season").unique()
    ga = onice.group_by("player_id", "game_id", "season").agg(ga=pl.len())
    blame = (pl.read_parquet(E2.REC).group_by("player_id", "game_id").agg(blame=pl.col("severity").sum()))
    toi = _bq_toi_game()
    sh = (pl.read_parquet(deploy.ATLAS / "shifts.parquet")
          .filter(pl.col("season_label").is_in(SEASONS))
          .group_by("player_id", "game_id").agg(shifts=pl.len()))
    g = (ga.join(blame, on=["player_id", "game_id"], how="left")
         .join(toi, on=["player_id", "game_id"], how="left")
         .join(sh, on=["player_id", "game_id"], how="left")
         .with_columns(blame=pl.col("blame").fill_null(0.0), toi_sec=pl.col("toi_sec").fill_null(0.0),
                       shifts=pl.col("shifts").fill_null(0)))
    return g


def _rates(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        per_goal=pl.when(pl.col("ga") > 0).then(pl.col("blame") / pl.col("ga")).otherwise(None),
        per60=pl.when(pl.col("toi_sec") > 0).then(pl.col("blame") / (pl.col("toi_sec") / 3600.0)).otherwise(None),
        per_shift=pl.when(pl.col("shifts") > 0).then(pl.col("blame") / (pl.col("shifts") / 100.0)).otherwise(None))


def season_rates() -> pl.DataFrame:
    g = per_game()
    s = g.group_by("player_id", "season").agg(
        blame=pl.col("blame").sum(), ga=pl.col("ga").sum(), toi_sec=pl.col("toi_sec").sum(), shifts=pl.col("shifts").sum())
    meta = LB.aggregate().select("player_id", "season", "pos", "nm", "sw", "trk_ga")
    return _rates(s).join(meta, on=["player_id", "season"], how="inner")


def _corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 else float("nan")


def _placebo(a, b, real, n=2000):
    rng = np.random.RandomState(20260716)
    null = np.array([np.corrcoef(a, rng.permutation(b))[0, 1] for _ in range(n)])
    return {"null": round(float(null.mean()), 3), "sd": round(float(null.std()), 3),
            "p_ge": round(float((null >= real).mean()), 4)}


def stability() -> dict:
    g = per_game().sort("player_id", "season", "game_id").with_columns(
        parity=pl.int_range(pl.len()).over("player_id", "season") % 2)
    half = g.group_by("player_id", "season", "parity").agg(
        blame=pl.col("blame").sum(), ga=pl.col("ga").sum(), toi_sec=pl.col("toi_sec").sum(), shifts=pl.col("shifts").sum())
    half = _rates(half)
    tot = g.group_by("player_id", "season").agg(tot_ga=pl.col("ga").sum())
    pos = LB.aggregate().select("player_id", "season", "pos")
    w = half.pivot(values=["per_goal", "per60", "per_shift"], index=["player_id", "season"], on="parity")
    w = w.join(tot, on=["player_id", "season"], how="left").join(pos, on=["player_id", "season"], how="inner")
    R = {}
    for pos_v in ["D", "F"]:
        for denom in ["per_goal", "per60", "per_shift"]:
            c0 = [c for c in w.columns if c.startswith(denom) and c.endswith("0")][0]
            c1 = [c for c in w.columns if c.startswith(denom) and c.endswith("1")][0]
            s = w.filter((pl.col("pos") == pos_v) & (pl.col("tot_ga") >= MIN_GA)).drop_nulls([c0, c1])
            a, b = s[c0].to_numpy(), s[c1].to_numpy()
            r = _corr(a, b)
            R[f"{pos_v}_{denom}"] = {"n": len(a), "r": round(r, 3), **_placebo(a, b, r)}
    return R


def _eye(sr, pos, denom, anchors_hi, anchors_lo):
    s = sr.filter((pl.col("pos") == pos) & (pl.col("trk_ga") >= MIN_GA)).with_columns(
        rk=pl.col(denom).rank(), n=pl.len())
    out = {"least": [], "most": [], "anchors": {}}
    for x in s.sort(denom).head(12).iter_rows(named=True):
        out["least"].append(f"{x['nm']}({x[denom]:.3f})")
    for x in s.sort(denom, descending=True).head(12).iter_rows(named=True):
        out["most"].append(f"{x['nm']}({x[denom]:.3f})")
    for a in anchors_hi + anchors_lo:
        for x in s.filter(pl.col("nm").str.contains(a)).iter_rows(named=True):
            out["anchors"][f"{a} ({x['season']})"] = f"rank {int(x['rk'])}/{int(x['n'])} ({int(x['rk']/x['n']*100)}%ile)"
    return out


def write() -> dict:
    R = stability()
    sr = season_rates()
    L = []; W = L.append
    W("# Blame-rate DENOMINATOR comparison — stability + eye test (owner follow-up; nothing promoted)\n")
    W("Numerator (tracked-goal blame) identical across all three; only the exposure denominator changes. "
      "**(a) per_goal** = blame / tracked 5v5 GA · **(b) per60** = blame / (5v5 TOI min / 60) · "
      "**(c) per_shift** = blame / (shifts / 100). Split-half by ODD/EVEN GAMES, min 40 tracked GA, vs 2000-perm "
      "placebo, 0.30 bar; F25 offensive-signature reference 0.41-0.76.\n")
    W("## Split-half stability by denominator × position\n")
    W("| pos · denominator | n | split-half r | placebo | p(null≥r) | vs 0.30 |")
    W("|---|---|---|---|---|---|")
    for k, v in R.items():
        W(f"| {k} | {v['n']} | **{v['r']}** | {v['null']}±{v['sd']} | {v['p_ge']} | {'PASS' if v['r'] >= 0.30 else 'FAIL'} |")
    HI_D = ["Karlsson", "Bouchard", "Hughes", "Hutson", "Chabot", "Sergachev"]
    LO_D = ["Lindholm", "Lindell", "Ekholm", "Brodin", "Cernak", "Slavin", "McCabe"]
    HI_F, LO_F = ["Backlund", "Blueger", "Coyle", "Lundell", "Danault"], ["MacKinnon", "Kucherov", "Draisaitl", "McDavid"]
    for pos, hi, lo in [("D", HI_D, LO_D), ("F", HI_F, LO_F)]:
        for denom in ["per_goal", "per60", "per_shift"]:
            e = _eye(sr, pos, denom, hi, lo)
            W(f"\n## Eye test — {pos} · {denom}\n")
            W(f"- **least blame:** {', '.join(e['least'])}")
            W(f"- **most blame:** {', '.join(e['most'])}")
            W("- anchors: " + "; ".join(f"{k} {v}" for k, v in e["anchors"].items()))
    W("\n## STOP — which denominator × position is eye-test-valid AND clears split-half at min-40.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "denom_comparison.md").write_text("\n".join(L))
    return R


if __name__ == "__main__":
    import json
    print(json.dumps(write(), indent=1))
