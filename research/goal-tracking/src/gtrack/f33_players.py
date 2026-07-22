"""F33 role-projection for named players (directional lean; NOT a verdict; predicts USAGE not PRODUCTION).

Applies the F33 finding (the stable F25 offensive signature adds to predicting future 5v5 role/TOI beyond
current usage — robust even vs the most-recent box) to specific players. Signatures span TWO gated universes:
  pbp     : finisher_share, net_front_share  (finishing signal)
  carrier : carrier_share, rush_share, entry_driver_share  (buildup signal)
each gated at >=15 involvements. Reuses player_signatures read-only. Reports per player: valid signature +
tracked-goal counts (confidence), the signature loadings, and the F33 usage LEAN (does style project higher /
similar / lower usage than current deployment implies). Refuses to project a player without a valid signature.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config
from .f25_predict import outcomes

SIG = config.PARQUET / "player_signatures.parquet"
GATE = 15
PBP_F = ["finisher_share", "net_front_share"]
CAR_F = ["carrier_share", "rush_share", "entry_driver_share"]
ALLF = PBP_F + CAR_F
PLAYERS = {"Matvei Michkov": 8484387, "Simon Edvinsson": 8482762, "Bowen Byram": 8481524,
           "Marco Kasper": 8483464, "Anton Frondell": 8485391}


def _combined(season: str) -> pl.DataFrame:
    s = pl.read_parquet(SIG).filter(pl.col("season") == season)
    pbp = s.filter(pl.col("involvement") == "pbp").select("player_id", *PBP_F, n_pbp="n_involved")
    car = s.filter(pl.col("involvement") == "carrier").select("player_id", *CAR_F, n_carrier="n_involved")
    return pbp.join(car, on="player_id", how="full", coalesce=True)


FITF = PBP_F   # the reliably-gated universe for these players (finisher/net-front); carrier is thin league-wide


def _fit():
    """F33 role model on the cohort: future TOI(2025-26) ~ recent TOI(2024-25) + z(early pbp signature 2023-24).
    Uses the robust pbp universe (finisher/net-front). Returns standardized betas (5v5 min per SD) + mean/sd."""
    o = outcomes()
    sig = _combined("2023-24").drop_nulls(FITF)
    df = (sig.join(o.filter(pl.col("season") == "2024-25").select("player_id", recent="toi_min"), on="player_id", how="inner")
          .join(o.filter(pl.col("season") == "2025-26").select("player_id", future="toi_min"), on="player_id", how="inner")
          .drop_nulls(["recent", "future"]))
    df = df.filter(pl.all_horizontal([pl.col(f).is_finite() for f in FITF + ["recent", "future"]]))
    mu = {f: float(df[f].mean()) for f in FITF}; sd = {f: float(df[f].std()) for f in FITF}
    Z = np.column_stack([(df[f].to_numpy() - mu[f]) / sd[f] for f in FITF])
    X = np.column_stack([np.ones(df.height), df["recent"].to_numpy(), Z])
    beta, *_ = np.linalg.lstsq(X, df["future"].to_numpy(), rcond=None)
    return {"sig_beta": dict(zip(FITF, beta[2:])), "mu": mu, "sd": sd, "n_cohort": df.height,
            "toi_sd": float(df["future"].std())}


def project(pid: int, m: dict):
    # earliest valid signature season for this player, per universe (>=GATE)
    seasons = ["2023-24", "2024-25", "2025-26"]
    pbp_row = car_row = None; pbp_season = car_season = None
    for s in seasons:
        c = _combined(s).filter(pl.col("player_id") == pid)
        if c.height:
            r = c.to_dicts()[0]
            if pbp_row is None and (r.get("n_pbp") or 0) >= GATE:
                pbp_row, pbp_season = r, s
            if car_row is None and (r.get("n_carrier") or 0) >= GATE:
                car_row, car_season = r, s
    if pbp_row is None and car_row is None:
        # report max samples seen
        allc = pl.concat([_combined(s).filter(pl.col("player_id") == pid) for s in seasons])
        np_ = int(allc["n_pbp"].fill_null(0).max() or 0); nc = int(allc["n_carrier"].fill_null(0).max() or 0)
        return {"valid": False, "n_pbp_max": np_, "n_carrier_max": nc}
    # loadings for display: pbp from the gated pbp row; carrier from the earliest carrier row (even if thin)
    sig = {}; nfo = {}
    for f in PBP_F:
        sig[f] = (pbp_row or {}).get(f)
    nfo["pbp"] = ((pbp_row or {}).get("n_pbp"), pbp_season)
    car_disp = None
    for s in seasons:
        c = _combined(s).filter(pl.col("player_id") == pid)
        if c.height and c.to_dicts()[0].get("carrier_share") is not None:
            car_disp = c.to_dicts()[0]; car_disp_season = s
            break
    for f in CAR_F:
        sig[f] = (car_disp or {}).get(f)
    nfo["carrier"] = ((car_disp or {}).get("n_carrier"), car_disp_season if car_disp else None)
    # LEAN from the robust pbp model only (finisher/net-front); carrier too thin to trust for these players
    lean = 0.0; contrib = {}
    for f in FITF:
        if sig.get(f) is not None:
            z = (sig[f] - m["mu"][f]) / m["sd"][f]; c = m["sig_beta"][f] * z; contrib[f] = c; lean += c
    return {"valid": True, "sig": sig, "n": nfo, "lean_min": lean, "lean_pbp_min": lean,
            "contrib": contrib, "toi_sd": m["toi_sd"], "pbp_ok": pbp_row is not None, "car_ok": car_row is not None}


def _dir(lean, toi_sd):
    frac = lean / (toi_sd + 1e-9)
    return "HIGHER" if frac > 0.15 else ("LOWER" if frac < -0.15 else "similar")


def write() -> dict:
    m = _fit()
    o = outcomes()
    L = []; W = L.append
    W("# F33 role-projection — named players (directional USAGE lean; NOT a verdict; predicts usage not production)\n")
    W(f"F33: the stable F25 offensive signature adds to predicting future 5v5 role/TOI beyond current usage "
      f"(robust vs recent box). Model fit on {m['n_cohort']} players (early signature 2023-24 → 2025-26 TOI, "
      f"controlling recent TOI). Signature gated at >=15 involvements PER universe (pbp: finisher/net-front; "
      "carrier: carrier/rush/entry-driver). **Caveat: F33 predicts USAGE/ROLE, not PRODUCTION; the lean is "
      "directional, not a verdict.**\n")
    out = {}
    for nm, pid in PLAYERS.items():
        p = project(pid, m); out[nm] = p
        cur = o.filter((pl.col("player_id") == pid) & (pl.col("season") == "2025-26"))
        cur_toi = round(float(cur["toi_min"][0]), 0) if cur.height and cur["toi_min"][0] is not None else None
        W(f"\n## {nm}\n")
        if not p["valid"]:
            W(f"- **NO VALID SIGNATURE — insufficient tracked-goal sample.** Max involvements in-window: "
              f"pbp {p['n_pbp_max']}, carrier {p['n_carrier_max']} (both below the 15 gate). **No projection is "
              "produced — refusing to fabricate a lean without input data.**")
            continue
        npbp, spbp = p["n"].get("pbp", (None, None)); ncar, scar = p["n"].get("carrier", (None, None))
        W(f"- **(1) Valid signature.** pbp universe: {'n='+str(npbp)+' ('+str(spbp)+')' if p['pbp_ok'] else 'THIN (<15)'}"
          f" · carrier universe: {'n='+str(ncar)+' ('+str(scar)+')' if p['car_ok'] else 'THIN (<15) — buildup loadings low-confidence'}")
        cn = p["n"]["carrier"][0] or 0
        W("- **(2) Early signature loadings** (share of involvements):")
        W(f"    - FINISHING (pbp, reliable): finisher {p['sig']['finisher_share']:.2f}, net_front {p['sig']['net_front_share']:.2f}")
        W(f"    - BUILDUP (carrier/rush/entry-driver): **INSUFFICIENT SAMPLE (carrier n={cn} < 15) — not reliably "
          "estimable, omitted** (thin-sample values would be degenerate).")
        direction = _dir(p["lean_min"], p["toi_sd"])
        W(f"- **(3) F33 usage LEAN — FINISHING sub-signature only (finisher/net-front; buildup under-sampled): "
          f"style projects {direction} usage than current deployment implies** (contribution {p['lean_min']:+.0f} 5v5 "
          f"min/season vs peers at the same current usage; current 2025-26 5v5 TOI ≈ {cur_toi} min). Drivers: " +
          ", ".join(f"{f.replace('_share','')} {p['contrib'][f]:+.0f}min" for f in FITF if f in p["contrib"]) +
          ". PARTIAL projection — the full F33 signal uses 5 fields; only 2 (finishing) are adequately sampled here.")
        conf = "HIGH" if (p["pbp_ok"] and (npbp or 0) >= 40) else ("MODERATE" if p["pbp_ok"] else "LOW")
        W(f"- **(4) Confidence: {conf}** (pbp n={npbp if p['pbp_ok'] else '<15'}; "
          f"{'carrier solid' if p['car_ok'] else 'carrier thin — buildup-side lean is low-confidence'}).")
    W("\n## STOP — owner review. F33 is a directional USAGE lean (not production, not a verdict). Nothing promoted.\n")
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    (config.REPORTS / "f33_players.md").write_text("\n".join(L))
    return out


if __name__ == "__main__":
    r = write()
    for nm, p in r.items():
        if p.get("valid"):
            print(f"{nm}: lean {p.get('lean_min'):+.0f}min (pbp {p.get('lean_pbp_min'):+.0f}), pbp_ok={p['pbp_ok']} car_ok={p['car_ok']}")
        else:
            print(f"{nm}: NO VALID SIGNATURE (pbp_max {p['n_pbp_max']}, carrier_max {p['n_carrier_max']})")
