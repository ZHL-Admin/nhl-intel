"""Phase 1 integrity, composition, and freeze.

Builds (or reads cached) the per-season pair/trio corpus, runs the 1.3 integrity suite, writes the
composition + pair-locking tables, and freezes the combined corpus to parquet with recorded sha256
hashes. Deterministic; sampling for the 1.3(c) reconciliation uses config.SEED.

Outputs:
  reports/phase1_analysis.json   — machine-readable integrity + composition results
  data/parquet/frozen/pairs_corpus.parquet, trios_corpus.parquet
  data/parquet/frozen/MANIFEST.json  — per-file sha256, rows, season span
"""
from __future__ import annotations

import hashlib
import json

import polars as pl

from . import config, corpus

FROZEN = config.PARQUET / "frozen"
CONS_TOL = 1e-6          # conservation ratio tolerance (float round-off only; identity is exact)


def _season_key(s: str) -> str:
    return s.replace("-", "_")


# ---------------------------------------------------------------- build / cache
def ensure_built(seasons: list[str], rebuild: bool = False) -> None:
    for s in seasons:
        pp = corpus.PAIR_DIR / f"{_season_key(s)}.parquet"
        tp = corpus.TRIO_DIR / f"{_season_key(s)}.parquet"
        if rebuild or not pp.exists():
            corpus.build_pairs(s)
        if rebuild or not tp.exists():
            corpus.build_trios(s)


def _read_all(directory) -> pl.DataFrame:
    files = sorted(directory.glob("*.parquet"))
    return pl.concat([pl.read_parquet(f) for f in files], how="vertical_relaxed")


# ---------------------------------------------------------------- 1.3 integrity
def check_symmetry(pairs: pl.DataFrame) -> dict:
    """1.3(a): canonical a<b holds everywhere; (a,b,team,season) is unique (no dup orderings)."""
    ab_ok = bool((pairs["a"] < pairs["b"]).all())
    n = pairs.height
    n_unique = pairs.select("season_label", "team_id", "a", "b").unique().height
    return {"canonical_a_lt_b": ab_ok, "rows": n, "unique_keys": n_unique,
            "duplicate_keys": n - n_unique}


def check_conservation(seasons: list[str]) -> list[dict]:
    """1.3(b): per season, partner-summed shared TOI / player 5v5 TOI == 4 (each stint places a
    player in exactly 4 teammate pairs). Report the ratio distribution and max abs deviation."""
    out = []
    for s in seasons:
        c = corpus.conservation(s)
        dev = (c["ratio"] - 4.0).abs()
        out.append({"season": s, "players": c.height,
                    "ratio_min": float(c["ratio"].min()), "ratio_max": float(c["ratio"].max()),
                    "ratio_mean": float(c["ratio"].mean()),
                    "max_abs_dev_from_4": float(dev.max()),
                    "within_tol": bool(dev.max() <= CONS_TOL)})
    return out


