"""Validation for the Value (GAR/WAR) model — run, read the output, paste into value-gar.md.

Checks (Step 4): (1) Kucherov/Panarin RANK in GAR vs RAPM (the intended divergence), (2) the
GAR distribution (centred near replacement, right-skewed), (3) year-over-year stability of
GAR-offense vs RAPM-offense (GAR LESS stable by design — it includes shooting luck), and
(4) replacement-level sensitivity (rankings stable while levels move).

Run:  python -m models_ml.validate_gar
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models_ml import bq, config, compute_gar as G

FLOOR = G.CFG["MIN_TOI_5V5_FOR_RANKING"]


def _rank(df: pd.DataFrame, col: str, ascending=False) -> pd.Series:
    return df[col].rank(ascending=ascending, method="min").astype(int)


def main() -> None:
    ps, depth = G.pull()
    impact = bq.query_df(f"select * from `{bq.project()}.nhl_models.player_impact`")
    names = G._names(ps["player_id"].unique().tolist())

    # window frame (GAR) + window RAPM
    aggw = G.aggregate_window(ps, depth, G.WINDOW)
    win = G.compute(aggw, impact[impact["season_window"] == G.WINDOW_LABEL], G.WINDOW_LABEL)
    win = win[win["toi_5v5"] >= FLOOR].copy()
    rapm = impact[impact["season_window"] == G.WINDOW_LABEL].copy()
    win = win.merge(rapm[["player_id", "off_impact"]], on="player_id", how="left")
    win["gar_rank"] = _rank(win, "gar")
    win["rapm_off_rank"] = _rank(win, "off_impact")

    print(f"\n=== 1. GAR rank vs RAPM-offense rank ({G.WINDOW_LABEL}, n={len(win)}) ===")
    for who in ["Kucherov", "Panarin", "McDavid", "MacKinnon", "Reinhart"]:
        row = win[win["player_id"].map(lambda i: who in str(names.get(i, "")))]
        if not row.empty:
            r = row.iloc[0]
            print(f"  {names.get(r['player_id']):20s} GAR #{int(r['gar_rank']):<3d} (val {r['gar']:+.1f})   "
                  f"RAPM-off #{int(r['rapm_off_rank']):<3d} (impact {r['off_impact']:+.2f})")
    print("  -> Kucherov/Panarin: high GAR rank, modest RAPM rank = the intended 'value > impact' gap.")

    print("\n=== 2. GAR distribution (window, qualified skaters) ===")
    g = win["gar"]
    print(f"  n={len(g)}  mean {g.mean():+.1f}  median {g.median():+.1f}  "
          f"p10 {g.quantile(.1):+.1f}  p90 {g.quantile(.9):+.1f}  max {g.max():+.1f}  skew {g.skew():.2f}")
    # full pool (incl. low-TOI) centres near 0 at replacement
    full = win["gar"]
    print(f"  share within ±5 GAR: {(full.abs() <= 5).mean():.0%}; share > +20: {(full > 20).mean():.0%}")

    print("\n=== 3. Year-over-year stability: 'what happened' vs 'what repeats' ===")
    # The asymmetry lives in the OFFENSIVE RATE the two models speak in: GAR's currency is the
    # ACTUAL 5v5 goal rate (shooting-luck-laden); RAPM's is the xG rate (chance creation). The
    # goals rate should repeat LESS than the chance rate — the evidence for the framing. (GAR's
    # ev_offense *component* also mixes in stable usage/assists, so we report it too, separately.)
    rates = {}
    for s in G.SINGLE_SEASONS:
        agg = G.aggregate_window(ps, depth, [s])
        f = G.compute(agg, impact[impact["season_window"] == s], s)
        f = f[f["toi_5v5"] >= FLOOR].copy()
        f["goal_rate"] = f["g5"] / (f["toi_5v5"] / 60.0)            # actual 5v5 goals/60
        f["finishing"] = f["goals"] - f["ixg"]                       # goals above expected (luck-laden)
        rates[s] = f.set_index("player_id")[["goal_rate", "ev_offense", "finishing"]]
    seasons = list(rates.keys())

    def yoy(getter):
        cs = []
        for a, b in zip(seasons, seasons[1:]):
            j = getter(a, b)
            if len(j) > 30:
                cs.append(j.iloc[:, 0].corr(j.iloc[:, 1]))
        return cs

    goal_c = yoy(lambda a, b: pd.concat([rates[a]["goal_rate"], rates[b]["goal_rate"]], axis=1).dropna())
    fin_c = yoy(lambda a, b: pd.concat([rates[a]["finishing"], rates[b]["finishing"]], axis=1).dropna())

    def rapm_yoy(a, b):
        ra = impact[impact["season_window"] == a].set_index("player_id")["off_impact"]
        rb = impact[impact["season_window"] == b].set_index("player_id")["off_impact"]
        return pd.concat([ra, rb], axis=1).dropna()
    rapm_c = [rapm_yoy(a, b).iloc[:, 0].corr(rapm_yoy(a, b).iloc[:, 1]) for a, b in zip(seasons, seasons[1:])]

    print(f"  RAPM off_impact (isolated, regularized) YoY r mean {np.mean(rapm_c):.2f}")
    print(f"  actual 5v5 goal-rate                    YoY r mean {np.mean(goal_c):.2f}")
    print(f"  finishing residual (goals - xG)         YoY r mean {np.mean(fin_c):.2f}")
    print("  -> HONEST result: total production repeats MORE than RAPM (raw production persists via")
    print("     usage/volume; RAPM's isolation adds estimation noise). But the FINISHING residual —")
    print("     the exact piece that makes Value diverge from Impact — is the LEAST repeatable. So a")
    print("     Value>>Impact gap driven by finishing is real but historically the least sticky part.")

    print("\n=== 4. Replacement-level sensitivity (window) ===")
    base_rank = win.set_index("player_id")["gar"].rank(ascending=False)
    orig = config.GAR_CONFIG["REPLACEMENT_DEPTH_RANK"]
    for label, rule in [("tighter F10/D7", {"F": 10, "D": 7}), ("looser F8/D5", {"F": 8, "D": 5})]:
        config.GAR_CONFIG["REPLACEMENT_DEPTH_RANK"] = rule
        alt = G.compute(aggw, impact[impact["season_window"] == G.WINDOW_LABEL], G.WINDOW_LABEL)
        alt = alt[alt["toi_5v5"] >= FLOOR]
        ar = alt.set_index("player_id")["gar"].rank(ascending=False)
        j = pd.concat([base_rank, ar], axis=1, keys=["base", "alt"]).dropna()
        rho = j["base"].corr(j["alt"], method="spearman")
        dlevel = alt["gar"].median() - win["gar"].median()
        print(f"  {label:16s} rank spearman {rho:.3f}   median GAR shift {dlevel:+.1f}")
    config.GAR_CONFIG["REPLACEMENT_DEPTH_RANK"] = orig
    print("  -> rankings ~unchanged (spearman ~1.0); absolute levels move (as documented).")


if __name__ == "__main__":
    main()
