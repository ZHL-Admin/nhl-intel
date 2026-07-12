"""Phase 4.1 — portability score + predicted-delta-by-destination.

Built on Design B (Phase 3.3). Per the Phase 3 gate ruling: the deployment-system terms are the
validated system signal; **zone_start_polarization is the PRIMARY portability axis** and
top6_fwd_toi_share carries its stability caveat everywhere (recommendation 3, adopted).

Decomposition of a player-season's modeled on-ice 5v5 xG share:
  offset (frozen RAPM quality)  -> SKILL value, portable by construction (travels with the player)
  deployment-system  + type x deployment  -> SYSTEM-DEPENDENT value (does NOT travel; it is a
                                            property of the current team's deployment fingerprint)
  style / schedule / season      -> context, not part of the portability split

  system_dependence = |sys| / (|sys| + |skill_dev|)   in [0,1]
  portability       = 1 - system_dependence           (high = value travels)

Uncertainty: the frozen offset (skill) is fixed by declaration; system value flows through the
shrunk, small deployment coefficients, so ALL the uncertainty is there. We grouped-bootstrap the
team-seasons (B, seed=config.SEED), refit the ridge, and recompute each player's sys contribution
and portability -> percentile CIs.

Predicted-delta-by-destination: for a (player, destination team-season) pair, the expected on-ice
xG-share shift from the destination's deployment fingerprint under the player's type
(role held at the player's type), with a bootstrap CI. Read WITH the F14 thin-mediation caveat.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from sklearn.linear_model import Ridge

from . import config, design_b as DB, team_season as TS

DEPLOY = TS.DEPLOY_AXES               # ["top6_fwd_toi_share", "zone_start_polarization"]
PRIMARY_AXIS = "zone_start_polarization"
ALPHA = 300.0
N_BOOT = 300
PORT_PARQUET = config.PARQUET / "portability.parquet"

# Materiality rule (amendment 4.1a). The "system-dependent" label attaches only where the
# absolute system contribution is both SIGNED (sys 90% CI excludes zero) and MATERIAL
# (|sys| >= 0.004 xG-share pts). 0.004 is p79 of |sys| in the 2024-25 700+-min exhibit pool
# (~the p80 the ruling cites) and p68 in the full multi-season table.
MATERIALITY_MIN = 0.004

# F14 — thin-mediation finding, quoted VERBATIM wherever portability is exposed.
F14_CAVEAT = (
    "F14 (thin mediation): a coach change's on-ice result effect is small (+0.004 score-close "
    "on-ice xG-share DiD, t=1.73) and only ~4% of the within-player result change is mediated by "
    "the measured deployment change (mediation R^2=0.04). Portability quantifies the "
    "deployment-system share of a player's CURRENT number; it is not a guarantee of result change "
    "on a move.")


def _fit():
    d = DB.player_season_table()
    q = d["q"].to_numpy(); y = d["xg_share"].to_numpy()
    A = np.column_stack([np.ones(len(q)), q]); coef_off, *_ = np.linalg.lstsq(A, y, rcond=None)
    offset = A @ coef_off
    resid = y - offset
    X, cols = DB._design_matrix(d)
    groups = np.array([f"{r['season_label']}|{r['team_id']}"
                       for r in d.select("season_label", "team_id").to_dicts()])
    m = Ridge(alpha=ALPHA).fit(X, resid)
    # DEPLOY standardization (per-column, as _design_matrix does)
    dep_raw = d.select(DEPLOY).to_numpy().astype(float)
    dep_mean, dep_std = dep_raw.mean(0), dep_raw.std(0) + 1e-9
    return d, X, cols, resid, groups, m, offset, dep_mean, dep_std


def _sys_contrib(coef_map, type_id, dep_z):
    """System-dependent contribution (xG-share pts) for a player of `type_id` at standardized
    deployment `dep_z` (len 2): sum over axes of (main + type-interaction) coef * z."""
    s = 0.0
    for j, ax in enumerate(DEPLOY):
        c = coef_map.get(ax, 0.0) + coef_map.get(f"{type_id}:x:{ax}", 0.0)
        s += c * dep_z[j]
    return s


def build(write: bool = True) -> pl.DataFrame:
    d, X, cols, resid, groups, m, offset, dep_mean, dep_std = _fit()
    coef_map = dict(zip(cols, m.coef_))
    dep_raw = d.select(DEPLOY).to_numpy().astype(float)
    dep_z = (dep_raw - dep_mean) / dep_std
    types = d["type_id"].to_list()
    skill_dev = offset - offset.mean()

    sys = np.array([_sys_contrib(coef_map, types[i], dep_z[i]) for i in range(len(types))])

    # grouped bootstrap for CI on sys (skill fixed; only coef varies)
    rng = np.random.default_rng(config.SEED)
    uniq = np.unique(groups)
    g_idx = {g: np.where(groups == g)[0] for g in uniq}
    boot_sys = np.zeros((N_BOOT, len(sys)))
    keep = DEPLOY + [c for c in cols if ":x:" in c and c.split(":x:")[1] in DEPLOY]
    boot_coefs = []
    for b in range(N_BOOT):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        rows = np.concatenate([g_idx[g] for g in pick])
        mb = Ridge(alpha=ALPHA).fit(X[rows], resid[rows])
        cmb = dict(zip(cols, mb.coef_))
        boot_sys[b] = [_sys_contrib(cmb, types[i], dep_z[i]) for i in range(len(types))]
        boot_coefs.append({k: float(cmb.get(k, 0.0)) for k in keep})
    sys_lo, sys_hi = np.percentile(boot_sys, [5, 95], axis=0)

    denom = np.abs(sys) + np.abs(skill_dev) + 1e-12
    system_dependence = np.abs(sys) / denom
    # CI on system_dependence via bootstrap sys (skill fixed)
    sd_boot = np.abs(boot_sys) / (np.abs(boot_sys) + np.abs(skill_dev)[None, :] + 1e-12)
    sd_lo, sd_hi = np.percentile(sd_boot, [5, 95], axis=0)

    out = d.select("player_id", "season_label", "team_id", "type_id", "toi_min", "q", "xg_share").with_columns(
        skill_dev=pl.Series(skill_dev),
        sys_contrib=pl.Series(sys), sys_ci_lo=pl.Series(sys_lo), sys_ci_hi=pl.Series(sys_hi),
        system_dependence=pl.Series(system_dependence),
        system_dependence_ci_lo=pl.Series(sd_lo), system_dependence_ci_hi=pl.Series(sd_hi),
        portability=pl.Series(1 - system_dependence),
        primary_axis_z=pl.Series(dep_z[:, DEPLOY.index(PRIMARY_AXIS)]),
    ).with_columns(
        abs_sys=pl.col("sys_contrib").abs(),
        sys_ci_excludes_zero=(pl.col("sys_ci_lo") > 0) | (pl.col("sys_ci_hi") < 0),
    ).with_columns(
        # materiality label (amendment 4.1a): signed AND material magnitude
        material=pl.col("sys_ci_excludes_zero") & (pl.col("abs_sys") >= MATERIALITY_MIN),
    )
    if write:
        out.write_parquet(PORT_PARQUET)
        # persist the coefficient map + standardization for the API's destination-delta accessor
        import json
        (config.PARQUET / "portability_model.json").write_text(json.dumps(
            {"coef": {k: float(v) for k, v in coef_map.items()},
             "dep_mean": dep_mean.tolist(), "dep_std": dep_std.tolist(),
             "deploy_axes": DEPLOY, "alpha": ALPHA, "boot_coef": boot_coefs}, indent=2))
    return out


# ---------------------------------------------------------------- destination delta
def _model_json():
    import json
    return json.loads((config.PARQUET / "portability_model.json").read_text())


def predicted_delta(player_id: int, season: str, dest_team_id: int, dest_season: str) -> dict:
    """Expected on-ice 5v5 xG-share shift for `player_id` (their `season` type) moving into the
    destination team-season's deployment fingerprint, role held at the player's type. Bootstrap
    CI. Reads WITH F14."""
    port = pl.read_parquet(PORT_PARQUET)
    row = port.filter((pl.col("player_id") == player_id) & (pl.col("season_label") == season))
    if row.height == 0:
        return {"error": f"no portability row for player {player_id} in {season}"}
    r = row.to_dicts()[0]
    fp = pl.read_parquet(TS.FP_PARQUET)
    cur = fp.filter((pl.col("team_id") == r["team_id"]) & (pl.col("season_label") == season))
    dst = fp.filter((pl.col("team_id") == dest_team_id) & (pl.col("season_label") == dest_season))
    if cur.height == 0 or dst.height == 0:
        return {"error": "missing team-season fingerprint"}
    mj = _model_json()
    mean, std = np.array(mj["dep_mean"]), np.array(mj["dep_std"])
    def z(tsrow):
        return (np.array([tsrow[a][0] for a in DEPLOY]) - mean) / std
    zc, zd = z(cur), z(dst)
    coef = mj["coef"]; t = r["type_id"]
    delta = _sys_contrib(coef, t, zd) - _sys_contrib(coef, t, zc)
    # bootstrap CI from the stored grouped-bootstrap coefficient draws (same linear form)
    boot = [_sys_contrib(bc, t, zd) - _sys_contrib(bc, t, zc) for bc in mj.get("boot_coef", [])]
    ci = [round(float(np.percentile(boot, 5)), 5), round(float(np.percentile(boot, 95)), 5)] if boot else None
    return {
        "player_id": player_id, "season": season, "type_id": t,
        "from_team": r["team_id"], "to_team": dest_team_id, "to_season": dest_season,
        "predicted_xg_share_delta": round(float(delta), 5), "ci90": ci,
        "primary_axis_shift_z": round(float((zd - zc)[DEPLOY.index(PRIMARY_AXIS)]), 3),
        "caveat": F14_CAVEAT,
    }


# ---------------------------------------------------------------- face-validity exhibit
def exhibit(season="2024-25", min_toi=700.0, n=15) -> dict:
    """Amendment 4.1a: primary ordering is the ABSOLUTE system contribution |sys| (xG-share pts,
    with CI) among players whose sys CI excludes zero; system_dependence shown as a SECONDARY
    column. The ratio is a denominator artifact for near-average-skill players, so it does not
    drive the ranking."""
    port = pl.read_parquet(PORT_PARQUET).filter(
        (pl.col("season_label") == season) & (pl.col("toi_min") >= min_toi))
    names = _names()
    from .opponent import TEAM_ABBR
    def fmt(r):
        return {"player": names.get(r["player_id"], str(r["player_id"])),
                "team": TEAM_ABBR.get(r["team_id"], str(r["team_id"])), "type": r["type_id"],
                "sys_contrib": round(r["sys_contrib"], 4),
                "sys_ci": [round(r["sys_ci_lo"], 4), round(r["sys_ci_hi"], 4)],
                "material": bool(r["material"]),
                "system_dependence": round(r["system_dependence"], 3)}  # secondary
    signed = port.filter(pl.col("sys_ci_excludes_zero"))
    dep = signed.sort("abs_sys", descending=True).head(n).to_dicts()
    ind = port.sort("abs_sys").head(n).to_dicts()   # smallest |sys| = most portable
    return {"season": season, "min_toi_min": min_toi, "n_pool": port.height,
            "materiality_rule": f"labelled system-dependent iff sys CI excludes 0 AND |sys| >= {MATERIALITY_MIN}",
            "n_signed": signed.height, "n_material": int(port["material"].sum()),
            "ranked_by": "absolute system contribution |sys| (xG-share pts)",
            "most_system_dependent": [fmt(r) for r in dep],
            "most_system_independent": [fmt(r) for r in ind]}


def _names() -> dict:
    p = config.CACHE / "warehouse" / "player_names.csv"
    if not p.exists():
        return {}
    df = pl.read_csv(p)
    return {r["player_id"]: f"{r['first_name']} {r['last_name']}" for r in df.to_dicts()}


if __name__ == "__main__":
    import json
    build()
    print(json.dumps(exhibit(), indent=2, default=str))
