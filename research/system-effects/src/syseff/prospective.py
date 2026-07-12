"""Phase 6.4 — prospective registration freeze for 2026-27 (internal track only).

Free agency for 2026-27 is IN PROGRESS: the mover cohort resolves naturally at season start, so
only the PREDICTOR INPUTS freeze now — each candidate player's 2025-26 values (variant RAPM q and
player type) that will feed the incumbent (variant) and challenger (variant + deployment) once
destinations are known. The Design B system coefficients (portability_model.json, fit through
2025-26) are the frozen challenger model; 2026-27/2027-28 outcomes do not exist yet, so applying
them to the 2026-27 movers is leakage-clean.

Registration protocol is frozen in reports/registration_2027.md. Amendments allowed only before
outcome data exists, recorded with dates.
"""
from __future__ import annotations

import polars as pl

from . import config

FREEZE_SEASON = "2025-26"
OUT_DIR = config.PARQUET / "prospective_2027"


def build(write: bool = True) -> pl.DataFrame:
    rapm = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet").filter(
        pl.col("season") == FREEZE_SEASON).select(
        "player_id", q=pl.col("off_impact") + pl.col("def_impact"), toi_min_rapm="toi_min")
    types = pl.read_parquet(config.PARQUET / "player_types.parquet").filter(
        pl.col("season_label") == FREEZE_SEASON).select("player_id", "type_id", "pg",
                                                        pl.col("toi_5v5_min").alias("toi_5v5_min"))
    p5 = pl.read_parquet(config.ATLAS_PARQUET / "player_5v5.parquet").filter(
        pl.col("season_label") == FREEZE_SEASON).select("player_id", pl.col("xg_share").alias("xg_share_2025_26"))
    out = (rapm.join(types, on="player_id", how="inner")
           .join(p5, on="player_id", how="left")
           .with_columns(freeze_season=pl.lit(FREEZE_SEASON),
                         high_toi_tier=pl.col("toi_5v5_min") >= pl.col("toi_5v5_min").quantile(0.66)))
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out.write_parquet(OUT_DIR / "frozen_predictors.parquet")
    return out


if __name__ == "__main__":
    d = build()
    print("frozen predictors 2025-26:", d.shape,
          "| high-TOI tier:", int(d["high_toi_tier"].sum()),
          "| D:", d.filter(pl.col("pg") == "D").height, "F:", d.filter(pl.col("pg") == "F").height)
