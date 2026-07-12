"""Phase 3.4 — OPPONENT track: style matchups + schedule bias.

Game-level model of 5v5 xG share between teams A and B as a function of both teams' STRENGTH
(roster variant-RAPM aggregates) plus STYLE-INTERACTION terms (A's attack profile vs B's
defensive profile, from Phase 2 metrics). Fit on 2010-11 … 2023-24 regular-season team-games;
2024-25 held out for the schedule-bias exhibit.

DELTA vs production models_ml/train_style_effect.py (audited Phase 3.4): that model predicts
playoff SERIES win probability (logistic, ~16 series/season, end-of-RS rating + same-season
fingerprint, shrink-to-validate). THIS is a different object entirely: continuous per-GAME 5v5
xG share over the full regular season, yielding (a) per-matchup style-interaction effects and
(b) a per-PLAYER schedule-bias correction — neither of which production produces. No overlap,
no duplication.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from sklearn.linear_model import Ridge

from . import config, context as C, team_season as TS

# Canonical NHL API team-id -> abbreviation (stable reference constants, not derived data;
# for exhibit readability only).
TEAM_ABBR = {1: "NJD", 2: "NYI", 3: "NYR", 4: "PHI", 5: "PIT", 6: "BOS", 7: "BUF", 8: "MTL",
             9: "OTT", 10: "TOR", 12: "CAR", 13: "FLA", 14: "TBL", 15: "WSH", 16: "CHI",
             17: "DET", 18: "NSH", 19: "STL", 20: "CGY", 21: "COL", 22: "EDM", 23: "VAN",
             24: "ANA", 25: "DAL", 26: "LAK", 28: "SJS", 29: "CBJ", 30: "MIN", 52: "WPG",
             53: "ARI", 54: "VGK", 55: "SEA", 59: "UTA"}

ATTACK = ["pace", "rush_share_for", "cycle_share_for", "point_shot_share_for"]
DEFENSE = ["loc_inner_against", "loc_outer_against", "loc_point_against"]
FIT_SEASONS = [f"{y}-{str(y+1)[2:]}" for y in range(2010, 2024)]   # 2010-11 … 2023-24
HOLDOUT = "2024-25"


def team_strength(seasons=None) -> pl.DataFrame:
    """TOI-weighted roster variant-RAPM per team-season: strength_off, strength_def."""
    seasons = seasons or config.SEASONS_ALL
    onice = pl.read_parquet(config.ATLAS_PARQUET / "player_season_team_onice.parquet").filter(
        pl.col("season_label").is_in(seasons))
    rapm = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet").select(
        "player_id", pl.col("season").alias("season_label"), "off_impact", "def_impact")
    j = onice.join(rapm, on=["player_id", "season_label"], how="inner")
    return j.group_by("season_label", "team_id").agg(
        strength_off=(pl.col("off_impact") * pl.col("toi_s")).sum() / pl.col("toi_s").sum(),
        strength_def=(pl.col("def_impact") * pl.col("toi_s")).sum() / pl.col("toi_s").sum())


def _team_game_xg(seasons):
    return pl.concat([C.build_team_game_xg(s) for s in seasons])


def _assemble(seasons):
    fp = pl.read_parquet(TS.FP_PARQUET)
    strn = team_strength(seasons)
    tg = _team_game_xg(seasons).with_columns(
        xg_share=pl.when(pl.col("xgf_close") + pl.col("xga_close") > 0)
        .then(pl.col("xgf_close") / (pl.col("xgf_close") + pl.col("xga_close"))).otherwise(None)
    ).filter(pl.col("xg_share").is_not_null())
    own = fp.select("season_label", "team_id", *ATTACK).join(strn, on=["season_label", "team_id"])
    opp = fp.select("season_label", pl.col("team_id").alias("opp_id"), *DEFENSE).join(
        strn.select("season_label", pl.col("team_id").alias("opp_id"),
                    pl.col("strength_off").alias("opp_strength_off"),
                    pl.col("strength_def").alias("opp_strength_def")),
        on=["season_label", "opp_id"])
    d = tg.join(own, on=["season_label", "team_id"], how="inner").join(
        opp, on=["season_label", "opp_id"], how="inner")
    return d.drop_nulls(["strength_off", "strength_def", "opp_strength_off", "opp_strength_def",
                         *ATTACK, *DEFENSE])


def _features(d, means=None, stds=None):
    strength = ["strength_off", "strength_def", "opp_strength_off", "opp_strength_def"]
    style = ATTACK + DEFENSE
    base = strength + style
    Xb = d.select(base).to_numpy().astype(float)
    if means is None:
        means, stds = Xb.mean(0), Xb.std(0) + 1e-9
    Xs = (Xb - means) / stds
    cols = list(base)
    blocks = [Xs]
    ai = [base.index(a) for a in ATTACK]; di = [base.index(a) for a in DEFENSE]
    for a in ATTACK:
        for b in DEFENSE:
            blocks.append((Xs[:, base.index(a)] * Xs[:, base.index(b)])[:, None])
            cols.append(f"{a}__x__{b}")
    return np.hstack(blocks), cols, means, stds, len(strength), len(style)


def run(seasons=None) -> dict:
    fit = _assemble(FIT_SEASONS)
    y = fit["xg_share"].to_numpy()
    X, cols, means, stds, n_str, n_sty = _features(fit)
    strength_cols = [c for c in cols if "strength" in c]
    inter_cols = [c for c in cols if "__x__" in c]
    style_main_cols = [c for c in cols if c in (ATTACK + DEFENSE)]

    m = Ridge(alpha=10.0).fit(X, y)
    coefs = dict(zip(cols, m.coef_))

    # variance explained: full vs strength-only vs +style-main vs +interactions
    def r2_of(cols_subset):
        idx = [cols.index(c) for c in cols_subset]
        mm = Ridge(alpha=10.0).fit(X[:, idx], y)
        pred = mm.predict(X[:, idx])
        return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    r2_strength = r2_of(strength_cols)
    r2_str_style = r2_of(strength_cols + style_main_cols)
    r2_full = r2_of(cols)

    out = {
        "n_fit_games": fit.height, "fit_seasons": f"{FIT_SEASONS[0]}..{FIT_SEASONS[-1]}",
        "estimator": "Ridge(alpha=10) on team-game 5v5 xG share (score-close)",
        "r2_strength_only": round(float(r2_strength), 4),
        "r2_strength_plus_style_main": round(float(r2_str_style), 4),
        "r2_full_with_interactions": round(float(r2_full), 4),
        "interaction_r2_gain": round(float(r2_full - r2_str_style), 5),
        "strength_coefs": {c: round(float(coefs[c]), 5) for c in strength_cols},
        "top_style_interactions": dict(sorted(
            {c: round(float(coefs[c]), 5) for c in inter_cols}.items(), key=lambda kv: -abs(kv[1]))[:8]),
        "coef_magnitude_strength_vs_interaction": {
            "mean_abs_strength": round(float(np.mean([abs(coefs[c]) for c in strength_cols])), 5),
            "mean_abs_interaction": round(float(np.mean([abs(coefs[c]) for c in inter_cols])), 5)},
        "schedule_bias_2024_25": _schedule_bias(m, means, stds, cols),
    }
    (config.REPORTS / "phase3_opponent.json").write_text(__import__("json").dumps(out, indent=2, default=str))
    return out


def _schedule_bias(model, means, stds, cols):
    """For 2024-25: per team-game, expected xg-share shift from the SPECIFIC opponent vs a
    league-average opponent, then aggregated to each player-season (TOI-weighted over the games
    they played). Positive = schedule-flattered (faced easy opponents). Report the 10 extremes
    each way."""
    d = _assemble([HOLDOUT])
    X, _, _, _, _, _ = _features(d, means, stds)
    pred_actual = model.predict(X)
    # neutral opponent: replace opponent columns (opp_strength_*, DEFENSE) with their league mean
    dn = d.clone()
    opp_cols = ["opp_strength_off", "opp_strength_def", *DEFENSE]
    for c in opp_cols:
        dn = dn.with_columns(pl.lit(float(d[c].mean())).alias(c))
    Xn, _, _, _, _, _ = _features(dn, means, stds)
    pred_neutral = model.predict(Xn)
    d = d.with_columns(sched_effect=pl.Series(pred_actual - pred_neutral))

    # player weighting: TOI per (game, player) from depfull for 2024-25
    depf = pl.read_parquet(C.DEPFULL_DIR / f"{HOLDOUT.replace('-', '_')}.parquet")
    pg = depf.join(d.select("game_id", "team_id", "sched_effect"), on=["game_id", "team_id"], how="inner")
    player = pg.group_by("player_id", "team_id").agg(
        toi=pl.col("toi_5v5_s").sum(),
        sched_bias=(pl.col("sched_effect") * pl.col("toi_5v5_s")).sum() / pl.col("toi_5v5_s").sum())
    player = player.filter(pl.col("toi") >= MIN_MIN_S).sort("sched_bias")
    names = _names()
    def fmt(r):
        nm = names.get(r["player_id"], "")
        return {"player": nm or str(r["player_id"]), "player_id": r["player_id"],
                "team": TEAM_ABBR.get(r["team_id"], str(r["team_id"])),
                "schedule_bias": round(r["sched_bias"], 5)}
    flat = [fmt(r) for r in player.tail(10).reverse().to_dicts()]   # most positive (flattered)
    pun = [fmt(r) for r in player.head(10).to_dicts()]              # most negative (punished)
    return {
        "holdout_season": HOLDOUT,
        "mean_abs_player_schedule_bias": round(float(player["sched_bias"].abs().mean()), 5),
        "p90_abs_player_schedule_bias": round(float(player["sched_bias"].abs().quantile(0.9)), 5),
        "interpretation": "xG-share points a player's season number is shifted by opponent-system exposure (+ = faced easy schedule, number flattered)",
        "most_flattered_top10": flat, "most_punished_top10": pun,
    }


def _names() -> dict:
    p = config.CACHE / "warehouse" / "player_names.csv"
    if not p.exists():
        return {}
    df = pl.read_csv(p)
    return {r["player_id"]: f"{r['first_name']} {r['last_name']}" for r in df.to_dicts()}


MIN_MIN_S = 200.0 * 60
SCHED_PARQUET = config.PARQUET / "schedule_adjustment.parquet"


# ---------------------------------------------------------------- Phase 4.2: strength-only survivor
def strength_schedule_table(write: bool = True) -> pl.DataFrame:
    """Phase 4.2 — the surviving OPPONENT-track product: a STRENGTH-ONLY schedule adjustment,
    published as DESCRIPTIVE accounting with NO predictive claim (the style-matchup interactions
    were KILLED at the Phase 3 gate). Per (player, season, team): the TOI-weighted opponent-
    strength exposure effect on the player's 5v5 xG share, vs a league-average opponent.

    Fit: team-game 5v5 xG share (close) ~ own strength (off/def) + opponent strength (off/def)
    only, on 2010-11..2023-24; applied to every season for the accounting."""
    strength = ["strength_off", "strength_def", "opp_strength_off", "opp_strength_def"]
    fit = _assemble(FIT_SEASONS)
    Xf = fit.select(strength).to_numpy().astype(float)
    mean, std = Xf.mean(0), Xf.std(0) + 1e-9
    model = Ridge(alpha=10.0).fit((Xf - mean) / std, fit["xg_share"].to_numpy())

    rows = []
    for season in config.SEASONS_ALL:
        d = _assemble([season])
        if d.height == 0:
            continue
        X = (d.select(strength).to_numpy().astype(float) - mean) / std
        pred_actual = model.predict(X)
        dn = d.clone()
        for c in ["opp_strength_off", "opp_strength_def"]:
            dn = dn.with_columns(pl.lit(float(d[c].mean())).alias(c))
        Xn = (dn.select(strength).to_numpy().astype(float) - mean) / std
        d = d.with_columns(sched_effect=pl.Series(pred_actual - model.predict(Xn)))
        depf = pl.read_parquet(C.DEPFULL_DIR / f"{season.replace('-', '_')}.parquet")
        pg = depf.join(d.select("game_id", "team_id", "sched_effect"), on=["game_id", "team_id"], how="inner")
        player = pg.group_by("player_id", "team_id").agg(
            toi=pl.col("toi_5v5_s").sum(),
            schedule_adjustment=(pl.col("sched_effect") * pl.col("toi_5v5_s")).sum() / pl.col("toi_5v5_s").sum())
        rows.append(player.filter(pl.col("toi") >= MIN_MIN_S).with_columns(season_label=pl.lit(season)))
    out = pl.concat(rows)
    if write:
        out.write_parquet(SCHED_PARQUET)
    return out


def schedule_exhibit(season="2024-25", n=10) -> dict:
    d = (pl.read_parquet(SCHED_PARQUET) if SCHED_PARQUET.exists() else strength_schedule_table()
         ).filter(pl.col("season_label") == season).sort("schedule_adjustment")
    names = _names()
    def fmt(r):
        return {"player": names.get(r["player_id"], str(r["player_id"])),
                "team": TEAM_ABBR.get(r["team_id"], str(r["team_id"])),
                "schedule_adjustment": round(r["schedule_adjustment"], 5)}
    return {
        "season": season, "n_pool": d.height,
        "framing": "DESCRIPTIVE opponent-strength accounting; NO predictive claim, NO validation bar",
        "mean_abs": round(float(d["schedule_adjustment"].abs().mean()), 5),
        "p90_abs": round(float(d["schedule_adjustment"].abs().quantile(0.9)), 5),
        "most_flattered_top10": [fmt(r) for r in d.tail(n).reverse().to_dicts()],
        "most_punished_top10": [fmt(r) for r in d.head(n).to_dicts()],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2, default=str))
