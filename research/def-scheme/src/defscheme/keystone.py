"""Phase 2 — THE KEYSTONE: does defensive identity emerge, and what does it TRACK (roster/coach/neither)?

2.1 cluster team-season z-scored deviation signatures into a coarse + fine vocabulary.
2.2 continuity per consecutive-season pair: ROSTER_CONTINUITY (returning 5v5 D-skater TOI share) and
    COACH_CONTINUITY (same head coach, regime ledger).
2.3 decomposition: (a) continuity gradient = identity persistence vs roster continuity; (b) four-cell
    roster x coach persistence; (c) within-season floor. Measures what identity tracks; assumes nothing.
"""
from __future__ import annotations

import glob

import numpy as np
import polars as pl
from sklearn.cluster import KMeans

from . import config as C, scheme_norm as SN

MATRIX = C.PARQUET / "team_season_matrix.parquet"
PAIRS = C.PARQUET / "continuity_pairs.parquet"
COARSE_K = 3
FINE_K = 6
MIN_PAIR = 8            # min season-pairs to read a four-cell cell
SEASON_ORD = {s: i for i, s in enumerate(C.SEASONS)}


# ---------------------------------------------------------------- 2.1 signatures -> matrix + clusters
def signature_matrix(grid: str) -> pl.DataFrame:
    sig = pl.read_parquet(SN.SIGNATURES).filter(pl.col("grid") == grid)
    zcols = [f"z_{f}" for f in SN.FEATURES]
    long = sig.select("defending_team_id", "season", "situation", *zcols)
    wide = long.pivot(on="situation", values=zcols, index=["defending_team_id", "season"])
    valcols = [c for c in wide.columns if c not in ("defending_team_id", "season")]
    return wide.with_columns([pl.col(c).fill_null(0.0) for c in valcols])   # keep id/season dtypes


def cluster(grid: str, k: int) -> pl.DataFrame:
    wide = signature_matrix(grid)
    X = wide.drop("defending_team_id", "season").to_numpy()
    km = KMeans(n_clusters=k, random_state=C.SEED_INT, n_init=10).fit(X)
    return wide.select("defending_team_id", "season").with_columns(cluster=pl.Series(km.labels_)), km, wide


# ---------------------------------------------------------------- 2.2 continuity
def _dskater_toi() -> pl.DataFrame:
    """Per (team, season, skater): 5v5 on-ice seconds, defensemen only (rosters position_code='D')."""
    st = pl.read_parquet(C.ATLAS_STINTS, columns=["game_id", "season_label", "strength_state",
                                                  "home_skater_ids", "away_skater_ids", "duration_seconds"])
    st = st.filter((pl.col("strength_state") == "5v5") & pl.col("season_label").is_in(C.SEASONS))
    on = pl.concat([
        st.select("game_id", "season_label", "duration_seconds", sk="home_skater_ids"),
        st.select("game_id", "season_label", "duration_seconds", sk="away_skater_ids")]).explode("sk")
    on = on.group_by("game_id", "season_label", "sk").agg(toi=pl.col("duration_seconds").sum())
    ros = pl.read_parquet(C.NIR / "research/deployment-atlas/data/parquet/rosters.parquet",
                          columns=["game_id", "player_id", "team_id", "position_code"])
    on = on.join(ros, left_on=["game_id", "sk"], right_on=["game_id", "player_id"], how="left")
    d = on.filter(pl.col("position_code") == "D")
    return d.group_by("team_id", "season_label", "sk").agg(toi=pl.col("toi").sum())


def _coach_by_team_season() -> pl.DataFrame:
    """Primary head coach per (team, season) = the regime covering the season with the most games."""
    rl = pl.read_parquet(C.SYSFX_REGIME)
    rows = []
    for r in rl.iter_rows(named=True):
        for s in C.SEASONS:
            if r["start_season"] <= s <= r["end_season"]:
                rows.append({"team_id": r["team_id"], "season": s, "coach": r["coach_name"],
                             "games": r["games_in_regime"]})
    df = pl.DataFrame(rows)
    return (df.sort("games", descending=True).group_by("team_id", "season").first()
            .select("team_id", "season", "coach"))


