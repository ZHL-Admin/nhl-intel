"""Phase 3.3 — INTERNAL track, Design B (joint model on player-seasons).

Outcome: season 5v5 ON-ICE xG share, computed per (player, season, TEAM) from
player_season_team_onice so each system exposure is its own row (a traded player contributes
two rows — extra leverage for separating player quality from team system).

Terms:
  own variant RAPM         -> OFFSET, not refit. A one-time frozen calibration maps the
                             player's RAPM quality q=off+def into xg-share units; entered as
                             an offset (coefficient fixed at 1). No per-player effect is
                             estimated, so the system terms cannot absorb player identity.
  own-team DEPLOYMENT (2)  -> the SYSTEM term (validated coaching-sensitive axes, Phase 2).
  own-team STYLE (8)       -> included but DESCRIPTIVE-CONTEXT (Phase 2 §4 caveat).
  opponent-schedule STYLE  -> the opponent track's covariates as controls (provenance does
                             not matter across the matchup boundary).
  type x deployment        -> PRIMARY interactions.
  type x style             -> SECONDARY, caveated.
  season effects.

Estimator: Ridge (L2 = hierarchical shrinkage on all system + interaction terms), alpha by
GroupKFold CV GROUPED ON team-season so no team-season leaks across folds. Player quality is
held out of the shrinkage via the frozen offset.

Identifiability note: player and system separate through player MOVEMENT and coach changes;
we report how many players anchor each system estimate (movers, roster sizes).
"""
from __future__ import annotations

import numpy as np
import polars as pl
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

from . import config, team_season as TS

DEPLOY = TS.DEPLOY_AXES
STYLE = TS.STYLE_AXES
SCHED = [f"sched_{a}" for a in STYLE]
MIN_MIN = 200.0


def player_season_table(seasons=None) -> pl.DataFrame:
    seasons = seasons or config.SEASONS_ALL
    onice = pl.read_parquet(config.ATLAS_PARQUET / "player_season_team_onice.parquet").filter(
        pl.col("season_label").is_in(seasons))
    onice = onice.with_columns(
        toi_min=pl.col("toi_s") / 60.0,
        xg_share=pl.when(pl.col("xgf") + pl.col("xga") > 0)
        .then(pl.col("xgf") / (pl.col("xgf") + pl.col("xga"))).otherwise(None),
    ).filter((pl.col("toi_min") >= MIN_MIN) & pl.col("xg_share").is_not_null())
    rapm = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet").select(
        "player_id", pl.col("season").alias("season_label"),
        q=pl.col("off_impact") + pl.col("def_impact"))
    types = pl.read_parquet(config.PARQUET / "player_types.parquet").select(
        "player_id", "season_label", "type_id")
    fp = pl.read_parquet(TS.FP_PARQUET)
    sched = TS.schedule_avg_style(seasons)
    d = (onice.join(rapm, on=["player_id", "season_label"], how="left")
         .join(types, on=["player_id", "season_label"], how="left")
         .join(fp.select("season_label", "team_id", *TS.ALL_AXES), on=["season_label", "team_id"], how="left")
         .join(sched, on=["season_label", "team_id"], how="left"))
    return d.drop_nulls(["q", "type_id", *DEPLOY, *STYLE, *SCHED])


def _design_matrix(d: pl.DataFrame):
    types = sorted(d["type_id"].unique().to_list())
    seasons = sorted(d["season_label"].unique().to_list())
    cont = DEPLOY + STYLE + SCHED
    Xc = d.select(cont).to_numpy().astype(float)
    Xc = (Xc - Xc.mean(0)) / (Xc.std(0) + 1e-9)
    cols = list(cont)
    blocks = [Xc]
    # type dummies (drop first)
    tid = d["type_id"].to_list()
    for t in types[1:]:
        blocks.append(np.array([[1.0 if x == t else 0.0] for x in tid])); cols.append(f"type={t}")
    # type x deployment (primary) and type x style (secondary)
    dep_idx = [cont.index(a) for a in DEPLOY]
    sty_idx = [cont.index(a) for a in STYLE]
    for t in types:
        tmask = np.array([1.0 if x == t else 0.0 for x in tid])
        for a in DEPLOY:
            blocks.append((tmask * Xc[:, cont.index(a)])[:, None]); cols.append(f"{t}:x:{a}")
        for a in STYLE:
            blocks.append((tmask * Xc[:, cont.index(a)])[:, None]); cols.append(f"{t}:x:{a}")
    # season dummies (drop first)
    sl = d["season_label"].to_list()
    for s in seasons[1:]:
        blocks.append(np.array([[1.0 if x == s else 0.0] for x in sl])); cols.append(f"season={s}")
    X = np.hstack(blocks)
    return X, cols


