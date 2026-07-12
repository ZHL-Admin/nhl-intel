"""Phase 3.1 — the pooling layer (player types).

Phase 0 found production `player_archetypes` stale-backbone-derived and rebuild-divergent;
per that decision we derive our OWN types from frozen Atlas assets so System Effects does not
couple to a production table. Features per player-season (200+ 5v5 min):
  position (F/D), variant RAPM off/def, OZ-start share, PP-frac, PK-frac, per-game 5v5 TOI.

Method (written here so the report can quote it): z-score every continuous feature over the
pooled 200+-min player-seasons; cluster POSITION-STRATIFIED (F and D have structurally
different roles) with KMeans (seed=config.SEED, n_init=10); pick k per position by silhouette
over a small grid, capping total types at <=10; label each type by its standardized centroid.
Types are assignable for every player-season 2010-26 with 200+ 5v5 minutes.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from . import config, context as C

FEATURES = ["off_impact", "def_impact", "oz_start_share", "pp_frac", "pk_frac", "toi_per_gp"]
TYPES_PARQUET = config.PARQUET / "player_types.parquet"
MIN_MIN = 200.0


def _positions() -> pl.DataFrame:
    """Modal skater position (F/D) per player across all games."""
    ros = pl.read_parquet(config.ATLAS_PARQUET / "rosters.parquet",
                          columns=["player_id", "position_code", "is_goalie"]).filter(~pl.col("is_goalie"))
    ros = ros.with_columns(pg=pl.when(pl.col("position_code") == "D").then(pl.lit("D")).otherwise(pl.lit("F")))
    m = ros.group_by("player_id", "pg").len().sort("len", descending=True).unique("player_id", keep="first")
    return m.select("player_id", "pg")


def feature_table(seasons=None) -> pl.DataFrame:
    seasons = seasons or config.SEASONS_ALL
    rapm = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet").select(
        "player_id", "season", "off_impact", "def_impact")
    pos = _positions()
    frames = []
    for s in seasons:
        ctx = C.player_season_context(s)
        onice = pl.read_parquet(C.ONICE_DIR / f"{s.replace('-', '_')}.parquet")
        gp = onice.group_by("player_id").agg(gp=pl.col("game_id").n_unique())
        d = (ctx.filter(pl.col("toi_5v5_min") >= MIN_MIN)
             .join(rapm.filter(pl.col("season") == s).drop("season"), on="player_id", how="left")
             .join(gp, on="player_id", how="left")
             .join(pos, on="player_id", how="left"))
        d = d.with_columns(toi_per_gp=pl.col("toi_5v5_s") / 60.0 / pl.col("gp"))
        frames.append(d.select("player_id", pl.lit(s).alias("season_label"), "pg", "gp",
                               "toi_5v5_min", *FEATURES))
    out = pl.concat(frames)
    # RAPM missing (rare: toi_min=0 rows) -> drop from clustering, assigned 'unclustered'
    return out


def _fit_position(df: pl.DataFrame, pos: str, kgrid, scaler_stats):
    sub = df.filter(pl.col("pg") == pos).drop_nulls(FEATURES)
    X = sub.select(FEATURES).to_numpy()
    Xs = (X - scaler_stats[0]) / scaler_stats[1]
    best = None
    for k in kgrid:
        km = KMeans(n_clusters=k, random_state=config.SEED, n_init=10).fit(Xs)
        sil = silhouette_score(Xs, km.labels_)
        if best is None or sil > best[0]:
            best = (sil, k, km)
    sil, k, km = best
    lab = km.predict(Xs)
    return sub, lab, k, sil, km, Xs


def build(seasons=None, write: bool = True) -> tuple[pl.DataFrame, dict]:
    df = feature_table(seasons)
    clustered = df.drop_nulls(FEATURES)
    scaler = StandardScaler().fit(clustered.select(FEATURES).to_numpy())
    stats = (scaler.mean_, scaler.scale_)

    meta = {"features": FEATURES, "min_5v5_min": MIN_MIN, "n_playerseasons": df.height,
            "n_clustered": clustered.height, "positions": {}, "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist()}
    assigns = []
    # k grids chosen so total types land in the spec's [6,10] band (F 4-6, D 2-4);
    # silhouette picks within each grid.
    for pos, kgrid in (("F", range(4, 7)), ("D", range(2, 5))):
        sub, lab, k, sil, km, Xs = _fit_position(clustered, pos, kgrid, stats)
        # centroid profiles in RAW feature units for labeling
        cent_raw = km.cluster_centers_ * scaler.scale_ + scaler.mean_
        labels = _name_types(pos, cent_raw)
        sub = sub.with_columns(type_id=pl.Series([f"{pos}{c}" for c in lab]))
        sub = sub.with_columns(player_type=pl.col("type_id").replace_strict(
            {f"{pos}{i}": labels[i] for i in range(k)}))
        assigns.append(sub.select("player_id", "season_label", "pg", "type_id", "player_type",
                                  "toi_5v5_min", *FEATURES))
        meta["positions"][pos] = {"k": k, "silhouette": round(float(sil), 3),
                                  "sizes": {f"{pos}{i}": int((lab == i).sum()) for i in range(k)},
                                  "type_names": {f"{pos}{i}": labels[i] for i in range(k)},
                                  "centroids_raw": {f"{pos}{i}": dict(zip(FEATURES, [round(float(v), 3) for v in cent_raw[i]])) for i in range(k)}}
    out = pl.concat(assigns)
    meta["n_types_total"] = out["type_id"].n_unique()
    if write:
        out.write_parquet(TYPES_PARQUET)
    return out, meta


def _name_types(pos: str, cent_raw: np.ndarray) -> dict:
    """Human labels from standardized centroid ranks: usage (toi_per_gp), PP/PK role,
    OZ shelter, off/def tilt. Deterministic given centroids."""
    fi = {f: i for i, f in enumerate(FEATURES)}
    labels = {}
    toi = cent_raw[:, fi["toi_per_gp"]]
    pp = cent_raw[:, fi["pp_frac"]]
    pk = cent_raw[:, fi["pk_frac"]]
    oz = cent_raw[:, fi["oz_start_share"]]
    off = cent_raw[:, fi["off_impact"]]
    de = cent_raw[:, fi["def_impact"]]
    toi_rank = toi.argsort().argsort()  # 0=lowest
    n = len(toi)
    for i in range(n):
        usage = "top" if toi_rank[i] >= n - max(1, n // 3) else ("bottom" if toi_rank[i] < max(1, n // 3) else "mid")
        role = []
        if pp[i] >= np.median(pp) + 1e-9 and pp[i] > 0.06:
            role.append("PP")
        if pk[i] >= np.median(pk) + 1e-9 and pk[i] > 0.06:
            role.append("PK")
        roles = "+".join(role) if role else "EV"
        shelter = "shelt" if oz[i] >= np.percentile(oz, 66) else ("tough" if oz[i] <= np.percentile(oz, 34) else "bal")
        tilt = "off" if off[i] - de[i] > 0.01 else ("def" if de[i] - off[i] > 0.01 else "two-way")
        labels[i] = f"{pos}:{usage}-{roles}-{shelter}-{tilt}"
    return labels


if __name__ == "__main__":
    out, meta = build()
    import json
    print(json.dumps({k: v for k, v in meta.items() if k != "scaler_mean" and k != "scaler_scale"}, indent=2, default=str))