def reconcile_player5v5(seasons: list[str], n_sample: int = 10) -> dict:
    """1.3(c): sample player-seasons and reconcile derived on-ice aggregates against frozen
    Atlas player_5v5 (the source of record). Reports per-sample ratios + worst-case deviation."""
    p5 = pl.read_parquet(config.ATLAS_PARQUET / "player_5v5.parquet").select(
        "player_id", "season_label", "toi_s", "xgf", "xga", "cf", "ca", "gf", "ga")
    frames = []
    for s in seasons:
        o = corpus.build_player_onice(s, write=False).with_columns(season_label=pl.lit(s))
        frames.append(o)
    onice = pl.concat(frames, how="vertical_relaxed")
    m = onice.join(p5, on=["player_id", "season_label"], how="inner", suffix="_p5")
    # deterministic sample (seeded)
    samp = m.sample(n=min(n_sample, m.height), seed=config.SEED)
    rows = []
    for r in samp.iter_rows(named=True):
        rows.append({
            "player_id": r["player_id"], "season": r["season_label"],
            "toi_ratio": round(r["toi"] / r["toi_s"], 5) if r["toi_s"] else None,
            "xgf_ratio": round(r["xgf"] / r["xgf_p5"], 5) if r["xgf_p5"] else None,
            "xga_ratio": round(r["xga"] / r["xga_p5"], 5) if r["xga_p5"] else None,
            "cf_match": int(r["cf"]) == int(r["cf_p5"]), "ca_match": int(r["ca"]) == int(r["ca_p5"]),
        })
    full = m.with_columns(
        tr=(pl.col("toi") / pl.col("toi_s")), xr=(pl.col("xgf") / pl.col("xgf_p5")),
        toi_abs=(pl.col("toi") - pl.col("toi_s")).abs())
    return {"joined_player_seasons": m.height, "sample": rows,
            "full_toi_ratio_median": float(full["tr"].median()),
            "full_toi_ratio_p01": float(full["tr"].quantile(0.01)),
            "full_toi_ratio_p99": float(full["tr"].quantile(0.99)),
            "full_xgf_ratio_median": float(full["xr"].median()),
            "full_max_abs_toi_diff_s": float(full["toi_abs"].max())}