def continuity_pairs() -> pl.DataFrame:
    toi = _dskater_toi()
    coach = _coach_by_team_season()
    rows = []
    for team, g in toi.partition_by("team_id", as_dict=True, include_key=True).items():
        tid = team[0] if isinstance(team, tuple) else team
        by_season = {s: sub for s, sub in g.partition_by("season_label", as_dict=True, include_key=False).items()}
        by_season = {(s[0] if isinstance(s, tuple) else s): v for s, v in
                     g.partition_by("season_label", as_dict=True, include_key=False).items()}
        for s in C.SEASONS[:-1]:
            s2 = C.SEASONS[SEASON_ORD[s] + 1]
            a = by_season.get(s); b = by_season.get(s2)
            if a is None or b is None:
                continue
            prev_sk = set(a["sk"].to_list())
            tot = b["toi"].sum()
            ret = b.filter(pl.col("sk").is_in(list(prev_sk)))["toi"].sum()
            rc = float(ret / tot) if tot else None
            rows.append({"team_id": tid, "season_from": s, "season_to": s2, "roster_continuity": rc})
    pairs = pl.DataFrame(rows)
    # coach continuity
    c_from = coach.rename({"season": "season_from", "coach": "coach_from"})
    c_to = coach.rename({"season": "season_to", "coach": "coach_to"})
    pairs = (pairs.join(c_from, on=["team_id", "season_from"], how="left")
             .join(c_to, on=["team_id", "season_to"], how="left")
             .with_columns(coach_continuity=pl.col("coach_from") == pl.col("coach_to")))
    return pairs


# ---------------------------------------------------------------- 2.3 persistence + decomposition
def _persistence(grid: str) -> pl.DataFrame:
    """Per (team, consecutive-season pair): correlation of the z-signature vector between seasons."""
    wide = signature_matrix(grid)
    cols = [c for c in wide.columns if c not in ("defending_team_id", "season")]
    rows = []
    for team, g in wide.partition_by("defending_team_id", as_dict=True, include_key=True).items():
        tid = team[0] if isinstance(team, tuple) else team
        vec = {r["season"]: np.array([r[c] for c in cols], float) for r in g.iter_rows(named=True)}
        for s in C.SEASONS[:-1]:
            s2 = C.SEASONS[SEASON_ORD[s] + 1]
            if s in vec and s2 in vec and np.std(vec[s]) > 0 and np.std(vec[s2]) > 0:
                rows.append({"team_id": tid, "season_from": s, "season_to": s2,
                             f"persist_{grid}": float(np.corrcoef(vec[s], vec[s2])[0, 1])})
    return pl.DataFrame(rows)


def _within_season_floor(grid: str) -> float:
    """Split-half persistence within a season (measurement-reliability reference), z-vector correlation."""
    fr = SN._frames().with_columns(h=pl.struct("game_id", "event_id").hash(seed=C.SEED_INT) % 2)
    situ = "situ_coarse" if grid == "coarse" else "situ_fine"
    halves = []
    for hv in (0, 1):
        s = SN._signature(fr.filter(pl.col("h") == hv), situ, ["defending_team_id", "season"])
        # z-score deviations within half
        for f in SN.FEATURES:
            s = s.with_columns(((pl.col(f) - pl.col(f).mean().over("situation")) / pl.col(f).std().over("situation")).alias(f"z_{f}"))
        halves.append(s.select("defending_team_id", "season", "situation", *[f"z_{f}" for f in SN.FEATURES]).with_columns(half=pl.lit(hv)))
    sh = pl.concat(halves)
    zc = [f"z_{f}" for f in SN.FEATURES]
    w = [sh.filter(pl.col("half") == hv).pivot(on="situation", values=zc, index=["defending_team_id", "season"]).fill_null(0.0) for hv in (0, 1)]
    cols = [c for c in w[0].columns if c not in ("defending_team_id", "season")]
    m = w[0].join(w[1], on=["defending_team_id", "season"], suffix="_1")
    rs = []
    for r in m.iter_rows(named=True):
        a = np.array([r[c] for c in cols]); b = np.array([r[c + "_1"] for c in cols])
        if np.std(a) > 0 and np.std(b) > 0:
            rs.append(np.corrcoef(a, b)[0, 1])
    return float(np.median(rs))


