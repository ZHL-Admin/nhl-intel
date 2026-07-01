"""
Goalie Value: Goals/Wins Above Replacement (Goalie GAR/WAR) — the goaltending entry in the
cross-position WAR currency.

This mirrors the skater GAR build (`compute_gar.py`) so the two are directly comparable: same
multi-season-window convention, and — critically — the SAME `GOALS_PER_WIN` divisor, which is
the ONLY thing that makes a goalie's WAR comparable to a skater's on one ranked list. It is
read-only over the GSAx layer (`int_goalie_shots` / `mart_goalie_*`); the xG model, RAPM, and the
skater GAR model are all UNTOUCHED.

Goalie GAR = goals SAVED above a freely-available replacement (backup) goalie, decomposed into the
stacked-bar components:
  hd_saves        high-danger goals saved above replacement  <- the difference-maker
  md_saves        mid-danger goals saved above replacement
  ld_saves        low-danger goals saved above replacement
  pk_goaltending  shorthanded (penalty-kill / special-teams) save value above replacement
The four partition every faced shot (EV/other split by danger; special = PK), so they sum to GAR.
GAR = Σ components; WAR = GAR / GOALS_PER_WIN. Output nhl_models.goalie_gar.

Uncertainty band: binomial save-outcome sd (sqrt(Σ xg·(1−xg)) in goals) × an instability-inflation
multiplier (goaltending regresses hard year to year). It is wider than skaters' by construction —
goalie rankings are presented at tier-level confidence, never false precision (principle 6).

Run:  python -m models_ml.compute_goalie_gar [--dry-run] [--since YYYY-MM-DD]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config

CFG = config.GOALIE_GAR_CONFIG
# Mirror the skater GAR windows EXACTLY so goalie and skater rows align on season_window.
SINGLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
WINDOW = ["2023-24", "2024-25", "2025-26"]
WINDOW_LABEL = "2023-24_2025-26"
COMPONENTS = [k for k, _ in config.GOALIE_GAR_COMPONENTS]   # hd_saves, md_saves, ld_saves, pk_goaltending
GPW = CFG["GOALS_PER_WIN"]

# Per (goalie, season): GSAx, shot count, and binomial save-outcome variance for each of the four
# buckets (EV high/med/low + PK), from the per-shot xG layer. EV folds the negligible 'other'
# strength + 'unknown'-danger rows into the low bucket so the four buckets partition all shots and
# the components sum to total goalie GSAx-above-replacement. game types 02/03 only.
GOALIE_SEASON_SQL = """
with shots as (
  select goalie_id, season, game_id, is_goal, xg,
    case
      when strength_vs = 'special' then 'pk'
      when danger_tier = 'high'   then 'hd'
      when danger_tier = 'medium' then 'md'
      else 'ld'                                   -- ev/other low + unknown-danger
    end as bucket
  from `{p}.nhl_staging.int_goalie_shots`
  where substr(cast(game_id as string), 5, 2) in ('02', '03')
)
select goalie_id, season,
  count(distinct game_id) as games_played,
  -- per-bucket GSAx (= Σxg − goals over ALL unblocked, the calibrated population) and shot counts
  {gsax_cols},
  {shot_cols},
  -- binomial save-outcome variance in goals: Σ xg·(1−xg) over all faced unblocked shots
  sum(xg * (1 - xg)) as xg_var
