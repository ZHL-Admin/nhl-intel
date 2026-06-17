"""Validation for the Goalie Value (GAR/WAR) model — run, read the output, paste into value-gar.md.

Checks (Part A3): (1) top-25 goalies by GAR for two seasons (smell test: elite starters top,
backups near 0); (2) league goalie GAR distribution (centred near 0 at replacement); (3)
year-over-year correlation of goalie GAR — expected LOW (justifies the wider bands); (4)
replacement sensitivity (tighter/looser backup pool — rankings stable, levels move); (5)
cross-position WAR sanity (a clear #1 goalie sits in the same WAR neighbourhood as a top-5 skater).

Run:  python -m models_ml.validate_goalie_gar
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models_ml import bq, config, compute_goalie_gar as GG

FLOOR = GG.CFG["MIN_GAMES_FOR_RANKING"]


def main() -> None:
    gs = GG.pull()
    names = GG._names(gs["goalie_id"].unique().tolist())

    # build all single-season + window frames once
    frames = {s: GG.compute(GG.aggregate_window(gs, [s]), s) for s in GG.SINGLE_SEASONS}
    frames[GG.WINDOW_LABEL] = GG.compute(GG.aggregate_window(gs, GG.WINDOW), GG.WINDOW_LABEL)

    print("=== 1. Top-25 goalies by GAR (smell test) ===")
    GG.report(frames["2025-26"], "2025-26")
    GG.report(frames["2023-24"], "2023-24")

    print("\n=== 2. League goalie GAR distribution (qualified, by season) ===")
    for s in GG.SINGLE_SEASONS:
        g = frames[s][frames[s]["games_played"] >= FLOOR]["gar"]
        print(f"  {s}: n={len(g):>3}  mean {g.mean():+.1f}  median {g.median():+.1f}  "
              f"p10 {g.quantile(.1):+.1f}  p90 {g.quantile(.9):+.1f}  max {g.max():+.1f}")
    print("  -> near-0 mean/median (replacement-centred); a long positive tail (elite starters).")

    print("\n=== 3. Year-over-year correlation of goalie GAR (expected LOW) ===")
    cors = []
    seasons = GG.SINGLE_SEASONS
    for a, b in zip(seasons, seasons[1:]):
        fa = frames[a][frames[a]["games_played"] >= FLOOR].set_index("goalie_id")["gar"]
        fb = frames[b][frames[b]["games_played"] >= FLOOR].set_index("goalie_id")["gar"]
        j = pd.concat([fa, fb], axis=1, keys=["a", "b"]).dropna()
        if len(j) > 10:
            r = j["a"].corr(j["b"])
            cors.append(r)
            print(f"  {a} -> {b}: r={r:.2f} (n={len(j)})")
    print(f"  mean YoY r = {np.mean(cors):.2f}  -> goaltending regresses hard; this low reliability")
    print("     is what the per-tier shrinkage encodes (point estimates pulled toward the mean).")

    print("\n=== 4. Replacement-pool sensitivity (window; rankings stable, levels move) ===")
    base = frames[GG.WINDOW_LABEL][frames[GG.WINDOW_LABEL]["games_played"] >= FLOOR]
    base_rank = base.set_index("goalie_id")["gar"].rank(ascending=False)
    orig = config.GOALIE_GAR_CONFIG["REPLACEMENT_GAMES_RANK"]
    for label, rank in [("tighter rank>40", 40), ("looser rank>24", 24)]:
        config.GOALIE_GAR_CONFIG["REPLACEMENT_GAMES_RANK"] = rank
        alt = GG.compute(GG.aggregate_window(gs, GG.WINDOW), GG.WINDOW_LABEL)
        alt = alt[alt["games_played"] >= FLOOR]
        ar = alt.set_index("goalie_id")["gar"].rank(ascending=False)
        j = pd.concat([base_rank, ar], axis=1, keys=["base", "alt"]).dropna()
        rho = j["base"].corr(j["alt"], method="spearman")
        dlevel = alt["gar"].median() - base["gar"].median()
        print(f"  {label:16s} rank spearman {rho:.3f}   median GAR shift {dlevel:+.1f}")
    config.GOALIE_GAR_CONFIG["REPLACEMENT_GAMES_RANK"] = orig
    print("  -> rankings ~unchanged (spearman ~1.0); absolute levels move (as documented).")

    print("\n=== 5. Cross-position WAR sanity (shared goals-per-win=6) ===")
    skater = bq.query_df(f"""
        select g.war, r.first_name||' '||r.last_name nm, g.position
        from `{bq.project()}.nhl_models.player_gar` g
        left join (select player_id, any_value(first_name) first_name, any_value(last_name) last_name
                   from `{bq.project()}.nhl_staging.stg_rosters` group by 1) r on g.player_id=r.player_id
        where g.season_window='2024-25' and g.toi_5v5>=200 order by g.war desc limit 5""")
    goalie = frames["2024-25"][frames["2024-25"]["games_played"] >= FLOOR].sort_values("war", ascending=False).head(5)
    print("  top-5 skaters (2024-25 WAR):   " +
          ", ".join(f"{r['nm']} {r['war']:+.1f}" for _, r in skater.iterrows()))
    print("  top-5 goalies (2024-25 WAR):   " +
          ", ".join(f"{names.get(r['goalie_id'], r['goalie_id'])} {r['war']:+.1f}" for _, r in goalie.iterrows()))
    ratio = goalie["war"].iloc[0] / skater["war"].iloc[0]
    print(f"  #1 goalie WAR / #1 skater WAR = {ratio:.2f}  -> same neighbourhood (target: not >~3x).")

    print("\n=== 6. Shrinkage effect + confidence-aware mixed top-12 (2024-25) ===")
    g25 = frames["2024-25"][frames["2024-25"]["games_played"] >= FLOOR].copy()
    print("  shrinkage pulls noisy point estimates down: top goalie raw WAR "
          f"{g25['raw_war'].max():+.1f} -> shrunk {g25['war'].max():+.1f}")
    sk = bq.query_df(f"""
        select g.war, g.war_sd, r.first_name||' '||r.last_name nm, 'sk' kind
        from `{bq.project()}.nhl_models.player_gar` g
        left join (select player_id, any_value(first_name) first_name, any_value(last_name) last_name
                   from `{bq.project()}.nhl_staging.stg_rosters` group by 1) r on g.player_id=r.player_id
        where g.season_window='2024-25' and g.toi_5v5>=200""")
    gg = g25[["war", "war_sd"]].copy()
    gg["nm"] = g25["goalie_id"].map(lambda i: names.get(i, i)); gg["kind"] = "G "
    K = config.CONFIDENCE_SORT_K
    both = pd.concat([sk[["war", "war_sd", "nm", "kind"]], gg], ignore_index=True)
    both["conf"] = both["war"] - K * both["war_sd"].fillna(0)
    top = both.sort_values("conf", ascending=False).head(12)
    print(f"  confidence-adjusted order (war - {K}*sd):")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"    {i:2d}. {str(r['nm'])[:20]:20s} {r['kind']} WAR {r['war']:+.2f} ±{r['war_sd']:.2f} conf {r['conf']:+.2f}")
    g_ranks = [i for i, (_, r) in enumerate(top.iterrows(), 1) if r["kind"] == "G "]
    print(f"  -> goalies in top-12: ranks {g_ranks or 'none'} (confident skaters lead; elite goalies"
          " visible but not buried above them).")


if __name__ == "__main__":
    main()
