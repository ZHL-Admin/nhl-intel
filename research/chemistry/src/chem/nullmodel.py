"""Phase 2 · 2.1 — the additive-plus-curvature null model.

Pair xG share during shared TOI is modeled from individual quality and context ONLY:
  - both players' rapm_variant off/def, symmetrized (sum_off, sum_def);
  - talent-curvature terms: product of the two total ratings, and squared-sum
    (so generic diminishing returns between two high-quality players is absorbed by the null and
    never misread as dyadic chemistry);
  - position-pair class (D-D/D-F/F-F), OZ start share, score-state mix, opponent strength;
  - season fixed effects.
Weighted Ridge (weights = shared TOI), CV grouped by season. The PAIR RESIDUAL (observed − predicted)
is the candidate chemistry quantity, carried TOI-weighted everywhere downstream.

Two anchors (2.1b), addressing same-season anchor contamination for locked pairs:
  - "same"  : same-season rapm_variant (primary; conservative for chemistry).
  - "prior" : prior-season rapm_variant mapped through a league-wide drift regression
              (rating_t ~ a + b*rating_{t-1}, fit per component). Uncontaminated but noisier;
              players without a prior season drop and are counted. NOTE: the frozen Atlas inputs
              carry NO birthdate/age, so the spec's "simple age-drift adjustment" is realized as this
              empirical pooled drift/mean-reversion map (its slope IS the aging+reversion trend).
              Flagged in reports/phase2.md.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from sklearn.linear_model import RidgeCV

from . import config

SEASONS = config.SEASONS_ALL
_SIDX = {s: i for i, s in enumerate(SEASONS)}
FROZEN_PAIRS = config.PARQUET / "frozen" / "pairs_corpus.parquet"

# design columns (continuous, standardized) + categorical expansions built in _design()
_CONT = ["sum_off", "sum_def", "prod", "ssum", "oz_start_share", "share_lead", "share_trail", "opp_rapm"]
_POS = ["D-F", "F-F"]                    # base = D-D
_ALPHAS = (0.1, 1.0, 10.0, 100.0)


def _rapm() -> pl.DataFrame:
    return (pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet")
            .select("player_id", "season", "off_impact", "def_impact")
            .with_columns(si=pl.col("season").replace_strict(_SIDX, return_dtype=pl.Int32)))


def drift_coeffs() -> dict:
    """League-wide pooled OLS rating_t ~ a + b*rating_{t-1} per component (the 'drift adjustment')."""
    r = _rapm()
    cur = r.select("player_id", "si", off_t="off_impact", def_t="def_impact")
    prev = r.select("player_id", (pl.col("si") + 1).alias("si"), off_p="off_impact", def_p="def_impact")
    j = cur.join(prev, on=["player_id", "si"], how="inner")
    out = {"n_pairs": j.height}
    for c in ("off", "def"):
        b = np.polyfit(j[f"{c}_p"].to_numpy(), j[f"{c}_t"].to_numpy(), 1)
        out[c] = {"intercept": float(b[1]), "slope": float(b[0])}
    return out


def rating_table(anchor: str) -> pl.DataFrame:
    """Per (player_id, season) the (off, deff) rating to use under the given anchor."""
    r = _rapm()
    if anchor == "same":
        return r.select("player_id", season="season", off="off_impact", deff="def_impact")
    if anchor != "prior":
        raise ValueError(anchor)
    d = drift_coeffs()
    seasondf = pl.DataFrame({"si": list(range(len(SEASONS))), "season_out": SEASONS})
    prev = (r.select("player_id", (pl.col("si") + 1).alias("si"), off_p="off_impact", def_p="def_impact")
            .join(seasondf, on="si", how="inner"))
    return prev.select(
        "player_id", season=pl.col("season_out"),
        off=d["off"]["intercept"] + d["off"]["slope"] * pl.col("off_p"),
        deff=d["def"]["intercept"] + d["def"]["slope"] * pl.col("def_p"))


def attach_ratings(pairs: pl.DataFrame, anchor: str) -> tuple[pl.DataFrame, int]:
    """Join both players' anchor ratings and build the symmetric quality + curvature features.
    Returns (rows-with-both-ratings, n_dropped_for_missing_rating)."""
    rt = rating_table(anchor)
    for who in ("a", "b"):
        rr = rt.rename({"player_id": who, "season": "season_label",
                        "off": f"{who}_off", "deff": f"{who}_def"})
        pairs = pairs.join(rr, on=[who, "season_label"], how="left")
    n0 = pairs.height
    pairs = pairs.drop_nulls(["a_off", "a_def", "b_off", "b_def"])
    pairs = pairs.with_columns(
        sum_off=pl.col("a_off") + pl.col("b_off"), sum_def=pl.col("a_def") + pl.col("b_def"),
        qa=pl.col("a_off") + pl.col("a_def"), qb=pl.col("b_off") + pl.col("b_def"))
    pairs = pairs.with_columns(prod=pl.col("qa") * pl.col("qb"), ssum=(pl.col("qa") + pl.col("qb")) ** 2)
    return pairs, n0 - pairs.height


class NullModel:
    """Fitted weighted-Ridge null. `.predict(df)` works on any frame carrying the raw feature
    columns (ratings-derived + context + pos_pair + season_label), e.g. split halves."""

    def __init__(self, anchor: str):
        self.anchor = anchor
        self.mean_ = None
        self.std_ = None
        self.ridge_ = None
        self.cols_ = None

    def _design(self, df: pl.DataFrame) -> np.ndarray:
        cont = df.select(_CONT).to_numpy()
        pos = np.column_stack([(df["pos_pair"] == p).to_numpy().astype(float) for p in _POS])
        # season fixed effects (base = first season present in the training set)
        seas = np.column_stack([(df["season_label"] == s).to_numpy().astype(float)
                                for s in self.season_levels_])
        return cont, pos, seas

    def fit(self, df: pl.DataFrame):
        self.season_levels_ = SEASONS[1:]      # base = 2010-11
        cont, pos, seas = self._design(df)
        self.mean_ = cont.mean(axis=0)
        self.std_ = cont.std(axis=0)
        self.std_[self.std_ == 0] = 1.0
        X = np.hstack([(cont - self.mean_) / self.std_, pos, seas])
        y = df["xg_share"].to_numpy()
        w = df["toi"].to_numpy().astype(float)
        self.ridge_ = RidgeCV(alphas=_ALPHAS).fit(X, y, sample_weight=w)
        return self

    def predict(self, df: pl.DataFrame) -> np.ndarray:
        cont, pos, seas = self._design(df)
        X = np.hstack([(cont - self.mean_) / self.std_, pos, seas])
        return self.ridge_.predict(X)

    def coefficients(self) -> dict:
        names = _CONT + _POS + [f"season:{s}" for s in self.season_levels_]
        coef = dict(zip(names, [float(c) for c in self.ridge_.coef_]))
        return {"alpha": float(self.ridge_.alpha_), "intercept": float(self.ridge_.intercept_),
                "coef": coef}


def _weighted_r2(y, pred, w) -> float:
    wm = np.average(y, weights=w)
    ss_res = np.sum(w * (y - pred) ** 2)
    ss_tot = np.sum(w * (y - wm) ** 2)
    return float(1 - ss_res / ss_tot)


def fit_null(pairs_with_ratings: pl.DataFrame, anchor: str) -> tuple[NullModel, dict, pl.DataFrame]:
    """Fit the null on the full (ratings-attached) pair corpus; return (model, diagnostics, pairs+residual).
    Diagnostics include leave-one-season-out CV weighted R² (fit quality) and coefficient sanity."""
    df = pairs_with_ratings
    model = NullModel(anchor).fit(df)
    # LOSO CV weighted R²
    seasons = sorted(df["season_label"].unique().to_list())
    oof_y, oof_p, oof_w = [], [], []
    per_season = {}
    for s in seasons:
        tr = df.filter(pl.col("season_label") != s)
        te = df.filter(pl.col("season_label") == s)
        m = NullModel(anchor).fit(tr)
        pr = m.predict(te)
        yy = te["xg_share"].to_numpy(); ww = te["toi"].to_numpy().astype(float)
        oof_y.append(yy); oof_p.append(pr); oof_w.append(ww)
        per_season[s] = _weighted_r2(yy, pr, ww)
    cv_r2 = _weighted_r2(np.concatenate(oof_y), np.concatenate(oof_p), np.concatenate(oof_w))
    # full-fit residuals (null carries no pair identity -> conservative for chemistry)
    pred = model.predict(df)
    out = df.with_columns(pred=pl.Series(pred),
                          residual=pl.col("xg_share") - pl.Series(pred))
    diag = {"anchor": anchor, "n": df.height,
            "cv_r2_loso_weighted": cv_r2, "in_sample_r2_weighted": _weighted_r2(
                df["xg_share"].to_numpy(), pred, df["toi"].to_numpy().astype(float)),
            "cv_r2_per_season": per_season, "coefficients": model.coefficients(),
            "residual_toi_wtd_mean": float(np.average(out["residual"].to_numpy(),
                                                      weights=out["toi"].to_numpy().astype(float))),
            "residual_sd": float(out["residual"].std())}
    return model, diag, out
