"""Atlas research-layer RAPM variant (Phase 4.3).

Triggered because production player_impact is built on the stale, dup-contaminated
segment backbone (missing all 563 backfilled games, incl. 38% of 2025-26). This
variant refits the SAME two-sided ridge design on the CLEAN Atlas stint corpus
(deduplicated, backfilled, goal-cut, shift-derived strength).

Spec: two rows per stint (per attacking direction); y = directional xGF/60;
weight = stint seconds; per-player offence (+1 attackers) and defence (+1
defenders) columns; controls = home-attacking, score state, startType, game-time
bucket; ridge lambda by 5-fold CV grouped by game (grid 1e2..1e6, 13 log pts);
fit per season on that season + prior season downweighted 0.5 (sensitivity 0/1);
exclude stints < 5s and the 753 quarantined stints; pool < 100-min players into
replacement columns by position group (F, D). Production is never modified.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from scipy import sparse
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge

from . import config, sources, stints as stints_mod

ALPHAS = np.logspace(2, 6, 13)
MIN_STINT_SECONDS = 5
REPLACEMENT_MIN_MINUTES = 100
SCOPE_SEASONS = [f"{y}-{str(y+1)[2:]}" for y in range(2015, 2026)]  # 2015-16..2025-26


def _prev_season(label: str) -> str:
    y = int(label[:4])
    return f"{y-1}-{str(y)[2:]}"


def _position_group() -> dict[int, str]:
    ros = pl.read_parquet(sources.ROSTERS_PARQUET).filter(~pl.col("is_goalie"))
    ros = ros.with_columns(pg=pl.when(pl.col("position_code") == "D").then(pl.lit("D")).otherwise(pl.lit("F")))
    # modal position group per player
    m = ros.group_by("player_id", "pg").len().sort("len", descending=True).unique("player_id", keep="first")
    return dict(zip(m["player_id"], m["pg"]))


def _load_5v5(season: str, prior_weight: float) -> pl.DataFrame:
    st = pl.read_parquet(stints_mod.STINTS_PARQUET)
    is5 = ((st["home_skater_ids"].list.len() == 5) & (st["away_skater_ids"].list.len() == 5)
           & st["home_goalie_id"].is_not_null() & st["away_goalie_id"].is_not_null())
    seasons = [season] + ([_prev_season(season)] if prior_weight > 0 else [])
    st = st.filter(is5 & (pl.col("duration_seconds") >= MIN_STINT_SECONDS)
                   & ~pl.col("is_quarantined") & pl.col("season_label").is_in(seasons))
    st = st.with_columns(sw=pl.when(pl.col("season_label") == season).then(1.0).otherwise(prior_weight))
    return st


def _flip_zone(z: str) -> str:
    return {"OZ": "DZ", "DZ": "OZ", "NZ": "NZ", "OTF": "OTF"}.get(z, "OTF")


def _expand(st: pl.DataFrame) -> list[dict]:
    rows = []
    for r in st.iter_rows(named=True):
        dur = r["duration_seconds"]; w = dur * r["sw"]
        gid = r["game_id"]
        gt = min((r["start_seconds"] // 1200), 3)  # game-time bucket: 0=p1,1=p2,2=p3,3=OT+
        home_lead = r["score_state"]
        # home attacking
        rows.append({"game_id": gid, "off": r["home_skater_ids"], "deff": r["away_skater_ids"],
                     "y": r["home_xg"] / dur * 3600.0, "w": w, "home_att": 1,
                     "ss": ("lead" if home_lead > 0 else "trail" if home_lead < 0 else "tie"),
                     "zone": r["start_type"], "gt": gt})
        # away attacking (flip score + zone perspective)
        rows.append({"game_id": gid, "off": r["away_skater_ids"], "deff": r["home_skater_ids"],
                     "y": r["away_xg"] / dur * 3600.0, "w": w, "home_att": 0,
                     "ss": ("lead" if -home_lead > 0 else "trail" if -home_lead < 0 else "tie"),
                     "zone": _flip_zone(r["start_type"]), "gt": gt})
    return rows


def _build_design(rows, pos: dict[int, str]):
    # per-player TOI (row weight counts once per appearance; approximate via unique players)
    toi = {}
    for row in rows:
        for p in row["off"] + row["deff"]:
            toi[p] = toi.get(p, 0.0) + row["w"] / 2.0  # each direction-row is half a stint's players' second-share
    # replacement pooling: <100 min -> REPL by position group
    def col_key(p, side):
        if toi.get(p, 0) / 60.0 < REPLACEMENT_MIN_MINUTES:
            return f"REPL_{pos.get(p,'F')}_{side}"
        return f"{p}_{side}"
    off_players = sorted({col_key(p, "off") for row in rows for p in row["off"]})
    def_players = sorted({col_key(p, "def") for row in rows for p in row["deff"]})
    # unified player index (off and def separate blocks); map keys
    off_idx = {k: i for i, k in enumerate(off_players)}
    def_idx = {k: i for i, k in enumerate(def_players)}
    n_off, n_def = len(off_players), len(def_players)
    ctrl_base = n_off + n_def
    # controls: ss(lead,trail vs tie)=2, zone(OZ,DZ,NZ vs OTF)=3, home_att=1, gt(1,2,3 vs 0)=3
    ss_cats = {"lead": 0, "trail": 1}; zone_cats = {"OZ": 0, "DZ": 1, "NZ": 2}
    n_ctrl = 2 + 3 + 1 + 3
    n_rows = len(rows)
    y = np.empty(n_rows); w = np.empty(n_rows); games = np.empty(n_rows, dtype=np.int64)
    ri, ci, dv = [], [], []
    for i, row in enumerate(rows):
        y[i] = row["y"]; w[i] = row["w"]; games[i] = row["game_id"]
        for p in row["off"]:
            ri.append(i); ci.append(off_idx[col_key(p, "off")]); dv.append(1.0)
        for p in row["deff"]:
            ri.append(i); ci.append(n_off + def_idx[col_key(p, "def")]); dv.append(1.0)
        c = ctrl_base
        if row["ss"] in ss_cats:
            ri.append(i); ci.append(c + ss_cats[row["ss"]]); dv.append(1.0)
        c += 2
        if row["zone"] in zone_cats:
            ri.append(i); ci.append(c + zone_cats[row["zone"]]); dv.append(1.0)
        c += 3
        if row["home_att"]:
            ri.append(i); ci.append(c); dv.append(1.0)
        c += 1
        if row["gt"] >= 1:
            ri.append(i); ci.append(c + row["gt"] - 1); dv.append(1.0)
    X = sparse.csr_matrix((dv, (ri, ci)), shape=(n_rows, ctrl_base + n_ctrl))
    return X, y, w, games, off_players, def_players, n_off, toi


def _cv_alpha(X, y, w, games, folds=5):
    rng = np.random.default_rng(0)
    uniq = np.unique(games); rng.shuffle(uniq)
    fold_of = {g: i % folds for i, g in enumerate(uniq)}
    fa = np.array([fold_of[g] for g in games])
    curve = []
    for a in ALPHAS:
        errs = []
        for f in range(folds):
            val = fa == f
            m = Ridge(alpha=a, solver="lsqr", fit_intercept=True, max_iter=1500)
            m.fit(X[~val], y[~val], sample_weight=w[~val])
            pred = m.predict(X[val])
            errs.append(np.average((pred - y[val]) ** 2, weights=w[val]))
        curve.append((float(a), float(np.mean(errs))))
    best = min(curve, key=lambda t: t[1])[0]
    return best, curve


def fit_season(season: str, prior_weight: float = 0.5, cv: bool = True) -> dict[str, Any]:
    pos = _position_group()
    st = _load_5v5(season, prior_weight)
    rows = _expand(st)
    X, y, w, games, off_players, def_players, n_off, toi = _build_design(rows, pos)
    if cv:
        alpha, curve = _cv_alpha(X, y, w, games)
    else:
        alpha, curve = 10000.0, []
    m = Ridge(alpha=alpha, solver="lsqr", fit_intercept=True, max_iter=3000)
    m.fit(X, y, sample_weight=w)
    coef = m.coef_
    off = coef[:n_off]; deff = coef[n_off:n_off + len(def_players)]
    off_c = off - off.mean(); def_c = deff - deff.mean()
    # map back to players (skip REPL columns)
    def rows_out(keys, vals, side):
        out = []
        for k, v in zip(keys, vals):
            if k.startswith("REPL_"):
                continue
            pid = int(k.rsplit("_", 1)[0])
            out.append((pid, v))
        return dict(out)
    off_map = rows_out(off_players, off_c, "off")
    def_map = rows_out(def_players, -def_c, "def")  # higher = better defence
    # season-only 5v5 TOI per player (for qualification/QoC; the pooling `toi`
    # above spans season+prior and is only for replacement-column assignment).
    season_st = st.filter(pl.col("season_label") == season)
    stoi: dict[int, float] = {}
    for r in season_st.iter_rows(named=True):
        for p in r["home_skater_ids"] + r["away_skater_ids"]:
            stoi[p] = stoi.get(p, 0.0) + r["duration_seconds"]
    players = sorted(set(off_map) | set(def_map))
    df = pd.DataFrame({"player_id": players,
                       "off_impact": [off_map.get(p, np.nan) for p in players],
                       "def_impact": [def_map.get(p, np.nan) for p in players],
                       "toi_min": [stoi.get(p, 0.0) / 60.0 for p in players]})
    df["season"] = season; df["alpha"] = alpha; df["prior_weight"] = prior_weight
    return {"df": df, "alpha": alpha, "cv_curve": curve, "n_stints": st.height,
            "n_rows": len(rows), "n_off_cols": n_off}


if __name__ == "__main__":
    import sys
    seasons = sys.argv[1:] or SCOPE_SEASONS
    frames = []
    for s in seasons:
        print(f"fitting {s}...", flush=True)
        r = fit_season(s)
        print(f"  {s}: alpha={r['alpha']:.0f} stints={r['n_stints']:,} players={len(r['df'])}", flush=True)
        frames.append(r["df"])
        if s == "2024-25":
            import json
            (config.REPORTS_DIR / "rapm_variant_cv_2024_25.json").write_text(
                json.dumps({"alpha": r["alpha"], "cv_curve": r["cv_curve"]}, indent=2))
    out = pd.concat(frames, ignore_index=True)
    pl.from_pandas(out).write_parquet(config.PARQUET_DIR / "rapm_variant.parquet")
    print(f"wrote rapm_variant.parquet: {len(out)} player-seasons")