from shots
group by goalie_id, season
"""


def _bucket_sql() -> tuple[str, str]:
    gsax = ",\n  ".join(
        f"sum(if(bucket='{b}', coalesce(xg,0), 0)) - countif(bucket='{b}' and is_goal) as gsax_{b}"
        for b in ["hd", "md", "ld", "pk"])
    shots = ",\n  ".join(
        f"countif(bucket='{b}') as shots_{b}" for b in ["hd", "md", "ld", "pk"])
    return gsax, shots


GSAX_B = ["gsax_hd", "gsax_md", "gsax_ld", "gsax_pk"]
SHOT_B = ["shots_hd", "shots_md", "shots_ld", "shots_pk"]
NUM = ["games_played", "xg_var"] + GSAX_B + SHOT_B
# bucket -> output component name
BUCKET_COMP = {"hd": "hd_saves", "md": "md_saves", "ld": "ld_saves", "pk": "pk_goaltending"}


def pull() -> pd.DataFrame:
    gsax_cols, shot_cols = _bucket_sql()
    df = bq.query_df(GOALIE_SEASON_SQL.format(p=bq.project(), gsax_cols=gsax_cols, shot_cols=shot_cols))
    for c in NUM:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    return df


def aggregate_window(gs: pd.DataFrame, seasons: list[str]) -> pd.DataFrame:
    """Sum a goalie's buckets/games/variance over the window's seasons (one row per goalie)."""
    sub = gs[gs["season"].isin(seasons)]
    return sub.groupby("goalie_id").agg(**{c: (c, "sum") for c in NUM}).reset_index()


def compute(agg: pd.DataFrame, window_label: str) -> pd.DataFrame:
    m = agg.copy()
    # replacement pool: backups = goalies ranked OUTSIDE the top-32 by window games, with a shot
    # floor for rate stability. Widen (drop the shot floor) if the pool is too thin.
    m["games_rank"] = m["games_played"].rank(ascending=False, method="first")
    m["shots_total"] = m[SHOT_B].sum(axis=1)
    is_repl = (m["games_rank"] > CFG["REPLACEMENT_GAMES_RANK"]) & (m["shots_total"] >= CFG["REPLACEMENT_MIN_SHOTS"])
    if int(is_repl.sum()) < CFG["REPLACEMENT_MIN_POOL"]:
        is_repl = m["games_rank"] > CFG["REPLACEMENT_GAMES_RANK"]
    m["is_replacement"] = is_repl
    pool = m[is_repl]

    # replacement GSAx-per-shot in each bucket (pooled over the backup goalies)
    repl_rate = {}
    for b in ["hd", "md", "ld", "pk"]:
        denom = pool[f"shots_{b}"].sum()
        repl_rate[b] = float(pool[f"gsax_{b}"].sum() / denom) if denom > 0 else 0.0

    # RAW component GAR = bucket GSAx − replacement-rate × bucket shots (goals saved above a backup).
    raw_comp = {}
    for b, comp in BUCKET_COMP.items():
        raw_comp[comp] = m[f"gsax_{b}"] - repl_rate[b] * m[f"shots_{b}"]
    m["raw_gar"] = sum(raw_comp.values())
    m["raw_war"] = m["raw_gar"] / GPW

    # RELIABILITY SHRINKAGE (empirical Bayes). Goaltending is low-signal, so the honest point
    # estimate regresses the raw value toward the workload-conditional league mean in proportion to
    # MEASURED reliability(shots) = shots / (shots + k) (k per tier, archive/models_ml/measure_goalie_reliability.py).
    # Per tier: neutral_b = (league above-replacement rate in tier b) × this goalie's tier shots —
    # i.e. what an average goalie produces on this workload; we keep volume credit and only regress
    # the rate. Low-workload / low-signal tiers (esp. low-danger, k→∞) pull hard to neutral; high-
    # workload elite goalies move little. The shrunk values are what everything user-facing uses.
    kcfg = CFG["RELIABILITY_K"]
    for b, comp in BUCKET_COMP.items():
        shots_b = m[f"shots_{b}"]
        tot_shots = shots_b.sum()
        pop_rate = float(raw_comp[comp].sum() / tot_shots) if tot_shots > 0 else 0.0  # league rate above repl
        neutral = pop_rate * shots_b
        reliability = shots_b / (shots_b + kcfg[b])
        m[comp] = neutral + reliability * (raw_comp[comp] - neutral)   # shrunk component (displayed)

    m["gar"] = m[COMPONENTS].sum(axis=1)          # shrunk GAR (the honest point estimate)
    m["war"] = m["gar"] / GPW

    # uncertainty band = the within-season binomial save-outcome sd (sqrt(Σ xg·(1−xg)) in goals).
    # NOTE: the year-to-year INSTABILITY is now modelled explicitly by the reliability shrinkage
    # above (the point estimate is regressed toward the mean), so the band is NO LONGER inflated for
    # instability — that would double-count it. It stays the pure sampling uncertainty, still ~3×
    # wider than skaters' (principle 6), and the SHRUNK point now sits honestly inside it.
    m["gar_sd"] = np.sqrt(m["xg_var"].clip(lower=0))
    m["war_sd"] = m["gar_sd"] / GPW

    m["position"] = "G"
    m["season_window"] = window_label
    m["repl_level_meta"] = (
        f"backup pool rank>{CFG['REPLACEMENT_GAMES_RANK']} by games, "
        f"min{CFG['REPLACEMENT_MIN_SHOTS']}sh, pool={int(is_repl.sum())}, "
        f"replGSAx/sh hd={repl_rate['hd']:.4f} md={repl_rate['md']:.4f} "
        f"ld={repl_rate['ld']:.4f} pk={repl_rate['pk']:.4f}")
    return m


OUT_COLS = (["goalie_id", "season_window", "position", "gar", "war", "gar_sd", "war_sd",
             "raw_gar", "raw_war"]
            + COMPONENTS + ["games_played", "shots_total", "is_replacement", "repl_level_meta"])


def _names(ids):
    ids = [int(i) for i in ids if pd.notna(i)]
    if not ids:
        return {}
    df = bq.query_df(f"""
        select player_id, any_value(first_name || ' ' || last_name) as name
        from `{bq.project()}.nhl_staging.stg_rosters`
        where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


def report(df: pd.DataFrame, label: str) -> None:
    names = _names(df["goalie_id"].tolist())
    floor = CFG["MIN_GAMES_FOR_RANKING"]
    top = df[df["games_played"] >= floor].sort_values("gar", ascending=False).head(25)
    print(f"\n=== Goalie GAR top-25 ({label}) — shrunk (raw) ===")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"  {i:2d}. {names.get(r['goalie_id'], r['goalie_id']):22s} "
              f"GAR {r['gar']:+6.1f} (raw {r['raw_gar']:+6.1f})  WAR {r['war']:+4.1f} ±{r['war_sd']:.1f}  "
              f"sh {int(r['shots_total']):>4d}  (HD {r['hd_saves']:+.1f} MD {r['md_saves']:+.1f} "
              f"LD {r['ld_saves']:+.1f} PK {r['pk_goaltending']:+.1f})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--since", default=None,
                    help="(accepted for DAG symmetry; goalie_gar is a full WRITE_TRUNCATE rebuild)")
    args = ap.parse_args()

    gs = pull()
    frames = []
    for s in SINGLE_SEASONS:
        frames.append(compute(aggregate_window(gs, [s]), s))
    frames.append(compute(aggregate_window(gs, WINDOW), WINDOW_LABEL))

    report(frames[-1], WINDOW_LABEL)
    report(frames[SINGLE_SEASONS.index("2025-26")], "2025-26")

    out = pd.concat(frames, ignore_index=True)[OUT_COLS]
    out["goalie_id"] = out["goalie_id"].astype("int64")
    out["model_version"] = "goalie_gar_v1"
    if args.dry_run:
        print(f"\n[dry-run] {len(out):,} rows not written")
        return
    bq.write_df(out, "goalie_gar", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "goalie_id"])
    print(f"\nWrote {len(out):,} rows to nhl_models.goalie_gar.")


if __name__ == "__main__":
    main()
