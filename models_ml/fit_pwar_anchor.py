"""Anchor box production to real WAR (Handoff 5, Phase B) so realized career value (pWAR) can be
expressed in the SAME WAR units as player_gar — across 2010-2025, even though real WAR only exists
2021-22..2025-26.

On the overlap (single-season GAR windows where both real WAR and box production exist) we fit:

    skater:  war_season ~ f(points_per82, games_played, age, is_forward)
    goalie:  war_season ~ f(games_played, save_pct_vs_league)

Two model families per group: a monotone LightGBM (WAR non-decreasing in production and games) and a
linear baseline. We pick the family with the better season-held-out (leave-one-season-out) R^2, and
prefer the simpler linear model when the two are close. Acceptance gate: pooled Spearman of fitted vs
real WAR on the overlap >= config.DRAFT_VALUE['MIN_SPEARMAN'].

Artifact: models_ml/artifacts/pwar_anchor_v1.joblib (+ _manifest.json). compute_pwar.py loads it and
applies it to every player-season 2010-11..2025-26. This module also exposes load_artifact() and
predict_skater()/predict_goalie() so the apply step reuses the exact fitted objects.

Run:
    python -m models_ml.fit_pwar_anchor --dry-run                 # print pull SQL, exit
    python -m models_ml.fit_pwar_anchor --sample 2024-25          # slice-verify on one season
    python -m models_ml.fit_pwar_anchor                           # full fit -> artifact (READY gate)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from models_ml import bq, config

D = config.DRAFT_VALUE
ARTIFACT_DIR = Path(__file__).parent / "artifacts"
ARTIFACT = ARTIFACT_DIR / f"{D['ANCHOR_VERSION']}.joblib"
MANIFEST = ARTIFACT_DIR / f"{D['ANCHOR_VERSION']}_manifest.json"

# Long-history skater signals only — every feature is populated back to 2010-11 (ixG/xGF% 100%,
# TOI ~94%, points/GP from boxscores), so the anchor can be applied to the full back-cast window.
SKATER_FEATURES = ["points_per82", "ixg_per82", "toi5v5_per_gp", "on_ice_xgf_pct",
                   "games_played", "age", "is_forward"]
SKATER_MONO = [1, 1, 1, 1, 1, 0, 0]   # WAR up in production, chances, ice time, play-driving & games
GOALIE_FEATURES = ["games_played", "save_pct_vs_league"]
GOALIE_MONO = [1, 1]


# --------------------------------------------------------------------------- data pulls
def _season_end_year(season: str) -> int:
    return int(season[:4]) + 1


def _nhl_game_filter() -> str:
    types = ", ".join(f"'{t}'" for t in D["NHL_GAME_TYPES"])
    return f"substr(cast(game_id as string), 5, 2) in ({types})"


def skater_pull_sql(seasons: list[str]) -> str:
    seasons_sql = ", ".join(f"'{s}'" for s in seasons)
    P = bq.project()
    return f"""
    with prod as (
        select player_id, season,
               count(distinct game_id) as games_played,
               sum(individual_goals + first_assists + second_assists) as points,
               sum(ixg) as ixg,
               sum(toi_5v5) as toi_5v5_total,
               -- TOI-weighted season on-ice xGF% (per-game value -> season mean)
               safe_divide(sum(on_ice_xgf_pct * toi_5v5), nullif(sum(toi_5v5), 0)) as on_ice_xgf_pct
        from `{P}.nhl_mart.mart_player_game_stats`
        where {_nhl_game_filter()}
        group by 1, 2
    )
    select g.player_id, g.season_window as season, g.position, g.war,
           p.games_played, p.points, p.ixg, p.toi_5v5_total, p.on_ice_xgf_pct,
           b.birth_date
    from `{P}.nhl_models.player_gar` g
    join prod p on p.player_id = g.player_id and p.season = g.season_window
    left join `{P}.nhl_staging.stg_player_bio` b on b.player_id = g.player_id
    where g.season_window in ({seasons_sql})
    """


def goalie_pull_sql(seasons: list[str]) -> str:
    seasons_sql = ", ".join(f"'{s}'" for s in seasons)
    P = bq.project()
    return f"""
    select g.goalie_id, g.season_window as season, g.war,
           s.games_played, s.shots_faced, s.save_pct
    from `{P}.nhl_models.goalie_gar` g
    join `{P}.nhl_mart.mart_goalie_season` s
      on s.goalie_id = g.goalie_id and s.season = g.season_window
    where g.season_window in ({seasons_sql}) and s.shots_faced > 0
    """


def _prep_skaters(df: pd.DataFrame) -> pd.DataFrame:
    """Build the skater feature frame. Shared by the anchor fit (has the `war` target) and the apply
    step (no target) — `war` is handled only when present."""
    df = df.copy()
    num = ["games_played", "points", "ixg", "toi_5v5_total", "on_ice_xgf_pct"]
    for c in (num + (["war"] if "war" in df.columns else [])):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    gp = df["games_played"].clip(lower=1)
    df["points_per82"] = df["points"] / gp * D["GAMES_FULL_82"]
    df["ixg_per82"] = df["ixg"].fillna(0) / gp * D["GAMES_FULL_82"]
    df["toi5v5_per_gp"] = (df["toi_5v5_total"].fillna(0) / gp)
    df["on_ice_xgf_pct"] = df["on_ice_xgf_pct"].fillna(df["on_ice_xgf_pct"].median())
    df["is_forward"] = (df["position"].str.upper() != "D").astype(int)
    end_year = df["season"].map(_season_end_year)
    bd = pd.to_datetime(df["birth_date"], errors="coerce")
    ref = pd.to_datetime(dict(year=end_year, month=2, day=1))
    df["age"] = (ref - bd).dt.days / 365.25
    df["age"] = df["age"].fillna(df["age"].median())
    df[SKATER_FEATURES] = df[SKATER_FEATURES].astype(float)
    subset = ["games_played", "points_per82"]
    if "war" in df.columns:
        df["war"] = df["war"].astype(float)
        subset = ["war"] + subset
    return df.dropna(subset=subset)


def _prep_goalies(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in (["games_played", "shots_faced", "save_pct"] + (["war"] if "war" in df.columns else [])):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # shots-weighted league save% per season -> save_pct vs league
    lg = (df.groupby("season")
            .apply(lambda x: np.average(x["save_pct"], weights=x["shots_faced"]))
            .rename("lg_save_pct").reset_index())
    df = df.merge(lg, on="season", how="left")
    df["save_pct_vs_league"] = df["save_pct"] - df["lg_save_pct"]
    df[GOALIE_FEATURES] = df[GOALIE_FEATURES].astype(float)
    subset = ["games_played", "save_pct_vs_league"]
    if "war" in df.columns:
        df["war"] = df["war"].astype(float)
        subset = ["war"] + subset
    return df.dropna(subset=subset)


# --------------------------------------------------------------------------- model fitting
def _fit_lgb(X: pd.DataFrame, y, w, mono: list[int]):
    params = {**D["LGB_PARAMS"], "monotone_constraints": mono}
    dset = lgb.Dataset(X, label=y, weight=w, free_raw_data=False)
    return lgb.train(params, dset, num_boost_round=D["LGB_NUM_ROUNDS"])


def _fit_linear(X: pd.DataFrame, y, w):
    m = LinearRegression()
    m.fit(X, y, sample_weight=w)
    return m


def _loso(df: pd.DataFrame, feats: list[str], mono: list[int]) -> dict:
    """Leave-one-season-out: pooled OOS R^2 and Spearman for both families."""
    seasons = sorted(df["season"].unique())
    if len(seasons) < 2:
        return {}
    oos = {"lgb": [], "lin": []}
    truth = []
    for s in seasons:
        tr, te = df[df.season != s], df[df.season == s]
        Xtr, Xte = tr[feats], te[feats]
        ytr, yte = tr["war"].values, te["war"].values
        wtr = tr["games_played"].values
        lgbm = _fit_lgb(Xtr, ytr, wtr, mono)
        lin = _fit_linear(Xtr, ytr, wtr)
        oos["lgb"].append(pd.Series(lgbm.predict(Xte), index=te.index))
        oos["lin"].append(pd.Series(lin.predict(Xte), index=te.index))
        truth.append(pd.Series(yte, index=te.index))
    y = pd.concat(truth)
    out = {}
    for k in ("lgb", "lin"):
        p = pd.concat(oos[k]).reindex(y.index)
        out[k] = {"r2": float(r2_score(y, p)), "spearman": float(spearmanr(p, y).statistic)}
    return out


def _choose(loso: dict) -> str:
    """Pick the better OOS R^2; prefer the simpler linear model when within 0.01 R^2."""
    if not loso:
        return "lgb"
    if loso["lin"]["r2"] >= loso["lgb"]["r2"] - 0.01:
        return "lin"
    return "lgb"


def _fit_group(df: pd.DataFrame, feats: list[str], mono: list[int], sample_one: bool) -> dict:
    loso = {} if sample_one else _loso(df, feats, mono)
    choice = _choose(loso)
    X, y, w = df[feats], df["war"].values, df["games_played"].values
    lgbm = _fit_lgb(X, y, w, mono)
    lin = _fit_linear(X, y, w)
    # in-sample fitted (for the gate Spearman + report); OOS is the honest metric when available
    fit_pred = (lgbm.predict(X) if choice == "lgb" else lin.predict(X))
    resid_sd = float(np.std(y - fit_pred, ddof=1))   # band width for pwar_hat (inflated for back-cast)
    return {
        "choice": choice, "features": feats, "monotone": mono,
        "lgb": lgbm, "lin": lin, "loso": loso, "resid_sd": resid_sd,
        "in_sample": {"r2": float(r2_score(y, fit_pred)),
                      "spearman": float(spearmanr(fit_pred, y).statistic)},
        "n": int(len(df)),
    }


# --------------------------------------------------------------------------- apply (reused by compute_pwar)
def load_artifact() -> dict:
    return joblib.load(ARTIFACT)


def _predict(group: dict, X: pd.DataFrame) -> np.ndarray:
    m = group["lgb"] if group["choice"] == "lgb" else group["lin"]
    return np.asarray(m.predict(X[group["features"]]))


def predict_skater(art: dict, X: pd.DataFrame) -> np.ndarray:
    return _predict(art["skater"], X)


def predict_goalie(art: dict, X: pd.DataFrame) -> np.ndarray:
    return _predict(art["goalie"], X)


# --------------------------------------------------------------------------- report
def _report(skater: dict, goalie: dict, sk_df: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print("pWAR ANCHOR — fit report")
    print("=" * 78)
    for name, g in [("SKATER", skater), ("GOALIE", goalie)]:
        print(f"\n[{name}] n={g['n']}  chosen={g['choice']}")
        if g["loso"]:
            for k in ("lgb", "lin"):
                m = g["loso"][k]
                star = " <-" if k[:3] == g["choice"][:3] else ""
                print(f"  LOSO {k}: R2={m['r2']:.3f}  Spearman={m['spearman']:.3f}{star}")
        print(f"  in-sample: R2={g['in_sample']['r2']:.3f}  Spearman={g['in_sample']['spearman']:.3f}")
        sp = g["loso"][g["choice"]]["spearman"] if g["loso"] else g["in_sample"]["spearman"]
        kind = "LOSO" if g["loso"] else "in-sample"
        print(f"  Spearman gate ({D['MIN_SPEARMAN']}, {kind}): "
              f"{'PASS' if sp >= D['MIN_SPEARMAN'] else 'FAIL'} ({sp:.3f})")
    # smell test: fitted top/bottom skaters
    art = {"skater": skater}
    sk_df = sk_df.copy()
    sk_df["fit_war"] = predict_skater(art, sk_df)
    print("\n  Top fitted skater-seasons:")
    for _, r in sk_df.sort_values("fit_war", ascending=False).head(6).iterrows():
        print(f"    {int(r.player_id)} {r.season} {r.position}: fit={r.fit_war:5.1f} real={r.war:5.1f} "
              f"pts/82={r.points_per82:4.0f} gp={int(r.games_played)}")


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print pull SQL and exit")
    ap.add_argument("--sample", default=None, help="restrict to one season (slice-verify), e.g. 2024-25")
    args = ap.parse_args()

    seasons = [args.sample] if args.sample else D["ANCHOR_SEASONS"]
    if args.dry_run:
        print(skater_pull_sql(seasons))
        print("\n-- goalie --\n")
        print(goalie_pull_sql(seasons))
        return

    print(f"Anchoring on seasons: {seasons}")
    sk = _prep_skaters(bq.query_df(skater_pull_sql(seasons)))
    go = _prep_goalies(bq.query_df(goalie_pull_sql(seasons)))
    print(f"overlap rows: skaters={len(sk)} goalies={len(go)}")

    sample_one = args.sample is not None
    skater = _fit_group(sk, SKATER_FEATURES, SKATER_MONO, sample_one)
    goalie = _fit_group(go, GOALIE_FEATURES, GOALIE_MONO, sample_one)
    _report(skater, goalie, sk)

    if sample_one:
        print("\n[--sample] slice-verify only; artifact NOT written (run without --sample for the full fit).")
        return

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {"version": D["ANCHOR_VERSION"], "skater": skater, "goalie": goalie,
                "anchor_seasons": seasons, "seed": D["RANDOM_SEED"],
                "built_at": _dt.datetime.utcnow().isoformat()}
    joblib.dump(artifact, ARTIFACT)
    h = hashlib.md5(ARTIFACT.read_bytes()).hexdigest()[:12]

    manifest = {
        "model_version": D["ANCHOR_VERSION"],
        "artifact_md5": h,
        "anchor_seasons": seasons,
        "skater": {"choice": skater["choice"], "n": skater["n"], "features": SKATER_FEATURES,
                   "loso": skater["loso"], "in_sample": skater["in_sample"]},
        "goalie": {"choice": goalie["choice"], "n": goalie["n"], "features": GOALIE_FEATURES,
                   "loso": goalie["loso"], "in_sample": goalie["in_sample"]},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"\nSaved {ARTIFACT.name} (md5 {h}) + manifest.")


if __name__ == "__main__":
    main()