def decomposition() -> dict:
    pairs = continuity_pairs().with_columns(pl.col("team_id").cast(pl.Int64))
    for grid in ("coarse", "fine"):
        per = _persistence(grid).with_columns(pl.col("team_id").cast(pl.Int64))
        pairs = pairs.join(per, on=["team_id", "season_from", "season_to"], how="left")
    pairs.write_parquet(PAIRS)
    p = pairs.drop_nulls(["roster_continuity", "persist_coarse"])
    out = {"n_pairs": p.height}
    # (a) gradient: persistence ~ roster_continuity (OLS slope + CI via bootstrap)
    x = p["roster_continuity"].to_numpy()
    for grid in ("coarse", "fine"):
        y = p[f"persist_{grid}"].to_numpy()
        mask = ~np.isnan(y)
        xx, yy = x[mask], y[mask]
        slope, r = _ols(xx, yy)
        lo, hi = _boot_slope(xx, yy)
        # terciles
        q1, q2 = np.quantile(xx, [1 / 3, 2 / 3])
        hi_t = yy[xx >= q2]; lo_t = yy[xx <= q1]
        out[grid] = {"slope": slope, "slope_ci": [lo, hi], "pearson_r": r,
                     "persist_high_tercile": float(np.mean(hi_t)), "persist_low_tercile": float(np.mean(lo_t)),
                     "n_high": int(len(hi_t)), "n_low": int(len(lo_t)),
                     "within_season_floor": _within_season_floor(grid)}
    # (b) four-cell: roster hi/lo (median split) x coach same/diff
    med = float(np.median(x))
    fc = (p.with_columns(roster_hi=pl.col("roster_continuity") >= med)
          .group_by("roster_hi", "coach_continuity")
          .agg(n=pl.len(), persist_coarse=pl.col("persist_coarse").mean(), persist_fine=pl.col("persist_fine").mean()))
    out["four_cell"] = fc.sort("roster_hi", "coach_continuity", descending=[True, True]).to_dicts()
    out["roster_median"] = med
    out["pairs"] = p
    return out


def _ols(x, y):
    if len(x) < 3:
        return float("nan"), float("nan")
    b = np.polyfit(x, y, 1)[0]
    r = float(np.corrcoef(x, y)[0, 1])
    return float(b), r


def _boot_slope(x, y, n=2000):
    rng = np.random.default_rng(C.SEED_INT)
    sl = []
    for _ in range(n):
        idx = rng.integers(0, len(x), len(x))
        if np.std(x[idx]) > 0:
            sl.append(np.polyfit(x[idx], y[idx], 1)[0])
    return float(np.quantile(sl, 0.05)), float(np.quantile(sl, 0.95))


if __name__ == "__main__":
    d = decomposition()
    print(f"season-pairs: {d['n_pairs']}")
    for grid in ("coarse", "fine"):
        g = d[grid]
        print(f"\n{grid}: gradient slope={g['slope']:.2f} CI[{g['slope_ci'][0]:.2f},{g['slope_ci'][1]:.2f}] "
              f"r={g['pearson_r']:.2f}")
        print(f"  persistence high-continuity tercile={g['persist_high_tercile']:.2f} (n={g['n_high']}) "
              f"vs low={g['persist_low_tercile']:.2f} (n={g['n_low']}) | within-season floor={g['within_season_floor']:.2f}")
    print("\nfour-cell (roster_hi x coach_same): persistence_coarse")
    for c in d["four_cell"]:
        print(f"  roster_hi={c['roster_hi']} coach_same={c['coach_continuity']}: n={c['n']} "
              f"persist_coarse={c['persist_coarse']:.2f}" + (" [THIN]" if c['n'] < MIN_PAIR else ""))