# ---------------------------------------------------------------- 1.3(d) composition + pair-locking
def composition(pairs: pl.DataFrame) -> dict:
    by_season_tier = (pairs.group_by("season_label", "tier").len()
                      .sort("season_label", "tier").to_dicts())
    by_season_pos = (pairs.group_by("season_label", "pos_pair").len()
                     .sort("season_label", "pos_pair").to_dicts())
    toi_dist = {q: float(pairs["toi"].quantile(q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.99)}
    toi_dist["min"] = float(pairs["toi"].min()); toi_dist["max"] = float(pairs["toi"].max())
    return {"pairs_by_season_tier": by_season_tier, "pairs_by_season_pos": by_season_pos,
            "shared_toi_seconds_dist": toi_dist,
            "pos_pair_totals": pairs.group_by("pos_pair").len().sort("len", descending=True).to_dicts()}


def pair_locking(seasons: list[str]) -> dict:
    """O3 refresh: per (player, season) top-partner TOI share + partner entropy from the UNFLOORED
    partner-TOI table (D vs F broken out). Reports the concentration distribution, per position."""
    pf = corpus._pos_frame()
    posmap = dict(zip(pf["player_id"].to_list(), pf["pg"].to_list()))
    rows = []          # all-partner concentration
    samepos = []       # SAME-position concentration (the real O3 D-locking cut)
    for s in seasons:
        long = corpus.partner_toi_long(s).with_columns(
            pg=pl.col("pid").replace_strict(posmap, default="F", return_dtype=pl.Utf8),
            ppg=pl.col("partner").replace_strict(posmap, default="F", return_dtype=pl.Utf8))
        agg = long.group_by("pid").agg(
            total=pl.col("toi").sum(), top=pl.col("toi").max(), n_partners=pl.len(),
            # Shannon entropy (nats) of the partner-TOI distribution
            ent=-((pl.col("toi") / pl.col("toi").sum())
                  * (pl.col("toi") / pl.col("toi").sum()).log()).sum())
        agg = agg.filter(pl.col("total") > 0).with_columns(
            top_share=pl.col("top") / pl.col("total"),
            pg=pl.col("pid").replace_strict(posmap, default="F", return_dtype=pl.Utf8),
            season=pl.lit(s))
        rows.append(agg.select("season", "pid", "pg", "top_share", "n_partners", "ent"))
        # same-position partners only: a D's concentration among his D partners, etc.
        sp = (long.filter(pl.col("pg") == pl.col("ppg"))
              .group_by("pid", "pg").agg(
                  sp_total=pl.col("toi").sum(), sp_top=pl.col("toi").max(), sp_n=pl.len())
              .filter(pl.col("sp_total") > 0)
              .with_columns(sp_top_share=pl.col("sp_top") / pl.col("sp_total"),
                            sp_top_min=pl.col("sp_top") / 60.0, season=pl.lit(s)))
        samepos.append(sp.select("season", "pid", "pg", "sp_top_share", "sp_top_min", "sp_n"))
    allp = pl.concat(rows, how="vertical_relaxed")
    allsp = pl.concat(samepos, how="vertical_relaxed")
    summ, summ_sp = {}, {}
    for pg in ("D", "F"):
        sub = allp.filter(pl.col("pg") == pg)
        summ[pg] = {"player_seasons": sub.height,
                    "top_share_median": float(sub["top_share"].median()),
                    "top_share_p90": float(sub["top_share"].quantile(0.90)),
                    "top_share_p99": float(sub["top_share"].quantile(0.99)),
                    "entropy_median": float(sub["ent"].median()),
                    "n_partners_median": float(sub["n_partners"].median())}
        s2 = allsp.filter(pl.col("pg") == pg)
        summ_sp[pg] = {"player_seasons": s2.height,
                       "samepos_top_share_median": float(s2["sp_top_share"].median()),
                       "samepos_top_share_p90": float(s2["sp_top_share"].quantile(0.90)),
                       # absolute magnitude alongside the ratio (presentation rule 4.1a)
                       "samepos_top_shared_min_median": float(s2["sp_top_min"].median()),
                       "samepos_top_shared_min_p90": float(s2["sp_top_min"].quantile(0.90)),
                       "samepos_n_partners_median": float(s2["sp_n"].median())}
    by_season = (allp.group_by("season", "pg").agg(
        top_share_median=pl.col("top_share").median()).sort("season", "pg").to_dicts())
    return {"by_position": summ, "by_position_samepos": summ_sp,
            "top_share_median_by_season_pos": by_season}


# ---------------------------------------------------------------- 1.4 freeze
def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze(seasons: list[str]) -> dict:
    FROZEN.mkdir(parents=True, exist_ok=True)
    pairs = _read_all(corpus.PAIR_DIR).sort("season_label", "team_id", "a", "b")
    trios = _read_all(corpus.TRIO_DIR).sort("season_label", "team_id", "f1", "f2", "f3")
    manifest = {"seed": config.SEED, "seasons": seasons, "floor_pairs_sec": corpus.FLOOR_SEC,
                "floor_trios_sec": corpus.TRIO_FLOOR_SEC, "files": {}}
    for name, df in (("pairs_corpus.parquet", pairs), ("trios_corpus.parquet", trios)):
        path = FROZEN / name
        df.write_parquet(path)
        seasons_present = sorted(df["season_label"].unique().to_list())
        manifest["files"][name] = {"rows": df.height, "sha256": _sha256(path),
                                   "season_span": [seasons_present[0], seasons_present[-1],
                                                   len(seasons_present)]}
    with open(FROZEN / "MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


# ---------------------------------------------------------------- driver
def run(seasons: list[str] | None = None, rebuild: bool = False) -> dict:
    seasons = seasons or config.SEASONS_ALL
    ensure_built(seasons, rebuild=rebuild)
    pairs = _read_all(corpus.PAIR_DIR)
    analysis = {
        "seed": config.SEED, "seasons": seasons,
        "symmetry": check_symmetry(pairs),
        "conservation": check_conservation(seasons),
        "reconciliation_player5v5": reconcile_player5v5(seasons),
        "composition": composition(pairs),
        "pair_locking": pair_locking(seasons),
        "freeze": freeze(seasons),
    }
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "phase1_analysis.json", "w") as f:
        json.dump(analysis, f, indent=2)
    return analysis


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    rebuild = "--rebuild" in args
    seas = [a for a in args if not a.startswith("--")] or None
    a = run(seas, rebuild=rebuild)
    print("symmetry:", a["symmetry"])
    print("conservation max dev:", max(c["max_abs_dev_from_4"] for c in a["conservation"]))
    print("reconcile median toi ratio:", a["reconciliation_player5v5"]["full_toi_ratio_median"])
    print("freeze:", {k: v["rows"] for k, v in a["freeze"]["files"].items()})
