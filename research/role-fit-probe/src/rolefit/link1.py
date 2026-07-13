"""Link 1 (GATE) — can we build a STABLE role profile per player?

Role space (1.2): PCA per position on the within-(position,season) z-scored shot-action axes
(PCA not NMF: the z-scored axes carry negatives, and we want orthogonal interpretable variance axes).
Stability (1.3), per position, with a shuffled-identity placebo (2000 perms, seed 20260713):
  a) split-half within season (odd vs even games, 40+ games);
  b) year-over-year, SAME primary team;
  c) year-over-year, ACROSS a team change  ->  the (b)-vs-(c) gap = "role = player vs team".
Verdict (1.4): PASS if split-half >= 0.50 AND same-team YoY >= 0.40 for the MAJORITY of named role
axes, each beating placebo at p < 0.05.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl
from sklearn.decomposition import PCA

from . import config
from . import profiles as P

PROFILE_DIR = P.PROFILE_DIR
SEED = config.SEED
SB_SPLIT = 0.50          # split-half reliability bar (raw odd/even correlation)
SB_YOY = 0.40            # same-team YoY correlation bar
N_PERM = 2000
TOI_FLOOR = 6000         # 100 min 5v5 for role-space membership
MIN_GAMES = 40           # split-half membership
N_COMP = 4               # interpretable components per position


def _load() -> pl.DataFrame:
    return pl.concat([pl.read_parquet(p) for p in sorted(PROFILE_DIR.glob("*.parquet"))],
                     how="vertical_relaxed")


def _zscore(df: pl.DataFrame, cols, suffix="") -> pl.DataFrame:
    """z-score each axis WITHIN (position, season) using FULL-season stats (so halves share a scale)."""
    stats = df.group_by("pg", "season_label").agg(
        [pl.col(f"{c}").mean().alias(f"{c}__m") for c in cols]
        + [pl.col(f"{c}").std().alias(f"{c}__s") for c in cols])
    return stats


def _apply_z(df, stats, cols, src_suffix, out_prefix):
    d = df.join(stats, on=["pg", "season_label"], how="left")
    exprs = []
    for c in cols:
        z = (pl.col(f"{c}{src_suffix}") - pl.col(f"{c}__m")) / pl.col(f"{c}__s")
        exprs.append(z.alias(f"{out_prefix}{c}"))
    return d.with_columns(exprs)


# ---------------------------------------------------------------- role space (1.2)
def fit_role_space(prof: pl.DataFrame):
    stats = _zscore(prof, P.AXES)
    spaces = {}
    for pos in ("F", "D"):
        base = prof.filter((pl.col("pg") == pos) & (pl.col("toi") >= TOI_FLOOR))
        base = _apply_z(base, stats, P.AXES, "", "z_").drop_nulls([f"z_{c}" for c in P.AXES])
        X = base.select([f"z_{c}" for c in P.AXES]).to_numpy()
        pca = PCA(n_components=N_COMP, random_state=SEED).fit(X)
        spaces[pos] = {"pca": pca, "explained": pca.explained_variance_ratio_.tolist(),
                       "loadings": {f"PC{i+1}": dict(zip(P.AXES, [round(float(x), 3) for x in pca.components_[i]]))
                                    for i in range(N_COMP)}}
    return stats, spaces


def _score(prof, stats, spaces, src_suffix, pos):
    """Project (full or half) z-scored profiles through the fitted PCA -> role scores. Returns
    (pid, season_label, team_id, games, PC1..PCk) for the given position."""
    base = prof.filter(pl.col("pg") == pos)
    base = _apply_z(base, stats, P.AXES, src_suffix, "z_")
    zc = [f"z_{c}" for c in P.AXES]
    base = base.drop_nulls(zc)
    X = base.select(zc).to_numpy()
    S = spaces[pos]["pca"].transform(X)
    out = base.select("pid", "season_label", "team_id",
                      pl.col(f"games{src_suffix}").alias("games"))
    return out.with_columns([pl.Series(f"PC{i+1}", S[:, i]) for i in range(N_COMP)])


# ---------------------------------------------------------------- stats helpers
def _corr(x, y):
    if len(x) < 10 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _perm_p(x, y, obs, rng, n=N_PERM):
    # placebo: shuffle identity (y) -> null correlation distribution; p = P(perm >= obs)
    perm = np.array([_corr(x, y[rng.permutation(len(y))]) for _ in range(n)])
    return float((np.sum(perm >= obs) + 1) / (n + 1)), float(np.nanmean(perm))


def _spearman_brown(r):
    return float(2 * r / (1 + r)) if r > -1 else float("nan")


# ---------------------------------------------------------------- 1.3a split-half
def split_half(prof, stats, spaces) -> dict:
    out = {}
    rng = np.random.default_rng(SEED)
    for pos in ("F", "D"):
        odd = _score(prof.filter(pl.col("games") >= MIN_GAMES), stats, spaces, "_odd", pos)
        even = _score(prof.filter(pl.col("games") >= MIN_GAMES), stats, spaces, "_even", pos)
        j = odd.join(even, on=["pid", "season_label"], how="inner", suffix="_e")
        res = {}
        for i in range(N_COMP):
            x = j[f"PC{i+1}"].to_numpy(); y = j[f"PC{i+1}_e"].to_numpy()
            r = _corr(x, y); p, pm = _perm_p(x, y, r, rng)
            res[f"PC{i+1}"] = {"n": j.height, "r": r, "sb": _spearman_brown(r),
                              "placebo_r": pm, "p": p}
        out[pos] = res
    return out


# ---------------------------------------------------------------- 1.3b/c year-over-year
def yoy(prof, stats, spaces) -> dict:
    sidx = {s: i for i, s in enumerate(config.SEASONS_ALL)}
    out = {}
    rng = np.random.default_rng(SEED)
    for pos in ("F", "D"):
        sc = _score(prof.filter(pl.col("toi") >= TOI_FLOOR), stats, spaces, "", pos).with_columns(
            si=pl.col("season_label").replace_strict(sidx, return_dtype=pl.Int32))
        nxt = sc.select("pid", (pl.col("si") - 1).alias("si"), team_next="team_id",
                        *[pl.col(f"PC{i+1}").alias(f"PC{i+1}_n") for i in range(N_COMP)])
        tr = sc.join(nxt, on=["pid", "si"], how="inner").with_columns(
            same_team=(pl.col("team_id") == pl.col("team_next")))
        res = {"n_same": tr.filter(pl.col("same_team")).height,
               "n_diff": tr.filter(~pl.col("same_team")).height, "axes": {}}
        for i in range(N_COMP):
            ax = {}
            for label, sub in (("same_team", tr.filter(pl.col("same_team"))),
                               ("across_team", tr.filter(~pl.col("same_team")))):
                x = sub[f"PC{i+1}"].to_numpy(); y = sub[f"PC{i+1}_n"].to_numpy()
                r = _corr(x, y); p, pm = _perm_p(x, y, r, rng)
                ax[label] = {"n": sub.height, "r": r, "placebo_r": pm, "p": p}
            res["axes"][f"PC{i+1}"] = ax
        out[pos] = res
    return out


# ---------------------------------------------------------------- naming + verdict (1.4)
def name_axes(spaces) -> dict:
    """Name a component where one/two loadings clearly dominate; else leave numbered."""
    names = {}
    for pos in ("F", "D"):
        names[pos] = {}
        for pc, load in spaces[pos]["loadings"].items():
            top = sorted(load.items(), key=lambda kv: -abs(kv[1]))[:3]
            names[pos][pc] = {"top_loadings": top}
    return names


def verdict(split, yy) -> dict:
    """PASS if, for the MAJORITY of components (pooled across positions), split-half >= 0.50 AND
    same-team YoY >= 0.40, each beating placebo at p<0.05."""
    rows = []
    for pos in ("F", "D"):
        for i in range(N_COMP):
            pc = f"PC{i+1}"
            sh = split[pos][pc]
            sy = yy[pos]["axes"][pc]["same_team"]
            passes = (sh["r"] >= SB_SPLIT and sh["p"] < 0.05
                      and sy["r"] >= SB_YOY and sy["p"] < 0.05)
            rows.append({"pos": pos, "pc": pc, "split_r": sh["r"], "split_p": sh["p"],
                         "yoy_same_r": sy["r"], "yoy_same_p": sy["p"], "passes": passes})
    n_pass = sum(r["passes"] for r in rows)
    majority = n_pass > len(rows) / 2
    split_ok = all(split[p][f"PC{i+1}"]["r"] >= 0 for p in ("F", "D") for i in range(N_COMP))  # sanity
    # within-season-only detection: split-half broadly clears but YoY does not
    split_clears = sum(split[p][f"PC{i+1}"]["r"] >= SB_SPLIT and split[p][f"PC{i+1}"]["p"] < 0.05
                       for p in ("F", "D") for i in range(N_COMP))
    yoy_clears = sum(yy[p]["axes"][f"PC{i+1}"]["same_team"]["r"] >= SB_YOY
                     and yy[p]["axes"][f"PC{i+1}"]["same_team"]["p"] < 0.05
                     for p in ("F", "D") for i in range(N_COMP))
    if majority:
        outcome = "PASS"
    elif split_clears > len(rows) / 2 and yoy_clears <= len(rows) / 2:
        outcome = "WITHIN_SEASON_ONLY"
    elif split_clears <= len(rows) / 2:
        outcome = "FAIL_SPLIT_HALF"
    else:
        outcome = "FAIL_MIXED__OWNER_RULES"
    return {"rows": rows, "n_components": len(rows), "n_pass": n_pass, "majority_pass": majority,
            "split_clears": split_clears, "yoy_clears": yoy_clears, "outcome": outcome,
            "bars": {"split_half": SB_SPLIT, "yoy_same_team": SB_YOY}}


def player_vs_team(yy) -> dict:
    """(b)-vs-(c): for each component, same-team vs across-team YoY. A large drop across team change
    means role is partly team-imposed (jointly player-and-team, not pure player)."""
    out = {}
    for pos in ("F", "D"):
        out[pos] = {}
        for pc, ax in yy[pos]["axes"].items():
            s, d = ax["same_team"]["r"], ax["across_team"]["r"]
            out[pos][pc] = {"same_team_r": s, "across_team_r": d, "retained_frac":
                            (float(d / s) if s and s > 0 else None)}
    return out


def run() -> dict:
    prof = _load()
    stats, spaces = fit_role_space(prof)
    split = split_half(prof, stats, spaces)
    yy = yoy(prof, stats, spaces)
    res = {"seed": SEED, "n_components_per_pos": N_COMP, "toi_floor": TOI_FLOOR, "min_games": MIN_GAMES,
           "role_space": {pos: {"explained_variance_ratio": spaces[pos]["explained"],
                                "loadings": spaces[pos]["loadings"]} for pos in ("F", "D")},
           "axis_naming": name_axes(spaces), "split_half": split, "yoy": yy,
           "player_vs_team": player_vs_team(yy)}
    res["verdict"] = verdict(split, yy)
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS / "link1_analysis.json", "w") as f:
        json.dump(res, f, indent=2)
    return res


if __name__ == "__main__":
    r = run()
    v = r["verdict"]
    print("ROLE SPACE explained variance:",
          {p: [round(x, 2) for x in r["role_space"][p]["explained_variance_ratio"]] for p in ("F", "D")})
    for row in v["rows"]:
        print(f"  {row['pos']} {row['pc']}: split r={row['split_r']:.2f}(p={row['split_p']:.3f}) "
              f"yoy_same r={row['yoy_same_r']:.2f}(p={row['yoy_same_p']:.3f}) pass={row['passes']}")
    print("VERDICT:", v["outcome"], f"({v['n_pass']}/{v['n_components']} components pass both bars)")