def run(seasons=None) -> dict:
    seasons = seasons or config.SEASONS_ALL
    d = player_season_table(seasons)
    # frozen offset: one-time OLS of xg_share on quality q; freeze -> offset, model residual
    q = d["q"].to_numpy(); y = d["xg_share"].to_numpy()
    A = np.column_stack([np.ones(len(q)), q])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    offset = A @ coef
    resid = y - offset
    X, cols = _design_matrix(d)
    groups = np.array([f"{r['season_label']}|{r['team_id']}" for r in d.select("season_label", "team_id").to_dicts()])

    # alpha by grouped CV
    gkf = GroupKFold(n_splits=5)
    alphas = [10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0]
    best = None
    for al in alphas:
        r2s = []
        for tr, te in gkf.split(X, resid, groups):
            m = Ridge(alpha=al).fit(X[tr], resid[tr])
            pred = m.predict(X[te])
            ss_res = ((resid[te] - pred) ** 2).sum(); ss_tot = ((resid[te] - resid[te].mean()) ** 2).sum()
            r2s.append(1 - ss_res / ss_tot)
        cv = float(np.mean(r2s))
        if best is None or cv > best[0]:
            best = (cv, al, r2s)
    cv_r2, alpha, foldr2 = best

    # baseline: offset-only CV R^2 on xg_share (how much quality alone explains)
    ss_res0 = ((y - offset) ** 2).sum(); ss_tot0 = ((y - y.mean()) ** 2).sum()
    offset_r2 = 1 - ss_res0 / ss_tot0

    final = Ridge(alpha=alpha).fit(X, resid)
    coefs = dict(zip(cols, final.coef_))
    dep_coefs = {c: round(float(v), 5) for c, v in coefs.items() if c in DEPLOY}
    inter_primary = {c: round(float(v), 5) for c, v in coefs.items() if ":x:" in c and c.split(":x:")[1] in DEPLOY}
    # rank interactions by |coef|
    top_inter = sorted(inter_primary.items(), key=lambda kv: -abs(kv[1]))[:12]

    out = {
        "n_rows": d.height, "n_players": d["player_id"].n_unique(),
        "n_team_seasons": d.select("season_label", "team_id").unique().height,
        "offset": {"intercept": round(float(coef[0]), 5), "q_slope": round(float(coef[1]), 5),
                   "offset_only_r2_on_xgshare": round(float(offset_r2), 4),
                   "note": "frozen calibration; player RAPM enters as offset (coef=1), not refit"},
        "estimator": f"Ridge(alpha={alpha}), GroupKFold(5) grouped on team-season",
        "cv_r2_residual": round(float(cv_r2), 4), "cv_fold_r2": [round(x, 4) for x in foldr2],
        "deployment_system_coefs": dep_coefs,
        "top_type_x_deployment_interactions": {k: v for k, v in top_inter},
        "anchoring": _anchoring(seasons),
    }
    (config.REPORTS / "phase3_designB.json").write_text(__import__("json").dumps(out, indent=2, default=str))
    return out


def _anchoring(seasons):
    """How many players anchor each system estimate: movers (players in >=2 distinct
    team-seasons) enable separating player quality from team system; roster sizes give the
    per-system player count."""
    onice = pl.read_parquet(config.ATLAS_PARQUET / "player_season_team_onice.parquet").filter(
        pl.col("season_label").is_in(seasons)).with_columns(toi_min=pl.col("toi_s") / 60.0
        ).filter(pl.col("toi_min") >= MIN_MIN)
    per_player_teams = onice.group_by("player_id").agg(
        n_team_seasons=pl.struct("season_label", "team_id").n_unique(),
        n_distinct_teams=pl.col("team_id").n_unique())
    movers = per_player_teams.filter(pl.col("n_distinct_teams") >= 2)
    roster = onice.group_by("season_label", "team_id").agg(n_players=pl.col("player_id").n_unique())
    # anchoring per team-season: how many of its players also appear in another team-season
    mv_ids = set(movers["player_id"].to_list())
    onice2 = onice.with_columns(is_mover=pl.col("player_id").is_in(list(mv_ids)))
    anchors = onice2.group_by("season_label", "team_id").agg(
        n_players=pl.col("player_id").n_unique(),
        n_mover_anchors=pl.col("player_id").filter(pl.col("is_mover")).n_unique())
    return {
        "n_players_total": per_player_teams.height,
        "n_movers_ge2_teams": movers.height,
        "pct_movers": round(100 * movers.height / per_player_teams.height, 1),
        "median_roster_per_team_season": int(roster["n_players"].median()),
        "median_mover_anchors_per_team_season": int(anchors["n_mover_anchors"].median()),
        "min_mover_anchors_per_team_season": int(anchors["n_mover_anchors"].min()),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2, default=str))
